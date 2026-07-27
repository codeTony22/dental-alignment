"""The BFF app shell. Presentation-shaped resources mount here; physics never does.

Runs beside the frozen demo on ITS OWN port (8001) — see .claude/launch.json "bff".
``create_app`` takes explicit ``Settings`` so tests wire tmp trees; the module-level
``app`` uses the repo defaults for uvicorn. Sessions rehydrate at construction (grill
AM-4): a corrupt session file fails the BOOT loudly, not a random later request.
"""
from __future__ import annotations

from typing import Optional

from fastapi import FastAPI

from .config import Settings, default_settings
from .resources import case_sessions
from .session import SessionStore


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or default_settings()
    app = FastAPI(title="case-flow BFF")
    app.state.settings = settings
    app.state.sessions = SessionStore(settings.product_root)
    app.state.sessions.rehydrate()
    app.include_router(case_sessions.router)

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "service": "bff"}

    return app


app = create_app()
