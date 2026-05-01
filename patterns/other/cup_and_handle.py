"""
Cup and Handle detector.

Math approach:
  - Cup: fit degree-2 polynomial to the lows of a price series.
    Valid cup: concave-up (positive leading coefficient), R² > 0.7,
    left rim ≈ right rim price.
  - Handle: small downward drift after the right rim (< 50% of cup depth),
    lasting 5–20 candles.
  - Breakout = close above left rim / handle resistance.
"""

from typing import Optional
import numpy as np

from patterns.base import BasePatternDetector, PatternRegistry
from models.schemas import PatternResult
from models.enums import PatternType, TrendDirection
from analysis.regression import (
    build_trendline, polynomial_regression, is_concave_up
)
from analysis.breakout import breakout_confirmation
from analysis.indicators import volume_surge_factor
from config import settings


CUP_MIN_CANDLES = 30
CUP_MAX_CANDLES = 120
CUP_POLY_R2_MIN = 0.65
CUP_RIM_SYMMETRY_TOL = 0.04   # 4% price diff between rims is acceptable
HANDLE_MAX_CANDLES = 20
HANDLE_MIN_CANDLES = 5
HANDLE_MAX_RETRACE = 0.50


@PatternRegistry.register(PatternType.CUP_AND_HANDLE)
class CupAndHandleDetector(BasePatternDetector):
    """
    Cup and Handle: bullish continuation pattern.
    Uses polynomial curve fitting to confirm the rounded bottom.
    """
    pattern_type = PatternType.CUP_AND_HANDLE
    MIN_CANDLES = CUP_MIN_CANDLES + HANDLE_MIN_CANDLES

    def detect(self) -> Optional[PatternResult]:
        if not self.has_enough_data():
            return None

        best = None
        best_score = -1.0

        # Try different cup windows ending at various points
        for cup_end in range(CUP_MIN_CANDLES, self.n - HANDLE_MIN_CANDLES):
            for cup_start in range(max(0, cup_end - CUP_MAX_CANDLES), cup_end - CUP_MIN_CANDLES + 1):
                cup_lows = self.lows[cup_start:cup_end + 1]
                cup_x = np.arange(len(cup_lows), dtype=float)
                result = polynomial_regression(cup_x, cup_lows, degree=2)

                if result.r_squared < CUP_POLY_R2_MIN:
                    continue
                if not is_concave_up(result.coefficients):
                    continue

                # Check rim symmetry
                left_rim = float(self.closes[cup_start])
                right_rim = float(self.closes[cup_end])
                rim_diff = abs(left_rim - right_rim) / (max(left_rim, right_rim) + 1e-9)
                if rim_diff > CUP_RIM_SYMMETRY_TOL:
                    continue

                # Validate handle
                handle_data = self.lows[cup_end: cup_end + HANDLE_MAX_CANDLES]
                if len(handle_data) < HANDLE_MIN_CANDLES:
                    continue
                cup_depth = left_rim - float(np.min(cup_lows))
                handle_low = float(np.min(handle_data))
                handle_retrace = (right_rim - handle_low) / (cup_depth + 1e-9)
                if handle_retrace > HANDLE_MAX_RETRACE or handle_retrace < 0.05:
                    continue

                score = result.r_squared * (1 - rim_diff) * (1 - handle_retrace)
                if score > best_score:
                    best_score = score
                    best = {
                        "cup_start": cup_start,
                        "cup_end": cup_end,
                        "left_rim": left_rim,
                        "right_rim": right_rim,
                        "cup_depth": cup_depth,
                        "handle_retrace": handle_retrace,
                        "regression": result,
                    }

        if best is None:
            return None

        breakout_level = max(best["left_rim"], best["right_rim"])
        cup_x_full = np.arange(best["cup_end"] - best["cup_start"] + 1, dtype=float)

        # Use trendlines on cup edges for support/resistance
        res_line = build_trendline(
            np.array([float(best["cup_start"]), float(best["cup_end"])]),
            np.array([best["left_rim"], best["right_rim"]]),
        )
        sup_line = build_trendline(cup_x_full, self.lows[best["cup_start"]:best["cup_end"] + 1])

        vol_surge = volume_surge_factor(self.volumes)
        vol_confirmed = vol_surge >= settings.BREAKOUT_VOLUME_FACTOR

        confidence = self._confidence_base(best["regression"].r_squared)
        # Reward tight rim symmetry
        rim_diff = abs(best["left_rim"] - best["right_rim"]) / (breakout_level + 1e-9)
        confidence += (1 - rim_diff / CUP_RIM_SYMMETRY_TOL) * 10
        if vol_confirmed:
            confidence = min(confidence + 10, 92)

        _, conf_boost, _ = breakout_confirmation(
            self.closes, breakout_level, "UP", self.volumes
        )
        confidence = min(confidence + conf_boost, 92)

        return PatternResult(
            pattern_type=PatternType.CUP_AND_HANDLE,
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
            start_date=self._date_str(best["cup_start"]),
            end_date=self._date_str(-1),
            candles_analyzed=self.n - best["cup_start"],
            regression=best["regression"],
            raw_notes=(
                f"Cup depth: {best['cup_depth']:.2f}, "
                f"Rim diff: {rim_diff*100:.1f}%, "
                f"Handle retrace: {best['handle_retrace']*100:.1f}%, "
                f"Poly R²: {best['regression'].r_squared:.3f}"
            ),
        )
