"""Vercel Python entrypoint (auto-detected: root main.py exposing `app`).

One-line re-export so local development, Docker and CI keep using
`uvicorn backend.main:app` exactly as before — Vercel loads this file,
everything else lives in backend/."""
from backend.main import app

__all__ = ["app"]
