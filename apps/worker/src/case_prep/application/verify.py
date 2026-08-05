"""THE STANDING FLEET VERIFICATION (§10-AH's automation ask, client 2026-08-04:
"re-run the verification ... across all the cases ... what other tooling do we need
to make the experience and product automated").

``make verify-fleet``: for every case with a LANDED run, re-run each site from the
seed provenances actually available to it — the case record's own pair (the
baseline the run used), the operator's re-mark when a session carries one, and the
live detector's proposal when one speaks for the tooth — each into a SCRATCH dir
(AM-1: no landed run or session is touched), scored with the repo's PUBLISHED
acceptance instrument (``site_deviation_stats``, the number the run row and the
Declare strip print). A variant is only ever called an improvement when it BEATS
the baseline on that instrument — the same monotonic-accept discipline
``auto_flow`` itself applies.

This is a REPORT, not a gate: ``rehearse`` stays the gate. The report says which
sites have a better seat AVAILABLE and from which provenance, so "most cases are
wrong" becomes a table instead of an impression. The §10-AH instrument-honesty
rule stands: no client-side estimator, no ICP sweep (its real-data spread exceeds
the effect it would measure) — the production pipeline and the published metric
carry every number here.

A proposal may speak for a tooth only when the detector GUESSED that tooth or the
proposal sits within ``PICK_RADIUS_MM`` of the site's centre — the same guard the
product's adopt door applies (a nearest-match beyond it is a DIFFERENT cap;
cap7020's "9mm disagreement" was its neighbour).
"""
from __future__ import annotations

import json
import math
import shutil
import tempfile
from pathlib import Path
from typing import Optional, Sequence

from .cases import CaseRecord, discover_cases
from .detection import detect
from .run import RunSelection, run_case

# the product's own adopt-door guard (domain/intake.SITE_PICK_RADIUS_MM), mirrored —
# a proposal farther than this from a site it never guessed is some other cap
PICK_RADIUS_MM = 6.0

# an "improvement" must clear the instrument's own noise floor, not tie with it
MIN_GAIN_RMS_MM = 0.01


def latest_run_dir(product_root: Path, case_id: str) -> Optional[Path]:
    """The newest landed run dir that actually holds implant records — run dirs are
    immutable history (AM-1), so the newest complete one is the standing baseline."""
    runs = product_root / case_id / "runs"
    if not runs.is_dir():
        return None
    for run in sorted(runs.iterdir(), reverse=True):
        if any(run.glob("*-implant.json")):
            return run
    return None


def marked_centers_of(product_root: Path, case_id: str) -> dict:
    """The operator's standing re-marks, read off the session document (never a
    curated value — ``marked_center`` has exactly two writers, both operator acts)."""
    session = product_root / case_id / "session.json"
    if not session.is_file():
        return {}
    try:
        doc = json.loads(session.read_text())
    except ValueError:
        return {}
    out = {}
    for tooth, site in (doc.get("sites") or {}).items():
        centre = (site or {}).get("marked_center")
        if centre is not None:
            out[int(tooth)] = [float(c) for c in centre]
    return out


def proposal_for(proposals: Sequence, tooth: int,
                 centre: Sequence[float]) -> Optional[Sequence[float]]:
    """The one proposal allowed to speak for this tooth, or None — the adopt door's
    own rule: guessed for the tooth, or within the pick radius of its centre."""
    best = None
    best_mm = None
    for p in proposals:
        mm = math.dist(tuple(p.center), tuple(centre))
        if p.tooth_guess != tooth and mm > PICK_RADIUS_MM:
            continue
        if best_mm is None or mm < best_mm:
            best, best_mm = list(p.center), mm
    return best


def _seed_variants(site: dict, tooth: int, marked: dict,
                   proposals: Sequence) -> "list[tuple[str, dict]]":
    """Each provenance as the site-record override its run would use. The baseline
    re-runs the record AS IS; the operator's mark and the detector's proposal seed
    ALONE (the §10-AH rule: the record's pair belongs to the record's own centre)."""
    variants = [("baseline (record)", dict(site))]
    if tooth in marked:
        bare = {k: v for k, v in site.items()
                if k not in ("center_mark", "rim_mark", "marked_points",
                             "rim_points")}
        variants.append(("operator mark", {**bare, "center": marked[tooth]}))
    centre = site.get("center")
    if centre is not None:
        det = proposal_for(proposals, tooth, centre)
        if det is not None and math.dist(tuple(det), tuple(centre)) > 0.05:
            bare = {k: v for k, v in site.items()
                    if k not in ("center_mark", "rim_mark", "marked_points",
                                 "rim_points")}
            variants.append(("detector", {**bare, "center": det}))
    return variants


