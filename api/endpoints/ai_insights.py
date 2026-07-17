"""
AI Insights endpoint — on-demand Claude-powered trade thesis + curated news.
Cached per-ticker (see AI_INSIGHT_CACHE_TTL_SEC) to control API spend.

POST /api/v1/ai/insight
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from scheduler.price_fetcher import fetch_history
from core.engine import run_analysis
from ai.insights import build_insight
from auth.dependencies import get_current_user
from db.models import User

logger = logging.getLogger(__name__)
router = APIRouter()


class InsightRequest(BaseModel):
    ticker: str
    force_refresh: bool = False


@router.post("/ai/insight")
async def ai_insight(req: InsightRequest, user: User = Depends(get_current_user)):
    ticker = req.ticker.upper().strip()

    df = fetch_history(ticker, period="3mo")
    if df is None or len(df) < 20:
        raise HTTPException(status_code=422, detail=f"No usable data for '{ticker}'.")

    technicals = {
        "pattern": "—", "signal": "WATCH", "confidence": None,
        "rsi": None, "macd": None, "risk": "—",
    }
    try:
        analysis = run_analysis(df=df.copy())
        ta = next((r for r in analysis.results if r.ticker == ticker), None)
        if ta:
            tp, tr, rk = ta.top_pattern, ta.trade_recommendation, ta.risk_assessment
            technicals.update({
                "pattern":    tp.pattern_type.value.replace("_", " ").title() if tp else "—",
                "confidence": round(tp.confidence_score, 1) if tp else None,
                "signal":     tr.signal.value if tr else "WATCH",
                "rsi":        ta.current_rsi,
                "macd":       ta.current_macd,
                "risk":       rk.risk_score.value if rk else "—",
            })
    except Exception as exc:
        logger.warning(f"{ticker}: technical analysis failed, proceeding with news-only insight: {exc}")

    return build_insight(ticker, technicals, force_refresh=req.force_refresh)
