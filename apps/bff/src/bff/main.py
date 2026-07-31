"""The BFF app shell. Presentation-shaped resources mount here; physics never does.

Runs beside the frozen demo on ITS OWN port (8001) — see .claude/launch.json "bff".
``create_app`` takes explicit ``Settings`` so tests wire tmp trees; the module-level
``app`` uses the repo defaults for uvicorn. Sessions rehydrate at construction (grill
AM-4): a corrupt session file fails the BOOT loudly, not a random later request.
"""
from __future__ import annotations

import math
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .config import Settings, default_settings
from .ports.worker import InProcessWorker
from .resources import activity, adjust, case_sessions, deliver, library
from .session import SessionStore


def _finite_safe(value):
    """Non-finite floats become their names. The validation corpus refuses NaN/inf
    (plan §6 finiteness), and FastAPI's default 422 handler echoes the offending input
    back — json.dumps(allow_nan=False) then crashes the REFUSAL itself into a 500.
    Found by test_a_non_finite_relief_is_refused: a refusal must always serialize."""
    if isinstance(value, float) and not math.isfinite(value):
        return repr(value)  # "nan" / "inf" — words, since JSON has no such numbers
    if isinstance(value, dict):
        return {k: _finite_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_finite_safe(v) for v in value]
    return value


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or default_settings()
    app = FastAPI(title="case-flow BFF")
    app.state.settings = settings
    app.state.sessions = SessionStore(settings.product_root)
    app.state.sessions.rehydrate()
    # the ONE doorway to the physics (plan §3/AM-3): resources speak the job-shaped
    # port; swapping this adapter for the SQS one changes nothing above it
    app.state.worker = InProcessWorker(settings.data_root, settings.product_root)
    app.include_router(case_sessions.router)
    # the disclosure edge (plan §4 Deliver / AM-1): evidence ungated, artifacts
    # gated — mounted after case_sessions so its multi-segment paths never shadow
    # the single-segment detail route
    app.include_router(deliver.router)
    # the terms document (client 2026-07-30): case-independent, so its own
    # resource — a recorded terms_version must resolve to the text it names
    app.include_router(deliver.terms_router)
    # the rework surface (plan §4 Adjust / slice 6): mounted after case_sessions for
    # the same reason deliver is — its multi-segment per-site paths must never shadow
    # the single-segment detail route
    app.include_router(adjust.router)
    # the case's narrative (gap ``session-activity-log``): GET-only, mounted after
    # case_sessions for the same path-shadowing reason as the two above
    app.include_router(activity.router)
    app.include_router(library.router)

    @app.exception_handler(RequestValidationError)
    async def validation_refusal(request: Request, exc: RequestValidationError):
        # the default handler's shape, made non-finite-input-safe (see _finite_safe)
        return JSONResponse(status_code=422, content={
            "detail": _finite_safe(jsonable_encoder(exc.errors()))})

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "service": "bff"}

    return app


app = create_app()
