from fastapi import FastAPI
from main import app  # your existing FastAPI app

# Vercel expects this
handler = app