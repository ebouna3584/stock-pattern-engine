"""
CSV Template Validator.

Enforces the required column structure and data quality rules.
Rejects malformed uploads with clear, actionable error messages.
"""

import io
import pandas as pd
import numpy as np
from typing import Tuple
from models.schemas import ValidationResult
from models.enums import ValidationStatus
from config import settings


# Required columns every valid CSV must contain
REQUIRED_COLUMNS = {
    "ticker", "date", "open", "high", "low", "close", "volume"
}

# Optional indicator columns (ignored safely if absent)
OPTIONAL_COLUMNS = {
    "RSI", "MACD", "EMA_20", "EMA_50", "SMA_200",
    "Bollinger_upper", "Bollinger_lower", "ATR",
}

# Numeric columns that must not contain non-numeric values
NUMERIC_COLUMNS = {
    "open", "high", "low", "close", "volume",
    "RSI", "MACD", "EMA_20", "EMA_50", "SMA_200",
    "Bollinger_upper", "Bollinger_lower", "ATR",
}


def validate_csv(file_bytes: bytes) -> Tuple[ValidationResult, pd.DataFrame]:
    """
    Full pipeline validation.
    Returns (ValidationResult, parsed DataFrame).
    On failure, DataFrame may be empty.
    """
    errors = []
    warnings = []

    # ── Parse ────────────────────────────────────────────────────────────────
    try:
        df = pd.read_csv(io.BytesIO(file_bytes))
    except Exception as e:
        return ValidationResult(
            status=ValidationStatus.INVALID,
            row_count=0,
            ticker="UNKNOWN",
            errors=[f"Failed to parse CSV: {str(e)}"],
        ), pd.DataFrame()

    df.columns = [c.strip() for c in df.columns]

    # ── File Size Guard ───────────────────────────────────────────────────────
    size_mb = len(file_bytes) / (1024 * 1024)
    if size_mb > settings.MAX_UPLOAD_SIZE_MB:
        errors.append(f"File too large: {size_mb:.1f}MB (max {settings.MAX_UPLOAD_SIZE_MB}MB).")

    # ── Required Columns ─────────────────────────────────────────────────────
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        errors.append(f"Missing required columns: {sorted(missing)}. "
                      f"Please use the official template.")

    if errors:
        return ValidationResult(
            status=ValidationStatus.INVALID,
            row_count=len(df),
            ticker="UNKNOWN",
            errors=errors,
            detected_columns=list(df.columns),
        ), pd.DataFrame()

    # ── Row Count ─────────────────────────────────────────────────────────────
    if len(df) < settings.MIN_ROWS:
        errors.append(
            f"Too few rows: {len(df)} (minimum {settings.MIN_ROWS} required for pattern detection)."
        )
    if len(df) > settings.MAX_ROWS:
        warnings.append(
            f"Large dataset ({len(df)} rows). Only the last {settings.MAX_ROWS} rows will be analyzed."
        )
        df = df.tail(settings.MAX_ROWS).reset_index(drop=True)

    # ── Ticker Column ─────────────────────────────────────────────────────────
    if df["ticker"].nunique() > 1:
        warnings.append(
            f"Multiple tickers detected: {df['ticker'].unique().tolist()}. "
            "Each ticker will be analyzed separately."
        )
    ticker = str(df["ticker"].iloc[0]).strip().upper()

    # ── Date Column ───────────────────────────────────────────────────────────
    try:
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)
    except Exception:
        errors.append("Could not parse 'date' column. "
                      "Expected format: YYYY-MM-DD or MM/DD/YYYY.")

    # ── Numeric Columns ───────────────────────────────────────────────────────
    for col in NUMERIC_COLUMNS:
        if col not in df.columns:
            continue
        # Strip commas that Excel inserts when exporting formatted numbers to CSV
        # e.g. #,##0 format turns 57126363 → "57,126,363" which pandas can't parse
        cleaned = df[col].astype(str).str.replace(",", "", regex=False).str.strip()
        df[col] = pd.to_numeric(cleaned, errors="coerce")
        nan_pct = df[col].isna().mean()
        if nan_pct > 0.30:
            errors.append(
                f"Column '{col}' has {nan_pct*100:.0f}% missing values (max 30% allowed)."
            )
        elif nan_pct > 0:
            warnings.append(
                f"Column '{col}' has {nan_pct*100:.0f}% missing values — will be forward-filled."
            )
            df[col] = df[col].ffill().bfill()

    # ── OHLC Sanity ───────────────────────────────────────────────────────────
    bad_ohlc = df[
        (df["high"] < df["low"]) |
        (df["open"] > df["high"] * 1.5) |
        (df["close"] < 0)
    ]
    if len(bad_ohlc) > 0:
        errors.append(
            f"{len(bad_ohlc)} rows have invalid OHLC values "
            f"(e.g., high < low, negative close). "
            f"First bad row: {bad_ohlc.index[0]}."
        )

    # ── Volume ────────────────────────────────────────────────────────────────
    if (df["volume"] < 0).any():
        errors.append("Volume column contains negative values.")

    # ── Detect Optional Columns ───────────────────────────────────────────────
    present_optional = [c for c in OPTIONAL_COLUMNS if c in df.columns]
    if not present_optional:
        warnings.append(
            "No indicator columns (RSI, MACD, ATR, etc.) found. "
            "Risk scoring and signal confirmation will be reduced."
        )

    status = ValidationStatus.INVALID if errors else ValidationStatus.VALID

    return ValidationResult(
        status=status,
        row_count=len(df),
        ticker=ticker,
        errors=errors,
        warnings=warnings,
        detected_columns=list(df.columns),
    ), df
