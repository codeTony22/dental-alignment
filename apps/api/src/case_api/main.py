"""The case API app shell. Presentation-shaped resources; physics never lives here.

Runs on :8002 beside the BFF (:8001) and the frozen demo (:8000).
"""
from __future__ import annotations

import math
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .config import Settings, default_settings
from .resources import adjust


def _finite_safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return repr(value)
    if isinstance(value, dict):
        return {k: _finite_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_finite_safe(v) for v in value]
    return value


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or default_settings()
    app = FastAPI(title="case-api")
    app.state.settings = settings
    app.include_router(adjust.router)

    @app.exception_handler(RequestValidationError)
    async def validation_refusal(request: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content={
            "detail": _finite_safe(jsonable_encoder(exc.errors()))})

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "service": "case-api"}

    return app


app = create_app()
