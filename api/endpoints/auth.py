"""
Email + password accounts.

POST /api/v1/auth/signup   — create account, sends a verification email
GET  /api/v1/auth/verify   — clicked from the verification email
POST /api/v1/auth/login    — sets an HttpOnly session cookie
POST /api/v1/auth/logout   — clears the session cookie
GET  /api/v1/auth/me       — current session, or 401 if not logged in
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from api.config import settings
from auth.dependencies import get_current_user
from auth.security import (
    COOKIE_NAME, hash_password, verify_password,
    generate_token, create_session_token,
)
from db.database import get_db
from db.models import User
from notifications.mailer import send_verification_email

logger = logging.getLogger(__name__)
router = APIRouter()


class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    newsletter_subscribed: bool = True


class NewsletterSubscribeRequest(BaseModel):
    subscribed: bool


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


def _set_session_cookie(response: Response, user: User):
    token = create_session_token(user.id, user.email)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=settings.JWT_EXPIRE_MINUTES * 60,
        httponly=True,
        samesite="lax",
        secure=settings.APP_BASE_URL.startswith("https"),
        path="/",
    )


@router.post("/auth/signup")
async def signup(req: SignupRequest, db: Session = Depends(get_db)):
    if len(req.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")

    existing = db.query(User).filter(User.email == req.email.lower()).first()
    if existing:
        raise HTTPException(status_code=400, detail="An account with that email already exists.")

    # Without a Resend key there's no way to deliver a verification link, so
    # requiring verification would permanently lock every signup out — fall
    # back to auto-verified until email sending is actually configured.
    email_configured = bool(settings.RESEND_API_KEY)

    user = User(
        email=req.email.lower(),
        hashed_password=hash_password(req.password),
        verification_token=generate_token() if email_configured else None,
        is_verified=not email_configured,
        newsletter_subscribed=req.newsletter_subscribed,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    if email_configured:
        send_verification_email(user.email, user.verification_token)
        message = "Account created — check your email to verify before logging in."
    else:
        message = "Account created — you can log in now (email verification isn't configured yet)."
    return {"ok": True, "message": message}


@router.get("/auth/verify")
async def verify_email(token: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.verification_token == token).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or already-used verification link.")
    user.is_verified = True
    user.verification_token = None
    db.commit()
    return RedirectResponse(url=f"{settings.APP_BASE_URL}/?verified=1")


@router.post("/auth/login")
async def login(req: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email.lower()).first()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    if not user.is_verified:
        raise HTTPException(status_code=403, detail="Please verify your email before logging in.")

    _set_session_cookie(response, user)
    return {
        "ok": True,
        "email": user.email,
        "is_admin": user.email.lower() == settings.ADMIN_EMAIL.lower(),
        "newsletter_subscribed": user.newsletter_subscribed,
    }


@router.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/auth/me")
async def me(user: User = Depends(get_current_user)):
    return {
        "email": user.email,
        "is_admin": user.email.lower() == settings.ADMIN_EMAIL.lower(),
        "newsletter_subscribed": user.newsletter_subscribed,
    }


@router.post("/auth/newsletter_subscribe")
async def newsletter_subscribe(
    req: NewsletterSubscribeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user.newsletter_subscribed = req.subscribed
    db.commit()
    return {"ok": True, "newsletter_subscribed": user.newsletter_subscribed}
