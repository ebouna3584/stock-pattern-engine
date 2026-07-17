"""
Watchlist manager — max 4 tickers per user (free tier), backed by the DB
now that each account needs its own list instead of one shared global file.
"""
from sqlalchemy.orm import Session

from db.models import WatchlistItem

MAX_TICKERS = 4


def load(db: Session, user_id: int) -> dict:
    """Returns {ticker: {purchase_price: float|None}} for this user."""
    items = db.query(WatchlistItem).filter(WatchlistItem.user_id == user_id).all()
    return {i.ticker: {"purchase_price": i.purchase_price} for i in items}


def get_tickers(db: Session, user_id: int) -> list:
    return list(load(db, user_id).keys())


def add_ticker(db: Session, user_id: int, ticker: str, purchase_price=None) -> dict:
    ticker = ticker.upper().strip()
    existing = db.query(WatchlistItem).filter_by(user_id=user_id, ticker=ticker).first()
    if existing:
        return {"ok": True, "message": f"{ticker} already in watchlist"}

    count = db.query(WatchlistItem).filter(WatchlistItem.user_id == user_id).count()
    if count >= MAX_TICKERS:
        raise ValueError(f"Free tier limit: max {MAX_TICKERS} tickers. Remove one first.")

    db.add(WatchlistItem(user_id=user_id, ticker=ticker, purchase_price=purchase_price))
    db.commit()
    return {"ok": True, "message": f"{ticker} added"}


def remove_ticker(db: Session, user_id: int, ticker: str) -> dict:
    ticker = ticker.upper().strip()
    item = db.query(WatchlistItem).filter_by(user_id=user_id, ticker=ticker).first()
    if not item:
        raise KeyError(f"{ticker} not in watchlist")
    db.delete(item)
    db.commit()
    return {"ok": True, "message": f"{ticker} removed"}


def set_purchase_price(db: Session, user_id: int, ticker: str, price: float):
    ticker = ticker.upper().strip()
    item = db.query(WatchlistItem).filter_by(user_id=user_id, ticker=ticker).first()
    if not item:
        raise KeyError(f"{ticker} not in watchlist")
    item.purchase_price = price
    db.commit()


def get_purchase_price(db: Session, user_id: int, ticker: str):
    item = db.query(WatchlistItem).filter_by(user_id=user_id, ticker=ticker.upper().strip()).first()
    return item.purchase_price if item else None


def get_all_distinct_tickers(db: Session) -> list:
    """Union of tickers across every user's watchlist — the scheduler refreshes
    each ticker once regardless of how many users are tracking it."""
    rows = db.query(WatchlistItem.ticker).distinct().all()
    return [r[0] for r in rows]


def get_all_user_ids(db: Session) -> list:
    rows = db.query(WatchlistItem.user_id).distinct().all()
    return [r[0] for r in rows]
