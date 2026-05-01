"""
Regression and curve-fitting utilities.
All pattern detectors depend on these mathematical primitives.
"""

import numpy as np
from scipy import stats
from scipy.optimize import curve_fit
from typing import Tuple, List, Optional
from models.schemas import TrendLine, RegressionResult


# ─── Linear Regression ───────────────────────────────────────────────────────

def linear_regression(x: np.ndarray, y: np.ndarray) -> Tuple[float, float, float]:
    """
    Fit y = mx + b via OLS.
    Returns (slope, intercept, r_squared).
    """
    if len(x) < 2:
        return 0.0, float(y[0]) if len(y) else 0.0, 0.0
    slope, intercept, r_value, _, _ = stats.linregress(x.astype(float), y.astype(float))
    return float(slope), float(intercept), float(r_value ** 2)


def build_trendline(x: np.ndarray, y: np.ndarray, label: str = "") -> TrendLine:
    """
    Fit a linear trendline and return a TrendLine schema.
    x = integer index array, y = price array (highs or lows).
    """
    slope, intercept, r2 = linear_regression(x, y)
    start_price = float(intercept + slope * x[0])
    end_price = float(intercept + slope * x[-1])
    if abs(slope) < 1e-4:
        direction = "flat"
    elif slope > 0:
        direction = "ascending"
    else:
        direction = "descending"
    return TrendLine(
        slope=slope,
        intercept=intercept,
        r_squared=r2,
        start_price=start_price,
        end_price=end_price,
        direction=direction,
    )


# ─── Polynomial Regression ───────────────────────────────────────────────────

def polynomial_regression(
    x: np.ndarray, y: np.ndarray, degree: int = 2
) -> RegressionResult:
    """
    Fit y = a₀ + a₁x + a₂x² + … via numpy polyfit.
    Degree 2 is used for cup/rounded bottom detection.
    """
    x_f = x.astype(float)
    y_f = y.astype(float)
    coeffs = np.polyfit(x_f, y_f, degree)
    y_pred = np.polyval(coeffs, x_f)
    ss_res = np.sum((y_f - y_pred) ** 2)
    ss_tot = np.sum((y_f - np.mean(y_f)) ** 2)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    residual_std = float(np.std(y_f - y_pred))
    return RegressionResult(
        model_type="polynomial",
        coefficients=coeffs.tolist(),
        r_squared=float(r2),
        residual_std=residual_std,
    )


def is_concave_up(coeffs: List[float]) -> bool:
    """
    For a degree-2 polynomial ax² + bx + c, concave-up means a > 0.
    Used to confirm U-shaped (cup) patterns.
    """
    if len(coeffs) < 3:
        return False
    return float(coeffs[0]) > 0


# ─── Exponential Regression ──────────────────────────────────────────────────

def exponential_regression(
    x: np.ndarray, y: np.ndarray
) -> Tuple[float, float, float]:
    """
    Fit y = a * e^(b*x) by linearizing: ln(y) = ln(a) + b*x.
    Returns (a, b, r_squared). b > 0 means exponential growth.
    Skips if any y <= 0.
    """
    x_f = x.astype(float)
    y_f = y.astype(float)
    if np.any(y_f <= 0):
        return 1.0, 0.0, 0.0
    log_y = np.log(y_f)
    b, log_a, r_value, _, _ = stats.linregress(x_f, log_y)
    a = float(np.exp(log_a))
    return a, float(b), float(r_value ** 2)


# ─── Slope & Derivative Utilities ────────────────────────────────────────────

def compute_slope_angle(slope: float, price_scale: float = 1.0) -> float:
    """Convert slope to degrees for human-readable steepness."""
    normalized = slope / max(price_scale, 1e-9)
    return float(np.degrees(np.arctan(normalized)))


def first_derivative(y: np.ndarray) -> np.ndarray:
    """Numerical first derivative (dy/dx) using numpy gradient."""
    return np.gradient(y.astype(float))


def second_derivative(y: np.ndarray) -> np.ndarray:
    """Numerical second derivative (d²y/dx²)."""
    return np.gradient(first_derivative(y))


def slope_consistency(slopes: np.ndarray, tolerance: float = 0.02) -> float:
    """
    Returns a consistency score [0,1].
    High score → slopes are consistently in the same direction.
    Used to validate clean trendlines.
    """
    if len(slopes) == 0:
        return 0.0
    positive = float(np.sum(slopes > tolerance))
    negative = float(np.sum(slopes < -tolerance))
    neutral = float(np.sum(np.abs(slopes) <= tolerance))
    dominant = max(positive, negative, neutral)
    return dominant / len(slopes)


# ─── Support / Resistance Detection ─────────────────────────────────────────

def detect_pivot_highs(
    highs: np.ndarray, window: int = 3
) -> np.ndarray:
    """
    Returns indices of local pivot highs within a rolling window.
    A pivot high at index i satisfies: highs[i] == max(highs[i-w:i+w+1]).
    """
    indices = []
    for i in range(window, len(highs) - window):
        if highs[i] == np.max(highs[i - window: i + window + 1]):
            indices.append(i)
    return np.array(indices, dtype=int)


def detect_pivot_lows(
    lows: np.ndarray, window: int = 3
) -> np.ndarray:
    """Returns indices of local pivot lows."""
    indices = []
    for i in range(window, len(lows) - window):
        if lows[i] == np.min(lows[i - window: i + window + 1]):
            indices.append(i)
    return np.array(indices, dtype=int)


def price_channel_width(
    resistance_line: TrendLine,
    support_line: TrendLine,
    x_end: float,
) -> float:
    """Width between two trendlines at a given x position."""
    r_price = resistance_line.intercept + resistance_line.slope * x_end
    s_price = support_line.intercept + support_line.slope * x_end
    return abs(r_price - s_price)
