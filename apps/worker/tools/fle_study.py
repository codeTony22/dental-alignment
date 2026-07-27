"""Operator centre-click FLE (fiducial localization error) study — turnkey ~10-minute
protocol + analysis.

WHY: `docs/research/fle-calibration.md` calibrated `_pose_stability_bootstrap`'s
`sigma_mm=0.3` (`src/case_prep/pipeline/auto_flow.py`) from BORDER-click (`rim_points`)
repeat-click scatter. It found the CENTRE-click channel (`center_mark`) supplied ZERO
usable data: every pair-type (`center_mark`+`rim_mark`) entry in
`reports/live-demo/run-history.jsonl` was a byte-identical replay of the site's static
`data/real/scans/*/sites.json` curation, not a fresh operator click (see that doc's S1,
"Finding that reshapes the method"). A centre click resolves through a hit-anchored ball
percentile (the cap centre is a screw-recess hole) — a different motor task with its own
error distribution, distinct from tracing a border ring. This tool makes it turnkey to
collect and analyze real centre-click repeat data.

Two subcommands:

    .venv/bin/python tools/fle_study.py instructions
    .venv/bin/python tools/fle_study.py analyze [--since ISO_TS | --after-line N] [--write]

CLI is a thin wrapper — every analysis function below is pure/importable and covered by
`tests/test_fle_study.py`.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

WORKER_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = WORKER_ROOT.parents[1]

DEFAULT_HISTORY = WORKER_ROOT / "reports" / "live-demo" / "run-history.jsonl"
DEFAULT_SCANS_DIR = WORKER_ROOT / "data" / "real" / "scans"
DEFAULT_DOC = REPO_ROOT / "docs" / "research" / "fle-calibration.md"

# The 3-4 demo cases with a real, addressable healing-cap site (doctor-<case_id>/sites.json)
# — matches the case ids the live-demo UI actually exposes.
STUDY_CASES: Tuple[Tuple[str, int], ...] = (
    ("276794487-zimmer-4.5", 3),
    ("295811960-neodent-gm", 29),
    ("297589851-neodent-gm", 20),
    ("cap6030-neodent-gm", 29),
)

SLIP_THRESHOLD_MM = 2.0
MIN_N_FOR_PERCENTILES = 4
CURATED_REPLAY_TOL_MM = 1e-6
BASELINE_SIGMA_MM = 0.3
BASELINE_REL_TOL = 0.15  # +/-15% band counted as "holds"

Point3 = Tuple[float, float, float]


# --------------------------------------------------------------------------------------
# Loading run-history.jsonl
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class RunRecord:
    line_no: int  # 1-based line number in the jsonl file
    ts: str
    case_id: str
    sites_in: List[dict]


def count_lines(history_path: Path) -> int:
    """Number of non-blank lines currently in run-history.jsonl (0 if the file doesn't
    exist yet) — the "starting point" an operator notes before a study session."""
    if not history_path.exists():
        return 0
    with history_path.open() as f:
        return sum(1 for line in f if line.strip())


def load_run_history(history_path: Path) -> List[RunRecord]:
    """Parse every JSON line into a RunRecord, tagged with its 1-based line number.
    Malformed lines are skipped rather than raising — history must never block analysis."""
    records: List[RunRecord] = []
    if not history_path.exists():
        return records
    with history_path.open() as f:
        for line_no, raw_line in enumerate(f, start=1):
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                raw = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            records.append(RunRecord(
                line_no=line_no,
                ts=raw.get("ts", ""),
                case_id=raw.get("case_id", ""),
                sites_in=raw.get("sites_in") or [],
            ))
    return records


def filter_range(records: List[RunRecord], since: Optional[str] = None,
                  after_line: Optional[int] = None) -> List[RunRecord]:
    """Keep only records at/after `since` (ISO timestamp, inclusive) and/or strictly after
    `after_line` (1-based line number, exclusive of that line itself)."""
    out = records
    if after_line is not None:
        out = [r for r in out if r.line_no > after_line]
    if since is not None:
        since_dt = datetime.fromisoformat(since)
        out = [r for r in out
               if r.ts and _safe_parse_ts(r.ts) is not None and _safe_parse_ts(r.ts) >= since_dt]
    return out


def _safe_parse_ts(ts: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


# --------------------------------------------------------------------------------------
# Site reference (curated sites.json values), for curated-replay exclusion
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class SiteReference:
    center_mark: Optional[Point3]
    center: Optional[Point3]
    rim_mark: Optional[Point3]


def _as_point(v: Optional[list]) -> Optional[Point3]:
    if not v:
        return None
    return (float(v[0]), float(v[1]), float(v[2]))


def load_site_references(scans_dir: Path) -> Dict[Tuple[str, int], SiteReference]:
    """Read every `doctor-*/sites.json` under `scans_dir` into a (case_id, tooth) ->
    SiteReference lookup, used to detect curated-replay marks."""
    refs: Dict[Tuple[str, int], SiteReference] = {}
    if not scans_dir.exists():
        return refs
    for sites_json in sorted(scans_dir.glob("doctor-*/sites.json")):
        case_id = sites_json.parent.name[len("doctor-"):]
        try:
            data = json.loads(sites_json.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        for s in data.get("suggested_sites", []):
            tooth = s.get("tooth")
            if tooth is None:
                continue
            refs[(case_id, int(tooth))] = SiteReference(
                center_mark=_as_point(s.get("center_mark")),
                center=_as_point(s.get("center")),
                rim_mark=_as_point(s.get("rim_mark")),
            )
    return refs


def _allclose(a: Point3, b: Point3, tol: float) -> bool:
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def _is_curated_replay(value: Point3, ref: Optional[SiteReference], field_name: str,
                        tol: float = CURATED_REPLAY_TOL_MM) -> bool:
    if ref is None:
        return False
    if field_name == "center_mark":
        candidates = [ref.center_mark, ref.center]
    elif field_name == "rim_mark":
        candidates = [ref.rim_mark]
    else:
        raise ValueError(f"unknown field_name {field_name!r}")
    return any(c is not None and _allclose(value, c, tol) for c in candidates)


# --------------------------------------------------------------------------------------
# Fresh-click extraction (curated-replay exclusion + consecutive-duplicate dedupe)
# --------------------------------------------------------------------------------------

SiteKey = Tuple[str, int]


@dataclass(frozen=True)
class FreshMark:
    ts: str
    line_no: int
    value: Point3


@dataclass
class SiteExtraction:
    case_id: str
    tooth: int
    fresh: List[FreshMark] = field(default_factory=list)
    curated_excluded: int = 0
    duplicate_excluded: int = 0
    derived_excluded: int = 0


def extract_fresh_marks(records: List[RunRecord], refs: Dict[SiteKey, SiteReference],
                         field_name: str) -> Dict[SiteKey, SiteExtraction]:
    """For every (case_id, tooth) site, walk its `field_name` (`"center_mark"` or
    `"rim_mark"`) values in file order and keep only genuinely fresh clicks:

    - THE KEY TRAP (fle-calibration.md S1): when a submission is a border-click gesture
      (`rim_points` present), its `center_mark` is NOT the operator's centre click at all
      -- it's an unrelated derived value (the existing study found it differs from both
      the pair's static centre and the border centroid by up to 1.3mm in z) left over from
      a different code path. Any site entry with `rim_points` set is excluded from the
      centre-click (`center_mark`) channel entirely, for the same reason a curated replay
      is excluded: it is not a real ⊕ centre-click aim.
    - a value byte-identical (within 1e-6mm) to the immediately preceding raw value for
      that site is a cache re-submission (Recompute without a new click) -> dropped, and
      does NOT reset the "last seen" tracker (still the same physical click).
    - a value byte-identical (within 1e-6mm) to the site's static sites.json curation
      (`center_mark` or `center` for the centre channel, `rim_mark` for the rim channel)
      is a curated replay, never an operator click -> dropped.
    - everything else is a fresh click.
    """
    sites: Dict[SiteKey, SiteExtraction] = {}
    last_raw: Dict[SiteKey, Point3] = {}
    for rec in records:
        for s in rec.sites_in:
            tooth = s.get("tooth")
            if tooth is None:
                continue
            raw = s.get(field_name)
            if raw is None:
                continue
            value = _as_point(raw)
            if value is None:
                continue
            key: SiteKey = (rec.case_id, int(tooth))
            entry = sites.setdefault(key, SiteExtraction(case_id=rec.case_id, tooth=int(tooth)))

            if field_name == "center_mark" and s.get("rim_points"):
                entry.derived_excluded += 1
                continue

            prev = last_raw.get(key)
            if prev is not None and _allclose(value, prev, CURATED_REPLAY_TOL_MM):
                entry.duplicate_excluded += 1
                continue

            last_raw[key] = value
            if _is_curated_replay(value, refs.get(key), field_name):
                entry.curated_excluded += 1
                continue

            entry.fresh.append(FreshMark(ts=rec.ts, line_no=rec.line_no, value=value))
    return sites


# --------------------------------------------------------------------------------------
# Per-site occlusal-plane (xy) scatter, slip flagging, percentiles
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Percentiles:
    n: int
    p50: float
    p68: float
    p90: float
    max: float


def compute_percentiles(deviations_mm: List[float]) -> Optional[Percentiles]:
    if not deviations_mm:
        return None
    arr = np.asarray(deviations_mm, dtype=float)
    return Percentiles(
        n=len(arr),
        p50=float(np.percentile(arr, 50)),
        p68=float(np.percentile(arr, 68)),
        p90=float(np.percentile(arr, 90)),
        max=float(arr.max()),
    )


@dataclass(frozen=True)
class Slip:
    ts: str
    line_no: int
    deviation_mm: float


@dataclass(frozen=True)
class SiteScatter:
    case_id: str
    tooth: int
    n_fresh: int  # all fresh clicks, before slip removal
    centroid_xy: Optional[Tuple[float, float]]
    core_deviations_mm: List[float]  # slip-excluded xy radial deviations from centroid
    slips: List[Slip]
    percentiles: Optional[Percentiles]  # over core_deviations_mm
    insufficient: bool  # n_core < MIN_N_FOR_PERCENTILES


def compute_site_scatter(case_id: str, tooth: int, marks: List[FreshMark]) -> SiteScatter:
    """Occlusal-plane (xy) scatter of `marks` about their own robust (median) centroid —
    matches the border-click study's method (per-position deviation from that position's
    own median centre across its repeats). Points >2mm from the centroid are flagged as
    slips and excluded from the core distribution."""
    if not marks:
        return SiteScatter(case_id, tooth, 0, None, [], [], None, True)

    xy = np.array([[m.value[0], m.value[1]] for m in marks], dtype=float)
    centroid = np.median(xy, axis=0)
    deviations = np.linalg.norm(xy - centroid, axis=1)

    core_devs: List[float] = []
    slips: List[Slip] = []
    for mark, dev in zip(marks, deviations):
        dev = float(dev)
        if dev > SLIP_THRESHOLD_MM:
            slips.append(Slip(ts=mark.ts, line_no=mark.line_no, deviation_mm=dev))
        else:
            core_devs.append(dev)

    pct = compute_percentiles(core_devs)
    return SiteScatter(
        case_id=case_id, tooth=tooth, n_fresh=len(marks),
        centroid_xy=(float(centroid[0]), float(centroid[1])),
        core_deviations_mm=core_devs, slips=slips, percentiles=pct,
        insufficient=len(core_devs) < MIN_N_FOR_PERCENTILES,
    )


def pooled_percentiles(site_scatters: Dict[SiteKey, SiteScatter]) -> Optional[Percentiles]:
    """Pool every site's core (slip-excluded) deviations into one distribution — the
    headline "pooled centre-click FLE" number, same construction as the border study's
    "per-position repeat-click xy scatter, pooled across gestures" table."""
    pooled: List[float] = []
    for scatter in site_scatters.values():
        pooled.extend(scatter.core_deviations_mm)
    return compute_percentiles(pooled)


# --------------------------------------------------------------------------------------
# Sigma inversion (Rayleigh radial scatter -> per-axis Gaussian sigma)
# --------------------------------------------------------------------------------------

def invert_sigma(radial_mm: float, pct: float) -> float:
    """`_pose_stability_bootstrap` perturbs marks with an i.i.d. per-axis Gaussian, so xy
    radial deviation follows a Rayleigh distribution with scale `sigma`. Inverting a
    percentile: `sigma = r / sqrt(-2 * ln(1 - pct))` (fle-calibration.md S4's method;
    at pct=0.68 this is `r / 1.509...`, i.e. the "sigma ~= p68_radial / 1.51" shorthand)."""
    if not (0.0 < pct < 1.0):
        raise ValueError(f"pct must be in (0, 1), got {pct}")
    return radial_mm / math.sqrt(-2.0 * math.log(1.0 - pct))


@dataclass(frozen=True)
class SigmaEstimate:
    at_p50: float
    at_p68: float
    at_p90: float
    mean: float


def sigma_estimate(pct: Percentiles) -> SigmaEstimate:
    at_p50 = invert_sigma(pct.p50, 0.50)
    at_p68 = invert_sigma(pct.p68, 0.68)
    at_p90 = invert_sigma(pct.p90, 0.90)
    return SigmaEstimate(at_p50=at_p50, at_p68=at_p68, at_p90=at_p90,
                          mean=statistics.mean([at_p50, at_p68, at_p90]))


def sigma_verdict(measured_sigma_mm: Optional[float], baseline_mm: float = BASELINE_SIGMA_MM,
                   rel_tol: float = BASELINE_REL_TOL) -> str:
    if measured_sigma_mm is None:
        return (f"insufficient centre-click data to compare against the sigma_mm={baseline_mm} "
                f"default — no verdict.")
    lo, hi = baseline_mm * (1 - rel_tol), baseline_mm * (1 + rel_tol)
    if lo <= measured_sigma_mm <= hi:
        return (f"**sigma_mm={baseline_mm} holds for the centre-click channel too** "
                f"(measured {measured_sigma_mm:.3f}mm, within +/-{rel_tol:.0%} of {baseline_mm}mm).")
    direction = "higher" if measured_sigma_mm > baseline_mm else "lower"
    return (f"**data implies a {direction} per-axis sigma for centre clicks: "
            f"~{measured_sigma_mm:.3f}mm** (current default {baseline_mm}mm). "
            f"Recommendation only — no production default changed by this tool.")


# --------------------------------------------------------------------------------------
# Border (rim_points) bonus data — counted and deferred to the existing study, not
# re-analyzed here (that would duplicate fle-calibration.md's own method/scope).
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class RimPointsGesture:
    ts: str
    line_no: int
    case_id: str
    tooth: int
    n_points: int


def collect_fresh_rim_points_gestures(records: List[RunRecord]) -> List[RimPointsGesture]:
    """Multi-point border-click (`rim_points`) gestures in range, deduped against an
    immediately-repeated identical gesture for the same site (cache re-submission)."""
    out: List[RimPointsGesture] = []
    last_raw: Dict[SiteKey, list] = {}
    for rec in records:
        for s in rec.sites_in:
            tooth = s.get("tooth")
            rp = s.get("rim_points")
            if tooth is None or not rp:
                continue
            key: SiteKey = (rec.case_id, int(tooth))
            if key in last_raw and _points_allclose(rp, last_raw[key]):
                continue
            last_raw[key] = rp
            out.append(RimPointsGesture(ts=rec.ts, line_no=rec.line_no, case_id=rec.case_id,
                                         tooth=int(tooth), n_points=len(rp)))
    return out


def _points_allclose(a: list, b: list, tol: float = CURATED_REPLAY_TOL_MM) -> bool:
    if len(a) != len(b):
        return False
    return all(_allclose(_as_point(pa), _as_point(pb), tol) for pa, pb in zip(a, b))


# --------------------------------------------------------------------------------------
# Top-level analysis
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class ChannelResult:
    site_extractions: Dict[SiteKey, SiteExtraction]
    site_scatters: Dict[SiteKey, SiteScatter]
    pooled: Optional[Percentiles]
    pooled_all_incl_slips: Optional[Percentiles]
    sigma: Optional[SigmaEstimate]
    n_fresh_total: int
    n_slips_total: int


@dataclass(frozen=True)
class AnalysisResult:
    since: Optional[str]
    after_line: Optional[int]
    n_records_total: int
    n_records_in_range: int
    center: ChannelResult
    rim: ChannelResult
    rim_points_gestures: List[RimPointsGesture]
    verdict: str
    has_fresh_data: bool


def _channel_result(records: List[RunRecord], refs: Dict[SiteKey, SiteReference],
                     field_name: str) -> ChannelResult:
    extractions = extract_fresh_marks(records, refs, field_name)
    scatters = {key: compute_site_scatter(key[0], key[1], ext.fresh)
                for key, ext in extractions.items()}
    pooled = pooled_percentiles(scatters)
    all_devs: List[float] = []
    n_slips_total = 0
    for scatter in scatters.values():
        all_devs.extend(scatter.core_deviations_mm)
        all_devs.extend(s.deviation_mm for s in scatter.slips)
        n_slips_total += len(scatter.slips)
    pooled_all = compute_percentiles(all_devs)
    # a pooled n below the per-site insufficiency bar produces a degenerate/meaningless
    # sigma estimate (e.g. n=1 -> zero deviation from its own centroid) -- withhold it
    # rather than print a spuriously precise-looking number.
    sigma = (sigma_estimate(pooled)
             if pooled is not None and pooled.n >= MIN_N_FOR_PERCENTILES else None)
    n_fresh_total = sum(len(ext.fresh) for ext in extractions.values())
    return ChannelResult(
        site_extractions=extractions, site_scatters=scatters, pooled=pooled,
        pooled_all_incl_slips=pooled_all, sigma=sigma,
        n_fresh_total=n_fresh_total, n_slips_total=n_slips_total,
    )


def analyze(history_path: Path, scans_dir: Path, since: Optional[str] = None,
            after_line: Optional[int] = None) -> AnalysisResult:
    all_records = load_run_history(history_path)
    records = filter_range(all_records, since=since, after_line=after_line)
    refs = load_site_references(scans_dir)

    center = _channel_result(records, refs, "center_mark")
    rim = _channel_result(records, refs, "rim_mark")
    rim_points_gestures = collect_fresh_rim_points_gestures(records)

    has_fresh_data = center.n_fresh_total > 0 or rim.n_fresh_total > 0
    center_sigma_mean = center.sigma.mean if center.sigma is not None else None
    verdict = sigma_verdict(center_sigma_mean)

    return AnalysisResult(
        since=since, after_line=after_line,
        n_records_total=len(all_records), n_records_in_range=len(records),
        center=center, rim=rim, rim_points_gestures=rim_points_gestures,
        verdict=verdict, has_fresh_data=has_fresh_data,
    )


# --------------------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------------------

NO_DATA_MESSAGE = "no new study data — run `instructions` and click first"


def _fmt_mm(x: Optional[float]) -> str:
    return "-" if x is None else f"{x:.3f}mm"


def _site_table(site_scatters: Dict[SiteKey, SiteScatter],
                 extractions: Dict[SiteKey, SiteExtraction]) -> str:
    if not site_scatters:
        return "_(no sites with any fresh marks in range)_\n"
    lines = [
        "| case | tooth | n fresh | curated excl. | dup excl. | border-derived excl. | n core | "
        "n slips | p50 | p68 | p90 | max | note |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for key in sorted(site_scatters.keys()):
        scatter = site_scatters[key]
        ext = extractions.get(key)
        curated = ext.curated_excluded if ext else 0
        dup = ext.duplicate_excluded if ext else 0
        derived = ext.derived_excluded if ext else 0
        pct = scatter.percentiles
        note = "insufficient (n<4)" if scatter.insufficient else "ok"
        lines.append(
            f"| {scatter.case_id} | t{scatter.tooth} | {scatter.n_fresh} | {curated} | {dup} | "
            f"{derived} | {len(scatter.core_deviations_mm)} | {len(scatter.slips)} | "
            f"{_fmt_mm(pct.p50 if pct else None)} | {_fmt_mm(pct.p68 if pct else None)} | "
            f"{_fmt_mm(pct.p90 if pct else None)} | {_fmt_mm(pct.max if pct else None)} | {note} |"
        )
    return "\n".join(lines) + "\n"


def _slip_table(site_scatters: Dict[SiteKey, SiteScatter]) -> str:
    rows = []
    for key in sorted(site_scatters.keys()):
        scatter = site_scatters[key]
        for s in scatter.slips:
            rows.append((scatter.case_id, scatter.tooth, s.ts, s.line_no, s.deviation_mm))
    if not rows:
        return "_(no slips >2mm flagged)_\n"
    lines = ["| case | tooth | ts | line | xy deviation |", "|---|---:|---|---:|---:|"]
    for case_id, tooth, ts, line_no, dev in rows:
        lines.append(f"| {case_id} | t{tooth} | {ts} | {line_no} | {dev:.3f}mm |")
    return "\n".join(lines) + "\n"


def _pooled_block(label: str, channel: ChannelResult) -> str:
    if channel.pooled is None:
        return f"**{label} pooled:** no fresh clicks in range.\n"
    p = channel.pooled
    p_all = channel.pooled_all_incl_slips
    out = [
        f"**{label} pooled (core, slips excluded):** n={p.n}  "
        f"p50={_fmt_mm(p.p50)}  p68={_fmt_mm(p.p68)}  p90={_fmt_mm(p.p90)}  max={_fmt_mm(p.max)}",
    ]
    if p_all is not None and p_all.n != p.n:
        out.append(
            f"**{label} pooled (all, slips included):** n={p_all.n}  "
            f"p50={_fmt_mm(p_all.p50)}  p68={_fmt_mm(p_all.p68)}  p90={_fmt_mm(p_all.p90)}  "
            f"max={_fmt_mm(p_all.max)}"
        )
    if channel.sigma is not None:
        s = channel.sigma
        out.append(
            f"**{label} implied sigma_mm** (inverted Rayleigh, `r / sqrt(-2*ln(1-pct))`): "
            f"@p50={s.at_p50:.3f}  @p68={s.at_p68:.3f}  @p90={s.at_p90:.3f}  mean={s.mean:.3f}"
        )
    elif p.n < MIN_N_FOR_PERCENTILES:
        out.append(
            f"**{label} implied sigma_mm:** withheld — pooled n={p.n} is below the n>=4 "
            f"floor for a percentile-based estimate to mean anything."
        )
    return "\n\n".join(out) + "\n"


def render_report(result: AnalysisResult, generated_at: Optional[str] = None) -> str:
    """Full markdown section, including the dated H2 header. `generated_at` defaults to
    today's date; pass an explicit value for deterministic tests."""
    date_str = generated_at or datetime.now().strftime("%Y-%m-%d")
    scope_bits = []
    if result.since:
        scope_bits.append(f"since {result.since}")
    if result.after_line is not None:
        scope_bits.append(f"after line {result.after_line}")
    scope = ", ".join(scope_bits) if scope_bits else "entire run-history.jsonl"

    lines: List[str] = []
    lines.append(f"## Centre-click channel (study of {date_str})")
    lines.append("")
    lines.append(
        f"Scope: {scope}. {result.n_records_in_range}/{result.n_records_total} run-history "
        f"records considered. Method matches this document's S2 (per-position repeat-click "
        f"xy scatter about a robust median centroid, >2mm flagged as a slip and excluded from "
        f"core, Rayleigh sigma inversion) — see `tools/fle_study.py` for the exact functions. "
        f"Per S1's trap, `center_mark` values logged alongside a `rim_points` border gesture "
        f"are excluded from the centre-click channel (\"border-derived excl.\" below) — that "
        f"field is a derived artifact of the border-click path, not a ⊕ centre-click aim."
    )
    lines.append("")

    if not result.has_fresh_data:
        lines.append(NO_DATA_MESSAGE)
        lines.append("")
        return "\n".join(lines)

    lines.append("### Centre-click (`center_mark`) sites")
    lines.append("")
    lines.append(_site_table(result.center.site_scatters, result.center.site_extractions))
    lines.append("")
    lines.append(_pooled_block("Centre-click", result.center))
    lines.append("")
    lines.append("Slips (centre-click, >2mm, excluded from core above):")
    lines.append("")
    lines.append(_slip_table(result.center.site_scatters))
    lines.append("")

    lines.append("### Rim-click (`rim_mark`) sites — bonus pair-channel data")
    lines.append("")
    lines.append(_site_table(result.rim.site_scatters, result.rim.site_extractions))
    lines.append("")
    lines.append(_pooled_block("Rim-click", result.rim))
    lines.append("")
    lines.append("Slips (rim-click, >2mm, excluded from core above):")
    lines.append("")
    lines.append(_slip_table(result.rim.site_scatters))
    lines.append("")

    lines.append("### Border (`rim_points`) gestures observed in range")
    lines.append("")
    if result.rim_points_gestures:
        lines.append(
            f"{len(result.rim_points_gestures)} fresh multi-point border gesture(s) logged in "
            f"range. This tool does not re-run the border-click Kasa/leave-one-out analysis — "
            f"that channel is already calibrated in this document's own primary study (S3, "
            f"n=27-40 clicks). Listed for awareness only:"
        )
        lines.append("")
        lines.append("| case | tooth | ts | line | n points |")
        lines.append("|---|---:|---|---:|---:|")
        for g in result.rim_points_gestures:
            lines.append(f"| {g.case_id} | t{g.tooth} | {g.ts} | {g.line_no} | {g.n_points} |")
    else:
        lines.append("_(none in range)_")
    lines.append("")

    lines.append("### Verdict")
    lines.append("")
    lines.append(result.verdict)
    lines.append("")

    return "\n".join(lines)


