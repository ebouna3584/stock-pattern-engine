"""
Data Preprocessor.

Cleans and prepares DataFrame subsets for each ticker before
pattern detection runs.
"""

import pandas as pd
import numpy as np
from typing import Dict, List
from analysis.indicators import compute_atr_from_df


def split_by_ticker(df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """Split a multi-ticker DataFrame into per-ticker DataFrames."""
    return {
        ticker.upper(): group.reset_index(drop=True)
        for ticker, group in df.groupby("ticker", sort=False)
    }


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Lowercase all column names for internal consistency.
    User's CSV may have mixed-case optional columns.
    """
    col_map = {c: c.strip() for c in df.columns}
    df = df.rename(columns=col_map)
    return df


def fill_missing_atr(df: pd.DataFrame) -> pd.DataFrame:
    """Compute ATR from OHLC if the column is missing or fully null."""
    if "ATR" not in df.columns or df["ATR"].isna().all():
        df = df.copy()
        df["ATR"] = compute_atr_from_df(df, period=14)
    return df


def prepare_window(df: pd.DataFrame, window: int = 100) -> pd.DataFrame:
    """
    Return the most recent `window` rows for pattern analysis.
    Using a rolling window keeps compute costs bounded.
    """
    if len(df) > window:
        return df.tail(window).reset_index(drop=True)
    return df


def validate_price_continuity(df: pd.DataFrame, max_gap_days: int = 10) -> List[str]:
    """
    Check for large date gaps (weekends + holidays are fine; >10 days is suspicious).
    Returns list of warning strings.
    """
    warnings = []
    if "date" not in df.columns:
        return warnings
    dates = pd.to_datetime(df["date"]).sort_values()
    gaps = dates.diff().dt.days.dropna()
    large_gaps = gaps[gaps > max_gap_days]
    if len(large_gaps) > 0:
        warnings.append(
            f"{len(large_gaps)} date gap(s) > {max_gap_days} days detected. "
            "Results may be less reliable around gap boundaries."
        )
    return warnings


def compute_derived_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add convenience derived columns used across detectors.
    """
    df = df.copy()
    df["body_size"] = (df["close"] - df["open"]).abs()
    df["range_size"] = df["high"] - df["low"]
    df["close_pct_change"] = df["close"].pct_change().fillna(0)
    return df
