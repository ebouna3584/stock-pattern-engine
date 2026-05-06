"""
Watchlist manager — max 3 tickers (free tier).
Persists to watchlist.json in the project root.
"""
import json
from pathlib import Path
from threading import Lock

MAX_TICKERS = 3
_STORE = Path(__file__).parent.parent / "watchlist.json"
_lock = Lock()


def load() -> dict:
    """Returns {ticker: {purchase_price: float|None}}"""
    if _STORE.exists():
        try:
            return json.loads(_STORE.read_text())
        except Exception:
            pass
    return {}


def save(data: dict):
    with _lock:
        _STORE.write_text(json.dumps(data, indent=2))


def get_tickers() -> list:
    return list(load().keys())


def add_ticker(ticker: str, purchase_price=None) -> dict:
    ticker = ticker.upper().strip()
    data = load()
    if ticker in data:
        return {"ok": True, "message": f"{ticker} already in watchlist"}
    if len(data) >= MAX_TICKERS:
        raise ValueError(
            f"Free tier limit: max {MAX_TICKERS} tickers. Remove one first."
        )
    data[ticker] = {"purchase_price": purchase_price}
    save(data)
    return {"ok": True, "message": f"{ticker} added"}


def remove_ticker(ticker: str) -> dict:
    ticker = ticker.upper().strip()
    data = load()
    if ticker not in data:
        raise KeyError(f"{ticker} not in watchlist")
    del data[ticker]
    save(data)
    return {"ok": True, "message": f"{ticker} removed"}


def set_purchase_price(ticker: str, price: float):
    data = load()
    ticker = ticker.upper().strip()
    if ticker not in data:
        raise KeyError(f"{ticker} not in watchlist")
    data[ticker]["purchase_price"] = price
    save(data)


def get_purchase_price(ticker: str):
    return load().get(ticker.upper().strip(), {}).get("purchase_price")