def append_to_doc(markdown_section: str, doc_path: Path) -> None:
    """Append `markdown_section` to `doc_path`, never touching existing content — the
    agreed convention for a study dated after fle-calibration.md's original authorship."""
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    existing = doc_path.read_text() if doc_path.exists() else ""
    prefix = "" if (not existing or existing.endswith("\n\n")) else (
        "\n" if existing.endswith("\n") else "\n\n"
    )
    with doc_path.open("a") as f:
        f.write(prefix + markdown_section.rstrip("\n") + "\n")


# --------------------------------------------------------------------------------------
# `instructions` subcommand
# --------------------------------------------------------------------------------------

def render_instructions(line_count: int) -> str:
    case_lines = "\n".join(f"  {i}. {case_id}  (tooth {tooth})"
                            for i, (case_id, tooth) in enumerate(STUDY_CASES, start=1))
    return f"""Operator centre-click FLE study — ~10 minutes, {len(STUDY_CASES)} cases.

WHY: the confidence bootstrap's click-noise number (sigma_mm=0.3) was calibrated from
BORDER clicks only (docs/research/fle-calibration.md) — the centre-click (⊕) channel has
never had a single fresh click logged; every pair entry on file is a byte-identical replay
of the curated sites.json marks. A centre click resolves through a hit-anchored ball
percentile (the cap centre is a screw-recess hole) -- a different motor task from tracing a
border ring, worth measuring on its own.

run-history.jsonl currently has {line_count} lines. Note that number now — after clicking,
run:

    .venv/bin/python tools/fle_study.py analyze --after-line {line_count}

PROTOCOL (repeat for each case below):
{case_lines}

For each case:
  1. Open the case in the live-demo UI and step through to step 3 (Confirm).
  2. Click ⊕ centre FRESH, aiming at the cap's top centre.
  3. Press "Recompute alignment" (every Recompute logs the exact gesture to
     run-history.jsonl -- that's the data this study reads).
  4. Repeat steps 2-3 six to eight (6-8) times for this case.
  5. OPTIONAL, bonus pair data: also re-click the rim mark each round before Recompute.

IMPORTANT -- aim genuinely each time:
  - Do NOT try to click the exact same pixel twice. Aim fresh, as you naturally would.
  - Work at your normal pace -- don't slow down or speed up for the study.
  - Use whatever camera angle you'd naturally use to see the cap; rotate between clicks
    if that's normal for you.
  - The study measures YOUR real operating precision -- forced precision or forced
    repetition would measure something else and mis-calibrate the confidence number.

When done (24-32+ fresh centre clicks across the {len(STUDY_CASES)} cases), run:

    .venv/bin/python tools/fle_study.py analyze --after-line {line_count}

Add --write to append the dated results section to docs/research/fle-calibration.md
(default is a dry-run print -- nothing is written until you pass --write).
"""


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fle_study.py",
        description="Operator centre-click FLE study: protocol + run-history analysis.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("instructions", help="Print the ~10-minute centre-click protocol.")

    analyze_p = sub.add_parser("analyze", help="Analyze run-history.jsonl for fresh clicks.")
    analyze_p.add_argument("--since", default=None,
                            help="ISO timestamp lower bound (inclusive), e.g. 2026-07-18T12:00:00")
    analyze_p.add_argument("--after-line", type=int, default=None,
                            help="Only consider entries after this 1-based line number.")
    analyze_p.add_argument("--write", action="store_true",
                            help="Append the dated section to docs/research/fle-calibration.md "
                                 "(default: dry-run, print only).")
    analyze_p.add_argument("--history", default=None,
                            help="Override path to run-history.jsonl (mainly for testing).")
    analyze_p.add_argument("--scans-dir", default=None,
                            help="Override path to data/real/scans (mainly for testing).")
    analyze_p.add_argument("--doc", default=None,
                            help="Override the output doc path (mainly for testing).")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "instructions":
        print(render_instructions(count_lines(DEFAULT_HISTORY)))
        return 0

    if args.command == "analyze":
        history_path = Path(args.history) if args.history else DEFAULT_HISTORY
        scans_dir = Path(args.scans_dir) if args.scans_dir else DEFAULT_SCANS_DIR
        doc_path = Path(args.doc) if args.doc else DEFAULT_DOC

        result = analyze(history_path, scans_dir, since=args.since, after_line=args.after_line)
        report = render_report(result)
        print(report)

        if not result.has_fresh_data:
            return 0

        if args.write:
            append_to_doc(report, doc_path)
            print(f"[written] appended to {doc_path}")
        else:
            print("[dry-run] pass --write to append this section to "
                  f"{doc_path} (default is print-only).")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
