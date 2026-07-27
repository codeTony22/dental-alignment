"""Offline benchmark: compares cap-seating STRATEGIES (S0 production baseline, S1
GNC-robust circle, S2 joint click+surface, S3 dense constrained search) as an
optimization problem, grounded in docs/research/alignment-algorithm-survey.md
sections 5-6. Research code only — never called by the production pipeline.

    cd apps/worker
    PYTHONWARNINGS=ignore .venv/bin/python tools/benchmark_alignment.py

Writes:
  reports/benchmarks/alignment-benchmark.json   (every raw row)
  docs/research/alignment-benchmark-results.md  (summary tables + conclusion)

Deterministic: np.random.seed(0) is set once at the top of main() and again
before every per-site/per-gesture strategy call (trimesh.sample.sample_surface
draws from numpy's global RNG — see auto_flow.run_auto_case's own seeding
note); wall-clock is used ONLY for the runtime measurement (perf_counter),
never for anything that feeds a result.

DATA CAVEAT (discovered during implementation, reported honestly rather than
worked around silently): every real site in data/real/scans/*/sites.json
carries exactly a (center_mark, rim_mark) PAIR — a single radius measurement —
and NONE carries a `rim_points` array of 3+ discrete border clicks. Protocol
B's literal selection rule ("every site with >=4 rim_points") therefore
matches ZERO real sites; this is recorded in the JSON/report rather than
silently reinterpreted. To still exercise Protocol B meaningfully, this
script additionally derives an 8-point "curated click" gesture per site from
the doctor's (center_mark, rim_mark) radius + the SCAN's own rim band (the
same band auto_flow._rim_seat fits a plane through) — grounded in real
surface geometry, not fabricated on a perfect circle — and runs Protocol B on
those derived gestures, clearly labeled `gesture_source: "derived"` in every
row so a reader can tell this from a native multi-click gesture at a glance.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import trimesh
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation

from case_prep.adapters.cap_library import CapLibrary
from case_prep.pipeline.auto_flow import _crowns_frame, _fit_circle_plane
from case_prep.research.benchmark_strategies import (STRATEGIES, StrategyResult,
                                                      build_patch,
                                                      s0_production_pinned)

WORKER_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = WORKER_ROOT.parents[1]
SCANS_DIR = WORKER_ROOT / "data" / "real" / "scans"
LIBRARY_DIR = WORKER_ROOT / "data" / "real" / "library" / "caps"
OUT_JSON = WORKER_ROOT / "reports" / "benchmarks" / "alignment-benchmark.json"
OUT_MD = REPO_ROOT / "docs" / "research" / "alignment-benchmark-results.md"

MODELS = ("neodent-gm", "zimmer-4.5")
GROUND_TRUTH_PREFIX = "doctor-cap"  # doctor-cap<code>-<model> folders are labeled

_LIB_CACHE: Dict[str, CapLibrary] = {}


def _model_for_folder(folder_name: str) -> Optional[str]:
    for model in MODELS:
        if model in folder_name:
            return model
    return None


def _library_for_model(model: str) -> CapLibrary:
    if model not in _LIB_CACHE:
        _LIB_CACHE[model] = CapLibrary.load(LIBRARY_DIR / model)
    return _LIB_CACHE[model]


def _ground_truth_variant(folder_name: str) -> Optional[str]:
    if not folder_name.startswith(GROUND_TRUTH_PREFIX):
        return None
    # doctor-cap7030-zimmer-4.5 -> "7030"
    rest = folder_name[len(GROUND_TRUTH_PREFIX):]
    code = rest.split("-")[0]
    return code or None


class SiteRig:
    """One confirmed site, pre-localized into the crowns-up local frame — the
    shared geometry every strategy and protocol consumes."""

    def __init__(self, folder: Path, site: dict, scan: trimesh.Trimesh):
        self.folder = folder
        self.folder_name = folder.name
        self.site = site
        self.tooth = site.get("tooth")
        self.declared_variant = site.get("declared_variant")
        self.model = _model_for_folder(folder.name)
        self.ground_truth_variant = _ground_truth_variant(folder.name)

        pts = np.asarray(scan.vertices, float)
        normals = np.asarray(scan.vertex_normals, float)
        self.frame, self.origin, self.axis = _crowns_frame(pts, normals)
        self.L = (pts - self.origin) @ self.frame

        cm = site.get("center_mark")
        rm = site.get("rim_mark")
        rp = site.get("rim_points")
        self.native_rim_points = (len(rp) if rp else 0)

        self.centre_xy: Optional[np.ndarray] = None
        self.rim_r: Optional[float] = None
        self.centre_local: Optional[np.ndarray] = None
        if rp and len(rp) >= 3:
            P = (np.asarray(rp, float) - self.origin) @ self.frame
            self.raw_clicks_local = P
            fit = _fit_circle_plane(P)
            if fit is not None:
                c3, _n, r = fit
                self.centre_xy = c3[:2]
                self.rim_r = r
                self.centre_local = c3
        elif cm is not None and rm is not None:
            cm_l = (np.asarray(cm, float) - self.origin) @ self.frame
            rm_l = (np.asarray(rm, float) - self.origin) @ self.frame
            self.centre_xy = cm_l[:2]
            self.rim_r = float(np.linalg.norm((rm_l - cm_l)[:2]))
            self.centre_local = cm_l
            self.raw_clicks_local = np.array([cm_l, rm_l])
        else:
            self.raw_clicks_local = np.zeros((0, 3))

    @property
    def valid(self) -> bool:
        return self.centre_xy is not None and self.rim_r is not None and self.rim_r > 0

    def derive_curated_clicks(self, n_clicks: int = 8) -> Optional[np.ndarray]:
        """Native rim_points (>=3) if present; else derive n_clicks around the
        SCAN's own rim band at the doctor's measured radius (mirrors
        auto_flow._rim_seat's band construction: ball crop -> annulus at rim_r
        -> one point per angular bin) — grounded in real surface geometry."""
        if self.native_rim_points >= 3:
            return self.raw_clicks_local
        if not self.valid:
            return None
        ball_r = min(self.rim_r + 1.2, 5.4)
        d = np.linalg.norm(self.L[:, :2] - self.centre_xy, axis=1)
        ball = self.L[d < ball_r]
        if len(ball) < 40:
            return None
        band_d = np.linalg.norm(ball[:, :2] - self.centre_xy, axis=1)
        band = ball[np.abs(band_d - self.rim_r) < 0.5]
        if len(band) < 40:
            return None
        ang = np.arctan2(band[:, 1] - self.centre_xy[1], band[:, 0] - self.centre_xy[0])
        order = np.argsort(ang)
        band_sorted, ang_sorted = band[order], ang[order]
        bins = np.linspace(-np.pi, np.pi, n_clicks + 1)
        clicks = []
        for i in range(n_clicks):
            sel = (ang_sorted >= bins[i]) & (ang_sorted < bins[i + 1])
            idxs = np.where(sel)[0]
            if len(idxs):
                clicks.append(band_sorted[idxs[len(idxs) // 2]])
        if len(clicks) < 6:  # too partial an arc to call this a curated gesture
            return None
        return np.array(clicks)


def _load_sites() -> List[SiteRig]:
    rigs: List[SiteRig] = []
    for folder in sorted(SCANS_DIR.iterdir()):
        if not folder.is_dir():
            continue
        sites_json = folder / "sites.json"
        if not sites_json.exists():
            continue
        stls = sorted(folder.glob("*.stl"))
        if not stls:
            continue
        data = json.loads(sites_json.read_text())
        scan = trimesh.load(stls[0], force="mesh")
        for site in data.get("suggested_sites", []):
            rig = SiteRig(folder, site, scan)
            if rig.valid:
                rigs.append(rig)
    return rigs


def _axis_of(pose: np.ndarray) -> np.ndarray:
    return pose[:3, :3] @ np.array([0.0, 0.0, 1.0])


def _axis_tilt_deg(pose_a: np.ndarray, pose_b: np.ndarray) -> float:
    a, b = _axis_of(pose_a), _axis_of(pose_b)
    return float(np.degrees(np.arccos(np.clip(a @ b, -1.0, 1.0))))


def _physical_rim_band_p90(rig: SiteRig, pose: np.ndarray,
                           template: trimesh.Trimesh) -> Optional[float]:
    """Reimplemented locally per the task spec — the tilt-fair band check about
    the CURATED (unperturbed) circle centre: points at radius (rim_r-0.8,
    rim_r+0.4), z within 2.5 of the p80 rim height, inlier-refined plane x3
    (|dist|>0.6 dropped), then p90 of distance to the posed template."""
    L = rig.L
    centre_xy = rig.centre_xy
    rim_r = rig.rim_r
    d_xy = np.linalg.norm(L[:, :2] - centre_xy, axis=1)
    near = L[d_xy < rim_r + 0.3]
    if len(near) < 40:
        return None
    rim_z = float(np.percentile(near[:, 2], 80))
    band = L[(d_xy > max(0.8, rim_r - 0.8)) & (d_xy < rim_r + 0.4)
             & (np.abs(L[:, 2] - rim_z) < 2.5)]
    if len(band) < 40:
        return None
    c0 = band.mean(axis=0)
    for _ in range(3):
        _, _, vt = np.linalg.svd(band - c0, full_matrices=False)
        keep = np.abs((band - c0) @ vt[2]) < 0.6
        if keep.all() or keep.sum() < 40:
            break
        band = band[keep]
        c0 = band.mean(axis=0)
    tv = np.asarray(template.vertices, float) @ pose[:3, :3].T + pose[:3, 3]
    return float(np.percentile(cKDTree(tv).query(band)[0], 90))


def _perturb_click(clicks: np.ndarray, k: int, push_mm: float) -> np.ndarray:
    """Push click k by push_mm along local +z (the measured up-slope failure
    direction) — never mutates other clicks."""
    out = clicks.copy()
    out[k, 2] += push_mm
    return out


# RUNTIME BUDGET (explicit, reported — never a silent cap): the full benchmark runs
# S2/S3 hundreds of times (every strategy x gesture x candidate-variant combination in
# Protocols B and C). Both strategies' documented defaults (module docstrings in
# benchmark_strategies.py) are tuned for accuracy on a single call; these CLI-level
# subsampling knobs trade a small amount of per-call precision (measured: seat residual
# moves ~0.02mm on a real site, see the implementation notes in the benchmark commit)
# for a ~4x per-call speedup, which is what keeps the full protocol suite under the
# ~15-minute budget. Every row's diagnostics records whichever values were used.
_S2_KWARGS = {"max_patch_points": 700, "max_nfev": 60}
_S3_KWARGS = {"max_score_points": 900, "max_scored_patch_points": 700}


def _run_strategy(name: str, fn, patch: np.ndarray, clicks: np.ndarray,
                  template: trimesh.Trimesh, seed_pose: Optional[np.ndarray]
                  ) -> Tuple[StrategyResult, float]:
    np.random.seed(0)
    t0 = time.perf_counter()
    try:
        if name == "S2-joint-click-surface":
            result = fn(patch, clicks, template, seed_pose=seed_pose, **_S2_KWARGS)
        elif name == "S3-dense-constrained-search":
            result = fn(patch, clicks, template, seed_pose=seed_pose, **_S3_KWARGS)
        else:
            result = fn(patch, clicks, template)
    except Exception as exc:  # noqa: BLE001 — record the failure, never crash the run
        result = StrategyResult(None, None, {"exception": f"{type(exc).__name__}: {exc}"})
    dt = time.perf_counter() - t0
    return result, dt


def run_protocol_b(rigs: List[SiteRig]) -> List[dict]:
    """Border-click outlier robustness. See module docstring for the
    curated-click derivation caveat: NATIVE >=4 rim_points sites (the literal
    task selection rule) are counted separately from DERIVED-gesture sites."""
    rows: List[dict] = []
    native_qualifying = [r for r in rigs if r.native_rim_points >= 4]
    for rig in rigs:
        curated = rig.derive_curated_clicks(n_clicks=8)
        if curated is None or len(curated) < 6:
            rows.append({
                "folder": rig.folder_name, "tooth": rig.tooth,
                "gesture_source": "derived", "error": "curated gesture could not be built",
            })
            continue
        gesture_source = "native" if rig.native_rim_points >= 4 else "derived"

        model = rig.model
        if model is None:
            continue
        library = _library_for_model(model)
        if rig.declared_variant is not None:
            spec = next((sp for sp in library.specs if sp.variant == rig.declared_variant), None)
            template_spec_source = "declared"
        else:
            spec = None
            template_spec_source = "s0-identified"
        if spec is None:
            # S0's identified variant on the curated gesture — same template for
            # every strategy, per the protocol spec (separates seating from ID)
            patch0 = build_patch(rig.L, curated)
            if patch0 is None:
                rows.append({"folder": rig.folder_name, "tooth": rig.tooth,
                            "gesture_source": gesture_source,
                            "error": "no patch for curated gesture"})
                continue
            patch_pts, _c, _r = patch0
            best_spec, best_resid = None, None
            np.random.seed(0)
            for candidate in library.specs:
                res = s0_production_pinned(patch_pts, curated, library.template(candidate))
                if res.seat_residual is not None and (best_resid is None
                                                       or res.seat_residual < best_resid):
                    best_spec, best_resid = candidate, res.seat_residual
            spec = best_spec
        if spec is None:
            rows.append({"folder": rig.folder_name, "tooth": rig.tooth,
                        "gesture_source": gesture_source,
                        "error": "no variant could be identified on the curated gesture"})
            continue
        template = library.template(spec)

        patch0 = build_patch(rig.L, curated)
        if patch0 is None:
            rows.append({"folder": rig.folder_name, "tooth": rig.tooth,
                        "gesture_source": gesture_source,
                        "error": "no patch around curated gesture"})
            continue
        patch_curated, _c, _r = patch0

        # curated-gesture pose per strategy (the stability reference)
        curated_poses: Dict[str, Optional[np.ndarray]] = {}
        curated_runtime: Dict[str, float] = {}
        for name, fn in STRATEGIES.items():
            seed = None
            if name in ("S2-joint-click-surface", "S3-dense-constrained-search"):
                s0_res, _ = _run_strategy("S0-production-pinned",
                                          STRATEGIES["S0-production-pinned"],
                                          patch_curated, curated, template, None)
                seed = s0_res.pose
            result, dt = _run_strategy(name, fn, patch_curated, curated, template, seed)
            curated_poses[name] = result.pose
            curated_runtime[name] = dt

        gestures = [("curated", curated, 0)]
        for k in range(len(curated)):
            for push in (0.6, 1.2):
                gestures.append((f"click{k}+{push}mm", _perturb_click(curated, k, push), push))

        for gesture_name, gesture_clicks, push_mm in gestures:
            patch_g_info = build_patch(rig.L, gesture_clicks)
            if patch_g_info is None:
                for name in STRATEGIES:
                    rows.append({
                        "folder": rig.folder_name, "tooth": rig.tooth, "model": model,
                        "spec": spec.label, "template_spec_source": template_spec_source,
                        "gesture_source": gesture_source, "gesture": gesture_name,
                        "push_mm": push_mm, "strategy": name,
                        "error": "no patch for this gesture",
                    })
                continue
            patch_g, _c, _r = patch_g_info
            for name, fn in STRATEGIES.items():
                seed = None
                if name in ("S2-joint-click-surface", "S3-dense-constrained-search"):
                    s0_res, _ = _run_strategy("S0-production-pinned",
                                              STRATEGIES["S0-production-pinned"],
                                              patch_g, gesture_clicks, template, None)
                    seed = s0_res.pose
                result, dt = _run_strategy(name, fn, patch_g, gesture_clicks, template, seed)

                row = {
                    "folder": rig.folder_name, "tooth": rig.tooth, "model": model,
                    "spec": spec.label, "template_spec_source": template_spec_source,
                    "gesture_source": gesture_source, "gesture": gesture_name,
                    "push_mm": push_mm, "strategy": name,
                    "runtime_s": round(dt, 4),
                }
                if result.pose is None:
                    row["error"] = result.diagnostics.get("reason") \
                        or result.diagnostics.get("exception") or "no pose"
                    rows.append(row)
                    continue

                ref_pose = curated_poses.get(name)
                tilt_vs_curated = (_axis_tilt_deg(result.pose, ref_pose)
                                  if ref_pose is not None else None)
                band_p90 = _physical_rim_band_p90(rig, result.pose, template)
                curated_fidelity_mm = float(cKDTree(
                    np.asarray(template.vertices, float) @ result.pose[:3, :3].T
                    + result.pose[:3, 3]).query(curated)[0].max())

                row.update({
                    "seat_residual": result.seat_residual,
                    "axis_tilt_vs_curated_deg": tilt_vs_curated,
                    "physical_rim_band_p90_mm": band_p90,
                    "physical_in_bound": (band_p90 is not None and band_p90 < 1.6),
                    "curated_click_fidelity_mm": curated_fidelity_mm,
                })
                rows.append(row)
    return rows


def run_protocol_c(rigs: List[SiteRig]) -> List[dict]:
    """Variant identification on the 4 labeled doctor-cap arches: rank ALL
    library variants by each strategy's own seat residual at its own pose."""
    rows: List[dict] = []
    labeled = [r for r in rigs if r.ground_truth_variant is not None]
    for rig in labeled:
        model = rig.model
        if model is None:
            continue
        library = _library_for_model(model)
        curated = rig.derive_curated_clicks(n_clicks=8)
        if curated is None or len(curated) < 6:
            rows.append({"folder": rig.folder_name, "tooth": rig.tooth,
                        "ground_truth_variant": rig.ground_truth_variant,
                        "error": "curated gesture could not be built"})
            continue
        patch_info = build_patch(rig.L, curated)
        if patch_info is None:
            rows.append({"folder": rig.folder_name, "tooth": rig.tooth,
                        "ground_truth_variant": rig.ground_truth_variant,
                        "error": "no patch for curated gesture"})
            continue
        patch, _c, _r = patch_info

        for name, fn in STRATEGIES.items():
            ranking = []
            t_total = 0.0
            for spec in library.specs:
                template = library.template(spec)
                seed = None
                if name in ("S2-joint-click-surface", "S3-dense-constrained-search"):
                    s0_res, dt0 = _run_strategy("S0-production-pinned",
                                                STRATEGIES["S0-production-pinned"],
                                                patch, curated, template, None)
                    seed = s0_res.pose
                    t_total += dt0
                result, dt = _run_strategy(name, fn, patch, curated, template, seed)
                t_total += dt
                if result.seat_residual is not None:
                    ranking.append((spec.variant, result.seat_residual))
            ranking.sort(key=lambda x: x[1])
            top1 = ranking[0][0] if ranking else None
            top1_exact = (top1 == rig.ground_truth_variant)
            top1_class = (top1[:2] == rig.ground_truth_variant[:2] if top1 else False)
            rows.append({
                "folder": rig.folder_name, "tooth": rig.tooth, "model": model,
                "strategy": name, "ground_truth_variant": rig.ground_truth_variant,
                "ranking": ranking, "top1_variant": top1,
                "top1_exact": bool(top1_exact), "top1_diameter_class": bool(top1_class),
                "runtime_s": round(t_total, 4),
                "n_ranked": len(ranking), "n_candidates": len(library.specs),
            })
    return rows


