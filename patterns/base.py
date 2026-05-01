"""
Abstract base class for all pattern detectors.
Every pattern module subclasses BasePatternDetector and
implements the detect() method.
"""

from abc import ABC, abstractmethod
from typing import Optional, List
import numpy as np
import pandas as pd
from models.schemas import PatternResult
from models.enums import PatternType, TrendDirection


class BasePatternDetector(ABC):
    """
    Contract all pattern detectors must satisfy.
    Subclasses override detect() and optionally _score().
    """

    MIN_CANDLES: int = 20        # Minimum candles required to attempt detection
    IDEAL_CANDLES: int = 50      # Preferred window for clean patterns
    pattern_type: PatternType    # Must be set by subclass

    def __init__(self, df: pd.DataFrame) -> None:
        """
        df must have at minimum: open, high, low, close, volume (lowercase).
        Optional indicator columns are accessed safely via df.get().
        """
        self.df = df.copy()
        self.closes = df["close"].to_numpy()
        self.highs = df["high"].to_numpy()
        self.lows = df["low"].to_numpy()
        self.opens = df["open"].to_numpy()
        self.volumes = df["volume"].to_numpy()
        self.x = np.arange(len(df), dtype=float)
        self.n = len(df)

    @abstractmethod
    def detect(self) -> Optional[PatternResult]:
        """
        Attempt to detect the pattern in self.df.
        Returns PatternResult if found, else None.
        """
        ...

    def _safe_get(self, col: str, idx: int = -1) -> Optional[float]:
        """Safely retrieve a column value from the dataframe."""
        if col in self.df.columns:
            val = self.df[col].iloc[idx]
            return float(val) if pd.notna(val) else None
        return None

    def _rsi(self) -> Optional[float]:
        return self._safe_get("RSI")

    def _macd(self) -> Optional[float]:
        return self._safe_get("MACD")

    def _atr(self) -> Optional[float]:
        return self._safe_get("ATR")

    def _date_str(self, idx: int) -> str:
        if "date" in self.df.columns:
            return str(self.df["date"].iloc[idx])
        return str(idx)

    def _volatility_estimate(self) -> float:
        """Annualized close-to-close volatility over the window."""
        if self.n < 2:
            return 0.0
        returns = np.diff(np.log(self.closes.astype(float) + 1e-9))
        return float(np.std(returns) * np.sqrt(252))

    def _avg_volume(self, lookback: int = 20) -> float:
        return float(np.mean(self.volumes[-lookback:]))

    def _confidence_base(self, r_squared: float) -> float:
        """
        Base confidence from regression fit quality.
        R² → [30, 80] range; further boosted by volume and indicators.
        """
        return float(np.clip(30 + r_squared * 50, 30, 80))

    def has_enough_data(self) -> bool:
        return self.n >= self.MIN_CANDLES


class PatternRegistry:
    """
    Registry of all available detectors.
    Used by the engine to run all detectors against a dataframe.
    Supports future plug-in detectors added at runtime.
    """
    _registry: dict = {}

    @classmethod
    def register(cls, pattern_type: PatternType):
        """Decorator to register a detector class."""
        def decorator(klass):
            cls._registry[pattern_type] = klass
            return klass
        return decorator

    @classmethod
    def all_detectors(cls) -> List[type]:
        return list(cls._registry.values())

    @classmethod
    def get(cls, pattern_type: PatternType):
        return cls._registry.get(pattern_type)
