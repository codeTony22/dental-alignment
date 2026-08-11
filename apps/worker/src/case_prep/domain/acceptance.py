"""The acceptance-numbers catalog: the verification numbers a doctor confirms after alignment.

Every metric pairs OUR measured number (a run-row field) with the industry reference the
doctor already knows ("RealGUIDE ships 0.28 mm avg", "the ±0.5 mm difference-map convention")
and a proposed pass / review / fail band anchored either to a cited industry number or to a
constant the pipeline already enforces — exposing them creates no contract the code doesn't
already honor. Sources per metric are cited inline; the full table lives in the
acceptance-numbers catalog (docs/research/doctor-inputs-research.md,
docs/engagement/alignment-perfection-strategy.md, phase2a-completion-report §6–7,
docs/research/fle-calibration.md, docs/RUN-DEMO.md).

Pure domain: no IO, no framework — a run row (plain dict, as served/persisted in run.json)
in, an evaluation out. Missing values are reported as ``missing``, never silently passed.

FRE≠TRE caveat (rows 1–5): registration/agreement numbers are VERIFICATION numbers (the
industry's difference-map convention), never accuracy guarantees — surface agreement at the
measured points does not bound target error at the platform.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

# Band verdicts (the UI chip states). MISSING is an honest "we did not measure this here" —
# it is never counted as a pass, and evaluate_acceptance lists every missing key in overall.
PASS = "pass"
REVIEW = "review"
FAIL = "fail"
MISSING = "missing"


@dataclass(frozen=True)
class IndustryRef:
    """The reference number the doctor can hold ours against, with its citation."""

    value: str
    source: str


@dataclass(frozen=True)
class Bands:
    """Lower-is-better thresholds: value <= pass_max -> pass; <= review_max -> review;
    beyond -> fail. Metrics with non-scalar verdicts carry their logic in a custom
    evaluator instead (bands is None on the spec)."""

    pass_max: float
    review_max: float


@dataclass(frozen=True)
class MetricSpec:
    key: str
    label: str  # the doctor's language, not the field name
    unit: str
    audience: str  # "doctor" (verification set) | "lab" (QC-facing)
    industry_ref: IndustryRef
    bands: Optional[Bands] = None
    note: Optional[str] = None  # standing caveat shown with the metric


# --- the catalog -----------------------------------------------------------------------
# Order = presentation order. Keys are the wire/UI contract.

CATALOG: Tuple[MetricSpec, ...] = (
    # 1. RealGUIDE's Registration Error dialog ships 0.28 mm avg (docs/RUN-DEMO.md step 4);
    #    our healthy fleet reads ~0.4–0.8. >1.5 is the known-bad-site class.
    MetricSpec(
        key="fit_avg_mm",
        label="Registration error — average",
        unit="mm",
        audience="doctor",
        industry_ref=IndustryRef("RealGUIDE ships 0.28 mm avg", "docs/RUN-DEMO.md step 4"),
        bands=Bands(0.8, 1.5),
    ),
    # 2. RealGUIDE's max reads 2.40 mm (RUN-DEMO); our max structurally lands on screw-recess
    #    points the template's bore can never cover — a gross-outlier tripwire, avg is the
    #    discriminator.
    MetricSpec(
        key="fit_max_mm",
        label="Registration error — worst point",
        unit="mm",
        audience="doctor",
        industry_ref=IndustryRef("RealGUIDE ships 2.40 mm max", "docs/RUN-DEMO.md step 4"),
        bands=Bands(2.5, 4.0),
        note="max lands on screw-recess points the template bore cannot cover — "
             "a gross-outlier tripwire, not the discriminator",
    ),
    # 3. The ±0.5 mm colormap is the industry lab acceptance convention (ZimVie difference-map,
    #    Control-X; strategy §1); 200 µm is the published misfit-acceptability line
    #    (doctor-inputs (b) rank 1, PMC10756734). Exported per run row since 2026-07-24
    #    (panel-completion wave, §8 item 12): the row carries the SAME scalar the map
    #    prints (qc_render.site_deviation_stats — one shared source).
    MetricSpec(
        key="deviation_rms_mm",
        label="Surface deviation map — RMS",
        unit="mm",
        audience="doctor",
        industry_ref=IndustryRef(
            "±0.5 mm map convention; 200 µm misfit-acceptability line",
            "alignment-perfection-strategy §1; PMC10756734"),
        bands=Bands(0.2, 0.5),
        note="the same scalar printed on the deviation map (shared stats source); "
             "cap-footprint inspection band only",
    ),
    # 4. No direct commercial per-site number (survey addendum: exposed scan-body ~38–90 µm vs
    #    coded-healing-abutment 35–425 µm, PMC10724348/PMC12270716). review_max 1.6 IS the
    #    shipped band-refusal gate constant, so the doctor number and the pipeline guard
    #    can't disagree. Submerged sites honestly sit ~1.5 (physics floor).
    MetricSpec(
        key="rim_agreement_mm",
        label="Rim seating agreement (p90)",
        unit="mm",
        audience="doctor",
        industry_ref=IndustryRef(
            "no direct commercial number; scan-body agreement literature 38–425 µm",
            "alignment-algorithm-survey addendum (PMC10724348, PMC12270716)"),
        bands=Bands(0.5, 1.6),
        note="0.5–1.6 needs the submergence flag read alongside; 1.6 is the shipped "
             "band-refusal gate constant; a MACHINE-anchored twin "
             "(rim_agreement_machine_mm, anchored to the island ring — invariant Q2) "
             "is dual-reported on the row since 2026-07-24: this banded value stays "
             "click-anchored until promotion (a deliberate-bounds decision, slice 29)",
    ),
    # 5. No industry per-site equivalent; 1.5 mm p90 is OUR certification ride-off bound
    #    (phase2a-completion-report §6.3) — the fail edge is exactly that bound.
    MetricSpec(
        key="top_face_p90_mm",
        label="Top-face agreement (depth)",
        unit="mm",
        audience="doctor",
        industry_ref=IndustryRef(
            "our certification ride-off bound: 1.5 mm p90",
            "phase2a-completion-report §6.3"),
        bands=Bands(0.75, 1.5),
    ),
    # 6. None external; the shipped centring shift cap is 0.8 mm (§6.3) and the fleet sits at
    #    ~zero (0.000–0.006, §6.4) — >=0.1 is a real regression signal. In the run row
    #    since 2026-07-24 (§8 item 12): auto_flow mirrors the scoreboard's
    #    marks-anchored construction (_rim_off_centre_mm); None without a centre+rim
    #    mark pair — the metric is anchored to the marks, never to the pose it judges.
    MetricSpec(
        key="rim_off_centre_mm",
        label="Rim centring",
        unit="mm",
        audience="lab",
        industry_ref=IndustryRef(
            "no external number; shipped centring cap 0.8 mm",
            "phase2a-completion-report §6.3"),
        bands=Bands(0.1, 0.4),
        note="marks-anchored (scoreboard construction); measured only when the "
             "centre+rim mark pair exists",
    ),
    # 7. Screw-joint literature: <2° stable joint, <5° rotational freedom for optimal
    #    stability, >5° harmful (Binon 1996, PubMed 8639238 + 9171488, web-verified);
    #    coded-cap envelope ~2.9° (PubMed 21453396); phantom goal <=2° exposed. Codes evidence
    #    required for a pass — the recess instrument is phantom-sim-convicted of 6.8–176°
    #    azimuth bias. Custom evaluator.
    MetricSpec(
        key="rotation_deg",
        label="Rotation of the cap (codes line up)",
        unit="deg",
        audience="doctor",
        industry_ref=IndustryRef(
            "<2° stable screw joint; >5° harmful",
            "Binon 1996 (PubMed 8639238, PubMed 9171488)"),
        note="pass needs codes evidence — the recess instrument carries a measured "
             "azimuth bias (phantom sim)",
    ),
    # 8. No industry equivalent — on a rigid part two instruments can't both be right (§7.2).
    #    pass edge = the shipped confirm re-read gate (12°, auto_flow); attention >20° is the
    #    shipped routing rule. An attention router, not a pose judgment.
    MetricSpec(
        key="rotation_consistency_deg",
        label="Two-instrument rotation agreement",
        unit="deg",
        audience="lab",
        industry_ref=IndustryRef(
            "no industry equivalent; our shipped gates (12° re-read, >20° attention)",
            "phase2a-completion-report §7.2"),
        bands=Bands(12.0, 20.0),
        note="an attention router, not a pose judgment, until phantom arbitration",
    ),
    # 9. No industry equivalent. σ is FLE-calibrated (click scatter xy p90 0.61 mm,
    #    fle-calibration.md); the shipped preliminary grade thresholds are fleet-
    #    discriminating, NOT truth-calibrated — the phantom pins them. Custom evaluator
    #    (the grade is already computed upstream; we translate, never re-judge).
    MetricSpec(
        key="confidence_grade",
        label="Confidence grade (pose stability under click noise)",
        unit="",
        audience="doctor",
        industry_ref=IndustryRef(
            "no industry equivalent; σ=0.3 mm FLE-calibrated (click p90 0.61 mm)",
            "docs/research/fle-calibration.md"),
        note="preliminary bands: fleet-discriminating, not truth-calibrated — "
             "phantom validation pending",
    ),
    # 10. The coded-cap standard requires the entire circumference + all markings visible, collar 1–2 mm
    #     (min 1 mm) supragingival, or REJECT/rescan (doctor-inputs (a), vendor-required).
    #     Our proxy today: rim arc occupancy (min_arc_bins=6 of 12 is the seat minimum).
    #     Collar height is not yet measured — arc-only read, custom evaluator.
    MetricSpec(
        key="rim_arc_visibility",
        label="Scan capture — rim visibility",
        unit="arc bins of 12",
        audience="lab",
        industry_ref=IndustryRef(
            "coded-cap standard: full circumference + collar >=1 mm visible, or rescan",
            "doctor-inputs-research (a) [vendor-required]"),
        note="arc-only proxy: collar height is not yet measured; the industry's real "
             "accuracy mechanism is re-capture while the patient is chairside",
    ),
    # 11. The coded-cap standard requires code markings clearly visible or reject; the numeric gates are OURS —
    #     the measured boundary of the validated regime (extractor 6/7 <=10°, §7.1):
    #     notch_corr >= 0.45, prominence >= 0.10 (occupancy >= 0.30 gate lives upstream).
    MetricSpec(
        key="code_band_readability",
        label="Scan capture — code-band readability",
        unit="",
        audience="lab",
        industry_ref=IndustryRef(
            "coded-cap standard: code markings clearly visible or reject; our gates corr>=0.45, "
            "prominence>=0.10",
            "doctor-inputs-research (a); phase2a-completion-report §7.1"),
    ),
    # 12. No industry per-site number (auto-detect ships with human fallback only, survey §2).
    #     0.5 ≈ the measured click p90 (0.61 mm, fle-calibration) — agreement within the
    #     human's own repeatability. Shadow-probe median 0.26 mm vs ship.
    MetricSpec(
        key="machine_agreement_mm",
        label="Machine-vs-doctor cap-location agreement",
        unit="mm",
        audience="doctor",
        industry_ref=IndustryRef(
            "no industry per-site number; pass edge ≈ measured click p90 (0.61 mm)",
            "alignment-algorithm-survey §2; docs/research/fle-calibration.md"),
        bands=Bands(0.5, 1.0),
        note="agreement within the human's own click repeatability",
    ),
    # 13. None external; formalizes the shipped contract (<=0.5 mm OR flagged, per-site
    #     ceilings, §6). Column meaning is degraded on codes-clocked sites until the phantom
    #     arbitrates the void detector's own bias. Scoreboard/report-only today.
    MetricSpec(
        key="bore_void_off_mm",
        label="Screw-recess landing",
        unit="mm",
        audience="lab",
        industry_ref=IndustryRef(
            "no external number; shipped contract <=0.5 mm or flagged",
            "phase2a-completion-report §6"),
        bands=Bands(0.5, 0.75),
        note="per-site ceilings apply above 0.5 (flagged); not yet exported per run row",
    ),
    # 14. MEASURED since 2026-07-24 (DELIBERATE change, master plan §8 item 12 + §1
    #     CONSTRUCT row). Old: placeholder, always "missing" — the deliverable was
    #     unmeasured. New: the G1/G3 chain landed (loop-truth boring + the as-built
    #     channel instrument), auto_flow now measures the emitted product per site
    #     (delivered_channel_offsets, shared with the scoreboard), so the row carries
    #     the number and this metric adopts the screw-recess bands (0.5/0.75) exactly
    #     as this spec's own note promised. Reason: honesty both ways — a fabricated
    #     figure was refused while unmeasured; an evergreen "missing" would be a lie
    #     now that the instrument exists. Custom evaluator (shows vs-cap alongside).
    MetricSpec(
        key="delivered_channel_vs_recess_mm",
        label="Delivered screw channel vs recess",
        unit="mm",
        audience="lab",
        industry_ref=IndustryRef(
            "no external number; screw-recess landing bands adopted (<=0.5 or flagged)",
            "phase2a-completion-report §6; alignment-master-plan CONSTRUCT row"),
        bands=Bands(0.5, 0.75),
        note="measured from the emitted product itself (as-built channel), never an "
             "estimator; recess-dip instrument carries its phantom-noted bias until "
             "arbitration",
    ),
    # 15. Identity is upstream metadata industry-wide (cap kit code, Medit library,
    #     Atlantis WebOrder — survey §2); we are stronger: mandatory declaration + an
    #     independent diameter cross-check. Custom evaluator.
    MetricSpec(
        key="cap_identity",
        label="Cap identity check (declared vs measured)",
        unit="",
        audience="doctor",
        industry_ref=IndustryRef(
            "identity is always upstream metadata (cap kit code, Atlantis WebOrder)",
            "alignment-algorithm-survey §2"),
        note="stronger than the industry norm: mandatory declaration plus an "
             "independent diameter-class cross-check",
    ),
)

_SPEC_BY_KEY: Dict[str, MetricSpec] = {s.key: s for s in CATALOG}

# 16. Explanatory context, not a gate: why the marks are locators. Shown as copy in the
#     verification panel, never as a chip.
CLICK_PRECISION_CONTEXT: Dict[str, Any] = {
    "label": "Operator click precision (context)",
    "text": "Single-operator click scatter xy p50/p68/p90 = 0.32/0.46/0.61 mm; TRE "
            "±0.15 mm at platform over 4 clicks. A 0.6 mm click error can move a "
            "2-click pose 1.09 mm / 16.6° — why marks are locators, not the pose.",
    "industry_ref": {
        "value": "FLE xy p50/p68/p90 = 0.32/0.46/0.61 mm; TRE ±0.15 mm",
        "source": "docs/research/fle-calibration.md; alignment-perfection-strategy §2",
    },
}


# --- evaluation ------------------------------------------------------------------------

def _get(row: Optional[dict], *path: str) -> Any:
    """None-safe nested lookup — a run row from an older cache may miss whole subtrees."""
    cur: Any = row
    for p in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(p)
    return cur


def _as_finite(value: Any) -> Optional[float]:
    """A metric value must be a finite number to be judged — anything else is missing
    (never trust a NaN through a threshold: it compares False and would slip to fail
    or pass depending on band phrasing)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    v = float(value)
    return v if v == v and abs(v) != float("inf") else None


