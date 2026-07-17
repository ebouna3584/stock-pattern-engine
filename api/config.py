from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional


class Settings(BaseSettings):
    APP_NAME: str = "Stock Pattern Engine"
    APP_VERSION: str = "1.0.0-mvp"
    DEBUG: bool = False

    # AI insights — on-demand trade thesis synthesis + news curation.
    # Left unset, the AI insight endpoint degrades gracefully (articles only, no thesis).
    ANTHROPIC_API_KEY: Optional[str] = None
    NEWS_API_KEY: Optional[str] = None
    AI_INSIGHT_CACHE_TTL_SEC: int = 1200  # 20 min — controls Anthropic/NewsAPI spend

    # Accounts — defaults to local SQLite; point DATABASE_URL at hosted Postgres
    # (Neon/Supabase/etc.) before deploying, since SQLite won't reliably persist
    # on Vercel's serverless filesystem.
    DATABASE_URL: str = "sqlite:///./app.db"
    JWT_SECRET_KEY: str = "dev-only-insecure-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 14  # 14 days

    # Email — verification links + the weekly newsletter. Left unset, emails are
    # logged instead of sent (safe no-op for local dev without a Resend account).
    RESEND_API_KEY: Optional[str] = None
    FROM_EMAIL: str = "onboarding@resend.dev"
    APP_BASE_URL: str = "http://localhost:8000"

    # Only this email can approve/send the newsletter or reach admin endpoints.
    ADMIN_EMAIL: str = "elizabethbounaaly@gmail.com"

    # CORS — comma-separated list; wildcard "*" can't be combined with
    # allow_credentials=True (cookies), so list real origins here once deployed.
    CORS_ALLOWED_ORIGINS: str = "http://localhost:8000,http://127.0.0.1:8000"

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
