from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import List, Optional, Dict, Any
from datetime import datetime
from models.enums import (
    PatternType, TrendDirection, TradeSignal,
    RiskLevel, HoldingTime, ValidationStatus
)


# ─── CSV Validation ────────────────────────────────────────────────────────────

class ValidationResult(BaseModel):
    status: ValidationStatus
    row_count: int
    ticker: str
    errors: List[str] = []
    warnings: List[str] = []
    detected_columns: List[str] = []


# ─── Regression / Math Models ─────────────────────────────────────────────────

class TrendLine(BaseModel):
    slope: float
    intercept: float
    r_squared: float
    start_price: float
    end_price: float
    direction: str  # "ascending" | "descending" | "flat"


class RegressionResult(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    model_type: str        # "linear" | "polynomial" | "exponential"
    coefficients: List[float]
    r_squared: float
    residual_std: float


# ─── Pattern Detection ────────────────────────────────────────────────────────

class PatternResult(BaseModel):
    pattern_type: PatternType
    trend_direction: TrendDirection
    confidence_score: float = Field(..., ge=0, le=100)
    breakout_level: float
    support_line: TrendLine
    resistance_line: TrendLine
    slope_support: float
    slope_resistance: float
    volatility_estimate: float
    volume_confirmation: float     # ratio of breakout volume to avg volume
    volume_confirmed: bool
    start_date: str
    end_date: str
    candles_analyzed: int
    regression: Optional[RegressionResult] = None
    raw_notes: Optional[str] = None


# ─── Risk Assessment ──────────────────────────────────────────────────────────

class RiskAssessment(BaseModel):
    risk_score: RiskLevel
    risk_numeric: float = Field(..., ge=0, le=100)
    slope_risk: float
    volatility_risk: float
    breakout_distance_risk: float
    rsi_confirmation: float
    macd_confirmation: float
    volume_surge_factor: float
    false_breakout_probability: float
    expected_upside_pct: float
    expected_downside_pct: float
    holding_time: HoldingTime


# ─── Trade Recommendation ─────────────────────────────────────────────────────

class TradeRecommendation(BaseModel):
    signal: TradeSignal
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    take_profit_3: float
    risk_reward_ratio: float
    position_size_pct: float       # % of portfolio based on risk
    atr_used: float
    confidence_adjusted_signal: str
    summary_explanation: str


# ─── Full Analysis Result ─────────────────────────────────────────────────────

class TickerAnalysis(BaseModel):
    ticker: str
    analysis_timestamp: str
    timeframe_start: str
    timeframe_end: str
    total_candles: int
    patterns_detected: List[PatternResult]
    top_pattern: Optional[PatternResult] = None
    risk_assessment: Optional[RiskAssessment] = None
    trade_recommendation: Optional[TradeRecommendation] = None
    current_price: float
    current_rsi: Optional[float] = None
    current_macd: Optional[float] = None
    disclaimer: str = (
        "This output is probabilistic technical analysis only. "
        "It does not guarantee profit. Past patterns do not guarantee future results. "
        "Always apply independent risk management before executing any trade."
    )


class AnalysisResponse(BaseModel):
    session_id: str
    analysis_timestamp: str
    tickers_analyzed: int
    results: List[TickerAnalysis]
    summary_table: List[Dict[str, Any]]


# ─── API Request/Response Wrappers ────────────────────────────────────────────

class UploadResponse(BaseModel):
    session_id: str
    validation: ValidationResult
    message: str


class ReportRequest(BaseModel):
    session_id: str
    format: str = "json"  # "json" | "csv"


# ─── Future Module Hooks (plug-in interfaces) ─────────────────────────────────

class MonteCarloConfig(BaseModel):
    """Plug-in config for Monte Carlo simulation module (future)."""
    num_simulations: int = 10000
    time_horizon_days: int = 30
    confidence_intervals: List[float] = [0.05, 0.25, 0.75, 0.95]
    enabled: bool = False


class QLearningConfig(BaseModel):
    """Plug-in config for Q-learning reinforcement agent (future)."""
    model_config = ConfigDict(protected_namespaces=())
    model_path: Optional[str] = None
    state_features: List[str] = []
    enabled: bool = False


class GameTheoryConfig(BaseModel):
    """Plug-in config for game-theory market behavior module (future)."""
    strategy: str = "nash_equilibrium"
    enabled: bool = False


class BayesianConfig(BaseModel):
    """Plug-in config for Bayesian confidence updater (future)."""
    prior_distribution: str = "uniform"
    enabled: bool = False
