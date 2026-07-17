"""
POST /get_report

Returns or streams a downloadable report in JSON or CSV format.
"""

import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional
import io

from models.schemas import AnalysisResponse
from core.engine import run_analysis
from api.endpoints.upload import get_session_df
from reports.generator import to_json, to_csv_bytes
from auth.dependencies import get_current_user
from db.models import User

router = APIRouter()

# Simple in-memory result cache keyed by session_id
_result_cache: dict = {}


def store_result(session_id: str, result: AnalysisResponse):
    _result_cache[session_id] = result


def get_result(session_id: str) -> AnalysisResponse:
    result = _result_cache.get(session_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No analysis result for session '{session_id}'. Run /analyze first.",
        )
    return result


class ReportRequest(BaseModel):
    session_id: str
    format: str = "json"  # "json" or "csv"
    # If true, re-run analysis before generating report
    rerun: bool = False


@router.post("/get_report")
async def get_report(request: ReportRequest, user: User = Depends(get_current_user)):
    """
    Download the analysis report for a session.

    format=json → returns structured JSON (default)
    format=csv  → returns downloadable CSV file
    """
    if request.format not in ("json", "csv"):
        raise HTTPException(status_code=400, detail="format must be 'json' or 'csv'.")

    if request.rerun or request.session_id not in _result_cache:
        df = get_session_df(request.session_id)
        result = run_analysis(df=df, session_id=request.session_id)
        store_result(request.session_id, result)
    else:
        result = get_result(request.session_id)

    if request.format == "csv":
        csv_bytes = to_csv_bytes(result)
        return StreamingResponse(
            io.BytesIO(csv_bytes),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="report_{request.session_id}.csv"'
            },
        )

    return JSONResponse(content=json.loads(to_json(result)))


class PdfReportRequest(BaseModel):
    session_id: str
    rerun: bool = False


@router.post("/get_pdf_report", tags=["Reports"])
async def get_pdf_report(request: PdfReportRequest, user: User = Depends(get_current_user)):
    """
    Generate and download a full investor-grade PDF report.

    Includes:
    - Cover page with disclaimer
    - Executive summary table + charts
    - Per-ticker price, volume, indicator, and pattern overlay charts
    - Pattern education reference page

    Returns a downloadable PDF file.
    """
    from reports.pdf_report_generator import generate_pdf_report

    if request.rerun or request.session_id not in _result_cache:
        df_raw = get_session_df(request.session_id)
        result = run_analysis(df=df_raw, session_id=request.session_id)
        store_result(request.session_id, result)
    else:
        result = get_result(request.session_id)
        df_raw = get_session_df(request.session_id)

    # Split combined DataFrame into per-ticker dict
    dataframes: dict = {}
    if "ticker" in df_raw.columns:
        for ticker, grp in df_raw.groupby("ticker", sort=False):
            dataframes[str(ticker).upper()] = grp.reset_index(drop=True)
    else:
        # Fallback: use session_id as key
        dataframes[result.results[0].ticker if result.results else "UNKNOWN"] = df_raw

    try:
        pdf_bytes = generate_pdf_report(result, dataframes)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"PDF generation failed: {str(exc)}",
        )

    from datetime import datetime as _dt
    ts = _dt.now().strftime("%Y%m%d_%H%M%S")
    filename = f"StockPatternReport_{ts}.pdf"

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )
