import logging
import os
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


IS_VERCEL = os.getenv("VERCEL") is not None


@asynccontextmanager
async def lifespan(app: FastAPI):
    from db.database import init_db
    init_db()

    # Vercel serverless functions can't host long-running background jobs
    # or persistent WebSocket connections — only start these off-Vercel.
    if not IS_VERCEL:
        from scheduler.job_manager import start_scheduler
        start_scheduler()
    yield
    if not IS_VERCEL:
        from scheduler.job_manager import stop_scheduler
        stop_scheduler()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Stock Pattern Engine API — V2 live screener",
    lifespan=lifespan,
)

# Wildcard origins can't be combined with allow_credentials=True (cookies) —
# list real origins in CORS_ALLOWED_ORIGINS (add your Vercel domain there).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ALLOWED_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register all API routes at import time so FastAPI builds the routing table
from api.endpoints import upload, analyze, report, template, auth
from api.endpoints import watchlist, quick_analyze, ai_insights, newsletter_admin, sectors
from fastapi import APIRouter

api_router = APIRouter()
api_router.include_router(auth.router,          tags=["Auth"])
api_router.include_router(template.router,      tags=["Template"])
api_router.include_router(upload.router,        tags=["Upload"])
api_router.include_router(analyze.router,       tags=["Analysis"])
api_router.include_router(quick_analyze.router, tags=["Quick Analyze"])
api_router.include_router(report.router,        tags=["Reports"])
api_router.include_router(watchlist.router,     tags=["Watchlist"])
api_router.include_router(ai_insights.router,   tags=["AI Insights"])
api_router.include_router(newsletter_admin.router, tags=["Admin Newsletter"])
api_router.include_router(sectors.router,       tags=["Sectors"])

# WebSocket + scheduled refresh require a persistent process — not available on Vercel
if not IS_VERCEL:
    from api.endpoints import ws
    api_router.include_router(ws.router, tags=["Live"])

app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health():
    payload = {"status": "ok", "version": settings.APP_VERSION}
    if not IS_VERCEL:
        from scheduler.price_fetcher import is_market_open
        payload["market_open"] = is_market_open()
    return payload


@app.get("/", response_class=FileResponse)
async def serve_ui():
    return FileResponse(_frontend / "index.html")
