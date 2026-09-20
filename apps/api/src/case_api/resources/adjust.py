"""Adjust + technique resources — UI-shaped adapters over the same seam MCP uses.

Prefix: ``/api/v1/cases/{case_id}/sites/{tooth}``.

Reads and acts call ``case_prep.application.adjust`` / ``technique`` through
``caseflow.resolve_site``. No BFF import, no ``case_prep.server``, no second
physics path. Session landing (status ladder, confirmation) stays the BFF's;
this peer reports outcomes and the full signal envelope.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, NoReturn, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from case_prep.application.adjust import (AdjustInvalid, AdjustOutcome,
                                          AdjustRefused, AlreadyOptimal,
                                          Correspondence, align_to_correspondence,
                                          align_to_mark, best_fit_site,
                                          clock_landmarks, load_site,
                                          rederived_reading, rotate_site,
                                          seated_payload)
from case_prep.application.caseflow import (CaseNotFound, SiteUnresolved,
                                            case_by_id, list_case_records,
                                            resolve_site)
from case_prep.application.signals import (SIGNAL_GROUPS, assemble_site_signals,
                                           outcome_to_dict)
from case_prep.application.technique import TechniqueAsk, run_technique
from case_prep.domain.acceptance import evaluate_acceptance

from ..config import Settings

router = APIRouter(prefix="/api/v1", tags=["case-api"])

_MAX_STEP_DEG = 45.0
_MAX_PAIRS = 8
_MIN_DIAMETER_MM = 0.05
_MAX_DIAMETER_MM = 2.0


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _finite_triple(value, field_name: str):
    if value is None:
        return value
    if len(value) != 3:
        raise ValueError(f"{field_name} must be an [x, y, z] triple")
    if not all(math.isfinite(c) for c in value):
        raise ValueError(f"{field_name} coordinates must be finite numbers")
    return [float(c) for c in value]


def _handle(exc: Exception) -> NoReturn:
    if isinstance(exc, CaseNotFound):
        raise HTTPException(404, str(exc)) from exc
    if isinstance(exc, SiteUnresolved):
        raise HTTPException(422, str(exc)) from exc
    if isinstance(exc, AlreadyOptimal):
        raise HTTPException(409, {
            "kind": "already_optimal",
            "message": str(exc),
            "matching_diameter_mm": exc.matching_diameter_mm,
            "suggested_diameter_mm": exc.suggested_diameter_mm,
        }) from exc
    if isinstance(exc, AdjustRefused):
        raise HTTPException(409, str(exc)) from exc
    if isinstance(exc, AdjustInvalid):
        raise HTTPException(422, str(exc)) from exc
    raise exc


def _site(request: Request, case_id: str, tooth: int, run_id: Optional[str] = None):
    settings = _settings(request)
    try:
        return resolve_site(settings.data_root, settings.product_root,
                            case_id, tooth, run_id=run_id)
    except (CaseNotFound, SiteUnresolved) as exc:
        _handle(exc)


class RotationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    step_deg: float = 0.0
    reset: bool = False

    @field_validator("step_deg")
    @classmethod
    def _bounded_step(cls, v):
        if not math.isfinite(v) or abs(v) > _MAX_STEP_DEG:
            raise ValueError(f"step_deg must be a finite step within ±{_MAX_STEP_DEG:.0f}°")
        return float(v)


class MarkTrenchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scan_point: List[float]

    @field_validator("scan_point")
    @classmethod
    def _finite_xyz(cls, v):
        return _finite_triple(v, "scan_point")


class PairIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    feature_id: Optional[str] = None
    part_point: Optional[List[float]] = None
    part_point_end: Optional[List[float]] = None
    scan_point: List[float]
    scan_point_end: Optional[List[float]] = None

    @field_validator("scan_point", "scan_point_end", "part_point", "part_point_end")
    @classmethod
    def _finite_xyz(cls, v, info):
        return _finite_triple(v, info.field_name)

    @model_validator(mode="after")
    def _one_part_half(self):
        if (self.feature_id is None) == (self.part_point is None):
            raise ValueError("each pair needs exactly one of feature_id or part_point")
        if self.part_point_end is not None and self.feature_id is not None:
            raise ValueError("a named feature has no second point")
        return self


class FitByPointsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pairs: List[PairIn] = Field(default_factory=list)

    @field_validator("pairs")
    @classmethod
    def _bounded_pairs(cls, v):
        if len(v) > _MAX_PAIRS:
            raise ValueError(f"a correspondence is capped at {_MAX_PAIRS} pairs")
        return v


class BestFitIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    matching_diameter_mm: float = 0.3
    apply: bool = True

    @field_validator("matching_diameter_mm")
    @classmethod
    def _bounded_diameter(cls, v):
        if not math.isfinite(v) or not (_MIN_DIAMETER_MM <= v <= _MAX_DIAMETER_MM):
            raise ValueError(
                f"matching_diameter_mm must be between {_MIN_DIAMETER_MM} "
                f"and {_MAX_DIAMETER_MM}mm")
        return float(v)


class TechniqueIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: str
    apply: bool = True
    matching_diameter_mm: float = 0.3
    step_deg: Optional[float] = None
    reset: bool = False
    scan_point: Optional[List[float]] = None
    pairs: Optional[List[PairIn]] = None
    run_id: Optional[str] = None

    @field_validator("mode")
    @classmethod
    def _known_mode(cls, v):
        if v not in ("deterministic", "intelligence"):
            raise ValueError("mode must be deterministic or intelligence")
        return v

    @field_validator("matching_diameter_mm")
    @classmethod
    def _bounded_diameter(cls, v):
        if not math.isfinite(v) or not (_MIN_DIAMETER_MM <= v <= _MAX_DIAMETER_MM):
            raise ValueError("matching_diameter_mm out of band")
        return float(v)

    @field_validator("scan_point")
    @classmethod
    def _finite_xyz(cls, v):
        return _finite_triple(v, "scan_point")


def _correspondences(pairs: List[PairIn]) -> List[Correspondence]:
    return [Correspondence(
        scan_point=p.scan_point, scan_point_end=p.scan_point_end,
        feature_id=p.feature_id, part_point=p.part_point,
        part_point_end=p.part_point_end) for p in pairs]


def _adjust_result(outcome: AdjustOutcome) -> Dict[str, Any]:
    return {"outcome": outcome_to_dict(outcome), "pane_payload": outcome.pane_payload}


def _apply(run):
    try:
        return _adjust_result(run())
    except (AdjustInvalid, AdjustRefused, AlreadyOptimal) as exc:
        _handle(exc)


@router.get("/cases")
def list_cases(request: Request) -> dict:
    settings = _settings(request)
    cases = list_case_records(settings.data_root)
    return {"cases": [
        {
            "id": c.id,
            "doctor": c.doctor,
            "jaw": c.jaw,
            "suggested_model": c.suggested_model,
            "suggested_construction": c.suggested_construction,
            "suggested_sites": [
                {"tooth": s.get("tooth"), "declared_variant": s.get("declared_variant")}
                for s in c.suggested_sites if isinstance(s, dict)
            ],
        }
        for c in cases
    ]}


@router.get("/cases/{case_id}")
def get_case(case_id: str, request: Request) -> dict:
    settings = _settings(request)
    try:
        case = case_by_id(settings.data_root, case_id)
    except CaseNotFound as exc:
        _handle(exc)
    teeth = []
    for site in case.suggested_sites:
        if isinstance(site, dict) and site.get("tooth") is not None:
            teeth.append(int(site["tooth"]))
    return {
        "id": case.id,
        "doctor": case.doctor,
        "jaw": case.jaw,
        "suggested_model": case.suggested_model,
        "suggested_construction": case.suggested_construction,
        "teeth": teeth,
        "suggested_sites": list(case.suggested_sites),
    }


@router.get("/cases/{case_id}/sites/{tooth}/signals")
def site_signals(case_id: str, tooth: int, request: Request) -> dict:
    handle = _site(request, case_id, tooth)
    landmarks = None
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


@router.get("/cases/{case_id}/sites/{tooth}/seated")
def site_seated(case_id: str, tooth: int, request: Request) -> dict:
    handle = _site(request, case_id, tooth)
    try:
        return seated_payload(handle.case, handle.run_dir, handle.tooth)
    except (AdjustInvalid, AdjustRefused) as exc:
        _handle(exc)


@router.get("/cases/{case_id}/sites/{tooth}/landmarks")
def site_landmarks(case_id: str, tooth: int, request: Request) -> dict:
    handle = _site(request, case_id, tooth)
    try:
        return {"landmarks": clock_landmarks(
            load_site(handle.case, handle.run_dir, handle.tooth).template)}
    except (AdjustInvalid, AdjustRefused) as exc:
        _handle(exc)


@router.get("/cases/{case_id}/sites/{tooth}/acceptance")
def site_acceptance(case_id: str, tooth: int, request: Request) -> dict:
    handle = _site(request, case_id, tooth)
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


@router.post("/cases/{case_id}/sites/{tooth}/re-preview")
def post_re_preview(case_id: str, tooth: int, request: Request) -> dict:
    handle = _site(request, case_id, tooth)
    try:
        payload = seated_payload(handle.case, handle.run_dir, handle.tooth)
    except (AdjustInvalid, AdjustRefused) as exc:
        _handle(exc)
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


@router.post("/cases/{case_id}/sites/{tooth}/rotation")
def post_rotation(case_id: str, tooth: int, body: RotationIn, request: Request) -> dict:
    handle = _site(request, case_id, tooth)
    return _apply(lambda: rotate_site(
        handle.case, handle.run_dir, handle.tooth,
        step_deg=body.step_deg, reset=body.reset))


@router.post("/cases/{case_id}/sites/{tooth}/mark-trench")
def post_mark_trench(case_id: str, tooth: int, body: MarkTrenchIn,
                     request: Request) -> dict:
    handle = _site(request, case_id, tooth)
    return _apply(lambda: align_to_mark(
        handle.case, handle.run_dir, handle.tooth, body.scan_point))


@router.post("/cases/{case_id}/sites/{tooth}/fit-by-points")
def post_fit_by_points(case_id: str, tooth: int, body: FitByPointsIn,
                       request: Request) -> dict:
    handle = _site(request, case_id, tooth)
    return _apply(lambda: align_to_correspondence(
        handle.case, handle.run_dir, handle.tooth, _correspondences(body.pairs)))


@router.post("/cases/{case_id}/sites/{tooth}/best-fit")
def post_best_fit(case_id: str, tooth: int, body: BestFitIn, request: Request) -> dict:
    handle = _site(request, case_id, tooth)
    return _apply(lambda: best_fit_site(
        handle.case, handle.run_dir, handle.tooth,
        matching_diameter_mm=body.matching_diameter_mm, apply=body.apply))


@router.post("/cases/{case_id}/sites/{tooth}/technique")
def post_technique(case_id: str, tooth: int, body: TechniqueIn,
                   request: Request) -> dict:
    handle = _site(request, case_id, tooth, run_id=body.run_id)
    ask = TechniqueAsk(
        mode=body.mode,
        apply=body.apply,
        matching_diameter_mm=body.matching_diameter_mm,
        step_deg=body.step_deg,
        reset=body.reset,
        scan_point=body.scan_point,
        pairs=_correspondences(body.pairs) if body.pairs else None,
    )
    try:
        result = run_technique(handle.case, handle.run_dir, handle.tooth, handle.row, ask)
    except (AdjustInvalid, AdjustRefused, AlreadyOptimal) as exc:
        _handle(exc)
    payload = result.to_dict()
    payload["case_id"] = handle.case.id
    payload["run_id"] = handle.run_id
    payload["tooth"] = handle.tooth
    payload["signal_groups"] = list(SIGNAL_GROUPS)
    return payload


@router.get("/signal-groups")
def signal_groups() -> dict:
    return {"groups": list(SIGNAL_GROUPS)}
