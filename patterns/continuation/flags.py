"""
Flag and Pennant pattern detectors.

Flags: Sharp pole move followed by a parallel channel consolidation.
Pennants: Sharp pole followed by converging symmetrical triangle consolidation.

Math:
  - Detect the "pole": large directional move (>= 5% in <= 10 candles)
  - Detect the "flag body": parallel channel or converging triangle after pole
  - Measure retracement depth (< 50% of pole for valid flag)
"""

from typing import Optional
import numpy as np

from patterns.base import BasePatternDetector, PatternRegistry
from models.schemas import PatternResult
from models.enums import PatternType, TrendDirection
from analysis.regression import build_trendline, detect_pivot_highs, detect_pivot_lows
from analysis.breakout import breakout_confirmation
from analysis.indicators import volume_surge_factor
from api.config import settings


POLE_MIN_MOVE_PCT = 0.04     # Minimum 4% price move to qualify as pole
POLE_MAX_CANDLES = 12        # Pole must form within this many candles
FLAG_BODY_MIN_CANDLES = 5    # Flag consolidation needs at least 5 candles
MAX_RETRACEMENT_PCT = 0.50   # Flag cannot retrace more than 50% of pole


class FlagPennantBase(BasePatternDetector):
    MIN_CANDLES = 20

    def _detect_pole(self) -> Optional[dict]:
        """
        Scan for the most recent strong directional move (the pole).
        Returns dict with direction, start_idx, end_idx, pole_pct, or None.
        """
        for end in range(self.n - FLAG_BODY_MIN_CANDLES - 1, POLE_MAX_CANDLES - 1, -1):
            for start in range(max(0, end - POLE_MAX_CANDLES), end):
                move = (self.closes[end] - self.closes[start]) / (self.closes[start] + 1e-9)
                if abs(move) >= POLE_MIN_MOVE_PCT:
                    return {
                        "direction": "UP" if move > 0 else "DOWN",
                        "start_idx": start,
                        "end_idx": end,
                        "pole_start_price": float(self.closes[start]),
                        "pole_end_price": float(self.closes[end]),
                        "pole_pct": float(move),
                    }
        return None

    def _flag_body_df(self, pole_end_idx: int):
        """Return the subset of data after the pole (the flag/pennant body)."""
        body_start = pole_end_idx + 1
        if body_start >= self.n:
            return None
        from pandas import DataFrame
        sub = self.df.iloc[body_start:].copy()
        sub = sub.reset_index(drop=True)
        return sub

    def _measure_retracement(self, pole: dict, body_lows: np.ndarray) -> float:
        """Retracement of body lows relative to pole size."""
        pole_range = abs(pole["pole_end_price"] - pole["pole_start_price"])
        if pole_range == 0:
            return 0.0
        if pole["direction"] == "UP":
            max_retrace = pole["pole_end_price"] - np.min(body_lows)
        else:
            max_retrace = np.max(body_lows) - pole["pole_end_price"]
        return float(max_retrace / pole_range)


@PatternRegistry.register(PatternType.FLAG_BULLISH)
class BullishFlagDetector(FlagPennantBase):
    """
    Bullish Flag: upward pole + downward sloping parallel consolidation.
    Breakout = close above upper flag boundary.
    """
    pattern_type = PatternType.FLAG_BULLISH

    def detect(self) -> Optional[PatternResult]:
        if not self.has_enough_data():
            return None
        pole = self._detect_pole()
        if not pole or pole["direction"] != "UP":
            return None
        body_df = self._flag_body_df(pole["end_idx"])
        if body_df is None or len(body_df) < FLAG_BODY_MIN_CANDLES:
            return None

        body_highs = body_df["high"].to_numpy()
        body_lows = body_df["low"].to_numpy()
        body_x = np.arange(len(body_df), dtype=float)

        res_line = build_trendline(body_x, body_highs)
        sup_line = build_trendline(body_x, body_lows)

        # Flag: both trendlines slope slightly downward and are roughly parallel
        both_down = res_line.slope < 0 and sup_line.slope < 0
        slope_diff = abs(res_line.slope - sup_line.slope)
        parallel = slope_diff < abs(res_line.slope) * 0.5  # within 50% of each other

        retracement = self._measure_retracement(pole, body_lows)
        valid_retrace = retracement <= MAX_RETRACEMENT_PCT

        if not (both_down and parallel and valid_retrace):
            return None

        breakout_level = float(res_line.intercept + res_line.slope * body_x[-1])
        vol_surge = volume_surge_factor(self.volumes)
        vol_confirmed = vol_surge >= settings.BREAKOUT_VOLUME_FACTOR

        r2_avg = (res_line.r_squared + sup_line.r_squared) / 2
        confidence = self._confidence_base(r2_avg)
        if vol_confirmed:
            confidence = min(confidence + 12, 92)

        _, conf_boost, _ = breakout_confirmation(
            self.closes, breakout_level, "UP", self.volumes
        )
        confidence = min(confidence + conf_boost, 92)

        return PatternResult(
            pattern_type=PatternType.FLAG_BULLISH,
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
            start_date=self._date_str(pole["start_idx"]),
            end_date=self._date_str(-1),
            candles_analyzed=self.n,
            raw_notes=f"Pole: {pole['pole_pct']*100:.1f}%, Retracement: {retracement*100:.1f}%",
        )


