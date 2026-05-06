"""
Trade Recommendation Module.

Generates entry, stop-loss, and take-profit levels using:
  - ATR-based stop placement (avoid noise)
  - Measured-move targets (pattern height projection)
  - Risk-adjusted position sizing (Kelly-lite / fixed fractional)
  - Confidence-gated signal threshold
"""

import numpy as np
from typing import Optional

from models.schemas import PatternResult, RiskAssessment, TradeRecommendation
from models.enums import TradeSignal, RiskLevel
from analysis.breakout import estimate_breakout_target
from api.config import settings


# Confidence gates: only issue BUY/SELL if confidence exceeds these thresholds
CONFIDENCE_GATE_BUY_SELL = 50.0    # Below this → WATCH
HIGH_CONFIDENCE_GATE = 75.0        # Above this → strong signal, larger sizing


def build_trade_recommendation(
    pattern: PatternResult,
    risk: RiskAssessment,
    current_price: float,
    atr: Optional[float],
    account_risk_pct: float = 1.0,   # % of account risked per trade (default 1%)
) -> TradeRecommendation:
    """
    Generate a complete trade plan from pattern + risk data.
    """
    atr_safe = atr if (atr and atr > 0) else current_price * 0.02
    is_bullish = pattern.trend_direction.value == "BULLISH"
    breakout = pattern.breakout_level
    pattern_height = abs(pattern.resistance_line.end_price - pattern.support_line.end_price)

    # ── Signal Decision ────────────────────────────────────────────────────────
    if pattern.confidence_score < CONFIDENCE_GATE_BUY_SELL:
        signal = TradeSignal.WATCH
    elif risk.risk_score == RiskLevel.HIGH and pattern.confidence_score < HIGH_CONFIDENCE_GATE:
        signal = TradeSignal.WATCH
    elif is_bullish:
        signal = TradeSignal.BUY
    else:
        signal = TradeSignal.SELL

    # ── Entry Price ────────────────────────────────────────────────────────────
    # For BUY: enter slightly above breakout (0.2% confirmation buffer)
    # For SELL: enter slightly below breakout
    if is_bullish:
        entry_price = breakout * 1.002
    else:
        entry_price = breakout * 0.998

    # ── Stop Loss ──────────────────────────────────────────────────────────────
    # ATR-based: 1.5x ATR from entry
    if is_bullish:
        stop_loss = entry_price - atr_safe * settings.DEFAULT_ATR_STOP_MULTIPLIER
        # Never below the support trendline (structural stop)
        structural_stop = pattern.support_line.end_price - atr_safe * 0.5
        stop_loss = max(stop_loss, structural_stop)
    else:
        stop_loss = entry_price + atr_safe * settings.DEFAULT_ATR_STOP_MULTIPLIER
        structural_stop = pattern.resistance_line.end_price + atr_safe * 0.5
        stop_loss = min(stop_loss, structural_stop)

    # ── Take Profit Targets ────────────────────────────────────────────────────
    # Measured move: T1 = 100%, T2 = 162% (Fib), T3 = 200% of pattern height
    t1, t2, t3 = estimate_breakout_target(breakout, pattern_height, "UP" if is_bullish else "DOWN")

    # ── Risk/Reward Ratio ──────────────────────────────────────────────────────
    risk_per_share = abs(entry_price - stop_loss)
    reward_t1 = abs(t1 - entry_price)
    rr_ratio = reward_t1 / max(risk_per_share, 1e-9)

    # ── Position Sizing ────────────────────────────────────────────────────────
    # Fixed fractional: allocate account_risk_pct% of portfolio risk per trade
    # position_size_pct = account_risk_pct / (risk_per_share / entry_price * 100)
    # Cap at 10% of portfolio
    if risk_per_share > 0 and entry_price > 0:
        stop_pct = risk_per_share / entry_price
        position_size_pct = min(account_risk_pct / (stop_pct * 100) * 100, 10.0)
    else:
        position_size_pct = 2.0  # Default fallback

    # Scale down for high-risk patterns
    if risk.risk_score == RiskLevel.HIGH:
        position_size_pct *= 0.5
    elif risk.risk_score == RiskLevel.MEDIUM:
        position_size_pct *= 0.75

    # ── Confidence-Adjusted Summary ────────────────────────────────────────────
    if pattern.confidence_score >= HIGH_CONFIDENCE_GATE:
        strength = "HIGH CONFIDENCE"
    elif pattern.confidence_score >= CONFIDENCE_GATE_BUY_SELL:
        strength = "MODERATE CONFIDENCE"
    else:
        strength = "LOW CONFIDENCE — WATCH ONLY"

    direction_word = "Bullish" if is_bullish else "Bearish"
    summary = (
        f"{strength} | {direction_word} {pattern.pattern_type.value.replace('_', ' ').title()} detected. "
        f"Pattern confidence: {pattern.confidence_score:.0f}/100. "
        f"Signal: {signal.value}. "
        f"Entry: {entry_price:.2f}, SL: {stop_loss:.2f}, "
        f"TP1: {t1:.2f} | TP2: {t2:.2f} | TP3: {t3:.2f}. "
        f"R/R: {rr_ratio:.2f}x. "
        f"Risk: {risk.risk_score.value} ({risk.risk_numeric:.0f}/100). "
        f"False breakout probability: {risk.false_breakout_probability*100:.0f}%. "
        f"DISCLAIMER: This is probabilistic technical analysis only. Not financial advice."
    )

    return TradeRecommendation(
        signal=signal,
        entry_price=round(entry_price, 4),
        stop_loss=round(stop_loss, 4),
        take_profit_1=round(t1, 4),
        take_profit_2=round(t2, 4),
        take_profit_3=round(t3, 4),
        risk_reward_ratio=round(rr_ratio, 2),
        position_size_pct=round(position_size_pct, 2),
        atr_used=round(atr_safe, 4),
        confidence_adjusted_signal=strength,
        summary_explanation=summary,
    )
