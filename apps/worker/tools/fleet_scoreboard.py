"""Fleet scoreboard (client ask 2026-07-18: "do this in the test cases across all of the
select cases ... as a test that we know what changes are improving or not improving the
model"). Runs EVERY real case's curated gesture through the production pipeline and scores
each site on the metrics that matter clinically, then compares against a stored baseline
snapshot so every algorithm change gets a per-site improved/regressed/unchanged verdict.

Usage (from apps/worker):
    .venv/bin/python tools/fleet_scoreboard.py                      # score + print
    .venv/bin/python tools/fleet_scoreboard.py --save baseline      # store a named snapshot
    .venv/bin/python tools/fleet_scoreboard.py --baseline baseline  # score + diff vs snapshot

Metrics per site (all mm/deg, smaller is better unless noted):
    rim_agreement   band-anchored rim seat (p90, the doctor-facing number)
    top_face_p90    posed top face -> scan (the depth/ride-off readout)
    rim_off_centre  posed rim-circle centre vs scanned rim-circle centre (occlusal)
    rim_agreement_machine / rim_off_centre_machine
                    MACHINE-ANCHORED QA twins (slices 14-15, §8 item 6, 2026-07-24):
                    the same two rim instruments anchored to the island shadow's
                    machine ring instead of the clicks (invariant Q2 — the click-
                    anchored copies grade the pose against the very gesture that
                    drove it; measured: a 1.09mm-off pose IMPROVED click-anchored
                    rim_agreement 0.62->0.88). None + row reason when the island is
                    unconverged. DUAL-REPORT period: deliberately NOT in _EPS — the
                    click-anchored columns stay the tracked metrics; when promotion
                    lands (DR1 cleared) the machine variants become the tracked/_EPS
                    columns and the click-anchored ones sunset (slice 29)
    bore_void_off   posed template BORE centre vs the scanned screw-recess VOID centre —
                    the "is the screw hole where the scan says it is" number (None when the
                    scan shows no usable void: shallow/sparse recess)
    id_match        identified variant class vs declared (when declared)
    confidence      the pipeline's own grade (high/medium/low)
    island_off      SHADOW (slice 6): machine-segmented island centre vs the shipped
                    rim centre — reported next to the pose, never moving it
    island_conv     SHADOW: island convergence (gates in domain/island.py); None on
                    rows from before the shadow landed
    delivered_channel_vs_recess / delivered_channel_vs_cap_channel / delivered_channel_r_mm
                    MEASUREMENT columns (G3 / slice 12, 2026-07-23): the AS-BUILT screw
                    channel of the site's emitted prosthesis STL (un-posed by
                    inv(pose_matrix), cross-section hole-ring stack —
                    final_product.measure_delivered_channel) vs (a) the RAW scanned
                    recess dip (occlusal, local frame) and (b) the cap CAD's loop-truth
                    channel at the shipped pose (shared canonical frame), plus the
                    as-built radius. Deliberately NOT in _EPS — these measure the
                    deliverable, they never vote improved/regressed. Seed rows (autopsy
                    2026-07-23, world-frame projection at the estimator-era void gate):
                    0.596/0.838/0.821 vs recess, 0.357/~0.38/0.375 vs cap channel; the
                    same shipped packages in THIS column's convention (local occlusal
                    frame, raw dip, loop-truth cap read, cap-mouth evaluation plane)
                    measure 0.720/0.840/0.876 and 0.358/0.344/0.375 — the same defect,
                    reproduced by the shipped instrument before the G1 fix landed.
                    Since 2026-07-24 the measurement itself is the SHARED instrument
                    auto_flow.delivered_channel_offsets (§8 item 12): the run row and
                    this column call one function — this file only loads + un-poses
                    the emitted STL.
    too_close       SURFACED (slice 4): the row's variant.candidates_too_close — the
                    scan could not separate the top two size candidates (an invisible
                    high-blocker before 2026-07-24); flag, tracked as changed
    detect_hit / detect_off_mm
                    DETECTION RECALL (slice 10, FIND instrumentation, 2026-07-24): did
                    the propose stage (find_cap_sites, run ONCE per case on the raw
                    scan) produce a candidate within 2.0mm — occlusal in-plane, the
                    click-noise convention — of this confirmed site's centre, and how
                    far was the nearest candidate. MEASUREMENT columns: never in _EPS
                    (detect_hit flips surface as "changed"); they instrument the FIND
                    link the strategy text used to overclaim ("detection already
                    works" — measured fleet-wide 2026-07-24: 8/10 hit at
                    0.002-0.51mm; 2 MISSES, cap7020-t3 and zimmer-t7, where
                    candidates exist elsewhere on the arch but the nearest sits
                    7.24/5.42mm from the confirmed site). Adds one find_cap_sites
                    call per case, ~5-20s each (measured 85s over the 9-case fleet)

Snapshots live in reports/scoreboard/<name>.json. Deterministic: same code + data = same
numbers (run_auto_case pins the RNG; find_cap_sites draws nothing)."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import trimesh
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from case_prep.adapters.cap_detection import find_cap_sites  # noqa: E402
from case_prep.adapters.cap_library import CapLibrary  # noqa: E402
from case_prep.pipeline.auto_flow import (  # noqa: E402
    ConfirmedSite,
    _crowns_frame,
    _ring_centre_3d,
    _screw_recess_centre,
    _template_bore_centre,
    delivered_channel_offsets,
    run_auto_case,
)

ROOT = Path(__file__).resolve().parents[1]
SNAP_DIR = ROOT / "reports" / "scoreboard"

# A metric delta smaller than this is noise, not a change (mm / deg as applicable).
_EPS = {"rim_agreement": 0.03, "top_face_p90": 0.03, "rim_off_centre": 0.03,
        "bore_void_off": 0.05, "notch_shift_deg": 2.0}

# Detection-recall hit bar (slice 10): a propose-stage candidate within this occlusal
# in-plane distance of the confirmed site centre counts as a hit. 2.0mm = comfortably
# inside the seat's own snap basin while far past the click-noise envelope (p90 0.61mm)
# — a candidate this close would have seeded the identical seat.
_DETECT_HIT_MM = 2.0


def _bore_void_offset(L, Rl, Tl, template) -> "float | None":
    """Posed template bore centre vs the scanned screw-recess void centre, occlusal mm —
    via the PRODUCTION helpers (single source of truth). None when the scan shows no
    usable void (sparse or shallow recess) — withheld rather than guessed. NOTE: the
    reachability convention follows the production pass of the day the snapshot was
    taken — 'baseline' (2026-07-18) used axis-relative reach with the below-plane-average
    estimator; since 2026-07-19 the pass is RING-FIXED, so reach is measured from the
    posed rim-ring centre with radius |bore - ring| (estimator differences <=~0.15mm —
    small next to the 0.5-1.5mm clocking effect being tracked). Since 2026-07-23 the
    bore is the BOUNDARY-LOOP truth read (domain/channel.py) — the old top-core
    centroid sat 0.87-1.06mm away at ~174deg the wrong azimuth, so this column is NOT
    comparable across that date: the loop-truth bore is nearly ring-concentric
    (|bore - ring| 0.02-0.11mm catalog-wide), which both moves the posed-bore end of
    the metric and tightens the reachability window (more honest Nones on sites whose
    recess dip sits beyond the bore's true reach)."""
    bore = _template_bore_centre(template)
    if bore is None:
        return None
    ring3 = _ring_centre_3d(template)
    ring3 = ring3 if ring3 is not None else np.zeros(3)
    g0 = (Rl @ ring3 + Tl)[:2]
    tv = np.asarray(template.vertices, float)
    top = tv[tv[:, 2] > tv[:, 2].max() - 1.0]
    rmax = float(np.percentile(np.linalg.norm(top[:, :2], axis=1), 95))
    void_c = _screw_recess_centre(L, g0, rmax,
                                expected_radius=float(
                                    np.linalg.norm((bore - ring3)[:2])))
    if void_c is None:
        return None
    return float(np.linalg.norm((Rl @ bore + Tl)[:2] - void_c))


def _delivered_channel_metrics(prod_path: Path, pose_w: np.ndarray, frame: np.ndarray,
                               origin: np.ndarray, L: np.ndarray,
                               template) -> dict:
    """MEASUREMENT columns (G3 / slice 12): the emitted prosthesis STL's as-built
    channel vs the raw recess dip and the cap's loop-truth channel. Since 2026-07-24
    (§8 item 12) the measurement itself is auto_flow.delivered_channel_offsets — ONE
    instrument shared with the run row the verification panel reads, so scoreboard and
    panel can never drift; this wrapper only loads the emitted STL and un-poses it
    into the canonical frame. None-safe: a missing product withholds every number."""
    out = {"delivered_channel_vs_recess": None, "delivered_channel_vs_cap_channel": None,
           "delivered_channel_r_mm": None}
    if not prod_path.exists():
        return out
    prod = trimesh.load(prod_path, force="mesh")
    prod.apply_transform(np.linalg.inv(np.asarray(pose_w, float)))
    return delivered_channel_offsets(prod, pose_w, frame, origin, L, template)


def score_fleet() -> dict:
    rows = []
    for folder in sorted(p.name for p in (ROOT / "data/real/scans").iterdir()
                         if (p / "sites.json").exists()):
        model = "neodent-gm" if "neodent-gm" in folder else "zimmer-4.5"
        scan = trimesh.load(next((ROOT / "data/real/scans" / folder).glob("*.stl")),
                            force="mesh")
        pts = np.asarray(scan.vertices, float)
        frame, origin, _ = _crowns_frame(pts, np.asarray(scan.vertex_normals, float))
        L = (pts - origin) @ frame
        # DETECTION RECALL (slice 10): the propose stage run ONCE per case on the raw
        # scan — the same call the server's propose endpoint makes — measured against
        # every confirmed site below (occlusal in-plane, the click-noise convention).
        # find_cap_sites draws nothing, so determinism is untouched.
        cand_xy = np.array([((np.asarray(c.center, float) - origin) @ frame)[:2]
                            for c in find_cap_sites(
                                pts, normals=np.asarray(scan.vertex_normals, float))])
        lib = CapLibrary.load(ROOT / "data/real/library/caps" / model)
        vendor_dir = next((ROOT / "data/real/library/construction").glob(
            f"*/{model}-scanbody.stl"))
        sites = json.loads((ROOT / "data/real/scans" / folder / "sites.json"
                            ).read_text())["suggested_sites"]
        confirmed = [ConfirmedSite(s["tooth"], tuple(s["center"]),
                                   s.get("declared_variant"),
                                   center_mark=s.get("center_mark"),
                                   rim_mark=s.get("rim_mark"),
                                   rim_points=s.get("rim_points")) for s in sites]
        tmp = Path(tempfile.mkdtemp())
        out = run_auto_case(case_id="sb", scan=scan, library=lib,
                            construction_mesh=trimesh.load(vendor_dir, force="mesh"),
                            vendor=vendor_dir.parent.name, confirmed=confirmed,
                            jaw_label="x", out_dir=tmp / "out",
                            compute_confidence=True)
        for s, row in zip(sites, out["sites"]):
            if row.get("error"):
                rows.append({"site": f"{folder}/t{s['tooth']}", "error": row["error"]})
                continue
            rec = json.loads((tmp / "out" / f"sb-{s['tooth']}-implant.json").read_text())
            pose_w = np.array(rec["pose_matrix"], float)
            Rl = frame.T @ pose_w[:3, :3]
            Tl = frame.T @ (pose_w[:3, 3] - origin)
            spec = next(sp for sp in lib.specs
                        if sp.variant == row["variant"]["identified"])
            template = lib.template(spec)

            # rim off-centre: posed rim ring vs scanned rim band (marks-anchored).
            # Since 2026-07-24 (§8 item 12) auto_flow computes this construction into
            # the run row itself (_rim_off_centre_mm — this file's math, moved to the
            # single source both panel and scoreboard read); the column consumes the
            # row rather than keeping a drift-prone second copy.
            rim_off = row.get("rim_off_centre")

            tvv = np.asarray(template.vertices, float)
            topf = tvv[tvv[:, 2] > tvv[:, 2].max() - 1.2]
            top_p90 = float(np.percentile(
                cKDTree(L).query(topf @ Rl.T + Tl)[0], 90))

            declared = s.get("declared_variant")
            dlv = _delivered_channel_metrics(
                tmp / "out" / f"sb-{s['tooth']}-prosthesis_cad.stl",
                pose_w, frame, origin, L, template)
            # detection recall for THIS site against the per-case candidate set
            site_xy = (frame.T @ (np.asarray(s["center"], float) - origin))[:2]
            detect_off = (float(np.min(np.linalg.norm(cand_xy - site_xy, axis=1)))
                          if len(cand_xy) else None)
            ck = row.get("clocking") or {}
            # SHADOW island columns (master plan slice 6): the machine-segmented
            # island vs the shipped rim centre — reported, never pose-affecting
            isl = row.get("island") or {}
            rows.append({
                "site": f"{folder}/t{s['tooth']}",
                "identified": row["variant"]["identified"],
                "declared": declared,
                "id_match": (None if not declared
                             else row["variant"]["identified"] == declared),
                "seat": row["seat_method"],
                "rim_agreement": row.get("rim_agreement_mm"),
                "top_face_p90": round(top_p90, 3),
                "rim_off_centre": (round(rim_off, 3) if rim_off is not None else None),
                # MACHINE-ANCHORED QA twins (slices 14-15): row fields computed by
                # auto_flow._machine_qa_twins against the island shadow's ring. NOT
                # in _EPS during the dual-report period — click-anchored stays the
                # tracked pair; at promotion (DR1) the machine variants take over
                # the _EPS slots and the click-anchored columns sunset (slice 29).
                "rim_agreement_machine": row.get("rim_agreement_machine_mm"),
                "rim_off_centre_machine": row.get("rim_off_centre_machine_mm"),
                "bore_void_off": (lambda v: round(v, 3) if v is not None else None)(
                    _bore_void_offset(L, Rl, Tl, template)),
                # coded-cutout clock (the client-facing rotation instrument):
                # shipped residual in degrees + which instrument anchored rotation
                "notch_shift_deg": ck.get("notch_shift_deg"),
                "clock_evidence": ck.get("evidence"),
                "clock_consistency_deg": ck.get("consistency_deg"),
                "island_off": isl.get("machine_centre_offset_mm"),
                "island_conv": isl.get("converged"),
                # G3 measurement columns — the delivered part itself, never estimators
                **dlv,
                # SURFACED (slice 4): the inseparable-variants verdict, now a column
                "too_close": row["variant"].get("candidates_too_close"),
                # FIND instrumentation (slice 10) — measurement columns, never in _EPS
                "detect_hit": bool(detect_off is not None
                                   and detect_off <= _DETECT_HIT_MM),
                "detect_off_mm": (round(detect_off, 3)
                                  if detect_off is not None else None),
                "confidence": (row.get("confidence") or {}).get("grade"),
                "gate": row["guidance"]["level"],
            })
    return {"rows": rows}


def compare(current: dict, baseline: dict) -> str:
    base = {r["site"]: r for r in baseline["rows"]}
    lines = ["| site | metric | baseline | now | verdict |", "|---|---|---|---|---|"]
    verdicts = {"improved": 0, "regressed": 0, "unchanged": 0}
    for r in current["rows"]:
        b = base.get(r["site"])
        if not b:
            continue
        for metric, eps in _EPS.items():
            cur, old = r.get(metric), b.get(metric)
            if cur is None or old is None:
                continue
            d = cur - old
            v = ("unchanged" if abs(d) <= eps
                 else "improved" if d < 0 else "regressed")
            verdicts[v] += 1
            if v != "unchanged":
                lines.append(f"| {r['site']} | {metric} | {old} | {cur} | **{v}** |")
        # island_conv is a SHADOW flag: convergence flips show as "changed" rows but
        # island_off is deliberately NOT in _EPS — shadow numbers must never mix into
        # the pose-metric improved/regressed verdict counts. Same rule for too_close
        # (slice 4) and detect_hit (slice 10): flips surface as "changed", but
        # detect_off_mm never votes improved/regressed (it measures FIND, not the pose)
        for flag in ("id_match", "confidence", "gate", "seat", "clock_evidence",
                     "island_conv", "too_close", "detect_hit"):
            if r.get(flag) != b.get(flag):
                lines.append(f"| {r['site']} | {flag} | {b.get(flag)} | {r.get(flag)} "
                             f"| **changed** |")
    lines.append("")
    lines.append(f"Summary: {verdicts['improved']} improved, "
                 f"{verdicts['regressed']} regressed, {verdicts['unchanged']} unchanged.")
    return "\n".join(lines)


def _render(snapshot: dict) -> str:
    lines = ["| site | id (decl) | seat | rim | rim-M | top p90 | off-ctr | off-ctr-M "
             "| bore-void "
             "| dlv-cap | dlv-recess | dlv-r "
             "| clock° (ev) | island (conv) | too-close | detect (off) "
             "| conf | gate |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in snapshot["rows"]:
        if "error" in r:
            lines.append(f"| {r['site']} | ERROR: {r['error']} |")
            continue
        decl = f" ({r['declared']})" if r["declared"] else ""
        clock = (f"{r.get('notch_shift_deg')} ({r.get('clock_evidence')})"
                 if r.get("clock_evidence") else "—")
        # SHADOW island: machine-centre offset vs shipped rim centre, or unconverged
        island = (f"{r.get('island_off')} (conv)" if r.get("island_conv")
                  else "unconv" if r.get("island_conv") is False else "—")
        # FIND recall: hit-with-distance, an explicit MISS, or — on pre-slice-10 rows
        detect = ("—" if r.get("detect_hit") is None
                  else f"hit ({r.get('detect_off_mm')})" if r.get("detect_hit")
                  else f"MISS ({r.get('detect_off_mm')})"
                  if r.get("detect_off_mm") is not None else "MISS (no candidate)")
        fmt = lambda v: "—" if v is None else v  # noqa: E731 — table cell shorthand
        lines.append(
            f"| {r['site']} | {r['identified']}{decl} | {r['seat']} "
            f"| {r['rim_agreement']} | {fmt(r.get('rim_agreement_machine'))} "
            f"| {r['top_face_p90']} | {r['rim_off_centre']} "
            f"| {fmt(r.get('rim_off_centre_machine'))} "
            f"| {r['bore_void_off']} "
            f"| {fmt(r.get('delivered_channel_vs_cap_channel'))} "
            f"| {fmt(r.get('delivered_channel_vs_recess'))} "
            f"| {fmt(r.get('delivered_channel_r_mm'))} "
            f"| {clock} | {island} "
            f"| {'yes' if r.get('too_close') else '—'} | {detect} "
            f"| {r['confidence']} | {r['gate']} |")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--save", metavar="NAME", help="store this run as a named snapshot")
    ap.add_argument("--baseline", metavar="NAME", help="diff against a stored snapshot")
    args = ap.parse_args()

    snap = score_fleet()
    print(_render(snap))
    if args.save:
        SNAP_DIR.mkdir(parents=True, exist_ok=True)
        (SNAP_DIR / f"{args.save}.json").write_text(json.dumps(snap, indent=2))
        print(f"\nsnapshot saved: reports/scoreboard/{args.save}.json")
    if args.baseline:
        base_path = SNAP_DIR / f"{args.baseline}.json"
        if not base_path.exists():
            raise SystemExit(f"no snapshot named {args.baseline!r} in reports/scoreboard/")
        print("\n== diff vs baseline ==")
        print(compare(snap, json.loads(base_path.read_text())))


if __name__ == "__main__":
    main()
