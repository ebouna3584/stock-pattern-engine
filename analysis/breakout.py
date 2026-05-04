"""
Breakout confirmation logic.
Determines whether price has or is about to break out of a detected pattern.
"""

import numpy as np
import pandas as pd
from typing import Optional, Tuple
from stock_pattern_engine.api.config import settings


def breakout_confirmation(
    closes: np.ndarray,
    breakout_level: float,
    direction: str,  # "UP" or "DOWN"
    volumes: Optional[np.ndarray] = None,
    volume_lookback: int = 20,
    close_confirmation_pct: float = 0.003,  # 0.3% above/below level
) -> Tuple[bool, float, str]:
    """
    Checks if the most recent close confirms a breakout.
    Returns (is_confirmed, confidence_boost, message).

    Criteria:
      1. Price closes beyond breakout_level by close_confirmation_pct.
      2. Volume on breakout candle exceeds average by BREAKOUT_VOLUME_FACTOR.
    """
    if len(closes) == 0:
        return False, 0.0, "Insufficient data"

    latest_close = float(closes[-1])
    price_break = False
    price_msg = ""

    if direction == "UP":
        threshold = breakout_level * (1 + close_confirmation_pct)
        price_break = latest_close > threshold
        price_msg = (
            f"Price {latest_close:.2f} > breakout {threshold:.2f}"
            if price_break
            else f"Price {latest_close:.2f} has not cleared {threshold:.2f}"
        )
    else:  # DOWN
        threshold = breakout_level * (1 - close_confirmation_pct)
        price_break = latest_close < threshold
        price_msg = (
            f"Price {latest_close:.2f} < breakout {threshold:.2f}"
            if price_break
            else f"Price {latest_close:.2f} has not broken {threshold:.2f}"
        )

    volume_break = False
    vol_surge = 1.0
    if volumes is not None and len(volumes) >= volume_lookback + 1:
        avg_vol = float(np.mean(volumes[-volume_lookback - 1: -1]))
        latest_vol = float(volumes[-1])
        vol_surge = latest_vol / max(avg_vol, 1)
        volume_break = vol_surge >= settings.BREAKOUT_VOLUME_FACTOR

    confirmed = price_break and volume_break
    confidence_boost = 0.0
    if price_break:
        confidence_boost += 10.0
    if volume_break:
        confidence_boost += 10.0 * min(vol_surge / settings.BREAKOUT_VOLUME_FACTOR, 2.0)

    status = "CONFIRMED" if confirmed else ("PARTIAL" if price_break else "NOT_CONFIRMED")
    return confirmed, confidence_boost, f"{status} | {price_msg} | Vol surge: {vol_surge:.2f}x"


def estimate_breakout_target(
    breakout_level: float,
    pattern_height: float,
    direction: str,
) -> Tuple[float, float, float]:
    """
    Classic measured-move projection.
    Target 1 = 100% of pattern height from breakout.
    Target 2 = 162% (Fibonacci extension).
    Target 3 = 200%.
    """
    if direction == "UP":
        t1 = breakout_level + pattern_height
        t2 = breakout_level + pattern_height * 1.618
        t3 = breakout_level + pattern_height * 2.0
    else:
        t1 = breakout_level - pattern_height
        t2 = breakout_level - pattern_height * 1.618
        t3 = breakout_level - pattern_height * 2.0
    return t1, t2, t3


def false_breakout_probability(
    slope_steepness: float,
    volume_surge: float,
    rsi: Optional[float] = None,
) -> float:
    """
    Heuristic estimate of false breakout probability [0,1].
    High slope + low volume + RSI extreme → higher false breakout risk.
    """
    base = 0.3  # baseline 30% false breakout rate (empirical assumption)

    # Steep parabolic moves often fail
    if abs(slope_steepness) > 0.05:
        base += 0.15

    # Low volume breakouts are unreliable
    if volume_surge < 1.2:
        base += 0.20
    elif volume_surge > 2.0:
        base -= 0.15

    # RSI extreme reduces continuation probability
    if rsi is not None:
        if rsi > 80 or rsi < 20:
            base += 0.15
        elif rsi < 40 and slope_steepness > 0:
            base -= 0.05  # oversold + upward move = more likely genuine

    return float(np.clip(base, 0.05, 0.95))


def nearest_support_resistance(
    closes: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    current_price: float,
    n_levels: int = 5,
    tolerance_pct: float = 0.01,
) -> Tuple[Optional[float], Optional[float]]:
    """
    Identify nearest support and resistance levels from pivot history.
    Returns (nearest_support, nearest_resistance).
    """
    from analysis.regression import detect_pivot_highs, detect_pivot_lows
    pivot_h_idx = detect_pivot_highs(highs, window=5)
    pivot_l_idx = detect_pivot_lows(lows, window=5)

    resistances = sorted(highs[pivot_h_idx], reverse=True) if len(pivot_h_idx) > 0 else []
    supports = sorted(lows[pivot_l_idx]) if len(pivot_l_idx) > 0 else []

    # Deduplicate levels within tolerance
    def dedupe(levels):
        result = []
        for lv in levels:
            if not result or abs(lv - result[-1]) / max(result[-1], 1e-9) > tolerance_pct:
                result.append(lv)
        return result

    resistances = dedupe(resistances)
    supports = dedupe(supports)

    nearest_res = next(
        (r for r in sorted(resistances) if r > current_price * (1 + tolerance_pct)),
        None
    )
    nearest_sup = next(
        (s for s in sorted(supports, reverse=True) if s < current_price * (1 - tolerance_pct)),
        None
    )
    return nearest_sup, nearest_res
