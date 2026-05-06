"""
Main Orchestration Engine.

Coordinates:
  1. Preprocessing
  2. All pattern detectors (via PatternRegistry)
  3. Risk scoring
  4. Trade recommendation
  5. Optional future modules (Monte Carlo, RL, Game Theory, Bayesian)
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional
import pandas as pd
import numpy as np

from models.schemas import (
    TickerAnalysis, AnalysisResponse, PatternResult,
    MonteCarloConfig, QLearningConfig, GameTheoryConfig, BayesianConfig,
)
from models.enums import TrendDirection
from core.preprocessor import (
    split_by_ticker, fill_missing_atr, prepare_window, compute_derived_features
)
from patterns.base import PatternRegistry
from risk.scorer import compute_risk
from recommendations.trade_planner import build_trade_recommendation
from api.config import settings

# Import all detector modules to trigger @PatternRegistry.register decorators
import patterns.continuation.triangles    # noqa: F401
import patterns.continuation.flags        # noqa: F401
import patterns.reversal.head_and_shoulders  # noqa: F401
import patterns.reversal.double_triple    # noqa: F401
import patterns.other.cup_and_handle      # noqa: F401
import patterns.other.wedges              # noqa: F401
import patterns.other.rectangles          # noqa: F401

logger = logging.getLogger(__name__)


def run_analysis(
    df: pd.DataFrame,
    session_id: Optional[str] = None,
    monte_carlo_cfg: Optional[MonteCarloConfig] = None,
    q_learning_cfg: Optional[QLearningConfig] = None,
    game_theory_cfg: Optional[GameTheoryConfig] = None,
    bayesian_cfg: Optional[BayesianConfig] = None,
) -> AnalysisResponse:
    """
    Full analysis pipeline entry point.
    Takes a validated DataFrame, returns an AnalysisResponse.
    """
    if session_id is None:
        session_id = str(uuid.uuid4())

    timestamp = datetime.now(timezone.utc).isoformat()
    ticker_dfs = split_by_ticker(df)
    results: List[TickerAnalysis] = []

    for ticker, ticker_df in ticker_dfs.items():
        logger.info(f"[{session_id}] Analyzing {ticker} ({len(ticker_df)} rows)...")
        try:
            analysis = _analyze_ticker(
                ticker=ticker,
                df=ticker_df,
                monte_carlo_cfg=monte_carlo_cfg,
                q_learning_cfg=q_learning_cfg,
                game_theory_cfg=game_theory_cfg,
                bayesian_cfg=bayesian_cfg,
            )
            results.append(analysis)
        except Exception as e:
            logger.error(f"[{session_id}] Error analyzing {ticker}: {e}", exc_info=True)
            # Append a minimal error entry rather than crashing the whole job
            results.append(TickerAnalysis(
                ticker=ticker,
                analysis_timestamp=timestamp,
                timeframe_start="N/A",
                timeframe_end="N/A",
                total_candles=len(ticker_df),
                patterns_detected=[],
                current_price=0.0,
            ))

    summary_table = _build_summary_table(results)

    return AnalysisResponse(
        session_id=session_id,
        analysis_timestamp=timestamp,
        tickers_analyzed=len(results),
        results=results,
        summary_table=summary_table,
    )


def _analyze_ticker(
    ticker: str,
    df: pd.DataFrame,
    monte_carlo_cfg: Optional[MonteCarloConfig],
    q_learning_cfg: Optional[QLearningConfig],
    game_theory_cfg: Optional[GameTheoryConfig],
    bayesian_cfg: Optional[BayesianConfig],
) -> TickerAnalysis:
    timestamp = datetime.now(timezone.utc).isoformat()

    # ── Prepare ────────────────────────────────────────────────────────────────
    df = fill_missing_atr(df)
    df = compute_derived_features(df)
    analysis_df = prepare_window(df, window=settings.MAX_ROWS)

    current_price = float(analysis_df["close"].iloc[-1])
    current_rsi = _safe_last(analysis_df, "RSI")
    current_macd = _safe_last(analysis_df, "MACD")
    current_atr = _safe_last(analysis_df, "ATR")

    # ── Run All Registered Pattern Detectors ──────────────────────────────────
    patterns_detected: List[PatternResult] = []
    for detector_cls in PatternRegistry.all_detectors():
        try:
            detector = detector_cls(analysis_df)
            result = detector.detect()
            if result is not None and result.confidence_score >= settings.MIN_CONFIDENCE_SCORE:
                patterns_detected.append(result)
        except Exception as e:
            logger.warning(f"Detector {detector_cls.__name__} failed for {ticker}: {e}")

    # Sort by confidence descending
    patterns_detected.sort(key=lambda p: p.confidence_score, reverse=True)

    # ── Optional: Bayesian Confidence Update (Future Module) ──────────────────
    if settings.ENABLE_BAYESIAN and bayesian_cfg and bayesian_cfg.enabled:
        patterns_detected = _apply_bayesian_update(patterns_detected, bayesian_cfg)

    top_pattern: Optional[PatternResult] = patterns_detected[0] if patterns_detected else None

    # ── Risk Scoring ───────────────────────────────────────────────────────────
    risk = None
    trade_rec = None
    if top_pattern:
        volumes = analysis_df["volume"].to_numpy()
        risk = compute_risk(
            pattern=top_pattern,
            current_price=current_price,
            atr=current_atr,
            rsi=current_rsi,
            macd=current_macd,
            volumes=volumes,
        )
        trade_rec = build_trade_recommendation(
            pattern=top_pattern,
            risk=risk,
            current_price=current_price,
            atr=current_atr,
        )

    # ── Optional: Monte Carlo Paths (Future Module) ───────────────────────────
    if settings.ENABLE_MONTE_CARLO and monte_carlo_cfg and monte_carlo_cfg.enabled:
        _run_monte_carlo(top_pattern, current_price, monte_carlo_cfg)

    # ── Optional: Q-Learning Agent Action (Future Module) ─────────────────────
    if settings.ENABLE_Q_LEARNING and q_learning_cfg and q_learning_cfg.enabled:
        _run_q_learning(analysis_df, q_learning_cfg)

    # ── Optional: Game Theory Market Model (Future Module) ───────────────────
    if settings.ENABLE_GAME_THEORY and game_theory_cfg and game_theory_cfg.enabled:
        _run_game_theory(top_pattern, game_theory_cfg)

    timeframe_start = str(analysis_df["date"].iloc[0]) if "date" in analysis_df.columns else "N/A"
    timeframe_end = str(analysis_df["date"].iloc[-1]) if "date" in analysis_df.columns else "N/A"

    return TickerAnalysis(
        ticker=ticker,
        analysis_timestamp=timestamp,
        timeframe_start=timeframe_start,
        timeframe_end=timeframe_end,
        total_candles=len(analysis_df),
        patterns_detected=patterns_detected,
        top_pattern=top_pattern,
        risk_assessment=risk,
        trade_recommendation=trade_rec,
        current_price=current_price,
        current_rsi=current_rsi,
        current_macd=current_macd,
    )


def _safe_last(df: pd.DataFrame, col: str) -> Optional[float]:
    if col in df.columns:
        val = df[col].iloc[-1]
        return float(val) if pd.notna(val) else None
    return None


def _build_summary_table(results: List[TickerAnalysis]) -> List[Dict]:
    rows = []
    for r in results:
        tp = r.top_pattern
        rk = r.risk_assessment
        tr = r.trade_recommendation
        rows.append({
            "ticker": r.ticker,
            "current_price": r.current_price,
            "patterns_found": len(r.patterns_detected),
            "top_pattern": tp.pattern_type.value if tp else "NONE",
            "confidence": tp.confidence_score if tp else 0,
            "trend_direction": tp.trend_direction.value if tp else "N/A",
            "breakout_level": tp.breakout_level if tp else None,
            "signal": tr.signal.value if tr else "WATCH",
            "entry": tr.entry_price if tr else None,
            "stop_loss": tr.stop_loss if tr else None,
            "take_profit_1": tr.take_profit_1 if tr else None,
            "risk_score": rk.risk_score.value if rk else "N/A",
            "risk_numeric": rk.risk_numeric if rk else None,
            "expected_upside_pct": rk.expected_upside_pct if rk else None,
            "holding_time": rk.holding_time.value if rk else "N/A",
            "rsi": r.current_rsi,
            "macd": r.current_macd,
        })
    return rows


# ─── Future Module Stubs ──────────────────────────────────────────────────────
# These are architectural placeholders. Each will become a full module later.

def _apply_bayesian_update(
    patterns: List[PatternResult],
    cfg: BayesianConfig,
) -> List[PatternResult]:
    """
    FUTURE: Update confidence scores using Bayesian inference.
    Prior = historical pattern success rates by type.
    Likelihood = current indicator alignment.
    Posterior = updated confidence.

    Plug-in contract:
      Input:  List[PatternResult], BayesianConfig
      Output: List[PatternResult] with updated confidence_score fields
    """
    logger.info("Bayesian updater stub called — module not yet implemented.")
    return patterns


def _run_monte_carlo(
    pattern: Optional[PatternResult],
    current_price: float,
    cfg: MonteCarloConfig,
) -> Dict:
    """
    FUTURE: Simulate N price paths using geometric Brownian motion (or jump-diffusion).
    Returns percentile price paths for the given time horizon.

    Plug-in contract:
      Input:  PatternResult (for drift + vol), current_price, MonteCarloConfig
      Output: Dict { 'paths': np.ndarray, 'percentiles': Dict[float, np.ndarray] }
    """
    logger.info("Monte Carlo stub called — module not yet implemented.")
    return {}


def _run_q_learning(
    df: pd.DataFrame,
    cfg: QLearningConfig,
) -> str:
    """
    FUTURE: Load a trained Q-table or DQN, build the state vector from
    current indicators, and return the optimal action (BUY/SELL/HOLD).

    Plug-in contract:
      Input:  latest OHLCV + indicator row as state, QLearningConfig (model_path)
      Output: action string
    """
    logger.info("Q-learning stub called — module not yet implemented.")
    return "HOLD"


def _run_game_theory(
    pattern: Optional[PatternResult],
    cfg: GameTheoryConfig,
) -> Dict:
    """
    FUTURE: Model the market as a multi-player game (market makers, retailers,
    institutions). Compute Nash equilibrium strategies and expected payoffs
    given the current pattern context.

    Plug-in contract:
      Input:  PatternResult (for breakout level, direction), GameTheoryConfig
      Output: Dict { 'dominant_strategy': str, 'expected_payoff': float }
    """
    logger.info("Game theory stub called — module not yet implemented.")
    return {}
