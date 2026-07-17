"""
Watchlist REST endpoints — scoped to the logged-in user.

GET  /api/v1/watchlist            — list tickers + live data
POST /api/v1/watchlist/add        — add a ticker (max 4)
POST /api/v1/watchlist/remove     — remove a ticker
POST /api/v1/watchlist/purchase_price — set purchase price
POST /api/v1/watchlist/refresh    — trigger immediate refresh
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session

from live.watchlist import (
    add_ticker, remove_ticker, get_tickers,
    set_purchase_price, load as load_watchlist,
)
from scheduler.price_fetcher import run_full_refresh, get_cached_payload_for_tickers
from live.excel_writer import write_live_data
from auth.dependencies import get_current_user
from db.database import get_db
from db.models import User

router = APIRouter()
logger = logging.getLogger(__name__)


class AddRequest(BaseModel):
    ticker: str
    purchase_price: Optional[float] = None


class RemoveRequest(BaseModel):
    ticker: str


class PurchasePriceRequest(BaseModel):
    ticker: str
    purchase_price: float


@router.get("/watchlist")
async def get_watchlist(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    data  = load_watchlist(db, user.id)
    last  = get_cached_payload_for_tickers(list(data.keys()))
    r_map = {r["ticker"]: r for r in last.get("results", [])}
    return {
        "tickers": [
            {
                "ticker":         t,
                "purchase_price": info.get("purchase_price"),
                **r_map.get(t, {}),
            }
            for t, info in data.items()
        ],
        "count":        len(data),
        "max":          4,
        "last_updated": last.get("timestamp"),
        "market_open":  last.get("market_open", False),
    }


@router.post("/watchlist/add")
async def add_to_watchlist(req: AddRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        return add_ticker(db, user.id, req.ticker, req.purchase_price)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/watchlist/remove")
async def remove_from_watchlist(req: RemoveRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        return remove_ticker(db, user.id, req.ticker)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/watchlist/purchase_price")
async def update_purchase_price(req: PurchasePriceRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        set_purchase_price(db, user.id, req.ticker, req.purchase_price)
        return {"ok": True, "ticker": req.ticker.upper(),
                "purchase_price": req.purchase_price}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/watchlist/refresh")
async def manual_refresh(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Force an immediate refresh of this user's own tickers (ignores market hours)."""
    tickers = get_tickers(db, user.id)
    if not tickers:
        raise HTTPException(
            status_code=400,
            detail="Watchlist is empty. Add tickers first.",
        )

    logger.info(f"Manual refresh (user={user.id}): {tickers}")
    payload = run_full_refresh(tickers)

    try:
        write_live_data(payload["results"])
    except Exception as exc:
        logger.warning(f"Excel write: {exc}")

    from api.endpoints.ws import manager
    try:
        await manager.broadcast_to_all()
    except Exception:
        pass

    return payload