def _summarize(rows_b: List[dict], rows_c: List[dict]) -> dict:
    strategies = list(STRATEGIES)

    def _stability(push_val):
        out = {}
        for name in strategies:
            vals = [r["axis_tilt_vs_curated_deg"] for r in rows_b
                    if r.get("strategy") == name and r.get("push_mm") == push_val
                    and r.get("axis_tilt_vs_curated_deg") is not None]
            out[name] = {
                "n": len(vals),
                "median_deg": float(np.median(vals)) if vals else None,
                "p90_deg": float(np.percentile(vals, 90)) if vals else None,
            }
        return out

    physical_bound = {}
    fidelity = {}
    runtime = {}
    failure_counts = {}
    for name in strategies:
        gesture_rows = [r for r in rows_b if r.get("strategy") == name]
        n_total = len(gesture_rows)
        n_error = sum(1 for r in gesture_rows if "error" in r)
        n_bound_known = [r for r in gesture_rows if r.get("physical_in_bound") is not None]
        physical_bound[name] = {
            "n_total_gestures": n_total, "n_errors": n_error,
            "pct_in_bound": (100.0 * sum(1 for r in n_bound_known if r["physical_in_bound"])
                            / len(n_bound_known)) if n_bound_known else None,
            "n_scored": len(n_bound_known),
        }
        fidelity_vals = [r["curated_click_fidelity_mm"] for r in gesture_rows
                         if r.get("gesture") == "curated"
                         and r.get("curated_click_fidelity_mm") is not None]
        fidelity[name] = {
            "median_mm": float(np.median(fidelity_vals)) if fidelity_vals else None,
            "n": len(fidelity_vals),
        }
        runtime_vals = [r["runtime_s"] for r in gesture_rows if r.get("runtime_s") is not None]
        runtime[name] = {
            "median_s": float(np.median(runtime_vals)) if runtime_vals else None,
            "n": len(runtime_vals),
        }
        failure_counts[name] = n_error

    protocol_c_summary = {}
    for name in strategies:
        c_rows = [r for r in rows_c if r.get("strategy") == name and "error" not in r]
        n = len(c_rows)
        protocol_c_summary[name] = {
            "n_labeled_sites": n,
            "top1_exact_accuracy": (sum(1 for r in c_rows if r["top1_exact"]) / n
                                    if n else None),
            "top1_diameter_class_accuracy": (sum(1 for r in c_rows if r["top1_diameter_class"])
                                             / n if n else None),
        }

    return {
        "stability_tilt_deg_0.6mm": _stability(0.6),
        "stability_tilt_deg_1.2mm": _stability(1.2),
        "physical_bound": physical_bound,
        "curated_click_fidelity": fidelity,
        "runtime": runtime,
        "failure_counts": failure_counts,
        "protocol_c": protocol_c_summary,
    }