def _banded(value: Optional[float], bands: Bands) -> str:
    if value is None:
        return MISSING
    if value <= bands.pass_max:
        return PASS
    if value <= bands.review_max:
        return REVIEW
    return FAIL


def _fmt(value: Optional[float], unit: str, digits: int = 2) -> Optional[str]:
    if value is None:
        return None
    text = f"{value:.{digits}f}"
    return f"{text} {unit}".strip()


# Shipped code-band evidence gates (e8; phase2a-completion-report §7.1) — the measured
# boundary of the validated regime, mirrored here for the readability verdict.
CODE_GATE_MIN_CORR = 0.45
CODE_GATE_MIN_PROMINENCE = 0.10

# Screw-joint literature thresholds (Binon 1996): <2° stable, >5° harmful.
ROTATION_PASS_MAX_DEG = 2.0
ROTATION_REVIEW_MAX_DEG = 5.0

_CODES_EVIDENCE = ("codes", "codes+recess", "both")

# Full-arc bin count for the rim-visibility read (12 bins = the whole circumference);
# min_arc_bins=6 is the shipped seat minimum.
RIM_ARC_FULL_BINS = 12
RIM_ARC_MIN_BINS = 6


def _eval_rotation(row: dict) -> Tuple[Optional[Any], str, Optional[str]]:
    clocking = row.get("clocking")
    if not isinstance(clocking, dict):
        return None, MISSING, None
    shift = _as_finite(clocking.get("notch_shift_deg"))
    evidence = clocking.get("evidence") or "none"
    display = _fmt(shift, "deg", 1)
    if display is not None:
        display += f" ({evidence})"
    if clocking.get("rotation_unverified") or evidence == "none":
        return shift, FAIL, display or f"unverified ({evidence})"
    if shift is not None and abs(shift) > ROTATION_REVIEW_MAX_DEG:
        return shift, FAIL, display
    if (shift is not None and abs(shift) <= ROTATION_PASS_MAX_DEG
            and evidence in _CODES_EVIDENCE):
        return shift, PASS, display
    # 2–5° with codes evidence, or recess-only evidence at any residual (instrument bias
    # unarbitrated), or a verified rotation whose codes residual read nothing.
    return shift, REVIEW, display or f"no code residual ({evidence})"


