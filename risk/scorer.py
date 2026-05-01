"""
Risk Scoring Engine.

Formula (weighted sum → normalized to 0–100):
  risk_numeric = (
      slope_risk        * SLOPE_WEIGHT           +
      volatility_risk   * VOLATILITY_WEIGHT       +
      breakout_distance * BREAKOUT_DISTANCE_WEIGHT +
      rsi_risk          * RSI_WEIGHT               +
      macd_risk         * MACD_WEIGHT              +
      volume_risk       * VOLUME_WEIGHT
  ) * 100

risk_numeric 0–30  → LOW
risk_numeric 30–60 → MEDIUM
risk_numeric 60+   → HIGH
"""

import numpy as np
from typing import Optional
from models.schemas import PatternResult, RiskAssessment
from models.enums import RiskLevel, HoldingTime
from analysis.indicators import rsi_risk_factor, atr_volatility_score, volume_surge_factor
from analysis.breakout import false_breakout_probability
from config import settings


def compute_risk(
    pattern: PatternResult,
    current_price: float,
    atr: Optional[float],
    rsi: Optional[float],
    macd: Optional[float],
    volumes: np.ndarray,
) -> RiskAssessment:
    """
    Compute a full risk assessment for a detected pattern.
    All sub-scores are [0,1] before weighting.
    """
    # ── 1. Slope Risk ──────────────────────────────────────────────────────────
    # Very steep support/resistance slope → less predictable breakout
    avg_slope = (abs(pattern.slope_support) + abs(pattern.slope_resistance)) / 2
    # Normalize: slope > 0.02 per candle is considered high risk
    slope_risk = float(np.clip(avg_slope / 0.02, 0, 1))

    # ── 2. Volatility Risk (ATR-based) ────────────────────────────────────────
    if atr and current_price > 0:
        volatility_risk = atr_volatility_score(atr, current_price)
    else:
        # Fall back to estimated annualized vol from pattern
        volatility_risk = float(np.clip(pattern.volatility_estimate / 1.0, 0, 1))

    # ── 3. Breakout Distance Risk ─────────────────────────────────────────────
    # How far is current price from the breakout level?
    # The further away, the higher the risk of a false signal
    if current_price > 0:
        breakout_dist_pct = abs(current_price - pattern.breakout_level) / current_price
        breakout_distance_risk = float(np.clip(breakout_dist_pct / 0.10, 0, 1))
    else:
        breakout_distance_risk = 0.5

    # ── 4. RSI Risk ────────────────────────────────────────────────────────────
    if rsi is not None:
        rsi_risk = rsi_risk_factor(rsi)
    else:
        rsi_risk = 0.5

    # ── 5. MACD Risk ───────────────────────────────────────────────────────────
    # MACD divergence from pattern direction adds risk
    if macd is not None:
        is_bullish = pattern.trend_direction.value == "BULLISH"
        if is_bullish and macd < 0:
            macd_risk = 0.7   # MACD diverging from bullish pattern
        elif not is_bullish and macd > 0:
            macd_risk = 0.7
        else:
            macd_risk = 0.2   # MACD aligned
    else:
        macd_risk = 0.5

    # ── 6. Volume Risk ─────────────────────────────────────────────────────────
    # Low volume breakout = higher risk
    vol_surge = pattern.volume_confirmation
    if vol_surge >= 2.0:
        volume_risk = 0.1
    elif vol_surge >= settings.BREAKOUT_VOLUME_FACTOR:
        volume_risk = 0.3
    elif vol_surge >= 1.0:
        volume_risk = 0.6
    else:
        volume_risk = 0.9

    # ── Weighted Composite ─────────────────────────────────────────────────────
    risk_numeric = (
        slope_risk          * settings.SLOPE_WEIGHT            +
        volatility_risk     * settings.VOLATILITY_WEIGHT        +
        breakout_distance_risk * settings.BREAKOUT_DISTANCE_WEIGHT +
        rsi_risk            * settings.RSI_WEIGHT               +
        macd_risk           * settings.MACD_WEIGHT              +
        volume_risk         * settings.VOLUME_WEIGHT
    ) * 100
    risk_numeric = float(np.clip(risk_numeric, 0, 100))

    # ── Risk Level Classification ──────────────────────────────────────────────
    if risk_numeric < 30:
        risk_level = RiskLevel.LOW
    elif risk_numeric < 60:
        risk_level = RiskLevel.MEDIUM
    else:
        risk_level = RiskLevel.HIGH

    # ── Expected Move Estimates ────────────────────────────────────────────────
    # Based on ATR and pattern height
    atr_safe = atr if (atr and atr > 0) else current_price * 0.02
    pattern_height = abs(pattern.resistance_line.end_price - pattern.support_line.end_price)
    is_bullish = pattern.trend_direction.value == "BULLISH"

    if is_bullish:
        expected_upside_pct = (pattern_height / (current_price + 1e-9)) * 100
        expected_downside_pct = (atr_safe * settings.DEFAULT_ATR_STOP_MULTIPLIER / (current_price + 1e-9)) * 100
    else:
        expected_downside_pct = (pattern_height / (current_price + 1e-9)) * 100
        expected_upside_pct = (atr_safe * settings.DEFAULT_ATR_STOP_MULTIPLIER / (current_price + 1e-9)) * 100

    # ── Holding Time Estimate ─────────────────────────────────────────────────
    # Inferred from pattern size and ATR
    if pattern.candles_analyzed <= 20:
        holding_time = HoldingTime.SHORT
    elif pattern.candles_analyzed <= 60:
        holding_time = HoldingTime.MEDIUM
    else:
        holding_time = HoldingTime.LONG

    # ── False Breakout Probability ────────────────────────────────────────────
    fbp = false_breakout_probability(
        slope_steepness=avg_slope,
        volume_surge=vol_surge,
        rsi=rsi,
    )

    return RiskAssessment(
        risk_score=risk_level,
        risk_numeric=round(risk_numeric, 1),
        slope_risk=round(slope_risk, 3),
        volatility_risk=round(volatility_risk, 3),
        breakout_distance_risk=round(breakout_distance_risk, 3),
        rsi_confirmation=round(1 - rsi_risk, 3),
        macd_confirmation=round(1 - macd_risk, 3),
        volume_surge_factor=round(vol_surge, 2),
        false_breakout_probability=round(fbp, 3),
        expected_upside_pct=round(expected_upside_pct, 2),
        expected_downside_pct=round(expected_downside_pct, 2),
        holding_time=holding_time,
    )
