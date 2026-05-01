"""
Rising Wedge (bearish) and Falling Wedge (bullish) detectors.

Math approach:
  - Fit linear regression to pivot highs → resistance trendline.
  - Fit linear regression to pivot lows → support trendline.
  - Rising Wedge: both slopes positive, but resistance slope < support slope (converging up).
  - Falling Wedge: both slopes negative, but resistance slope > support slope (converging down).
  - Convergence: the gap between lines shrinks toward the apex.
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


CONVERGENCE_MIN = 0.30   # Lines must converge at least 30% over the window


@PatternRegistry.register(PatternType.RISING_WEDGE)
class RisingWedgeDetector(BasePatternDetector):
    """
    Rising Wedge = BEARISH.
    Price is rising but the channel is narrowing → exhaustion move.
    """
    pattern_type = PatternType.RISING_WEDGE
    MIN_CANDLES = 25

    def detect(self) -> Optional[PatternResult]:
        if not self.has_enough_data():
            return None
        pivot_h = detect_pivot_highs(self.highs, window=3)
        pivot_l = detect_pivot_lows(self.lows, window=3)
        if len(pivot_h) < 3 or len(pivot_l) < 3:
            return None

        res_line = build_trendline(self.x[pivot_h], self.highs[pivot_h])
        sup_line = build_trendline(self.x[pivot_l], self.lows[pivot_l])

        # Both slopes must be positive
        if not (res_line.slope > settings.SLOPE_TOLERANCE and sup_line.slope > settings.SLOPE_TOLERANCE):
            return None
        # Support slope > resistance slope (lines converging upward)
        if not (sup_line.slope > res_line.slope):
            return None
        # Verify convergence
        early_gap = abs(
            (res_line.intercept) - (sup_line.intercept)
        )
        late_gap = abs(
            (res_line.intercept + res_line.slope * self.x[-1]) -
            (sup_line.intercept + sup_line.slope * self.x[-1])
        )
        if early_gap == 0 or late_gap >= early_gap * (1 - CONVERGENCE_MIN):
            return None

        # Bearish breakout below support trendline
        breakout_level = float(sup_line.intercept + sup_line.slope * self.x[-1])
        vol_surge = volume_surge_factor(self.volumes)
        vol_confirmed = vol_surge >= settings.BREAKOUT_VOLUME_FACTOR

        avg_r2 = (res_line.r_squared + sup_line.r_squared) / 2
        confidence = self._confidence_base(avg_r2)
        # Reward tighter convergence
        convergence_pct = 1 - late_gap / early_gap
        confidence += convergence_pct * 10
        if vol_confirmed:
            confidence = min(confidence + 8, 90)

        _, conf_boost, _ = breakout_confirmation(
            self.closes, breakout_level, "DOWN", self.volumes
        )
        confidence = min(confidence + conf_boost, 90)

        return PatternResult(
            pattern_type=PatternType.RISING_WEDGE,
            trend_direction=TrendDirection.BEARISH,
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
                f"Res slope: {res_line.slope:.4f}, Sup slope: {sup_line.slope:.4f}, "
                f"Convergence: {convergence_pct*100:.1f}%"
            ),
        )


@PatternRegistry.register(PatternType.FALLING_WEDGE)
class FallingWedgeDetector(BasePatternDetector):
    """
    Falling Wedge = BULLISH.
    Price is falling but the channel is narrowing → deceleration, expect reversal up.
    """
    pattern_type = PatternType.FALLING_WEDGE
    MIN_CANDLES = 25

    def detect(self) -> Optional[PatternResult]:
        if not self.has_enough_data():
            return None
        pivot_h = detect_pivot_highs(self.highs, window=3)
        pivot_l = detect_pivot_lows(self.lows, window=3)
        if len(pivot_h) < 3 or len(pivot_l) < 3:
            return None

        res_line = build_trendline(self.x[pivot_h], self.highs[pivot_h])
        sup_line = build_trendline(self.x[pivot_l], self.lows[pivot_l])

        # Both slopes must be negative
        if not (res_line.slope < -settings.SLOPE_TOLERANCE and sup_line.slope < -settings.SLOPE_TOLERANCE):
            return None
        # Resistance slope < support slope (less negative) → converging downward
        if not (res_line.slope < sup_line.slope):
            return None
        early_gap = abs(
            (res_line.intercept) - (sup_line.intercept)
        )
        late_gap = abs(
            (res_line.intercept + res_line.slope * self.x[-1]) -
            (sup_line.intercept + sup_line.slope * self.x[-1])
        )
        if early_gap == 0 or late_gap >= early_gap * (1 - CONVERGENCE_MIN):
            return None

        # Bullish breakout above resistance trendline
        breakout_level = float(res_line.intercept + res_line.slope * self.x[-1])
        vol_surge = volume_surge_factor(self.volumes)
        vol_confirmed = vol_surge >= settings.BREAKOUT_VOLUME_FACTOR

        avg_r2 = (res_line.r_squared + sup_line.r_squared) / 2
        confidence = self._confidence_base(avg_r2)
        convergence_pct = 1 - late_gap / early_gap
        confidence += convergence_pct * 10
        if vol_confirmed:
            confidence = min(confidence + 8, 90)

        _, conf_boost, _ = breakout_confirmation(
            self.closes, breakout_level, "UP", self.volumes
        )
        confidence = min(confidence + conf_boost, 90)

        return PatternResult(
            pattern_type=PatternType.FALLING_WEDGE,
            trend_direction=TrendDirection.BULLISH,
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
                f"Res slope: {res_line.slope:.4f}, Sup slope: {sup_line.slope:.4f}, "
                f"Convergence: {convergence_pct*100:.1f}%"
            ),
        )