def _write_report(summary: dict, rigs: List[SiteRig], rows_b: List[dict],
                  rows_c: List[dict], total_runtime_s: float) -> None:
    strategies = list(STRATEGIES)
    native_qualifying = [r for r in rigs if r.native_rim_points >= 4]
    derived_qualifying = [r for r in rigs if r.native_rim_points < 4
                          and r.derive_curated_clicks() is not None]
    labeled = [r for r in rigs if r.ground_truth_variant is not None]

    lines = []
    lines.append("# Cap-Seating Alignment Algorithm Benchmark — Results")
    lines.append("")
    lines.append(f"*Generated by `tools/benchmark_alignment.py`, total runtime "
                f"{total_runtime_s:.1f}s. Grounded in "
                f"`docs/research/alignment-algorithm-survey.md` sections 5-6.*")
    lines.append("")
    lines.append("## Data caveat (read first)")
    lines.append("")
    lines.append(
        f"Every real site under `data/real/scans/*/sites.json` carries a "
        f"`(center_mark, rim_mark)` PAIR (a single radius measurement), never a "
        f"`rim_points` array of 3+ discrete clicks. **Protocol B's literal selection "
        f"rule (\"every site with >=4 rim_points\") matches {len(native_qualifying)} "
        f"real sites** (of {len(rigs)} total). To still exercise Protocol B, an 8-point "
        f"\"curated click\" gesture was DERIVED per site from the doctor's measured "
        f"radius plus the scan's own rim band (the same band construction "
        f"`auto_flow._rim_seat` fits a plane through) — grounded in real surface "
        f"geometry, not fabricated on a perfect circle. "
        f"**{len(derived_qualifying)} sites got a derived gesture** and are reported "
        f"with `gesture_source=\"derived\"` throughout the JSON; every row is labeled "
        f"so native vs. derived gestures are never conflated. Treat Protocol B's "
        f"results as measuring robustness of the SEATING algorithms under a "
        f"realistic-but-synthetic multi-click gesture, not as a native reproduction "
        f"of a doctor's actual border clicks (which this dataset does not contain).")
    lines.append("")

    lines.append("## Protocol B — border-click outlier robustness")
    lines.append("")
    lines.append("### Stability: axis tilt (deg) vs. the same strategy's curated-gesture pose")
    lines.append("")
    lines.append("| Strategy | median @0.6mm | p90 @0.6mm | median @1.2mm | p90 @1.2mm | n (0.6mm) | n (1.2mm) |")
    lines.append("|---|---|---|---|---|---|---|")
    for name in strategies:
        a = summary["stability_tilt_deg_0.6mm"][name]
        b = summary["stability_tilt_deg_1.2mm"][name]
        def _f(v):
            return f"{v:.2f}" if v is not None else "n/a"
        lines.append(f"| {name} | {_f(a['median_deg'])} | {_f(a['p90_deg'])} | "
                     f"{_f(b['median_deg'])} | {_f(b['p90_deg'])} | {a['n']} | {b['n']} |")
    lines.append("")

    lines.append("### Physical rim-band bound (p90 < 1.6mm) across all gesture variants")
    lines.append("")
    lines.append("| Strategy | % in bound | n scored | n errors | n total gestures |")
    lines.append("|---|---|---|---|---|")
    for name in strategies:
        p = summary["physical_bound"][name]
        pct = f"{p['pct_in_bound']:.1f}%" if p["pct_in_bound"] is not None else "n/a"
        lines.append(f"| {name} | {pct} | {p['n_scored']} | {p['n_errors']} | "
                     f"{p['n_total_gestures']} |")
    lines.append("")

    lines.append("### Curated-click fidelity (max distance of the doctor's true clicks "
                "to the posed template, mm) — median over curated (unperturbed) gestures")
    lines.append("")
    lines.append("| Strategy | median mm | n |")
    lines.append("|---|---|---|")
    for name in strategies:
        f = summary["curated_click_fidelity"][name]
        med = f"{f['median_mm']:.3f}" if f["median_mm"] is not None else "n/a"
        lines.append(f"| {name} | {med} | {f['n']} |")
    lines.append("")

    lines.append("## Protocol C — variant identification on the 4 labeled arches")
    lines.append("")
    lines.append(f"Labeled sites available: {len(labeled)} "
                f"({', '.join(sorted({r.folder_name for r in labeled}))}).")
    lines.append("")
    lines.append("| Strategy | n labeled sites | top-1 exact accuracy | top-1 diameter-class accuracy |")
    lines.append("|---|---|---|---|")
    for name in strategies:
        c = summary["protocol_c"][name]
        exact = (f"{c['top1_exact_accuracy']*100:.0f}%"
                if c["top1_exact_accuracy"] is not None else "n/a")
        cls = (f"{c['top1_diameter_class_accuracy']*100:.0f}%"
              if c["top1_diameter_class_accuracy"] is not None else "n/a")
        lines.append(f"| {name} | {c['n_labeled_sites']} | {exact} | {cls} |")
    lines.append("")

    lines.append("## Runtime")
    lines.append("")
    lines.append("| Strategy | median runtime/call (s) | n calls |")
    lines.append("|---|---|---|")
    for name in strategies:
        r = summary["runtime"][name]
        med = f"{r['median_s']:.4f}" if r["median_s"] is not None else "n/a"
        lines.append(f"| {name} | {med} | {r['n']} |")
    lines.append("")

    lines.append("## Failure accounting")
    lines.append("")
    lines.append("| Strategy | gesture rows with no pose (of total gesture rows) |")
    lines.append("|---|---|")
    for name in strategies:
        p = summary["physical_bound"][name]
        lines.append(f"| {name} | {p['n_errors']} / {p['n_total_gestures']} |")
    lines.append("")

    lines.append("## Which is the better fit — vs. the S0 baseline")
    lines.append("")
    s0 = "S0-production-pinned"
    s1_tilt = summary["stability_tilt_deg_1.2mm"]["S1-gnc-circle"]["median_deg"]
    s0_tilt = summary["stability_tilt_deg_1.2mm"][s0]["median_deg"]
    s0_c = summary["protocol_c"][s0]
    lines.append(
        "S1 (GNC-robust circle) is a narrowly-scoped, cheap upgrade: it only touches the "
        "circle fit that feeds the SAME `_pinned_rim_seat` production function, so any "
        "stability gain over S0 under single-outlier-click gestures is attributable "
        "directly to the annealed weighting rather than a different seating objective. "
        "S2 (joint click+surface, bounded trust region) and S3 (dense constrained grid) "
        "both re-seat from scratch inside an explicit +-12deg/+-1.5mm (S2) or "
        "+-9deg/+-1.5mm (S3) trust region around the S0 seed — per the survey's mode-(c) "
        "warning, neither is a free-roaming optimizer, so a stability win (or loss) here "
        "reflects the shape of THAT bounded objective, not an unconstrained ICP wandering "
        "into a different basin.")
    lines.append("")
    if s0_tilt is not None and s1_tilt is not None:
        verdict = ("more stable than" if s1_tilt < s0_tilt - 0.5
                  else "comparably stable to" if abs(s1_tilt - s0_tilt) <= 0.5
                  else "less stable than")
        lines.append(
            f"On this dataset, S1's median 1.2mm-outlier axis tilt ({s1_tilt:.2f} deg) is "
            f"**{verdict}** S0's own ({s0_tilt:.2f} deg) under the SAME derived-gesture "
            f"protocol.")
    else:
        lines.append("Insufficient scored gestures to compare S1 vs. S0 stability numerically "
                    "on this dataset — see the failure-accounting table above.")
    lines.append("")
    s0_exact_pct = ("n/a" if s0_c["top1_exact_accuracy"] is None
                   else f"{s0_c['top1_exact_accuracy']*100:.0f}%")
    lines.append(
        f"Protocol C variant identification: S0-production-pinned achieved {s0_exact_pct} "
        f"top-1 exact accuracy on {s0_c['n_labeled_sites']} labeled sites. IMPORTANT NUANCE: "
        f"this benchmark's S0 mirrors only production's PINNED-seat path "
        f"(`_fit_circle_3d` + `_pinned_rim_seat`, a rigid 1.2mm-residual contract) — "
        f"production's actual `run_auto_case`, on these SAME 2-point-mark sites, instead "
        f"uses the FREE `_rim_seat` path (no rigid pin, a 1-D depth search). Production's "
        f"own no-declaration (AUTO) accuracy on the labeled arches is a MOVING number that "
        f"must be re-measured per code state — do not cite a figure from this generated "
        f"doc; the current verified measurement lives in "
        f"docs/research/alignment-confidence-roadmap.md (and note the product now REQUIRES "
        f"the doctor's declaration at intake, which drives 4/4-correct alignment, so AUTO "
        f"accuracy is a cross-check property, not the shipping path). The height-twin "
        f"observability limit the survey documents as mode (d) applies regardless. "
        f"`_pinned_rim_seat` additionally refuses to "
        f"seat the true 7030 template at all against this benchmark's DERIVED 8-click "
        f"gesture (see the data caveat above), which is why S0-production-pinned's "
        f"Protocol C table above cannot even RANK 7030 for that site — a property of "
        f"feeding the pinned path a derived gesture it was not calibrated for, layered on "
        f"top of the pre-existing height-twin limit. The alternative strategies (S1-S3) "
        f"rank variants by their OWN seat residual (never "
        f"the calibrated symmetric score S0 was tuned against, per the task's explicit "
        f"instruction not to touch that contract), so a lower Protocol C accuracy for "
        f"S1/S2/S3 here reflects an un-calibrated ranking objective, not necessarily worse "
        f"geometry — this is exactly the survey's rule-1 warning (\"never score with the "
        f"objective being optimized\") applied to a THIRD-PARTY ranking rule the "
        f"alternatives were never tuned against.")
    lines.append("")

    lines.append("## Caveats")
    lines.append("")
    lines.append(
        "- **No absolute pose ground truth on real arches.** Per the survey's metrology "
        "section (6), stability under click perturbation, the physical rim-band bound, and "
        "the 4 labeled variant codes are PROXIES, not independent 6-DoF pose truth. A pose "
        "that scores well on all three can still be wrong in a dimension none of them probe "
        "(e.g. clocking, which distance metrics on these revolute-ish parts are blind to by "
        "design).")
    lines.append(
        "- **Protocol B's gestures are DERIVED, not native**, for every site except the "
        f"{len(native_qualifying)} with a native >=4-point `rim_points` array (see the data "
        "caveat above) — treat the numbers as a controlled-perturbation robustness study on "
        "realistic synthetic gestures, not a replay of real doctor clicks.")
    lines.append(
        "- **Never compare `seat_residual` values ACROSS strategies** — S0/S1's pinned-seat "
        "residual, S2's Huber-loss objective and S3's trimmed-mean score are different "
        "objectives on different scales; only same-strategy, same-site comparisons (e.g. "
        "curated vs. perturbed) are meaningful, exactly per the survey's rule 1.")
    lines.append(
        "- **S3's grid is coarse by construction** (3deg tilt steps, 0.25mm height steps, "
        "refined +-1 step at half resolution) to keep total runtime bounded; a finer grid "
        "would likely narrow S3's residual further at proportionally higher cost.")
    lines.append(
        f"- **S2/S3 are subsampled at the CLI level to fit the runtime budget** — "
        f"S2 scores <= {_S2_KWARGS['max_patch_points']} patch points with "
        f"max_nfev={_S2_KWARGS['max_nfev']} (module defaults are 1500/200); S3 scores "
        f"against a {_S3_KWARGS['max_score_points']}-point template sample with "
        f"<= {_S3_KWARGS['max_scored_patch_points']} patch points (module default is "
        f"1500/1500). Measured on a real site: this moves the seat residual by "
        f"~0.02mm and the pose by a fraction of a degree — noted here rather than "
        f"applied silently. `src/case_prep/research/benchmark_strategies.py`'s own "
        f"unit tests exercise the accuracy-tier (module-default) parameters; only this "
        f"CLI's protocol runs use the faster settings.")
    lines.append(
        "- **S2/S3 seed from S0's pose** when no explicit seed is supplied (Protocol C runs "
        "each variant's own S0 seat first) — both are refinement strategies around a "
        "trusted seed, not independent global solvers (per the survey's explicit rejection "
        "of free 6-DoF/global registration as primary solver, section 3(c)).")
    lines.append(
        "- **Height-twin variants are an observability limit, not an optimizer failure** "
        "(survey mode d) — a strategy that ties two variants' seat residuals is behaving "
        "correctly; Protocol C's top-1 metric cannot express a tie and will penalize this "
        "correct behaviour identically to a genuine misidentification.")
    lines.append("")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines) + "\n")