def _eval_confidence(row: dict) -> Tuple[Optional[Any], str, Optional[str]]:
    grade = _get(row, "confidence", "grade")
    if grade not in ("high", "medium", "low"):
        return None, MISSING, None
    pos = _as_finite(_get(row, "confidence", "pose_pos_spread_mm"))
    axis = _as_finite(_get(row, "confidence", "pose_axis_spread_deg"))
    display = grade
    if pos is not None and axis is not None:
        display = f"{grade} ({pos:.2f} mm / {axis:.0f} deg spread)"
    band = {"high": PASS, "medium": REVIEW, "low": FAIL}[grade]
    return grade, band, display


def _eval_rim_arc(row: dict) -> Tuple[Optional[Any], str, Optional[str]]:
    bins = _as_finite(row.get("rim_arc_bins"))
    if bins is None:
        return None, MISSING, None
    display = f"{bins:.0f} / {RIM_ARC_FULL_BINS} arc bins"
    if bins >= RIM_ARC_FULL_BINS:
        return bins, PASS, display
    if bins >= RIM_ARC_MIN_BINS:
        return bins, REVIEW, display
    return bins, FAIL, display


def _eval_code_band(row: dict) -> Tuple[Optional[Any], str, Optional[str]]:
    clocking = row.get("clocking")
    if not isinstance(clocking, dict):
        return None, MISSING, None
    corr = _as_finite(clocking.get("notch_corr"))
    prom = _as_finite(clocking.get("notch_prominence"))
    if corr is None or prom is None:
        return None, MISSING, None
    display = f"corr {corr:.2f} / prominence {prom:.2f}"
    if corr >= CODE_GATE_MIN_CORR and prom >= CODE_GATE_MIN_PROMINENCE:
        return corr, PASS, display
    evidence = clocking.get("evidence") or "none"
    if "recess" in evidence:
        return corr, REVIEW, f"{display} — below gates, recess fallback"
    return corr, FAIL, f"{display} — below gates, no fallback"


