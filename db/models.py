"""
SQLAlchemy models — users, per-user watchlists, and newsletter issues.

Admin status is not a stored role: it's decided at request time by comparing
the authenticated user's email to settings.ADMIN_EMAIL (see auth/dependencies.py).
That keeps "only I can approve/send" a single source of truth in config,
matching the one-admin model this app actually needs.
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text,
    ForeignKey, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from db.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id                     = Column(Integer, primary_key=True)
    email                  = Column(String, unique=True, index=True, nullable=False)
    hashed_password        = Column(String, nullable=False)
    is_verified            = Column(Boolean, default=False, nullable=False)
    verification_token     = Column(String, unique=True, nullable=True)
    newsletter_subscribed  = Column(Boolean, default=True, nullable=False)
    created_at             = Column(DateTime, default=_utcnow, nullable=False)

    watchlist_items = relationship(
        "WatchlistItem", back_populates="user", cascade="all, delete-orphan"
    )


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (UniqueConstraint("user_id", "ticker", name="uq_user_ticker"),)

    id              = Column(Integer, primary_key=True)
    user_id         = Column(Integer, ForeignKey("users.id"), nullable=False)
    ticker          = Column(String, nullable=False)
    purchase_price  = Column(Float, nullable=True)
    added_at        = Column(DateTime, default=_utcnow, nullable=False)

    user = relationship("User", back_populates="watchlist_items")


class NewsletterIssue(Base):
    __tablename__ = "newsletter_issues"

    id             = Column(Integer, primary_key=True)
    week_label     = Column(String, nullable=False)
    subject        = Column(String, nullable=False)
    content_html   = Column(Text, nullable=False)
    status         = Column(String, default="draft", nullable=False)  # draft|approved|sent
    generated_at   = Column(DateTime, default=_utcnow, nullable=False)
    approved_by    = Column(String, nullable=True)
    approved_at    = Column(DateTime, nullable=True)
    sent_at        = Column(DateTime, nullable=True)
    recipient_count = Column(Integer, nullable=True)
