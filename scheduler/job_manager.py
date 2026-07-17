"""
APScheduler — fires a data refresh every 5 minutes during market hours.
"""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

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
    scheduler.add_job(
        _newsletter_draft_job,
        trigger=CronTrigger(day_of_week="mon", hour=8, minute=0),
        id="newsletter_draft",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.start()
    logger.info("Scheduler started — price refresh every 5 min, newsletter draft every Monday 8am ET")


def stop_scheduler():
    try:
        scheduler.shutdown(wait=False)
    except Exception:
        pass


async def _refresh_job():
    from scheduler.price_fetcher import run_full_refresh, is_market_open
    from live.watchlist import get_all_distinct_tickers
    from live.excel_writer import write_live_data
    from api.endpoints.ws import manager
    from db.database import SessionLocal

    if not is_market_open():
        logger.info("Market closed — skipping scheduled refresh")
        return

    db = SessionLocal()
    try:
        tickers = get_all_distinct_tickers(db)
    finally:
        db.close()

    if not tickers:
        return

    # Refresh the union of every user's watchlisted tickers once, not once per user.
    logger.info(f"Scheduled refresh: {tickers}")
    payload = run_full_refresh(tickers)

    try:
        write_live_data(payload["results"])
    except Exception as exc:
        logger.error(f"Excel write failed: {exc}")

    try:
        await manager.broadcast_to_all()
    except Exception as exc:
        logger.error(f"WebSocket broadcast failed: {exc}")


async def _newsletter_draft_job():
    """Auto-generates a draft every Monday — never auto-sends. It just saves
    the admin the step of clicking 'Generate' before reviewing and approving."""
    from newsletter.generator import generate_draft
    from db.database import SessionLocal

    db = SessionLocal()
    try:
        issue = generate_draft(db)
        logger.info(f"Newsletter draft #{issue.id} auto-generated — awaiting admin approval")
    except Exception as exc:
        logger.error(f"Newsletter draft generation failed: {exc}")
    finally:
        db.close()
