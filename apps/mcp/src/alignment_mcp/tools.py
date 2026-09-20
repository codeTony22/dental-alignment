"""The MCP tool table — READ / DRY_RUN / COMMIT over the adjust seam.

Each tool is a thin adapter: validate arguments, resolve the site through
``caseflow``, call ``case_prep.application.adjust`` or ``technique``. No second
physics path, no invented metrics.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from case_prep.application.adjust import (AdjustInvalid, AdjustRefused,
                                          AlreadyOptimal, Correspondence,
                                          align_to_correspondence, align_to_mark,
                                          best_fit_site, clock_landmarks,
                                          load_site, rederived_reading,
                                          rotate_site, seated_payload)
from case_prep.application.caseflow import (CaseNotFound, SiteUnresolved,
                                            list_case_records, resolve_site)
from case_prep.application.signals import assemble_site_signals, outcome_to_dict
from case_prep.application.technique import TechniqueAsk, run_technique
from case_prep.domain.acceptance import evaluate_acceptance

READ = "READ"
DRY_RUN = "DRY_RUN"
COMMIT = "COMMIT"


class ToolError(Exception):
    """A tool refusal that the JSON-RPC layer turns into an isError result."""

    def __init__(self, message: str, *, code: int = 400):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ToolSpec:
    name: str
    classification: str
    description: str
    input_schema: Dict[str, Any]
    handler: Callable[[Dict[str, Any], "ToolContext"], Dict[str, Any]]


@dataclass(frozen=True)
class ToolContext:
    data_root: Path
    product_root: Path


def _site(ctx: ToolContext, args: Dict[str, Any]):
    try:
        return resolve_site(
            ctx.data_root, ctx.product_root,
            str(args["case_id"]), int(args["tooth"]),
            run_id=args.get("run_id"))
    except CaseNotFound as exc:
        raise ToolError(str(exc), code=404) from exc
    except SiteUnresolved as exc:
        raise ToolError(str(exc), code=422) from exc


def _pairs(raw: Any) -> List[Correspondence]:
    if not isinstance(raw, list):
        raise ToolError("pairs must be a list")
    out: List[Correspondence] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ToolError("each pair must be an object")
        out.append(Correspondence(
            scan_point=item.get("scan_point"),
            scan_point_end=item.get("scan_point_end"),
            feature_id=item.get("feature_id"),
            part_point=item.get("part_point"),
            part_point_end=item.get("part_point_end"),
        ))
    return out


def _run_adjust(fn) -> Dict[str, Any]:
    try:
        outcome = fn()
    except AlreadyOptimal as exc:
        return {
            "ok": True,
            "status": "already_optimal",
            "detail": str(exc),
            "matching_diameter_mm": exc.matching_diameter_mm,
            "suggested_diameter_mm": exc.suggested_diameter_mm,
        }
    except AdjustRefused as exc:
        raise ToolError(str(exc), code=409) from exc
    except AdjustInvalid as exc:
        raise ToolError(str(exc), code=422) from exc
    return {"ok": True, "status": "ok", "outcome": outcome_to_dict(outcome)}


def _handle_list_cases(_args: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
    cases = list_case_records(ctx.data_root)
    return {
        "cases": [
            {
                "id": c.id,
                "doctor": c.doctor,
                "jaw": c.jaw,
                "suggested_model": c.suggested_model,
                "suggested_sites": list(c.suggested_sites),
            }
            for c in cases
        ]
    }


def _handle_get_case(args: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
    from case_prep.application.caseflow import case_by_id
    try:
        case = case_by_id(ctx.data_root, str(args["case_id"]))
    except CaseNotFound as exc:
        raise ToolError(str(exc), code=404) from exc
    session_path = ctx.product_root / case.id / "session.json"
    return {
        "id": case.id,
        "doctor": case.doctor,
        "jaw": case.jaw,
        "suggested_model": case.suggested_model,
        "suggested_construction": case.suggested_construction,
        "suggested_sites": list(case.suggested_sites),
        "has_session": session_path.is_file(),
    }


def _handle_get_site_signals(args: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
    handle = _site(ctx, args)
    landmarks: Optional[List[dict]] = None
    seated = None
    landmarks_error = None
    seated_error = None
    try:
        landmarks = clock_landmarks(load_site(handle.case, handle.run_dir, handle.tooth).template)
    except (AdjustInvalid, AdjustRefused, OSError, ValueError, RuntimeError) as exc:
        landmarks_error = str(exc)
    try:
        seated = seated_payload(handle.case, handle.run_dir, handle.tooth)
    except (AdjustInvalid, AdjustRefused, OSError, ValueError, RuntimeError) as exc:
        seated_error = str(exc)
    envelope = assemble_site_signals(
        handle.row, landmarks=landmarks, seated=seated,
        landmarks_error=landmarks_error, seated_error=seated_error)
    envelope["case_id"] = handle.case.id
    envelope["run_id"] = handle.run_id
    return envelope


def _handle_get_seated(args: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
    handle = _site(ctx, args)
    try:
        return seated_payload(handle.case, handle.run_dir, handle.tooth)
    except (AdjustInvalid, AdjustRefused) as exc:
        raise ToolError(str(exc), code=409 if isinstance(exc, AdjustRefused) else 422) from exc


def _handle_get_landmarks(args: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
    handle = _site(ctx, args)
    try:
        items = clock_landmarks(load_site(handle.case, handle.run_dir, handle.tooth).template)
    except (AdjustInvalid, AdjustRefused) as exc:
        raise ToolError(str(exc), code=409 if isinstance(exc, AdjustRefused) else 422) from exc
    return {"landmarks": items}


def _handle_get_acceptance(args: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
    handle = _site(ctx, args)
    evaluation = evaluate_acceptance(handle.row)
    rework = handle.row.get("rework") if isinstance(handle.row.get("rework"), dict) else {}
    return {
        "tooth": handle.tooth,
        "run_id": handle.run_id,
        "overall_band": str((evaluation.get("overall") or {}).get("band")),
        "missing": list((evaluation.get("overall") or {}).get("missing") or []),
        "metrics": list(evaluation.get("metrics") or []),
        "stale_metrics": [str(m) for m in (rework.get("stale_metrics") or [])],
        "context": dict(evaluation.get("context") or {}),
    }


def _handle_dry_run_best_fit(args: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
    handle = _site(ctx, args)
    return _run_adjust(lambda: best_fit_site(
        handle.case, handle.run_dir, handle.tooth,
        matching_diameter_mm=float(args.get("matching_diameter_mm", 0.3)),
        apply=False))


def _handle_dry_run_repreview(args: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
    handle = _site(ctx, args)
    try:
        payload = seated_payload(handle.case, handle.run_dir, handle.tooth)
    except (AdjustInvalid, AdjustRefused) as exc:
        raise ToolError(str(exc), code=409 if isinstance(exc, AdjustRefused) else 422) from exc
    rederived = rederived_reading(payload)
    previous = {key: handle.row.get(key) for key in rederived}
    return {
        "tooth": handle.tooth,
        "run_id": handle.run_id,
        "changed": previous != rederived,
        "rederived": rederived,
        "previous": previous,
        "stale_metrics": [
            str(m) for m in ((handle.row.get("rework") or {}).get("stale_metrics") or [])
        ],
        "pane_payload": payload,
    }


def _handle_commit_best_fit(args: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
    handle = _site(ctx, args)
    return _run_adjust(lambda: best_fit_site(
        handle.case, handle.run_dir, handle.tooth,
        matching_diameter_mm=float(args.get("matching_diameter_mm", 0.3)),
        apply=True))


def _handle_commit_rotation(args: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
    handle = _site(ctx, args)
    return _run_adjust(lambda: rotate_site(
        handle.case, handle.run_dir, handle.tooth,
        step_deg=float(args.get("step_deg", 0.0)),
        reset=bool(args.get("reset", False))))


def _handle_commit_mark_trench(args: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
    handle = _site(ctx, args)
    if "scan_point" not in args:
        raise ToolError("scan_point is required")
    return _run_adjust(lambda: align_to_mark(
        handle.case, handle.run_dir, handle.tooth, args["scan_point"]))


def _handle_commit_fit_by_points(args: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
    handle = _site(ctx, args)
    return _run_adjust(lambda: align_to_correspondence(
        handle.case, handle.run_dir, handle.tooth, _pairs(args.get("pairs") or [])))


def _handle_run_alignment_technique(args: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
    handle = _site(ctx, args)
    pairs = _pairs(args["pairs"]) if args.get("pairs") else None
    ask = TechniqueAsk(
        mode=str(args.get("mode", "intelligence")),
        apply=bool(args.get("apply", True)),
        matching_diameter_mm=float(args.get("matching_diameter_mm", 0.3)),
        step_deg=args.get("step_deg"),
        reset=bool(args.get("reset", False)),
        scan_point=args.get("scan_point"),
        pairs=pairs,
    )
    try:
        result = run_technique(handle.case, handle.run_dir, handle.tooth, handle.row, ask)
    except AdjustInvalid as exc:
        raise ToolError(str(exc), code=422) from exc
    payload = result.to_dict()
    payload["case_id"] = handle.case.id
    payload["run_id"] = handle.run_id
    payload["tooth"] = handle.tooth
    return payload


def _site_props() -> Dict[str, Any]:
    return {
        "case_id": {"type": "string"},
        "tooth": {"type": "integer"},
        "run_id": {"type": "string"},
    }


def _site_required() -> List[str]:
    return ["case_id", "tooth"]


TOOLS: List[ToolSpec] = [
    ToolSpec(
        name="list_cases", classification=READ,
        description="Discover scan folders as cases (directory shape only).",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        handler=_handle_list_cases,
    ),
    ToolSpec(
        name="get_case", classification=READ,
        description="One case's discovery record.",
        input_schema={"type": "object", "properties": {"case_id": {"type": "string"}},
                      "required": ["case_id"], "additionalProperties": False},
        handler=_handle_get_case,
    ),
    ToolSpec(
        name="get_site_signals", classification=READ,
        description="The full adjust/MCP signal taxonomy for one site.",
        input_schema={"type": "object", "properties": _site_props(),
                      "required": _site_required(), "additionalProperties": False},
        handler=_handle_get_site_signals,
    ),
    ToolSpec(
        name="get_seated", classification=READ,
        description="The shipped pose pane payload (same builder Declare uses).",
        input_schema={"type": "object", "properties": _site_props(),
                      "required": _site_required(), "additionalProperties": False},
        handler=_handle_get_seated,
    ),
    ToolSpec(
        name="get_landmarks", classification=READ,
        description="AUTO-MARK part-half landmarks, best lever first.",
        input_schema={"type": "object", "properties": _site_props(),
                      "required": _site_required(), "additionalProperties": False},
        handler=_handle_get_landmarks,
    ),
    ToolSpec(
        name="get_acceptance", classification=READ,
        description="Acceptance-catalog evaluation of the site's run row.",
        input_schema={"type": "object", "properties": _site_props(),
                      "required": _site_required(), "additionalProperties": False},
        handler=_handle_get_acceptance,
    ),
    ToolSpec(
        name="dry_run_best_fit", classification=DRY_RUN,
        description="Pipeline refinement measured only (apply=False).",
        input_schema={"type": "object", "properties": {
            **_site_props(),
            "matching_diameter_mm": {"type": "number"},
        }, "required": _site_required(), "additionalProperties": False},
        handler=_handle_dry_run_best_fit,
    ),
    ToolSpec(
        name="dry_run_repreview", classification=DRY_RUN,
        description="Re-read deviation at the shipped pose; writes nothing.",
        input_schema={"type": "object", "properties": _site_props(),
                      "required": _site_required(), "additionalProperties": False},
        handler=_handle_dry_run_repreview,
    ),
    ToolSpec(
        name="commit_best_fit", classification=COMMIT,
        description="Adopt the pipeline refinement at the matching diameter.",
        input_schema={"type": "object", "properties": {
            **_site_props(),
            "matching_diameter_mm": {"type": "number"},
        }, "required": _site_required(), "additionalProperties": False},
        handler=_handle_commit_best_fit,
    ),
    ToolSpec(
        name="commit_rotation", classification=COMMIT,
        description="Gated rotation step, or reset to the certified pose.",
        input_schema={"type": "object", "properties": {
            **_site_props(),
            "step_deg": {"type": "number"},
            "reset": {"type": "boolean"},
        }, "required": _site_required(), "additionalProperties": False},
        handler=_handle_commit_rotation,
    ),
    ToolSpec(
        name="commit_mark_trench", classification=COMMIT,
        description="Rotate so the nearest code feature lands on the scan mark.",
        input_schema={"type": "object", "properties": {
            **_site_props(),
            "scan_point": {"type": "array", "items": {"type": "number"}},
        }, "required": [*_site_required(), "scan_point"], "additionalProperties": False},
        handler=_handle_commit_mark_trench,
    ),
    ToolSpec(
        name="commit_fit_by_points", classification=COMMIT,
        description="Fit by operator correspondences (points or spans).",
        input_schema={"type": "object", "properties": {
            **_site_props(),
            "pairs": {"type": "array"},
        }, "required": [*_site_required(), "pairs"], "additionalProperties": False},
        handler=_handle_commit_fit_by_points,
    ),
    ToolSpec(
        name="run_alignment_technique", classification=COMMIT,
        description=(
            "Run Deterministic (one-shot best-fit) or Intelligence (full MCP "
            "tool walk). Intelligence never invents scan points."
        ),
        input_schema={"type": "object", "properties": {
            **_site_props(),
            "mode": {"type": "string", "enum": ["deterministic", "intelligence"]},
            "apply": {"type": "boolean"},
            "matching_diameter_mm": {"type": "number"},
            "step_deg": {"type": "number"},
            "reset": {"type": "boolean"},
            "scan_point": {"type": "array", "items": {"type": "number"}},
            "pairs": {"type": "array"},
        }, "required": [*_site_required(), "mode"], "additionalProperties": False},
        handler=_handle_run_alignment_technique,
    ),
]

TOOLS_BY_NAME = {tool.name: tool for tool in TOOLS}


def list_tools() -> List[Dict[str, Any]]:
    return [
        {
            "name": tool.name,
            "description": f"[{tool.classification}] {tool.description}",
            "inputSchema": tool.input_schema,
            "annotations": {"readOnlyHint": tool.classification == READ},
            "classification": tool.classification,
        }
        for tool in TOOLS
    ]


def call_tool(name: str, arguments: Optional[Dict[str, Any]], ctx: ToolContext) -> Dict[str, Any]:
    spec = TOOLS_BY_NAME.get(name)
    if spec is None:
        raise ToolError(f"unknown tool {name!r}", code=404)
    return spec.handler(arguments or {}, ctx)
