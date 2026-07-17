"""
FastAPI dependencies for authentication and admin gating.

Sessions live in an HttpOnly cookie (not localStorage) so the JWT is
inaccessible to page JS/XSS, and so the browser attaches it automatically —
including on the WebSocket upgrade request, which is why get_current_user_ws
below can reuse the exact same cookie.
"""
from fastapi import Depends, HTTPException, Request, WebSocket, status
from sqlalchemy.orm import Session

from api.config import settings
from auth.security import COOKIE_NAME, decode_session_token
from db.database import get_db
from db.models import User


def _load_user(db: Session, payload: dict) -> User:
    user = db.query(User).filter(User.id == int(payload["sub"])).first()
    if user is None:
        raise HTTPException(status_code=401, detail="Session no longer valid — please log in again.")
    return user


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not logged in.")
    payload = decode_session_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired — please log in again.")
    return _load_user(db, payload)


async def get_current_user_ws(websocket: WebSocket, db: Session) -> User:
    """Same cookie-based auth as get_current_user, adapted for the WS handshake
    (browsers send cookies on the upgrade request, but there's no Depends()
    injection point on a websocket route the way there is for HTTP)."""
    token = websocket.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Not logged in.")
    payload = decode_session_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Session expired.")
    return _load_user(db, payload)


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.email.lower() != settings.ADMIN_EMAIL.lower():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only.")
    return user
