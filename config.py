from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

from vscode.gliovex_opt import app


class Settings(BaseSettings):
    APP_NAME: str = "Stock Pattern Engine"
    APP_VERSION: str = "1.0.0-mvp"
    DEBUG: bool = False

    # Upload constraints
    MAX_UPLOAD_SIZE_MB: int = 10
    MAX_ROWS: int = 5000
    MIN_ROWS: int = 20  # Need enough data for pattern detection

    # Pattern detection thresholds
    MIN_CONFIDENCE_SCORE: float = 40.0
    SLOPE_TOLERANCE: float = 0.005       # Used to determine "flat" slopes
    SYMMETRY_TOLERANCE: float = 0.05     # Used for H&S shoulder symmetry
    BREAKOUT_VOLUME_FACTOR: float = 1.5  # Volume must be 1.5x average for confirmation

    # Risk scoring weights
    SLOPE_WEIGHT: float = 0.20
    VOLATILITY_WEIGHT: float = 0.25
    BREAKOUT_DISTANCE_WEIGHT: float = 0.20
    RSI_WEIGHT: float = 0.15
    MACD_WEIGHT: float = 0.10
    VOLUME_WEIGHT: float = 0.10

    # Trade defaults
    DEFAULT_RISK_REWARD_RATIO: float = 2.0
    DEFAULT_ATR_STOP_MULTIPLIER: float = 1.5
    DEFAULT_ATR_TARGET_MULTIPLIER: float = 3.0

    # Report settings
    REPORT_DIR: str = "/tmp/stock_reports"

    # Future: plug-in module flags (set True when modules are built)
    ENABLE_MONTE_CARLO: bool = False
    ENABLE_Q_LEARNING: bool = False
    ENABLE_GAME_THEORY: bool = False
    ENABLE_BAYESIAN: bool = False

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()

@app.get("/debug-imports")
def debug():
    import sys
    return {
        "python": sys.version,
        "path": sys.path,
    }