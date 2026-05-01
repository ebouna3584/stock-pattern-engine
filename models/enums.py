from enum import Enum


class PatternType(str, Enum):
    # Continuation
    ASCENDING_TRIANGLE = "ascending_triangle"
    DESCENDING_TRIANGLE = "descending_triangle"
    SYMMETRICAL_TRIANGLE = "symmetrical_triangle"
    FLAG_BULLISH = "flag_bullish"
    FLAG_BEARISH = "flag_bearish"
    PENNANT = "pennant"

    # Reversal
    HEAD_AND_SHOULDERS = "head_and_shoulders"
    INVERSE_HEAD_AND_SHOULDERS = "inverse_head_and_shoulders"
    DOUBLE_TOP = "double_top"
    DOUBLE_BOTTOM = "double_bottom"
    TRIPLE_TOP = "triple_top"
    TRIPLE_BOTTOM = "triple_bottom"

    # Other
    CUP_AND_HANDLE = "cup_and_handle"
    RISING_WEDGE = "rising_wedge"
    FALLING_WEDGE = "falling_wedge"
    RECTANGLE_BULLISH = "rectangle_bullish"
    RECTANGLE_BEARISH = "rectangle_bearish"


class TrendDirection(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class TradeSignal(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    WATCH = "WATCH"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class HoldingTime(str, Enum):
    SHORT = "SHORT"    # 1–5 days
    MEDIUM = "MEDIUM"  # 1–4 weeks
    LONG = "LONG"      # 1–3 months


class ValidationStatus(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"
    WARNING = "WARNING"