def _eval_identity(row: dict) -> Tuple[Optional[Any], str, Optional[str]]:
    identified = _get(row, "variant", "identified")
    if not identified:
        return None, MISSING, None
    declared = _get(row, "variant", "declared")
    if not declared:
        # the UI already blocks undeclared runs — an undeclared row here is a fail, never
        # a silent pass (declaration is a required intake field, measured 2026-07-15)
        return "undeclared", FAIL, f"measured {identified}, no declaration"
    display = f"declared {declared} / measured {identified}"
    if str(declared).strip().lower() == str(identified).strip().lower():
        return "match", PASS, display
    return "mismatch", REVIEW, f"{display} — diameter-class disagreement"


def _eval_machine_agreement(row: dict) -> Tuple[Optional[Any], str, Optional[str]]:
    island = row.get("island")
    if isinstance(island, dict):
        off = _as_finite(island.get("machine_centre_offset_mm"))
        if island.get("converged") is False:
            return off, FAIL, ((_fmt(off, "mm") or "no offset") + " — unconverged")
        if off is not None:
            spec = _SPEC_BY_KEY["machine_agreement_mm"]
            return off, _banded(off, spec.bands), _fmt(off, "mm")
    # the demo's Δ auto: distance from the human-marked site to the machine's own proposal
    delta = _as_finite(row.get("auto_delta_mm"))
    spec = _SPEC_BY_KEY["machine_agreement_mm"]
    return delta, _banded(delta, spec.bands), _fmt(delta, "mm")


