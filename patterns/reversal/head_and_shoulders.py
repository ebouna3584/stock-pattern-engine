"""
Head and Shoulders + Inverse Head and Shoulders detectors.

Math approach:
  - Find three prominent pivot highs (or lows for inverse).
  - Head must be highest (or lowest).
  - Shoulders must be roughly equal height (within symmetry tolerance).
  - Neckline = linear regression through the two troughs (or peaks for inverse).
  - Breakout = close below neckline (or above for inverse).
"""

from typing import Optional, List, Tuple
import numpy as np

from patterns.base import BasePatternDetector, PatternRegistry
from models.schemas import PatternResult, TrendLine
from models.enums import PatternType, TrendDirection
from analysis.regression import build_trendline, detect_pivot_highs, detect_pivot_lows
from analysis.breakout import breakout_confirmation
from analysis.indicators import volume_surge_factor
from config import settings


def _find_best_hs_triple(
    peaks: np.ndarray,
    prices: np.ndarray,
    mode: str = "HIGH",
    sym_tol: float = None,
) -> Optional[Tuple[int, int, int]]:
    """
    From a list of pivot indices, find the best (L, Head, R) triple where:
      HEAD is the extreme (max for H&S, min for inverse).
      |L_price - R_price| / head_price <= sym_tol.
    Returns (left_idx, head_idx, right_idx) from the original array, or None.
    """
    if sym_tol is None:
        sym_tol = settings.SYMMETRY_TOLERANCE
    if len(peaks) < 3:
        return None

    best = None
    best_score = float("inf")

    for i in range(len(peaks) - 2):
        li, hi, ri = peaks[i], peaks[i + 1], peaks[i + 2]
        lp, hp, rp = prices[li], prices[hi], prices[ri]

        if mode == "HIGH":
            is_head = hp > lp and hp > rp
        else:
            is_head = hp < lp and hp < rp

        if not is_head:
            continue

        sym = abs(lp - rp) / (abs(hp) + 1e-9)
        if sym > sym_tol:
            continue

        # Prefer tighter symmetry
        if sym < best_score:
            best_score = sym
            best = (li, hi, ri)

    return best


class HeadShouldersBase(BasePatternDetector):
    MIN_CANDLES = 30

    def _neckline_from_troughs(
        self,
        left_peak_idx: int,
        head_idx: int,
        right_peak_idx: int,
    ) -> TrendLine:
        """Neckline runs through the two troughs between peaks."""
        trough1_slice = self.lows[left_peak_idx:head_idx]
        trough2_slice = self.lows[head_idx:right_peak_idx]
        t1_idx = left_peak_idx + int(np.argmin(trough1_slice))
        t2_idx = head_idx + int(np.argmin(trough2_slice))
        x = np.array([float(t1_idx), float(t2_idx)])
        y = np.array([self.lows[t1_idx], self.lows[t2_idx]])
        return build_trendline(x, y)

    def _neckline_from_peaks(
        self,
        left_trough_idx: int,
        head_idx: int,
        right_trough_idx: int,
    ) -> TrendLine:
        """Neckline for inverse H&S runs through the two peaks between troughs."""
        peak1_slice = self.highs[left_trough_idx:head_idx]
        peak2_slice = self.highs[head_idx:right_trough_idx]
        p1_idx = left_trough_idx + int(np.argmax(peak1_slice))
        p2_idx = head_idx + int(np.argmax(peak2_slice))
        x = np.array([float(p1_idx), float(p2_idx)])
        y = np.array([self.highs[p1_idx], self.highs[p2_idx]])
        return build_trendline(x, y)

    def _pattern_height(
        self, head_price: float, neckline: TrendLine, head_idx: int
    ) -> float:
        neckline_at_head = neckline.intercept + neckline.slope * head_idx
        return abs(head_price - neckline_at_head)


