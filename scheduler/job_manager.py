"""
APScheduler — fires a data refresh every 5 minutes during market hours.
"""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger    = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone="America/New_York")


def start_scheduler():
    scheduler.add_job(
        _refresh_job,
        trigger=IntervalTrigger(minutes=5),
        id="price_refresh",
        replace_existing=True,
        misfire_grace_time=60,
    )
    scheduler.start()
    logger.info("Scheduler started — price refresh every 5 min (market hours only)")


def stop_scheduler():
    try:
        scheduler.shutdown(wait=False)
    except Exception:
        pass


async def _refresh_job():
    from scheduler.price_fetcher import run_full_refresh, is_market_open
    from live.watchlist import get_tickers
    from live.excel_writer import write_live_data
    from api.endpoints.ws import manager

    if not is_market_open():
        logger.info("Market closed — skipping scheduled refresh")
        return

    tickers = get_tickers()
    if not tickers:
        return

    logger.info(f"Scheduled refresh: {tickers}")
    payload = run_full_refresh(tickers)

    try:
        write_live_data(payload["results"])
    except Exception as exc:
        logger.error(f"Excel write failed: {exc}")

    try:
        await manager.broadcast(payload)
    except Exception as exc:
        logger.error(f"WebSocket broadcast failed: {exc}")
