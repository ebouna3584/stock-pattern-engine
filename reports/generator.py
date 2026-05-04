"""
Report Generator.

Produces:
  - JSON object (direct AnalysisResponse serialization)
  - Flat CSV report (summary table + per-pattern details)
"""

import os
import csv
import json
import uuid
import io
from datetime import datetime
from typing import Optional
from models.schemas import AnalysisResponse
from stock_pattern_engine.api.config import settings


def to_json(response: AnalysisResponse, indent: int = 2) -> str:
    """Serialize AnalysisResponse to a pretty-printed JSON string."""
    return response.model_dump_json(indent=indent)


def to_csv_bytes(response: AnalysisResponse) -> bytes:
    """
    Generate a flat CSV report from the analysis response.
    Each row = one detected pattern for one ticker.
    """
    output = io.StringIO()
    fieldnames = [
        "session_id",
        "analysis_timestamp",
        "ticker",
        "timeframe_start",
        "timeframe_end",
        "current_price",
        "current_rsi",
        "current_macd",
        "pattern_type",
        "trend_direction",
        "confidence_score",
        "breakout_level",
        "slope_support",
        "slope_resistance",
        "volatility_estimate",
        "volume_confirmation",
        "volume_confirmed",
        "signal",
        "entry_price",
        "stop_loss",
        "take_profit_1",
        "take_profit_2",
        "take_profit_3",
        "risk_reward_ratio",
        "position_size_pct",
        "risk_score",
        "risk_numeric",
        "false_breakout_probability",
        "expected_upside_pct",
        "expected_downside_pct",
        "holding_time",
        "summary_explanation",
        "disclaimer",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()

    for ticker_result in response.results:
        tr = ticker_result.trade_recommendation
        rk = ticker_result.risk_assessment

        for pattern in ticker_result.patterns_detected:
            row = {
                "session_id": response.session_id,
                "analysis_timestamp": response.analysis_timestamp,
                "ticker": ticker_result.ticker,
                "timeframe_start": ticker_result.timeframe_start,
                "timeframe_end": ticker_result.timeframe_end,
                "current_price": ticker_result.current_price,
                "current_rsi": ticker_result.current_rsi,
                "current_macd": ticker_result.current_macd,
                "pattern_type": pattern.pattern_type.value,
                "trend_direction": pattern.trend_direction.value,
                "confidence_score": pattern.confidence_score,
                "breakout_level": pattern.breakout_level,
                "slope_support": pattern.slope_support,
                "slope_resistance": pattern.slope_resistance,
                "volatility_estimate": pattern.volatility_estimate,
                "volume_confirmation": pattern.volume_confirmation,
                "volume_confirmed": pattern.volume_confirmed,
                # Trade recommendation columns (only on top pattern)
                "signal": tr.signal.value if tr and pattern == ticker_result.top_pattern else "N/A",
                "entry_price": tr.entry_price if tr and pattern == ticker_result.top_pattern else "",
                "stop_loss": tr.stop_loss if tr and pattern == ticker_result.top_pattern else "",
                "take_profit_1": tr.take_profit_1 if tr and pattern == ticker_result.top_pattern else "",
                "take_profit_2": tr.take_profit_2 if tr and pattern == ticker_result.top_pattern else "",
                "take_profit_3": tr.take_profit_3 if tr and pattern == ticker_result.top_pattern else "",
                "risk_reward_ratio": tr.risk_reward_ratio if tr and pattern == ticker_result.top_pattern else "",
                "position_size_pct": tr.position_size_pct if tr and pattern == ticker_result.top_pattern else "",
                # Risk columns (only on top pattern)
                "risk_score": rk.risk_score.value if rk and pattern == ticker_result.top_pattern else "",
                "risk_numeric": rk.risk_numeric if rk and pattern == ticker_result.top_pattern else "",
                "false_breakout_probability": rk.false_breakout_probability if rk and pattern == ticker_result.top_pattern else "",
                "expected_upside_pct": rk.expected_upside_pct if rk and pattern == ticker_result.top_pattern else "",
                "expected_downside_pct": rk.expected_downside_pct if rk and pattern == ticker_result.top_pattern else "",
                "holding_time": rk.holding_time.value if rk and pattern == ticker_result.top_pattern else "",
                "summary_explanation": tr.summary_explanation if tr and pattern == ticker_result.top_pattern else "",
                "disclaimer": ticker_result.disclaimer,
            }
            writer.writerow(row)

    return output.getvalue().encode("utf-8")


def save_report(response: AnalysisResponse, fmt: str = "json") -> str:
    """
    Save report to disk and return the file path.
    Used by the /get_report endpoint.
    """
    os.makedirs(settings.REPORT_DIR, exist_ok=True)
    filename = f"{response.session_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.{fmt}"
    filepath = os.path.join(settings.REPORT_DIR, filename)

    if fmt == "json":
        with open(filepath, "w") as f:
            f.write(to_json(response))
    elif fmt == "csv":
        with open(filepath, "wb") as f:
            f.write(to_csv_bytes(response))
    else:
        raise ValueError(f"Unsupported format: {fmt}")

    return filepath
