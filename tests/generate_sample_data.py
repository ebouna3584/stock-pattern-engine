"""
Generates a realistic synthetic sample CSV for testing.
Simulates an ascending triangle pattern for AAPL.

Run: python tests/generate_sample_data.py
"""

import numpy as np
import pandas as pd
from pathlib import Path


def generate_ascending_triangle(n=80, seed=42) -> pd.DataFrame:
    """
    Simulate an ascending triangle:
      - Resistance: flat at ~190
      - Support: rising from ~175 to ~187
    """
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-02", periods=n, freq="B")

    # Flat resistance
    resistance = np.full(n, 190.0)
    # Rising support
    support = np.linspace(175.0, 187.0, n)

    # Generate closes that bounce between support and resistance
    closes = []
    price = 180.0
    for i in range(n):
        # Drift toward resistance
        drift = 0.02
        noise = rng.normal(0, 0.5)
        price = price + drift + noise
        price = np.clip(price, support[i] + 0.1, resistance[i] - 0.1)
        closes.append(round(price, 2))

    closes = np.array(closes)
    highs = np.clip(closes + rng.uniform(0.5, 2.0, n), closes, resistance)
    lows = np.clip(closes - rng.uniform(0.5, 2.0, n), support, closes)
    opens = np.roll(closes, 1)
    opens[0] = closes[0] - 0.5

    # Volume: rising into potential breakout
    base_vol = 50_000_000
    volumes = (base_vol + rng.normal(0, 5_000_000, n) + np.linspace(0, 20_000_000, n)).astype(int)
    volumes = np.clip(volumes, 10_000_000, None)

    # Indicators
    def ema(s, span):
        return pd.Series(s).ewm(span=span, adjust=False).mean().values

    close_s = pd.Series(closes)
    rsi_vals = compute_rsi(close_s)
    macd_vals = ema(closes, 12) - ema(closes, 26)
    ema_20 = ema(closes, 20)
    ema_50 = ema(closes, 50)
    sma_200 = pd.Series(closes).rolling(200, min_periods=1).mean().values
    bb_std = close_s.rolling(20, min_periods=1).std().fillna(0).values
    bb_upper = ema_20 + 2 * bb_std
    bb_lower = ema_20 - 2 * bb_std
    atr = compute_atr(highs, lows, closes)

    df = pd.DataFrame({
        "ticker": "AAPL",
        "date": dates.strftime("%Y-%m-%d"),
        "open": np.round(opens, 2),
        "high": np.round(highs, 2),
        "low": np.round(lows, 2),
        "close": np.round(closes, 2),
        "volume": volumes,
        "RSI": np.round(rsi_vals, 1),
        "MACD": np.round(macd_vals, 4),
        "EMA_20": np.round(ema_20, 2),
        "EMA_50": np.round(ema_50, 2),
        "SMA_200": np.round(sma_200, 2),
        "Bollinger_upper": np.round(bb_upper, 2),
        "Bollinger_lower": np.round(bb_lower, 2),
        "ATR": np.round(atr, 2),
    })
    return df


def compute_rsi(close: pd.Series, period: int = 14) -> np.ndarray:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / (avg_loss + 1e-9)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50).values


def compute_atr(highs, lows, closes, period=14):
    n = len(closes)
    tr = np.zeros(n)
    tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
    atr = pd.Series(tr).rolling(period, min_periods=1).mean().values
    return atr


if __name__ == "__main__":
    df = generate_ascending_triangle(n=80)
    out = Path(__file__).parent / "sample_data.csv"
    df.to_csv(out, index=False)
    print(f"Sample data written to {out} ({len(df)} rows)")
    print(df.tail())
