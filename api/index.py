from fastapi import FastAPI
from stock_pattern_engine.api.main import app  # your existing FastAPI app

# Vercel expects this
handler = app