@PatternRegistry.register(PatternType.FLAG_BEARISH)
class BearishFlagDetector(FlagPennantBase):
    """
    Bearish Flag: downward pole + upward sloping parallel consolidation.
    Breakout = close below lower flag boundary.
    """
    pattern_type = PatternType.FLAG_BEARISH

    def detect(self) -> Optional[PatternResult]:
        if not self.has_enough_data():
            return None
        pole = self._detect_pole()
        if not pole or pole["direction"] != "DOWN":
            return None
        body_df = self._flag_body_df(pole["end_idx"])
        if body_df is None or len(body_df) < FLAG_BODY_MIN_CANDLES:
            return None

        body_highs = body_df["high"].to_numpy()
        body_lows = body_df["low"].to_numpy()
        body_x = np.arange(len(body_df), dtype=float)

        res_line = build_trendline(body_x, body_highs)
        sup_line = build_trendline(body_x, body_lows)

        both_up = res_line.slope > 0 and sup_line.slope > 0
        slope_diff = abs(res_line.slope - sup_line.slope)
        parallel = slope_diff < abs(res_line.slope) * 0.5

        retracement = self._measure_retracement(pole, body_highs)
        valid_retrace = retracement <= MAX_RETRACEMENT_PCT

        if not (both_up and parallel and valid_retrace):
            return None

        breakout_level = float(sup_line.intercept + sup_line.slope * body_x[-1])
        vol_surge = volume_surge_factor(self.volumes)
        vol_confirmed = vol_surge >= settings.BREAKOUT_VOLUME_FACTOR

        r2_avg = (res_line.r_squared + sup_line.r_squared) / 2
        confidence = self._confidence_base(r2_avg)
        if vol_confirmed:
            confidence = min(confidence + 12, 92)

        return PatternResult(
            pattern_type=PatternType.FLAG_BEARISH,
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
            start_date=self._date_str(pole["start_idx"]),
            end_date=self._date_str(-1),
            candles_analyzed=self.n,
            raw_notes=f"Pole: {pole['pole_pct']*100:.1f}%, Retracement: {retracement*100:.1f}%",
        )


@PatternRegistry.register(PatternType.PENNANT)
class PennantDetector(FlagPennantBase):
    """
    Pennant: pole followed by converging symmetrical triangle consolidation.
    Breakout direction matches the pole direction.
    """
    pattern_type = PatternType.PENNANT

    def detect(self) -> Optional[PatternResult]:
        if not self.has_enough_data():
            return None
        pole = self._detect_pole()
        if not pole:
            return None
        body_df = self._flag_body_df(pole["end_idx"])
        if body_df is None or len(body_df) < FLAG_BODY_MIN_CANDLES:
            return None

        body_highs = body_df["high"].to_numpy()
        body_lows = body_df["low"].to_numpy()
        body_x = np.arange(len(body_df), dtype=float)

        res_line = build_trendline(body_x, body_highs)
        sup_line = build_trendline(body_x, body_lows)

        # Pennant: converging (res declines, sup rises)
        converging = res_line.slope < 0 and sup_line.slope > 0
        early_gap = abs(
            (res_line.intercept) - (sup_line.intercept)
        )
        late_gap = abs(
            (res_line.intercept + res_line.slope * body_x[-1]) -
            (sup_line.intercept + sup_line.slope * body_x[-1])
        )
        actually_converging = late_gap < early_gap * 0.75

        if not (converging and actually_converging):
            return None

        trend_dir = TrendDirection.BULLISH if pole["direction"] == "UP" else TrendDirection.BEARISH
        if pole["direction"] == "UP":
            breakout_level = float(res_line.intercept + res_line.slope * body_x[-1])
            trade_dir = "UP"
        else:
            breakout_level = float(sup_line.intercept + sup_line.slope * body_x[-1])
            trade_dir = "DOWN"

        vol_surge = volume_surge_factor(self.volumes)
        r2_avg = (res_line.r_squared + sup_line.r_squared) / 2
        confidence = self._confidence_base(r2_avg)
        if vol_surge >= settings.BREAKOUT_VOLUME_FACTOR:
            confidence = min(confidence + 10, 90)

        return PatternResult(
            pattern_type=PatternType.PENNANT,
            trend_direction=trend_dir,
            confidence_score=round(confidence, 1),
            breakout_level=breakout_level,
            support_line=sup_line,
            resistance_line=res_line,
            slope_support=sup_line.slope,
            slope_resistance=res_line.slope,
            volatility_estimate=self._volatility_estimate(),
            volume_confirmation=round(vol_surge, 2),
            volume_confirmed=vol_surge >= settings.BREAKOUT_VOLUME_FACTOR,
            start_date=self._date_str(pole["start_idx"]),
            end_date=self._date_str(-1),
            candles_analyzed=self.n,
            raw_notes=f"Pole {pole['direction']} {pole['pole_pct']*100:.1f}%",
        )
