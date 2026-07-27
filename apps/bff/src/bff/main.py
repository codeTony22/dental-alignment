"""The BFF app shell. Presentation-shaped resources mount here; physics never does.

Runs beside the frozen demo on ITS OWN port (8001) — see .claude/launch.json "bff".
"""
from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="case-flow BFF")


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": "bff"}
