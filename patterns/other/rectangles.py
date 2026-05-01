"""
Rectangle (trading range / consolidation box) detector.

Math approach:
  - Both resistance and support trendlines must be flat (slope ≈ 0).
  - Channel must have at least 2 touches on each boundary.
  - Breakout direction determines bullish or bearish.
"""

from typing import Optional
import numpy as np

from patterns.base import BasePatternDetector, PatternRegistry
from models.schemas import PatternResult
from models.enums import PatternType, TrendDirection
from analysis.regression import build_trendline, detect_pivot_highs, detect_pivot_lows
from analysis.breakout import breakout_confirmation
from analysis.indicators import volume_surge_factor
from config import settings


FLAT_SLOPE_TOL = 0.008   # Max slope magnitude for a "flat" trendline
MIN_TOUCHES = 2          # Each boundary must be tested at least twice


@PatternRegistry.register(PatternType.RECTANGLE_BULLISH)
class RectangleDetector(BasePatternDetector):
    """
    Rectangle: price consolidates between two horizontal levels.
    Bullish version: in an uptrend, prior move was up, expect upside breakout.
    Bearish version: same pattern but context is downtrend.
    We detect the rectangle and classify based on macro trend.
    """
    pattern_type = PatternType.RECTANGLE_BULLISH
    MIN_CANDLES = 20

    def detect(self) -> Optional[PatternResult]:
        if not self.has_enough_data():
            return None
        pivot_h = detect_pivot_highs(self.highs, window=3)
        pivot_l = detect_pivot_lows(self.lows, window=3)
        if len(pivot_h) < MIN_TOUCHES or len(pivot_l) < MIN_TOUCHES:
            return None

        res_line = build_trendline(self.x[pivot_h], self.highs[pivot_h])
        sup_line = build_trendline(self.x[pivot_l], self.lows[pivot_l])

        # Both lines must be flat
        if abs(res_line.slope) > FLAT_SLOPE_TOL or abs(sup_line.slope) > FLAT_SLOPE_TOL:
            return None
        # Lines must be distinct (channel must have meaningful width)
        mid_res = (res_line.intercept + res_line.end_price) / 2
        mid_sup = (sup_line.intercept + sup_line.end_price) / 2
        channel_width = mid_res - mid_sup
        if channel_width <= 0 or channel_width / (mid_res + 1e-9) < 0.01:
            return None

        # Macro trend from first 10% of window
        macro_closes = self.closes[:max(5, self.n // 10)]
        macro_up = float(macro_closes[-1]) > float(macro_closes[0])

        pattern_type = PatternType.RECTANGLE_BULLISH if macro_up else PatternType.RECTANGLE_BEARISH
        trend_dir = TrendDirection.BULLISH if macro_up else TrendDirection.BEARISH

        if macro_up:
            breakout_level = float(res_line.intercept + res_line.slope * self.x[-1])
            trade_dir = "UP"
        else:
            breakout_level = float(sup_line.intercept + sup_line.slope * self.x[-1])
            trade_dir = "DOWN"

        vol_surge = volume_surge_factor(self.volumes)
        vol_confirmed = vol_surge >= settings.BREAKOUT_VOLUME_FACTOR
        avg_r2 = (res_line.r_squared + sup_line.r_squared) / 2
        confidence = self._confidence_base(avg_r2)
        # More pivot touches → higher confidence
        touch_bonus = min((len(pivot_h) + len(pivot_l)) * 2, 12)
        confidence = min(confidence + touch_bonus, 88)
        if vol_confirmed:
            confidence = min(confidence + 8, 88)

        _, conf_boost, _ = breakout_confirmation(
            self.closes, breakout_level, trade_dir, self.volumes
        )
        confidence = min(confidence + conf_boost, 88)

        return PatternResult(
            pattern_type=pattern_type,
            trend_direction=trend_dir,
            confidence_score=round(confidence, 1),
            breakout_level=breakout_level,
            support_line=sup_line,
            resistance_line=res_line,
            slope_support=sup_line.slope,
            slope_resistance=res_line.slope,
            volatility_estimate=self._volatility_estimate(),
            volume_confirmation=round(vol_surge, 2),
            volume_confirmed=vol_confirmed,
            start_date=self._date_str(0),
            end_date=self._date_str(-1),
            candles_analyzed=self.n,
            raw_notes=(
                f"Channel: {mid_sup:.2f} – {mid_res:.2f}, "
                f"Width: {channel_width:.2f} ({channel_width/mid_res*100:.1f}%)"
            ),
        )


# Register bearish variant pointing to same class
PatternRegistry.register(PatternType.RECTANGLE_BEARISH)(RectangleDetector)
