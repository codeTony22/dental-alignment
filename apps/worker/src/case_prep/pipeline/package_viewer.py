"""view.html — a self-contained, offline 3D viewer inside every case package.

The doctor/lab double-clicks ONE file: no installs, no server, works from file://.
Composition: the standalone viewer bundle (built from apps/web/viewer-standalone,
three.js inlined) + the case's STL parts embedded as base64 + the audit meta.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Dict, List

_BUNDLE = (Path(__file__).resolve().parents[4]
           / "web/viewer-standalone/dist/standalone-viewer.iife.js")


def write_view_html(case_id: str, out_dir, parts: List[Dict], meta: Dict) -> Path:
    """``parts``: [{name, role: arch|cap|construction, path}] — the deliverable STLs."""
    bundle = _BUNDLE.read_text()
    case = {
        "caseId": case_id,
        "parts": [{"name": p["name"], "role": p["role"],
                   "b64": base64.b64encode(Path(p["path"]).read_bytes()).decode()}
                  for p in parts],
        "meta": meta,
    }
    html = (
        "<!doctype html>\n<html><head><meta charset=\"utf-8\">"
        f"<title>{case_id} — case viewer</title>"
        "<style>html,body{margin:0;height:100%;background:#111}</style></head><body>"
        f"<script>window.__CASE__ = {json.dumps(case)};</script>"
        f"<script>{bundle}</script>"
        "</body></html>"
    )
    out = Path(out_dir) / "view.html"
    out.write_text(html)
    return out
