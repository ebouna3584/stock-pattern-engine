"""
Database engine/session setup.

Defaults to a local SQLite file so the app runs with zero setup, but SQLite's
file-based storage does not reliably persist on Vercel's serverless
filesystem — set DATABASE_URL to a hosted Postgres URL (Neon/Supabase/etc.)
before deploying there.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from api.config import settings

_connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(settings.DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from db import models  # noqa: F401 — register models on Base before create_all
    Base.metadata.create_all(bind=engine)
