"""
Stock Pattern Engine — FastAPI Application Entry Point
======================================================

Run:
    uvicorn main:app --reload --host 0.0.0.0 --port 8000

API Docs:
    http://localhost:8000/docs    (Swagger UI)
    http://localhost:8000/redoc   (ReDoc)
"""

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.router import api_router
from api.endpoints import dashboard
from config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Autonomous stock pattern trading assistant. "
        "Upload a CSV, detect chart patterns via mathematical regression, "
        "receive risk-scored trade recommendations. "
        "**Disclaimer: This is probabilistic technical analysis only. "
        "Not financial advice. Past patterns do not guarantee future results.**"
    ),
    openapi_tags=[
        {"name": "Template", "description": "Download the standardised Excel upload template"},
        {"name": "Upload",   "description": "CSV upload and validation"},
        {"name": "Analysis", "description": "Pattern detection and trade signals"},
        {"name": "Reports",  "description": "Downloadable JSON/CSV reports"},
        {"name": "Health",   "description": "Service health and metadata"},
    ],
)

# CORS — tighten origins in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")
app.include_router(dashboard.router)


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "version": settings.APP_VERSION}
