"""
WebSocket endpoint — pushes live screener data to all connected browser clients.
"""
import asyncio
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter()


class ConnectionManager:
    def __init__(self):
        self.active: list = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)
        logger.info(f"WS connected  (total={len(self.active)})")

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)
        logger.info(f"WS disconnected (total={len(self.active)})")

    async def broadcast(self, data: dict):
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            if ws in self.active:
                self.active.remove(ws)


manager = ConnectionManager()


@router.websocket("/ws/live")
async def websocket_live(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        from scheduler.price_fetcher import get_last_payload, run_full_refresh
        from live.watchlist import get_tickers

        last = get_last_payload()
        if last:
            # Send cached data immediately
            await websocket.send_json(last)
        else:
            # Cold start — fetch now in a thread so we don't block the event loop
            tickers = get_tickers()
            if tickers:
                loop = asyncio.get_event_loop()
                payload = await loop.run_in_executor(None, run_full_refresh, tickers)
                await manager.broadcast(payload)

        # Keep alive — browser sends periodic pings
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as exc:
        logger.error(f"WS error: {exc}")
        manager.disconnect(websocket)