def _eval_simple(key: str, *path: str) -> Callable[[dict], Tuple[Optional[Any], str, Optional[str]]]:
    """Threshold metric: fetch a finite number at ``path``, judge it against the spec's
    bands, format with the spec's unit."""
    spec = _SPEC_BY_KEY[key]
    assert spec.bands is not None

    def evaluate(row: dict) -> Tuple[Optional[Any], str, Optional[str]]:
        value = _as_finite(_get(row, *path))
        return value, _banded(value, spec.bands), _fmt(value, spec.unit)

    return evaluate


def _eval_delivered_channel(row: dict) -> Tuple[Optional[Any], str, Optional[str]]:
    """Banded on the vs-RECESS number (the patient-facing landing); the vs-cap-channel
    read rides along in the display when present. Row fields are the shared G3
    instrument's own names (auto_flow.delivered_channel_offsets — the scoreboard uses
    the same function, so panel and scoreboard can never disagree)."""
    spec = _SPEC_BY_KEY["delivered_channel_vs_recess_mm"]
    value = _as_finite(row.get("delivered_channel_vs_recess"))
    display = _fmt(value, spec.unit)
    vs_cap = _as_finite(row.get("delivered_channel_vs_cap_channel"))
    if display is not None and vs_cap is not None:
        display += f" (vs cap channel {vs_cap:.2f})"
    return value, _banded(value, spec.bands), display


