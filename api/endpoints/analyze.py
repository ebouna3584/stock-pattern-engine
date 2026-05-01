"""
POST /analyze

Runs the full pattern detection + risk + trade recommendation pipeline
against the uploaded CSV session.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from models.schemas import (
    AnalysisResponse,
    MonteCarloConfig, QLearningConfig, GameTheoryConfig, BayesianConfig,
)
from core.engine import run_analysis
from api.endpoints.upload import get_session_df

router = APIRouter()


class AnalyzeRequest(BaseModel):
    session_id: str
    monte_carlo: Optional[MonteCarloConfig] = None
    q_learning: Optional[QLearningConfig] = None
    game_theory: Optional[GameTheoryConfig] = None
    bayesian: Optional[BayesianConfig] = None


@router.post("/analyze", response_model=AnalysisResponse)
async def analyze(request: AnalyzeRequest) -> AnalysisResponse:
    """
    Run the full pattern detection pipeline on a previously uploaded CSV.

    - Detects all supported chart patterns (triangles, wedges, H&S, flags, etc.)
    - Scores each pattern for confidence
    - Produces risk assessment and actionable trade recommendation

    Returns structured JSON suitable for frontend rendering.

    **Disclaimer**: Results are probabilistic technical analysis only.
    Past patterns do not guarantee future results.
    """
    df = get_session_df(request.session_id)

    response = run_analysis(
        df=df,
        session_id=request.session_id,
        monte_carlo_cfg=request.monte_carlo,
        q_learning_cfg=request.q_learning,
        game_theory_cfg=request.game_theory,
        bayesian_cfg=request.bayesian,
    )

    return response