@PatternRegistry.register(PatternType.HEAD_AND_SHOULDERS)
class HeadAndShouldersDetector(HeadShouldersBase):
    """
    Head and Shoulders (bearish reversal).
    """
    pattern_type = PatternType.HEAD_AND_SHOULDERS

    def detect(self) -> Optional[PatternResult]:
        if not self.has_enough_data():
            return None
        pivot_h = detect_pivot_highs(self.highs, window=4)
        triple = _find_best_hs_triple(pivot_h, self.highs, mode="HIGH")
        if triple is None:
            return None
        li, hi_idx, ri = triple

        neckline = self._neckline_from_troughs(li, hi_idx, ri)
        breakout_level = float(neckline.intercept + neckline.slope * self.x[-1])
        pattern_h = self._pattern_height(self.highs[hi_idx], neckline, hi_idx)

        # Flat/close-to-flat neckline is more reliable
        neckline_flat_bonus = 10.0 if abs(neckline.slope) < settings.SLOPE_TOLERANCE * 5 else 0.0

        vol_surge = volume_surge_factor(self.volumes)
        vol_confirmed = vol_surge >= settings.BREAKOUT_VOLUME_FACTOR
        confidence = self._confidence_base(neckline.r_squared)
        confidence += neckline_flat_bonus
        if vol_confirmed:
            confidence = min(confidence + 10, 93)

        _, conf_boost, _ = breakout_confirmation(
            self.closes, breakout_level, "DOWN", self.volumes
        )
        confidence = min(confidence + conf_boost, 93)

        # Build a stub resistance/support for the output schema
        res_line = build_trendline(
            np.array([float(li), float(hi_idx), float(ri)]),
            self.highs[[li, hi_idx, ri]],
        )
        return PatternResult(
            pattern_type=PatternType.HEAD_AND_SHOULDERS,
            trend_direction=TrendDirection.BEARISH,
            confidence_score=round(confidence, 1),
            breakout_level=breakout_level,
            support_line=neckline,
            resistance_line=res_line,
            slope_support=neckline.slope,
            slope_resistance=res_line.slope,
            volatility_estimate=self._volatility_estimate(),
            volume_confirmation=round(vol_surge, 2),
            volume_confirmed=vol_confirmed,
            start_date=self._date_str(li),
            end_date=self._date_str(-1),
            candles_analyzed=self.n - li,
            raw_notes=(
                f"Left shoulder: {self.highs[li]:.2f}, "
                f"Head: {self.highs[hi_idx]:.2f}, "
                f"Right shoulder: {self.highs[ri]:.2f}, "
                f"Pattern height: {pattern_h:.2f}"
            ),
        )


@PatternRegistry.register(PatternType.INVERSE_HEAD_AND_SHOULDERS)
class InverseHeadAndShouldersDetector(HeadShouldersBase):
    """
    Inverse Head and Shoulders (bullish reversal).
    """
    pattern_type = PatternType.INVERSE_HEAD_AND_SHOULDERS

    def detect(self) -> Optional[PatternResult]:
        if not self.has_enough_data():
            return None
        pivot_l = detect_pivot_lows(self.lows, window=4)
        triple = _find_best_hs_triple(pivot_l, self.lows, mode="LOW")
        if triple is None:
            return None
        li, hi_idx, ri = triple

        neckline = self._neckline_from_peaks(li, hi_idx, ri)
        breakout_level = float(neckline.intercept + neckline.slope * self.x[-1])
        pattern_h = self._pattern_height(self.lows[hi_idx], neckline, hi_idx)

        neckline_flat_bonus = 10.0 if abs(neckline.slope) < settings.SLOPE_TOLERANCE * 5 else 0.0
        vol_surge = volume_surge_factor(self.volumes)
        vol_confirmed = vol_surge >= settings.BREAKOUT_VOLUME_FACTOR
        confidence = self._confidence_base(neckline.r_squared)
        confidence += neckline_flat_bonus
        if vol_confirmed:
            confidence = min(confidence + 10, 93)

        _, conf_boost, _ = breakout_confirmation(
            self.closes, breakout_level, "UP", self.volumes
        )
        confidence = min(confidence + conf_boost, 93)

        sup_line = build_trendline(
            np.array([float(li), float(hi_idx), float(ri)]),
            self.lows[[li, hi_idx, ri]],
        )
        return PatternResult(
            pattern_type=PatternType.INVERSE_HEAD_AND_SHOULDERS,
            trend_direction=TrendDirection.BULLISH,
            confidence_score=round(confidence, 1),
            breakout_level=breakout_level,
            support_line=sup_line,
            resistance_line=neckline,
            slope_support=sup_line.slope,
            slope_resistance=neckline.slope,
            volatility_estimate=self._volatility_estimate(),
            volume_confirmation=round(vol_surge, 2),
            volume_confirmed=vol_confirmed,
            start_date=self._date_str(li),
            end_date=self._date_str(-1),
            candles_analyzed=self.n - li,
            raw_notes=(
                f"Left shoulder: {self.lows[li]:.2f}, "
                f"Head: {self.lows[hi_idx]:.2f}, "
                f"Right shoulder: {self.lows[ri]:.2f}, "
                f"Pattern height: {pattern_h:.2f}"
            ),
        )
