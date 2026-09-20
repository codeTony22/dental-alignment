"""Case + current-run resolution for the API / MCP peers.

The BFF owns session *mutation* (status ladder, confirmation, activity). This
module is the READ of the same on-disk shape — ``<product_root>/<case>/session.json``
and ``runs/<run_id>/`` — so the agent-shaped MCP and the UI-shaped REST API can
find a site without importing ``bff`` or ``case_prep.server``.

Nothing here does physics. It names a case, a run directory, and the summary
row the last completed run already wrote.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .cases import CaseRecord, discover_cases


class CaseNotFound(LookupError):
    """No scan folder resolved to this case id."""


class SiteUnresolved(ValueError):
    """The case exists but this tooth has no completed-run verdict to rework."""


@dataclass(frozen=True)
class SiteHandle:
    """Everything a READ / DRY_RUN / COMMIT tool needs to name one site."""

    case: CaseRecord
    tooth: int
    run_id: str
    run_dir: Path
    row: Dict[str, Any]
    session: Optional[Dict[str, Any]]
    summary: Dict[str, Any]


def case_by_id(data_root: Path, case_id: str) -> CaseRecord:
    for case in discover_cases(data_root):
        if case.id == case_id:
            return case
    raise CaseNotFound(f"unknown case {case_id!r}")


def list_case_records(data_root: Path) -> List[CaseRecord]:
    return discover_cases(data_root)


def _load_session(product_root: Path, case_id: str) -> Optional[Dict[str, Any]]:
    path = Path(product_root) / case_id / "session.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _summary_row(summary: Dict[str, Any], tooth: int) -> Optional[Dict[str, Any]]:
    for row in summary.get("sites") or []:
        if not isinstance(row, dict):
            continue
        try:
            if int(row.get("tooth", -1)) == tooth:
                return row
        except (TypeError, ValueError):
            continue
    return None


def _latest_run_id(product_root: Path, case_id: str) -> Optional[str]:
    runs = Path(product_root) / case_id / "runs"
    if not runs.is_dir():
        return None
    dirs = sorted((p.name for p in runs.iterdir() if p.is_dir()), reverse=True)
    return dirs[0] if dirs else None


def resolve_site(
    data_root: Path,
    product_root: Path,
    case_id: str,
    tooth: int,
    run_id: Optional[str] = None,
) -> SiteHandle:
    """Resolve ``case_id`` / ``tooth`` to a completed-run site.

    Prefers the session's current done run (the same pointer the BFF lands on);
    falls back to an explicit ``run_id`` or the newest ``runs/`` directory so
    a peer that has a run dir but no session can still read signals.
    """
    case = case_by_id(data_root, case_id)
    session = _load_session(product_root, case_id)
    run = (session or {}).get("run") if isinstance((session or {}).get("run"), dict) else None
    summary: Dict[str, Any] = {}
    resolved_id = run_id

    if run is not None and run.get("state") == "done":
        if resolved_id is None:
            resolved_id = run.get("run_id") or run.get("job_id")
        if isinstance(run.get("summary"), dict):
            summary = run["summary"]

    if not resolved_id:
        resolved_id = _latest_run_id(product_root, case_id)
    if not resolved_id:
        raise SiteUnresolved(
            f"there is nothing to adjust on case {case_id!r} — Adjust reworks "
            f"the fits a completed run produced, and this case has no "
            f"completed current run"
        )

    run_dir = Path(product_root) / case_id / "runs" / str(resolved_id)
    if not run_dir.is_dir():
        raise SiteUnresolved(
            f"case {case_id!r} names run {resolved_id!r} but that run "
            f"directory is not on disk"
        )

    if not summary:
        summary_path = run_dir / "summary.json"
        if summary_path.is_file():
            try:
                loaded = json.loads(summary_path.read_text())
            except (OSError, json.JSONDecodeError):
                loaded = None
            if isinstance(loaded, dict):
                summary = loaded

    row = _summary_row(summary, tooth)
    if row is None:
        raise SiteUnresolved(
            f"tooth {tooth} carries no verdict from the current run — "
            f"adjusting a site the run never aligned is meaningless"
        )
    return SiteHandle(
        case=case,
        tooth=int(tooth),
        run_id=str(resolved_id),
        run_dir=run_dir,
        row=row,
        session=session,
        summary=summary,
    )
