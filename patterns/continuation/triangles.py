"""
Triangle pattern detectors: Ascending, Descending, Symmetrical.

Math approach:
  - Fit linear regression to pivot highs → resistance trendline
  - Fit linear regression to pivot lows → support trendline
  - Classify by slope signs and convergence
"""

from typing import Optional
import numpy as np

from patterns.base import BasePatternDetector, PatternRegistry
from models.schemas import PatternResult
from models.enums import PatternType, TrendDirection
from analysis.regression import (
    build_trendline, detect_pivot_highs, detect_pivot_lows, slope_consistency
)
from analysis.breakout import (
    breakout_confirmation, false_breakout_probability, estimate_breakout_target
)
from analysis.indicators import volume_surge_factor
from api.config import settings


class TriangleDetectorBase(BasePatternDetector):
    """Shared logic for all three triangle variants."""

    MIN_CANDLES = 25
    CONVERGENCE_RATIO_MIN = 0.4  # lines must converge at least 40%

    def _build_triangle_lines(self):
        pivot_h_idx = detect_pivot_highs(self.highs, window=3)
        pivot_l_idx = detect_pivot_lows(self.lows, window=3)
        if len(pivot_h_idx) < 3 or len(pivot_l_idx) < 3:
            return None, None
        res_line = build_trendline(self.x[pivot_h_idx], self.highs[pivot_h_idx])
        sup_line = build_trendline(self.x[pivot_l_idx], self.lows[pivot_l_idx])
        return res_line, sup_line

    def _lines_converging(self, res_line, sup_line) -> bool:
        """True if the gap between the lines is shrinking over the window."""
        early_gap = abs(
            (res_line.intercept + res_line.slope * self.x[0]) -
            (sup_line.intercept + sup_line.slope * self.x[0])
        )
        late_gap = abs(
            (res_line.intercept + res_line.slope * self.x[-1]) -
            (sup_line.intercept + sup_line.slope * self.x[-1])
        )
        if early_gap == 0:
            return False
        return late_gap < early_gap * (1 - self.CONVERGENCE_RATIO_MIN)

    def _build_result(
        self,
        pattern_type: PatternType,
        trend_dir: TrendDirection,
        res_line,
        sup_line,
        breakout_level: float,
        trade_dir: str,
    ) -> PatternResult:
        vol_surge = volume_surge_factor(self.volumes)
        vol_confirmed = vol_surge >= settings.BREAKOUT_VOLUME_FACTOR
        avg_r2 = (res_line.r_squared + sup_line.r_squared) / 2
        confidence = self._confidence_base(avg_r2)
        # Boost for volume
        if vol_confirmed:
            confidence = min(confidence + 10, 95)
        # Boost for RSI confirmation
        rsi = self._rsi()
        if rsi:
            if trade_dir == "UP" and rsi < 60:
                confidence = min(confidence + 5, 95)
            elif trade_dir == "DOWN" and rsi > 40:
                confidence = min(confidence + 5, 95)
        _, conf_boost, _ = breakout_confirmation(
            self.closes, breakout_level, trade_dir, self.volumes
        )
        confidence = min(confidence + conf_boost, 95)

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
        )


@PatternRegistry.register(PatternType.ASCENDING_TRIANGLE)
class AscendingTriangleDetector(TriangleDetectorBase):
    """
    Ascending Triangle:
      - Resistance: flat (slope ≈ 0)
      - Support: rising (slope > 0)
      - Bias: BULLISH (breakout above flat resistance)
    """
    pattern_type = PatternType.ASCENDING_TRIANGLE

    def detect(self) -> Optional[PatternResult]:
        if not self.has_enough_data():
            return None
        res_line, sup_line = self._build_triangle_lines()
        if res_line is None:
            return None
        flat_res = abs(res_line.slope) <= settings.SLOPE_TOLERANCE * 3
        rising_sup = sup_line.slope > settings.SLOPE_TOLERANCE
        if not (flat_res and rising_sup and self._lines_converging(res_line, sup_line)):
            return None
        breakout_level = float(res_line.intercept + res_line.slope * self.x[-1])
        return self._build_result(
            PatternType.ASCENDING_TRIANGLE,
            TrendDirection.BULLISH,
            res_line, sup_line,
            breakout_level, "UP",
        )


@PatternRegistry.register(PatternType.DESCENDING_TRIANGLE)
class DescendingTriangleDetector(TriangleDetectorBase):
    """
    Descending Triangle:
      - Resistance: declining (slope < 0)
      - Support: flat (slope ≈ 0)
      - Bias: BEARISH (breakout below flat support)
    """
    pattern_type = PatternType.DESCENDING_TRIANGLE

    def detect(self) -> Optional[PatternResult]:
        if not self.has_enough_data():
            return None
        res_line, sup_line = self._build_triangle_lines()
        if res_line is None:
            return None
        declining_res = res_line.slope < -settings.SLOPE_TOLERANCE
        flat_sup = abs(sup_line.slope) <= settings.SLOPE_TOLERANCE * 3
        if not (declining_res and flat_sup and self._lines_converging(res_line, sup_line)):
            return None
        breakout_level = float(sup_line.intercept + sup_line.slope * self.x[-1])
        return self._build_result(
            PatternType.DESCENDING_TRIANGLE,
            TrendDirection.BEARISH,
            res_line, sup_line,
            breakout_level, "DOWN",
        )


@PatternRegistry.register(PatternType.SYMMETRICAL_TRIANGLE)
class SymmetricalTriangleDetector(TriangleDetectorBase):
    """
    Symmetrical Triangle:
      - Resistance: declining (slope < 0)
      - Support: rising (slope > 0)
      - Both converge at apex
      - Breakout direction decided by prevailing trend (macro bias)
    """
    pattern_type = PatternType.SYMMETRICAL_TRIANGLE

    def detect(self) -> Optional[PatternResult]:
        if not self.has_enough_data():
            return None
        res_line, sup_line = self._build_triangle_lines()
        if res_line is None:
            return None
        declining_res = res_line.slope < -settings.SLOPE_TOLERANCE
        rising_sup = sup_line.slope > settings.SLOPE_TOLERANCE
        if not (declining_res and rising_sup and self._lines_converging(res_line, sup_line)):
            return None
        # Macro bias: last 10 closes direction
        macro_up = float(np.mean(np.diff(self.closes[-10:]))) > 0
        trend_dir = TrendDirection.BULLISH if macro_up else TrendDirection.BEARISH
        if macro_up:
            breakout_level = float(res_line.intercept + res_line.slope * self.x[-1])
            trade_dir = "UP"
        else:
            breakout_level = float(sup_line.intercept + sup_line.slope * self.x[-1])
            trade_dir = "DOWN"
        return self._build_result(
            PatternType.SYMMETRICAL_TRIANGLE,
            trend_dir,
            res_line, sup_line,
            breakout_level, trade_dir,
        )
