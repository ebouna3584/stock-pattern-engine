"""
Double Top / Double Bottom / Triple Top / Triple Bottom detectors.

Math approach:
  - Detect N prominent pivot highs (tops) or pivot lows (bottoms).
  - Peaks must be within price_tolerance % of each other.
  - Troughs between peaks define the neckline.
  - Volume on second/third peak should ideally be lower (distribution).
"""

from typing import Optional, List, Tuple
import numpy as np

from patterns.base import BasePatternDetector, PatternRegistry
from models.schemas import PatternResult
from models.enums import PatternType, TrendDirection
from analysis.regression import build_trendline, detect_pivot_highs, detect_pivot_lows
from analysis.breakout import breakout_confirmation
from analysis.indicators import volume_surge_factor
from config import settings


PRICE_TOLERANCE = 0.03   # Peaks must be within 3% of each other to qualify
MIN_PEAK_SEPARATION = 5  # Peaks must be at least 5 candles apart


def _peaks_equal(prices: np.ndarray, indices: List[int], tol: float = PRICE_TOLERANCE) -> bool:
    vals = [prices[i] for i in indices]
    mean_val = float(np.mean(vals))
    return all(abs(v - mean_val) / (mean_val + 1e-9) <= tol for v in vals)


def _peaks_separated(indices: List[int], min_gap: int = MIN_PEAK_SEPARATION) -> bool:
    return all(indices[i + 1] - indices[i] >= min_gap for i in range(len(indices) - 1))


class MultiTopBase(BasePatternDetector):
    MIN_CANDLES = 25
    N_PEAKS = 2  # Override in subclass

    def _detect_equal_peaks(
        self, pivot_fn, price_arr: np.ndarray
    ) -> Optional[List[int]]:
        pivots = pivot_fn(price_arr, window=4)
        if len(pivots) < self.N_PEAKS:
            return None
        # Slide a window over the pivots looking for N equal peaks
        for i in range(len(pivots) - self.N_PEAKS + 1):
            candidate = list(pivots[i: i + self.N_PEAKS])
            if (
                _peaks_separated(candidate)
                and _peaks_equal(price_arr, candidate)
            ):
                return candidate
        return None

    def _neckline_price(self, peak_indices: List[int], low_arr: np.ndarray) -> float:
        """Lowest trough between the first and last peak."""
        start = peak_indices[0]
        end = peak_indices[-1]
        return float(np.min(low_arr[start:end + 1]))

    def _avg_high_price(self, peak_indices: List[int], price_arr: np.ndarray) -> float:
        return float(np.mean([price_arr[i] for i in peak_indices]))


@PatternRegistry.register(PatternType.DOUBLE_TOP)
class DoubleTopDetector(MultiTopBase):
    pattern_type = PatternType.DOUBLE_TOP
    N_PEAKS = 2

    def detect(self) -> Optional[PatternResult]:
        if not self.has_enough_data():
            return None
        peaks = self._detect_equal_peaks(detect_pivot_highs, self.highs)
        if peaks is None:
            return None

        neckline_price = self._neckline_price(peaks, self.lows)
        avg_top = self._avg_high_price(peaks, self.highs)
        pattern_height = avg_top - neckline_price

        res_line = build_trendline(
            np.array([float(peaks[0]), float(peaks[1])]),
            self.highs[[peaks[0], peaks[1]]],
        )
        # Flat support at neckline
        sup_line = build_trendline(
            np.array([float(peaks[0]), float(peaks[-1])]),
            np.array([neckline_price, neckline_price]),
        )
        vol_surge = volume_surge_factor(self.volumes)
        vol_confirmed = vol_surge >= settings.BREAKOUT_VOLUME_FACTOR

        confidence = 55.0  # Structural pattern; not regression-based
        # Volume diminishing on second top is more bearish
        if peaks[1] < len(self.volumes) and peaks[0] < len(self.volumes):
            if self.volumes[peaks[1]] < self.volumes[peaks[0]]:
                confidence += 10
        if vol_confirmed:
            confidence = min(confidence + 8, 90)

        _, conf_boost, _ = breakout_confirmation(
            self.closes, neckline_price, "DOWN", self.volumes
        )
        confidence = min(confidence + conf_boost, 90)

        return PatternResult(
            pattern_type=PatternType.DOUBLE_TOP,
            trend_direction=TrendDirection.BEARISH,
            confidence_score=round(confidence, 1),
            breakout_level=neckline_price,
            support_line=sup_line,
            resistance_line=res_line,
            slope_support=0.0,
            slope_resistance=res_line.slope,
            volatility_estimate=self._volatility_estimate(),
            volume_confirmation=round(vol_surge, 2),
            volume_confirmed=vol_confirmed,
            start_date=self._date_str(peaks[0]),
            end_date=self._date_str(-1),
            candles_analyzed=self.n - peaks[0],
            raw_notes=f"Tops: {[round(self.highs[p], 2) for p in peaks]}, Neck: {neckline_price:.2f}",
        )