_EVALUATORS: Dict[str, Callable[[dict], Tuple[Optional[Any], str, Optional[str]]]] = {
    "fit_avg_mm": _eval_simple("fit_avg_mm", "fit", "avg_mm"),
    "fit_max_mm": _eval_simple("fit_max_mm", "fit", "max_mm"),
    "deviation_rms_mm": _eval_simple("deviation_rms_mm", "deviation_rms_mm"),
    "rim_agreement_mm": _eval_simple("rim_agreement_mm", "rim_agreement_mm"),
    "top_face_p90_mm": _eval_simple("top_face_p90_mm", "top_face_agreement_mm"),
    "rim_off_centre_mm": _eval_simple("rim_off_centre_mm", "rim_off_centre"),
    "rotation_deg": _eval_rotation,
    "rotation_consistency_deg": _eval_simple(
        "rotation_consistency_deg", "clocking", "consistency_deg"),
    "confidence_grade": _eval_confidence,
    "rim_arc_visibility": _eval_rim_arc,
    "code_band_readability": _eval_code_band,
    "machine_agreement_mm": _eval_machine_agreement,
    "bore_void_off_mm": _eval_simple("bore_void_off_mm", "bore_void_off"),
    "delivered_channel_vs_recess_mm": _eval_delivered_channel,
    "cap_identity": _eval_identity,
}

