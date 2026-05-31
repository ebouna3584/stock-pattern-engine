import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from api.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

_frontend = Path(__file__).parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup: scheduler only (routes already registered at import time) ────
    from scheduler.job_manager import start_scheduler
    start_scheduler()
    yield
    # ── Shutdown ──────────────────────────────────────────────────────────────
    from scheduler.job_manager import stop_scheduler
    stop_scheduler()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Stock Pattern Engine API — V2 live screener",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register all API routes at import time so FastAPI builds the routing table
from api.endpoints import upload, analyze, report, template
from api.endpoints import watchlist, ws, quick_analyze
from fastapi import APIRouter

api_router = APIRouter()
api_router.include_router(template.router,      tags=["Template"])
api_router.include_router(upload.router,        tags=["Upload"])
api_router.include_router(analyze.router,       tags=["Analysis"])
api_router.include_router(quick_analyze.router, tags=["Quick Analyze"])
api_router.include_router(report.router,        tags=["Reports"])
api_router.include_router(watchlist.router,     tags=["Watchlist"])
api_router.include_router(ws.router,            tags=["Live"])

app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health():
    from scheduler.price_fetcher import is_market_open
    return {
        "status":      "ok",
        "version":     settings.APP_VERSION,
        "market_open": is_market_open(),
    }


@app.get("/", response_class=FileResponse)
async def serve_ui():
    return FileResponse(_frontend / "index.html")