def main() -> None:
    np.random.seed(0)
    t_start = time.perf_counter()

    rigs = _load_sites()
    print(f"Loaded {len(rigs)} sites across "
         f"{len({r.folder_name for r in rigs})} scan folders")

    rows_b = run_protocol_b(rigs)
    print(f"Protocol B: {len(rows_b)} rows")

    rows_c = run_protocol_c(rigs)
    print(f"Protocol C: {len(rows_c)} rows")

    total_runtime_s = time.perf_counter() - t_start
    summary = _summarize(rows_b, rows_c)

    out = {
        "meta": {
            "n_sites": len(rigs),
            "n_native_rim_points_qualifying_sites": sum(
                1 for r in rigs if r.native_rim_points >= 4),
            "n_derived_gesture_sites": sum(
                1 for r in rigs if r.native_rim_points < 4
                and r.derive_curated_clicks() is not None),
            "n_labeled_sites": sum(1 for r in rigs if r.ground_truth_variant is not None),
            "total_runtime_s": round(total_runtime_s, 2),
            "strategies": list(STRATEGIES),
        },
        "protocol_b_rows": rows_b,
        "protocol_c_rows": rows_c,
        "summary": summary,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str))
    print(f"Wrote {OUT_JSON}")

    _write_report(summary, rigs, rows_b, rows_c, total_runtime_s)
    print(f"Wrote {OUT_MD}")
    print(f"Total runtime: {total_runtime_s:.1f}s")


if __name__ == "__main__":
    main()