def verify_case(case: CaseRecord, product_root: Path,
                scratch: Path) -> "list[dict]":
    """One case's verification rows. Refusals become rows, never raises — a fleet
    report that dies on its third case verified nothing."""
    import numpy as np
    import trimesh

    from ..adapters.ingest import canonicalize_revolute
    from ..adapters.qc_render import site_deviation_stats

    run_dir = latest_run_dir(product_root, case.id)
    if run_dir is None:
        return [{"case": case.id, "note": "no landed run — nothing to verify"}]
    records = sorted(run_dir.glob("*-implant.json"))
    marked = marked_centers_of(product_root, case.id)
    try:
        proposals = detect(case).proposals
    except Exception as exc:  # noqa: BLE001 — the report states it instead
        proposals = ()
        detect_note = f"detection unavailable: {exc}"
    else:
        detect_note = None

    scan = trimesh.load(str(case.scan), process=True)
    scan_pts = np.asarray(scan.vertices, float)
    rows: list[dict] = []
    for record_path in records:
        rec = json.loads(record_path.read_text())
        tooth = int(rec["tooth"])
        model, variant = rec["implant_model"], rec["variant_code"]
        site = next((dict(s) for s in case.suggested_sites
                     if int(s.get("tooth", -1)) == tooth), None)
        if site is None:
            # a session-only site: reconstruct the minimal record from the mark
            if tooth not in marked:
                rows.append({"case": case.id, "tooth": tooth,
                             "note": "no case record and no session mark"})
                continue
            site = {"tooth": tooth, "center": marked[tooth]}
        raw = trimesh.load(str(case.data_root / "library" / "caps" / model /
                               f"{model}-{variant}.stl"), process=True)
        template, _ = canonicalize_revolute(raw)
        shipped = site_deviation_stats(
            scan_pts, np.asarray(rec["pose_matrix"], float), template)
        row = {"case": case.id, "tooth": tooth, "variant": variant,
               "shipped_rms": round(shipped["rms_mm"], 4),
               "shipped_p90": round(shipped["p90_mm"], 4),
               "variants": [], "note": detect_note}
        for label, siteover in _seed_variants(site, tooth, marked, proposals):
            exp_case = CaseRecord(
                id=case.id, doctor=case.doctor, jaw=case.jaw, scan=case.scan,
                data_root=case.data_root, suggested_model=case.suggested_model,
                suggested_construction=case.suggested_construction,
                suggested_sites=({**siteover, "tooth": tooth,
                                  "declared_variant": variant},))
            selection = RunSelection(
                model=model,
                construction_path=case.suggested_construction
                or "dess/neodent-gm-scanbody.stl",
                variants={tooth: variant}, jaw=case.jaw)
            out = Path(tempfile.mkdtemp(prefix="verify-", dir=str(scratch)))
            try:
                run_case(exp_case, selection, out)
                pose = json.loads(
                    (out / f"{case.id}-{tooth}-implant.json").read_text())
                st = site_deviation_stats(
                    scan_pts, np.asarray(pose["pose_matrix"], float), template)
                row["variants"].append(
                    {"seed": label, "rms": round(st["rms_mm"], 4),
                     "p90": round(st["p90_mm"], 4)})
            except Exception as exc:  # noqa: BLE001
                row["variants"].append(
                    {"seed": label, "refused": f"{type(exc).__name__}: {exc}"})
            finally:
                shutil.rmtree(out, ignore_errors=True)
        rows.append(row)
    return rows


def improvement_of(row: dict) -> Optional[dict]:
    """The best variant BEATING the shipped pose by more than the noise floor, or
    None — a tie is not an improvement, and the shipped pose needs no defence."""
    best = None
    for v in row.get("variants", []):
        if "rms" not in v:
            continue
        if v["rms"] < row["shipped_rms"] - MIN_GAIN_RMS_MM:
            if best is None or v["rms"] < best["rms"]:
                best = v
    return best


def main() -> int:
    root = Path(__file__).resolve().parents[3]
    data_root = root / "data" / "real"
    product_root = root / "reports" / "product"
    with tempfile.TemporaryDirectory(prefix="verify-fleet-") as scratch_dir:
        scratch = Path(scratch_dir)
        improvements = 0
        for case in sorted(discover_cases(data_root), key=lambda c: c.id):
            for row in verify_case(case, product_root, scratch):
                if "shipped_rms" not in row:
                    print(f"{row['case']:42s}  {row.get('note', '')}")
                    continue
                line = (f"{row['case']:42s} t{row['tooth']:<3d} "
                        f"{row['variant']:>5s}  shipped {row['shipped_rms']:.4f}"
                        f"/{row['shipped_p90']:.4f}")
                for v in row["variants"]:
                    if "rms" in v:
                        line += f"  | {v['seed']}: {v['rms']:.4f}/{v['p90']:.4f}"
                    else:
                        line += f"  | {v['seed']}: REFUSED"
                print(line)
                best = improvement_of(row)
                if best is not None:
                    improvements += 1
                    print(f"{'':42s}  ^ IMPROVEMENT AVAILABLE via "
                          f"{best['seed']}: {row['shipped_rms']:.4f} -> "
                          f"{best['rms']:.4f} RMS")
        print(f"\n{improvements} site(s) with a better seat available. "
              "This is a report; rehearse remains the gate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
