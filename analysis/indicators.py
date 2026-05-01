"""
Technical indicator helpers.
These consume pre-loaded indicator columns from the CSV and
expose scoring functions used by the pattern and risk engines.
"""

import numpy as np
import pandas as pd
from typing import Optional, Tuple


# ─── RSI Scoring ─────────────────────────────────────────────────────────────

def rsi_confirmation(rsi: float, signal: str) -> float:
    """
    Returns a [0,1] confirmation score for a trade direction.
    BUY signal is confirmed when RSI < 70 (not overbought).
    SELL signal is confirmed when RSI > 30 (not oversold).
    Ideal zones produce higher scores.
    """
    if rsi is None or np.isnan(rsi):
        return 0.5  # neutral if missing
    if signal == "BUY":
        if rsi < 30:
            return 1.0   # oversold → strong buy confirmation
        elif rsi < 50:
            return 0.75
        elif rsi < 70:
            return 0.5
        else:
            return 0.1   # overbought → poor buy condition
    elif signal == "SELL":
        if rsi > 70:
            return 1.0   # overbought → strong sell confirmation
        elif rsi > 50:
            return 0.75
        elif rsi > 30:
            return 0.5
        else:
            return 0.1   # oversold → poor sell condition
    return 0.5


def rsi_risk_factor(rsi: float) -> float:
    """
    Risk penalty based on RSI extremes.
    Chasing a trade when RSI > 80 or < 20 is higher risk.
    Returns [0,1] where 1 = max risk.
    """
    if rsi is None or np.isnan(rsi):
        return 0.5
    if rsi > 80 or rsi < 20:
        return 0.9
    elif rsi > 70 or rsi < 30:
        return 0.6
    else:
        return 0.2


# ─── MACD Scoring ─────────────────────────────────────────────────────────────

def macd_confirmation(macd: float, signal: str) -> float:
    """
    Returns [0,1] score.
    Positive MACD confirms BUY; negative MACD confirms SELL.
    """
    if macd is None or np.isnan(macd):
        return 0.5
    if signal == "BUY":
        return float(np.clip(0.5 + macd / (abs(macd) + 1e-9) * 0.5, 0, 1))
    elif signal == "SELL":
        return float(np.clip(0.5 - macd / (abs(macd) + 1e-9) * 0.5, 0, 1))
    return 0.5


# ─── Volume Analysis ──────────────────────────────────────────────────────────

def volume_surge_factor(
    volumes: np.ndarray,
    lookback: int = 20,
    breakout_idx: int = -1
) -> float:
    """
    Computes ratio of breakout-candle volume to rolling average.
    Returns the ratio. > 1.5 is meaningful confirmation.
    """
    if len(volumes) < lookback + 1:
        return 1.0
    if breakout_idx == -1:
        breakout_idx = len(volumes) - 1
    start = max(0, breakout_idx - lookback)
    avg_volume = float(np.mean(volumes[start:breakout_idx]))
    if avg_volume == 0:
        return 1.0
    return float(volumes[breakout_idx] / avg_volume)


def rolling_volume_avg(volumes: pd.Series, window: int = 20) -> pd.Series:
    return volumes.rolling(window=window, min_periods=1).mean()


def volume_trend_slope(volumes: np.ndarray) -> float:
    """Linear slope of volume over the detection window. Positive = rising volume."""
    if len(volumes) < 2:
        return 0.0
    x = np.arange(len(volumes), dtype=float)
    slope, _, _, _, _ = __import__("scipy.stats", fromlist=["linregress"]).linregress(x, volumes.astype(float))
    return float(slope)


# ─── ATR-Based Volatility ─────────────────────────────────────────────────────

def atr_volatility_score(atr: float, close: float) -> float:
    """
    ATR as % of price. Normalized to [0,1] where 1 = high volatility (risky).
    ATR/close > 5% is considered high volatility.
    """
    if close <= 0 or atr is None or np.isnan(atr):
        return 0.5
    pct = atr / close
    return float(np.clip(pct / 0.05, 0, 1))


def compute_atr_from_df(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Compute ATR from OHLC if not already in the dataframe.
    True Range = max(H-L, |H-Cp|, |L-Cp|)
    """
    high = df["high"]
    low = df["low"]
    close_prev = df["close"].shift(1)
    tr1 = high - low
    tr2 = (high - close_prev).abs()
    tr3 = (low - close_prev).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return true_range.rolling(window=period, min_periods=1).mean()


# ─── EMA / SMA Trend Bias ─────────────────────────────────────────────────────

def ema_trend_bias(
    close: float,
    ema_20: Optional[float],
    ema_50: Optional[float],
    sma_200: Optional[float],
) -> Tuple[str, float]:
    """
    Determines macro trend bias from price vs. moving averages.
    Returns (direction, strength) where strength is [0,1].
    """
    checks = []
    if ema_20 and not np.isnan(ema_20):
        checks.append(1 if close > ema_20 else -1)
    if ema_50 and not np.isnan(ema_50):
        checks.append(1 if close > ema_50 else -1)
    if sma_200 and not np.isnan(sma_200):
        checks.append(1 if close > sma_200 else -1)
    if not checks:
        return "NEUTRAL", 0.5
    avg = float(np.mean(checks))
    if avg > 0.33:
        return "BULLISH", float(np.clip((avg + 1) / 2, 0, 1))
    elif avg < -0.33:
        return "BEARISH", float(np.clip((1 - (avg + 1) / 2), 0, 1))
    return "NEUTRAL", 0.5


# ─── Bollinger Band Squeeze Detection ────────────────────────────────────────

def bollinger_squeeze(
    bb_upper: float,
    bb_lower: float,
    close: float,
    period_avg_width: Optional[float] = None,
) -> float:
    """
    Returns squeeze score [0,1].
    1 = band width is very narrow relative to its historical average → breakout likely.
    """
    if not bb_upper or not bb_lower or close <= 0:
        return 0.0
    current_width = (bb_upper - bb_lower) / close
    if period_avg_width and period_avg_width > 0:
        return float(np.clip(1.0 - current_width / period_avg_width, 0, 1))
    # Without historical avg: just flag if band < 5% of price
    return float(np.clip(1.0 - current_width / 0.05, 0, 1))
