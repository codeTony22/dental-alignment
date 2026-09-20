"""THE ADJUST / MCP SIGNAL TAXONOMY — one readout, no invented metrics.

Every group below is a projection over facts the adjust seam already produces:
the run-row, ``evaluate_acceptance``, ``clock_landmarks``, ``seated_payload``,
and an ``AdjustOutcome`` when one exists. Nothing here measures geometry of its
own. A missing instrument is named ``missing``, never filled in.

The group names are the product-owner taxonomy (capture, measurement honesty,
seat, fit, correspondence, certification, residue, …). MCP ``get_site_signals``
and the REST technique result serve this exact envelope so the UI cannot show a
reduced subset by construction.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from case_prep.domain.acceptance import CATALOG, CLICK_PRECISION_CONTEXT, evaluate_acceptance

from .adjust import AdjustOutcome

# The taxonomy the MCP design names. Order is presentation order.
SIGNAL_GROUPS: tuple[str, ...] = (
    "capture",
    "measurement_honesty",
    "seat",
    "fit",
    "correspondence",
    "certification",
    "residue",
    "acceptance",
    "landmarks",
    "clocking",
    "stability",
    "guidance",
)


def _finite(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if number != number or abs(number) == float("inf"):
        return None
    return number


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def outcome_to_dict(outcome: Optional[AdjustOutcome]) -> Optional[Dict[str, Any]]:
    """Every field ``AdjustOutcome`` carries — including the seat-aware ones the
    BFF wire historically omitted. A peer that drops fields is a reduced subset."""
    if outcome is None:
        return None
    return {
        "tooth": outcome.tooth,
        "operation": outcome.operation,
        "detail": outcome.detail,
        "applied": outcome.applied,
        "files": list(outcome.files),
        "clocking": outcome.clocking,
        "deviation": outcome.deviation,
        "stale_metrics": list(outcome.stale_metrics),
        "nudge": outcome.nudge,
        "applied_delta_deg": outcome.applied_delta_deg,
        "cumulative_deg": outcome.cumulative_deg,
        "stability_excess_mm": outcome.stability_excess_mm,
        "best_fit": outcome.best_fit,
        "pairs": list(outcome.pairs),
        "residual_rms_mm": outcome.residual_rms_mm,
        "cross_checked": outcome.cross_checked,
        "translation_mm": outcome.translation_mm,
        "fit_version": outcome.fit_version,
        "seat_branch": outcome.seat_branch,
        "seat_band_mm": outcome.seat_band_mm,
        "click_azimuth_deg": outcome.click_azimuth_deg,
        "matched_feature_azimuth_deg": outcome.matched_feature_azimuth_deg,
        "pane_payload": outcome.pane_payload,
    }


def _capture(row: Dict[str, Any]) -> Dict[str, Any]:
    clocking = _as_dict(row.get("clocking"))
    return {
        "rim_arc_bins": row.get("rim_arc_bins"),
        "rim_arc_visibility": row.get("rim_arc_bins"),
        "code_band": {
            "notch_corr": clocking.get("notch_corr"),
            "notch_prominence": clocking.get("notch_prominence"),
            "evidence": clocking.get("evidence"),
        },
        "seed_source": row.get("seed_source"),
        "coverage": row.get("coverage"),
        "click_precision_context": dict(CLICK_PRECISION_CONTEXT),
    }


def _measurement_honesty(
    row: Dict[str, Any],
    acceptance: Dict[str, Any],
    outcome: Optional[AdjustOutcome],
) -> Dict[str, Any]:
    rework = _as_dict(row.get("rework"))
    stale = [str(m) for m in (rework.get("stale_metrics") or [])]
    if outcome is not None:
        stale = list(outcome.stale_metrics) or stale
    missing = [str(k) for k in (acceptance.get("overall") or {}).get("missing") or []]
    return {
        "stale_metrics": stale,
        "missing_acceptance": missing,
        "cross_checked": None if outcome is None else outcome.cross_checked,
        "residual_rms_mm": None if outcome is None else outcome.residual_rms_mm,
        "advisory": row.get("advisory"),
    }


def _seat(row: Dict[str, Any], outcome: Optional[AdjustOutcome]) -> Dict[str, Any]:
    return {
        "seat_method": row.get("seat_method"),
        "rim_agreement_mm": row.get("rim_agreement_mm"),
        "rim_agreement_machine_mm": row.get("rim_agreement_machine_mm"),
        "rim_off_centre_mm": row.get("rim_off_centre_mm") or row.get("rim_off_centre"),
        "top_face_p90_mm": row.get("top_face_p90_mm") or row.get("top_face_agreement_mm"),
        "seat_branch": None if outcome is None else outcome.seat_branch,
        "seat_band_mm": None if outcome is None else outcome.seat_band_mm,
    }


def _fit(row: Dict[str, Any], outcome: Optional[AdjustOutcome]) -> Dict[str, Any]:
    fit = _as_dict(row.get("fit"))
    return {
        "fit_avg_mm": fit.get("avg_mm") or row.get("fit_avg_mm"),
        "fit_max_mm": fit.get("max_mm") or row.get("fit_max_mm"),
        "n": fit.get("n"),
        "icp_fitness": row.get("icp_fitness"),
        "best_fit": None if outcome is None else outcome.best_fit,
        "row_best_fit": row.get("best_fit"),
    }


def _correspondence(row: Dict[str, Any], outcome: Optional[AdjustOutcome]) -> Dict[str, Any]:
    block = _as_dict(row.get("correspondence"))
    raw_pairs = block.get("pairs")
    if outcome is not None:
        pairs = list(outcome.pairs)
    elif isinstance(raw_pairs, list):
        pairs = list(raw_pairs)
    else:
        pairs = []
    if isinstance(raw_pairs, int):
        pair_count: Optional[int] = raw_pairs
    else:
        pair_count = len(pairs) or None
    return {
        "pairs": pairs,
        "pair_count": pair_count,
        "residual_rms_mm": (
            None if outcome is None else outcome.residual_rms_mm
        ) if outcome is not None else block.get("residual_rms_mm"),
        "cross_checked": (
            None if outcome is None else outcome.cross_checked
        ) if outcome is not None else block.get("cross_checked"),
        "fit_version": None if outcome is None else outcome.fit_version,
        "translation_mm": None if outcome is None else outcome.translation_mm,
        "click_azimuth_deg": None if outcome is None else outcome.click_azimuth_deg,
        "matched_feature_azimuth_deg": (
            None if outcome is None else outcome.matched_feature_azimuth_deg
        ),
    }


def _certification(row: Dict[str, Any]) -> Dict[str, Any]:
    guidance = _as_dict(row.get("guidance"))
    clocking = _as_dict(row.get("clocking"))
    confidence = _as_dict(row.get("confidence"))
    variant = _as_dict(row.get("variant"))
    return {
        "guidance_level": guidance.get("level"),
        "rotation_unverified": clocking.get("rotation_unverified"),
        "clock_evidence": clocking.get("evidence"),
        "confidence_grade": confidence.get("grade"),
        "auto_delta_mm": row.get("auto_delta_mm"),
        "alignment_error_mm": row.get("alignment_error_mm"),
        "cap_identity": {
            "declared": variant.get("declared"),
            "identified": variant.get("identified"),
            "measured_rim_diameter_mm": variant.get("measured_rim_diameter_mm"),
            "flags": list(variant.get("flags") or []),
        },
        "bore_void_off_mm": row.get("bore_void_off_mm"),
        "delivered_channel_vs_recess_mm": row.get("delivered_channel_vs_recess"),
    }


def _residue(row: Dict[str, Any], outcome: Optional[AdjustOutcome]) -> Dict[str, Any]:
    deviation = {} if outcome is None else _as_dict(outcome.deviation)
    return {
        "deviation_rms_mm": deviation.get("deviation_rms_mm", row.get("deviation_rms_mm")),
        "deviation_p90_mm": deviation.get("deviation_p90_mm", row.get("deviation_p90_mm")),
        "site_measurement": row.get("site_measurement"),
    }


def _clocking(row: Dict[str, Any], outcome: Optional[AdjustOutcome]) -> Dict[str, Any]:
    clocking = dict(_as_dict(row.get("clocking")))
    if outcome is not None and outcome.clocking:
        clocking.update(outcome.clocking)
    if outcome is not None:
        clocking["applied_delta_deg"] = outcome.applied_delta_deg
        clocking["cumulative_deg"] = outcome.cumulative_deg
        clocking["nudge"] = outcome.nudge
    return clocking


def _stability(row: Dict[str, Any], outcome: Optional[AdjustOutcome]) -> Dict[str, Any]:
    confidence = _as_dict(row.get("confidence"))
    return {
        "stability_excess_mm": None if outcome is None else outcome.stability_excess_mm,
        "confidence_grade": confidence.get("grade"),
        "confidence": confidence,
    }


def _guidance(row: Dict[str, Any]) -> Dict[str, Any]:
    guidance = _as_dict(row.get("guidance"))
    return {
        "level": guidance.get("level"),
        "actions": list(guidance.get("actions") or []),
    }


def assemble_site_signals(
    row: Dict[str, Any],
    *,
    landmarks: Optional[List[dict]] = None,
    seated: Optional[dict] = None,
    outcome: Optional[AdjustOutcome] = None,
    landmarks_error: Optional[str] = None,
    seated_error: Optional[str] = None,
) -> Dict[str, Any]:
    """The full taxonomy. ``landmarks`` / ``seated`` are passed in when the
    caller already paid for a mesh read; omitted keys stay ``missing`` rather
    than being guessed. Acceptance is always derived from ``row`` — the catalog
    never needs a mesh.
    """
    acceptance = evaluate_acceptance(row)
    groups = {
        "capture": _capture(row),
        "measurement_honesty": _measurement_honesty(row, acceptance, outcome),
        "seat": _seat(row, outcome),
        "fit": _fit(row, outcome),
        "correspondence": _correspondence(row, outcome),
        "certification": _certification(row),
        "residue": _residue(row, outcome),
        "acceptance": {
            "overall_band": (acceptance.get("overall") or {}).get("band"),
            "missing": list((acceptance.get("overall") or {}).get("missing") or []),
            "metrics": list(acceptance.get("metrics") or []),
            "context": dict(acceptance.get("context") or {}),
            "catalog_keys": [spec.key for spec in CATALOG],
        },
        "landmarks": {
            "items": list(landmarks or []),
            "missing": landmarks is None,
            "error": landmarks_error,
        },
        "clocking": _clocking(row, outcome),
        "stability": _stability(row, outcome),
        "guidance": _guidance(row),
    }
    if seated is not None:
        groups["seated"] = seated
    elif seated_error is not None:
        groups["seated"] = {"missing": True, "error": seated_error}
    else:
        groups["seated"] = {"missing": True}
    return {
        "tooth": row.get("tooth"),
        "groups": groups,
        "group_names": list(SIGNAL_GROUPS),
        "outcome": outcome_to_dict(outcome),
    }