@PatternRegistry.register(PatternType.DOUBLE_BOTTOM)
class DoubleBottomDetector(MultiTopBase):
    pattern_type = PatternType.DOUBLE_BOTTOM
    N_PEAKS = 2

    def detect(self) -> Optional[PatternResult]:
        if not self.has_enough_data():
            return None
        peaks = self._detect_equal_peaks(detect_pivot_lows, self.lows)
        if peaks is None:
            return None

        neckline_price = float(np.max(self.highs[peaks[0]:peaks[-1] + 1]))
        avg_bottom = self._avg_high_price(peaks, self.lows)
        pattern_height = neckline_price - avg_bottom

        sup_line = build_trendline(
            np.array([float(peaks[0]), float(peaks[1])]),
            self.lows[[peaks[0], peaks[1]]],
        )
        res_line = build_trendline(
            np.array([float(peaks[0]), float(peaks[-1])]),
            np.array([neckline_price, neckline_price]),
        )

        vol_surge = volume_surge_factor(self.volumes)
        confidence = 55.0
        if peaks[1] < len(self.volumes) and self.volumes[peaks[1]] > self.volumes[peaks[0]]:
            confidence += 8  # Volume increases on second bottom = bullish
        if vol_surge >= settings.BREAKOUT_VOLUME_FACTOR:
            confidence = min(confidence + 10, 90)

        _, conf_boost, _ = breakout_confirmation(
            self.closes, neckline_price, "UP", self.volumes
        )
        confidence = min(confidence + conf_boost, 90)

        return PatternResult(
            pattern_type=PatternType.DOUBLE_BOTTOM,
            trend_direction=TrendDirection.BULLISH,
            confidence_score=round(confidence, 1),
            breakout_level=neckline_price,
            support_line=sup_line,
            resistance_line=res_line,
            slope_support=sup_line.slope,
            slope_resistance=0.0,
            volatility_estimate=self._volatility_estimate(),
            volume_confirmation=round(vol_surge, 2),
            volume_confirmed=vol_surge >= settings.BREAKOUT_VOLUME_FACTOR,
            start_date=self._date_str(peaks[0]),
            end_date=self._date_str(-1),
            candles_analyzed=self.n - peaks[0],
            raw_notes=f"Bottoms: {[round(self.lows[p], 2) for p in peaks]}, Neck: {neckline_price:.2f}",
        )


@PatternRegistry.register(PatternType.TRIPLE_TOP)
class TripleTopDetector(MultiTopBase):
    pattern_type = PatternType.TRIPLE_TOP
    N_PEAKS = 3

    def detect(self) -> Optional[PatternResult]:
        if not self.has_enough_data():
            return None
        peaks = self._detect_equal_peaks(detect_pivot_highs, self.highs)
        if peaks is None:
            return None

        neckline_price = self._neckline_price(peaks, self.lows)
        res_line = build_trendline(
            np.array([float(p) for p in peaks]),
            self.highs[peaks],
        )
        sup_line = build_trendline(
            np.array([float(peaks[0]), float(peaks[-1])]),
            np.array([neckline_price, neckline_price]),
        )
        vol_surge = volume_surge_factor(self.volumes)
        confidence = 65.0  # Triple is more reliable than double
        if vol_surge >= settings.BREAKOUT_VOLUME_FACTOR:
            confidence = min(confidence + 8, 92)
        _, conf_boost, _ = breakout_confirmation(
            self.closes, neckline_price, "DOWN", self.volumes
        )
        confidence = min(confidence + conf_boost, 92)

        return PatternResult(
            pattern_type=PatternType.TRIPLE_TOP,
            trend_direction=TrendDirection.BEARISH,
            confidence_score=round(confidence, 1),
            breakout_level=neckline_price,
            support_line=sup_line,
            resistance_line=res_line,
            slope_support=0.0,
            slope_resistance=res_line.slope,
            volatility_estimate=self._volatility_estimate(),
            volume_confirmation=round(vol_surge, 2),
            volume_confirmed=vol_surge >= settings.BREAKOUT_VOLUME_FACTOR,
            start_date=self._date_str(peaks[0]),
            end_date=self._date_str(-1),
            candles_analyzed=self.n - peaks[0],
            raw_notes=f"Tops: {[round(self.highs[p], 2) for p in peaks]}, Neck: {neckline_price:.2f}",
        )


@PatternRegistry.register(PatternType.TRIPLE_BOTTOM)
class TripleBottomDetector(MultiTopBase):
    pattern_type = PatternType.TRIPLE_BOTTOM
    N_PEAKS = 3

    def detect(self) -> Optional[PatternResult]:
        if not self.has_enough_data():
            return None
        peaks = self._detect_equal_peaks(detect_pivot_lows, self.lows)
        if peaks is None:
            return None

        neckline_price = float(np.max(self.highs[peaks[0]:peaks[-1] + 1]))
        sup_line = build_trendline(
            np.array([float(p) for p in peaks]),
            self.lows[peaks],
        )
        res_line = build_trendline(
            np.array([float(peaks[0]), float(peaks[-1])]),
            np.array([neckline_price, neckline_price]),
        )
        vol_surge = volume_surge_factor(self.volumes)
        confidence = 65.0
        if vol_surge >= settings.BREAKOUT_VOLUME_FACTOR:
            confidence = min(confidence + 8, 92)
        _, conf_boost, _ = breakout_confirmation(
            self.closes, neckline_price, "UP", self.volumes
        )
        confidence = min(confidence + conf_boost, 92)

        return PatternResult(
            pattern_type=PatternType.TRIPLE_BOTTOM,
            trend_direction=TrendDirection.BULLISH,
            confidence_score=round(confidence, 1),
            breakout_level=neckline_price,
            support_line=sup_line,
            resistance_line=res_line,
            slope_support=sup_line.slope,
            slope_resistance=0.0,
            volatility_estimate=self._volatility_estimate(),
            volume_confirmation=round(vol_surge, 2),
            volume_confirmed=vol_surge >= settings.BREAKOUT_VOLUME_FACTOR,
            start_date=self._date_str(peaks[0]),
            end_date=self._date_str(-1),
            candles_analyzed=self.n - peaks[0],
            raw_notes=f"Bottoms: {[round(self.lows[p], 2) for p in peaks]}, Neck: {neckline_price:.2f}",
        )