_BAND_SEVERITY = {FAIL: 3, REVIEW: 2, PASS: 1, MISSING: 0}


def _spec_payload(spec: MetricSpec) -> Dict[str, Any]:
    return {
        "key": spec.key,
        "label": spec.label,
        "unit": spec.unit,
        "audience": spec.audience,
        "industry_ref": {"value": spec.industry_ref.value, "source": spec.industry_ref.source},
        "bands": ({"pass": spec.bands.pass_max, "review": spec.bands.review_max}
                  if spec.bands is not None else None),
        "note": spec.note,
    }


def evaluate_acceptance(row: dict) -> Dict[str, Any]:
    """Evaluate one run-site row against the catalog.

    Returns ``{"metrics": [...], "overall": {...}, "context": {...}}`` — per metric the
    spec fields plus ``value`` (raw, JSON-serializable), ``display`` (preformatted) and
    ``band`` (pass|review|fail|missing). ``overall.band`` is the worst evaluated band
    (fail > review > pass); metrics that could not be measured are listed in
    ``overall.missing`` and never counted as passes."""
    metrics: List[Dict[str, Any]] = []
    missing: List[str] = []
    counts = {PASS: 0, REVIEW: 0, FAIL: 0, MISSING: 0}
    for spec in CATALOG:
        value, band, display = _EVALUATORS[spec.key](row)
        counts[band] += 1
        if band == MISSING:
            missing.append(spec.key)
        payload = {**_spec_payload(spec),
                   "value": value, "display": display, "band": band}
        # THE BURIED-CODES ADVISORY (§10-AT A2, the client's tooth 20): when the
        # coded band reads below its gates AND rotation stands on no evidence at
        # all, the rotation row itself names the connection and the two honest
        # paths — otherwise the operator reads two unrelated FAILs and hunts
        # rotation by hand against a scan that cannot answer (four looping
        # one-pair fits, measured). Composed HERE, once, so the workspace
        # numbers, the digest and Delivery all speak the same sentence.
        if spec.key == "rotation_deg":
            clocking = row.get("clocking") if isinstance(row.get("clocking"), dict) else {}
            corr = _as_finite(clocking.get("notch_corr"))
            prom = _as_finite(clocking.get("notch_prominence"))
            codes_buried = (corr is not None and prom is not None
                            and (corr < CODE_GATE_MIN_CORR
                                 or prom < CODE_GATE_MIN_PROMINENCE))
            if codes_buried and (clocking.get("evidence") or "none") == "none":
                advisory = ("the coded band is unreadable on this scan (below "
                            "gates), so rotation has no automated evidence — "
                            "place 2+ point pairs on visible features, or "
                            "re-capture chairside")
                payload["note"] = (f"{spec.note} — {advisory}"
                                   if spec.note else advisory)
        metrics.append(payload)
    measured = [m["band"] for m in metrics if m["band"] != MISSING]
    overall_band = (max(measured, key=lambda b: _BAND_SEVERITY[b])
                    if measured else MISSING)
    return {
        "metrics": metrics,
        "overall": {"band": overall_band, "counts": counts, "missing": missing},
        "context": CLICK_PRECISION_CONTEXT,
    }
