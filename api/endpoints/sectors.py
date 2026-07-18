"""
Sector recommendations — ranks a sector's ETF + representative large-caps by
the same pattern-detection engine used everywhere else in the app (no extra
AI cost here; this is deterministic technical analysis, not a Claude call).

GET /api/v1/sectors              — list sector names for the nav dropdown
GET /api/v1/sectors/{key}        — ranked recommendations for one sector
"""
import logging
import time

from fastapi import APIRouter, Depends, HTTPException

from auth.dependencies import get_current_user
from db.models import User
from sectors.data import list_sectors, get_sector
from scheduler.price_fetcher import run_full_refresh

logger = logging.getLogger(__name__)
router = APIRouter()

_CACHE_TTL_SEC = 1800  # 30 min — these are five-stock fetches, cache to control load
_cache: dict = {}  # sector_key -> {"data": {...}, "ts": float}

_SIGNAL_RANK = {"BUY": 0, "WATCH": 1, "SELL": 2}


@router.get("/sectors")
async def sectors_list(user: User = Depends(get_current_user)):
    return list_sectors()


@router.get("/sectors/{key}")
async def sector_recommendations(key: str, force_refresh: bool = False, user: User = Depends(get_current_user)):
    sector = get_sector(key)
    if not sector:
        raise HTTPException(status_code=404, detail=f"Unknown sector '{key}'.")

    if not force_refresh:
        cached = _cache.get(key)
        if cached and (time.time() - cached["ts"]) < _CACHE_TTL_SEC:
            return cached["data"]

    tickers = [sector["etf"]] + sector["stocks"]
    logger.info(f"Sector refresh ({key}): {tickers}")
    payload = run_full_refresh(tickers)

    rows = {r["ticker"]: r for r in payload["results"]}
    etf_row = rows.pop(sector["etf"], {"ticker": sector["etf"], "error": "no data"})
    stock_rows = list(rows.values())
    stock_rows.sort(
        key=lambda r: (
            _SIGNAL_RANK.get((r.get("signal") or "WATCH").upper(), 1),
            -(r.get("confidence") or 0),
        )
    )

    buy_count  = sum(1 for r in stock_rows if (r.get("signal") or "").upper() == "BUY")
    sell_count = sum(1 for r in stock_rows if (r.get("signal") or "").upper() == "SELL")

    data = {
        "key": key,
        "name": sector["name"],
        "generated_at": payload["timestamp"],
        "etf": etf_row,
        "stocks": stock_rows,
        "buy_count": buy_count,
        "sell_count": sell_count,
        "watch_count": len(stock_rows) - buy_count - sell_count,
    }
    _cache[key] = {"data": data, "ts": time.time()}
    return data
