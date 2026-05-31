"""
Price fetcher — pulls OHLCV + indicators from Yahoo Finance,
runs the pattern engine, and returns a broadcast-ready payload.
"""
import logging
import uuid
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd
import pytz

logger = logging.getLogger(__name__)

# Rolling caches
_history_cache: dict = {}
_last_payload:  dict = {}

ET = pytz.timezone("America/New_York")


# ── Market hours ───────────────────────────────────────────────────────────────

def is_market_open() -> bool:
    now = datetime.now(ET)
    if now.weekday() >= 5:          # Saturday / Sunday
        return False
    open_t  = now.replace(hour=9,  minute=30, second=0, microsecond=0)
    close_t = now.replace(hour=16, minute=0,  second=0, microsecond=0)
    return open_t <= now <= close_t


# ── Indicator helpers ──────────────────────────────────────────────────────────

def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(period, min_periods=1).mean()
    loss  = (-delta.clip(upper=0)).rolling(period, min_periods=1).mean()
    rs    = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).round(1)


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    h, l, pc = df["high"], df["low"], df["close"].shift(1)
    tr = pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=1).mean().round(2)


# ── Yahoo Finance fetchers ─────────────────────────────────────────────────────

def fetch_history(
    ticker: str,
    period: str = "3mo",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Optional[pd.DataFrame]:
    """Download daily OHLCV and compute all indicators.

    Pass start_date (YYYY-MM-DD) to fetch from that date to end_date (or today).
    When start_date is omitted the period string is used instead.
    """
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        if start_date:
            raw = t.history(start=start_date, end=end_date, interval="1d", auto_adjust=True)
        else:
            raw = t.history(period=period, interval="1d", auto_adjust=True)
        if raw.empty:
            logger.warning(f"{ticker}: empty history from yfinance")
            return None

        df = raw.reset_index()
        df.columns = [str(c).lower().replace(" ", "_") for c in df.columns]
        df = df.rename(columns={"date": "date"})
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        df["ticker"]           = ticker
        df["timeframe"]        = "1D"
        df["template_version"] = "1.0.0"

        c = df["close"]
        df["RSI"]              = _rsi(c)
        df["EMA_20"]           = c.ewm(span=20, adjust=False).mean().round(2)
        df["EMA_50"]           = c.ewm(span=50, adjust=False).mean().round(2)
        df["SMA_200"]          = c.rolling(200, min_periods=1).mean().round(2)
        std20                  = c.rolling(20, min_periods=1).std().fillna(0)
        df["Bollinger_upper"]  = (df["EMA_20"] + 2 * std20).round(2)
        df["Bollinger_lower"]  = (df["EMA_20"] - 2 * std20).round(2)
        df["ATR"]              = _atr(df)
        ema12                  = c.ewm(span=12, adjust=False).mean()
        ema26                  = c.ewm(span=26, adjust=False).mean()
        df["MACD"]             = (ema12 - ema26).round(4)
        df["MACD_signal"]      = df["MACD"].ewm(span=9, adjust=False).mean().round(4)
        df["MACD_histogram"]   = (df["MACD"] - df["MACD_signal"]).round(4)

        keep = [
            "template_version", "ticker", "timeframe", "date",
            "open", "high", "low", "close", "volume",
            "RSI", "MACD", "MACD_signal", "MACD_histogram",
            "EMA_20", "EMA_50", "SMA_200",
            "Bollinger_upper", "Bollinger_lower", "ATR",
        ]
        df = df[[col for col in keep if col in df.columns]]
        df = df.dropna(subset=["close"]).reset_index(drop=True)
        logger.info(f"{ticker}: fetched {len(df)} rows")
        return df

    except Exception as exc:
        logger.error(f"fetch_history({ticker}): {exc}")
        return None


def get_live_quote(ticker: str) -> dict:
    """Return the latest price and day-change % for a single ticker."""
    try:
        import yfinance as yf
        fi = yf.Ticker(ticker).fast_info
        price = fi.get("last_price") or fi.get("regular_market_price")
        prev  = fi.get("previous_close") or fi.get("regular_market_previous_close")
        if price is None:
            return {}
        change_pct = round((price - prev) / prev * 100, 2) if prev else None
        return {
            "price":      round(float(price), 2),
            "prev_close": round(float(prev), 2) if prev else None,
            "change_pct": change_pct,
        }
    except Exception as exc:
        logger.error(f"get_live_quote({ticker}): {exc}")
        return {}


# ── Main refresh ───────────────────────────────────────────────────────────────

def run_full_refresh(tickers: list) -> dict:
    """
    For each ticker: fetch/update history → run pattern engine → build payload.
    Returns a dict suitable for WebSocket broadcast and Excel writing.
    """
    from core.engine import run_analysis

    results = []

    for ticker in tickers:
        logger.info(f"Refreshing {ticker}...")
        row: dict = {"ticker": ticker}

        # ── History ──────────────────────────────────────────────────────────
        df = fetch_history(ticker, period="3mo")
        if df is None or len(df) < 20:
            logger.warning(f"{ticker}: insufficient data, skipping analysis")
            row["error"] = "Insufficient history data"
            results.append(row)
            continue

        _history_cache[ticker] = df.copy()

        # ── Live quote ───────────────────────────────────────────────────────
        quote = get_live_quote(ticker)
        live_price = quote.get("price", float(df["close"].iloc[-1]))
        row["live_price"]  = live_price
        row["change_pct"]  = quote.get("change_pct")
        row["prev_close"]  = quote.get("prev_close")

        # Patch last row with live price
        df.loc[df.index[-1], "close"] = live_price

        # ── Pattern analysis ─────────────────────────────────────────────────
        try:
            session_id = str(uuid.uuid4())
            analysis   = run_analysis(df=df.copy(), session_id=session_id)
            ta         = next(
                (r for r in analysis.results if r.ticker == ticker), None
            )
        except Exception as exc:
            logger.error(f"{ticker} analysis error: {exc}")
            ta = None

        if ta:
            tp = ta.top_pattern
            tr = ta.trade_recommendation
            rk = ta.risk_assessment
            row.update({
                "pattern":    tp.pattern_type.value.replace("_", " ").title() if tp else "—",
                "confidence": round(tp.confidence_score, 1) if tp else None,
                "signal":     tr.signal.value if tr else "WATCH",
                "entry":      round(tr.entry_price,    2) if tr else None,
                "stop_loss":  round(tr.stop_loss,      2) if tr else None,
                "tp1":        round(tr.take_profit_1,  2) if tr else None,
                "tp2":        round(tr.take_profit_2,  2) if tr else None,
                "tp3":        round(tr.take_profit_3,  2) if tr else None,
                "rr_ratio":   round(tr.risk_reward_ratio, 2) if tr else None,
                "risk":       rk.risk_score.value if rk else "—",
                "rsi":        ta.current_rsi,
                "macd":       ta.current_macd,
                "session_id": session_id,
            })

            # Chart data — last 60 candles
            chart = df.tail(60)
            row["chart"] = {
                "dates":   chart["date"].tolist(),
                "closes":  chart["close"].round(2).tolist(),
                "highs":   chart["high"].round(2).tolist(),
                "lows":    chart["low"].round(2).tolist(),
                "volumes": chart["volume"].fillna(0).astype(int).tolist(),
                "rsi":     chart["RSI"].round(1).tolist() if "RSI" in chart else [],
                "macd":    chart["MACD"].round(4).tolist() if "MACD" in chart else [],
                "macd_signal": chart["MACD_signal"].round(4).tolist()
                               if "MACD_signal" in chart else [],
                "ema20":   chart["EMA_20"].round(2).tolist() if "EMA_20" in chart else [],
            }

            # Support / resistance levels for chart overlay
            if tp:
                row["support"]    = tp.support_line.end_price
                row["resistance"] = tp.resistance_line.end_price
                row["breakout"]   = tp.breakout_level

            # Cache result for PDF downloads
            try:
                from api.endpoints.report import store_result
                store_result(session_id, analysis)
            except Exception:
                pass
        else:
            row["pattern"]  = "—"
            row["signal"]   = "WATCH"
            row["confidence"] = None

        results.append(row)

    payload = {
        "timestamp":        datetime.now().isoformat(),
        "market_open":      is_market_open(),
        "next_refresh_sec": 300,
        "results":          results,
    }
    _last_payload.clear()
    _last_payload.update(payload)
    return payload


def get_last_payload() -> dict:
    return dict(_last_payload)
