"""FastAPI application factory."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .routes import router

_WEB_DIR = Path(__file__).parent


def create_app() -> FastAPI:
    app = FastAPI(title="Bright Data Web Research Agent")
    app.include_router(router)
    app.mount("/static", StaticFiles(directory=_WEB_DIR / "static"), name="static")
    return app
