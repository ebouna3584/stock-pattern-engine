"""
WebSocket endpoint — pushes live screener data to connected browser clients,
filtered per-connection to that user's own watchlist (accounts are per-user
now, so one shared broadcast would leak other users' tickers).
"""
import asyncio
import logging
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter()


class ConnectionManager:
    def __init__(self):
        self.active: list = []  # [(websocket, user_id), ...]

    async def connect(self, ws: WebSocket, user_id: int):
        await ws.accept()
        self.active.append((ws, user_id))
        logger.info(f"WS connected user={user_id} (total={len(self.active)})")

    def disconnect(self, ws: WebSocket):
        self.active = [(w, u) for (w, u) in self.active if w is not ws]
        logger.info(f"WS disconnected (total={len(self.active)})")

    async def send_to(self, ws: WebSocket, user_id: int):
        from scheduler.price_fetcher import get_cached_payload_for_tickers
        from live.watchlist import get_tickers
        from db.database import SessionLocal

        db = SessionLocal()
        try:
            tickers = get_tickers(db, user_id)
        finally:
            db.close()
        await ws.send_json(get_cached_payload_for_tickers(tickers))

    async def broadcast_to_all(self):
        """Called after a shared refresh — sends each connection its own
        watchlist's slice of the freshly-updated per-ticker cache."""
        dead = []
        for ws, user_id in list(self.active):
            try:
                await self.send_to(ws, user_id)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


@router.websocket("/ws/live")
async def websocket_live(websocket: WebSocket):
    from auth.dependencies import get_current_user_ws
    from db.database import SessionLocal

    db = SessionLocal()
    try:
        user = await get_current_user_ws(websocket, db)
    except HTTPException:
        await websocket.close(code=4401)
        return
    finally:
        db.close()

    await manager.connect(websocket, user.id)
    try:
        from scheduler.price_fetcher import has_cached_data, run_full_refresh
        from live.watchlist import get_tickers

        db2 = SessionLocal()
        try:
            tickers = get_tickers(db2, user.id)
        finally:
            db2.close()

        if tickers:
            if has_cached_data():
                await manager.send_to(websocket, user.id)
            else:
                # Cold start — fetch now in a thread so we don't block the event loop
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, run_full_refresh, tickers)
                await manager.broadcast_to_all()

        # Keep alive — browser sends periodic pings
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as exc:
        logger.error(f"WS error: {exc}")
        manager.disconnect(websocket)
