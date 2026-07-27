#!/usr/bin/env python
"""Library qualification gate (slice 31 / queue #10) — per-vendor-drop acceptance
report over ``data/real/library``.

The catalog already burned the project twice: zimmer-4.5-6020/6030 are BYTE-IDENTICAL
(sha256) to their neodent-gm counterparts and nothing noticed (autopsy L3, 2026-07-23),
and an earlier drop shipped mis-axed caps (superseded-2026-07-13). This tool is the
acceptance instrument a vendor drop must pass before its files feed the pipeline.

Per file it measures (all deterministic; RNG is a LOCAL ``default_rng(0)`` for the
area-uniform surface sampling — the pipeline's global seed is never touched):

- sha256 + byte size, with DUPLICATE DETECTION across models and vendors;
- filename parses to a CapSpec (caps only — construction parts have no size grammar);
- single connected component (a fragmented CAD would SDF/segment unpredictably);
- watertightness — RECORDED, not judged: caps and construction shells are open by
  design (their boundary loops ARE the channel record);
- canonicalization axis VERIFIES: revolution self-similarity about canonical +z
  (trimmed 60% mean self-distance over six angles, the ingest recipe) must be under
  0.25mm — the healthy catalog measures 0.048-0.109, a mis-axed part reads 10x that;
- channel boundary loop present (``domain/channel.py`` — the loop-truth bore G1 bores
  at; a cap without one falls back to the poisoned-era centroid path);
- rim ring measurable (caps): the trimmed-band Kasa read every clocking and seat
  instrument anchors on (recipe mirrors ``auto_flow._ring_centre_3d``).

Output: a markdown report to stdout; ``--write [PATH]`` also writes it (default
``reports/library-qualification.md``). The report is byte-deterministic for an
unchanged library (no timestamps), so re-runs diff clean.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import trimesh

_WORKER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_WORKER / "src"))

from case_prep.adapters.cap_library import parse_spec_filename  # noqa: E402
from case_prep.adapters.ingest import canonicalize_library, canonicalize_revolute  # noqa: E402
from case_prep.domain.channel import channel_from_boundary_loops  # noqa: E402
from case_prep.domain.design_rules import designed_lumen_radius  # noqa: E402

DEFAULT_LIBRARY = _WORKER / "data" / "real" / "library"
DEFAULT_REPORT = _WORKER / "reports" / "library-qualification.md"

MAX_REVOLUTION_ERROR_MM = 0.25  # healthy catalog 0.048-0.109 (measured 2026-07-23 at
#                                 2500 samples, caps AND construction); the superseded
#                                 mis-axed drop is the failure this bound exists to catch
_REV_SAMPLES = 2500
_REV_ANGLES_DEG = (30.0, 60.0, 90.0, 120.0, 150.0, 180.0)


@dataclass
class FileRecord:
    rel_path: str            # relative to the library root, posix separators
    kind: str                # "cap" | "construction"
    sha256: str
    size_bytes: int
    n_vertices: int
    n_faces: int
    bodies: int
    watertight: bool         # informational — open shells are the catalog norm
    spec_label: Optional[str]         # parsed CapSpec label (caps), None otherwise
    revolution_error_mm: Optional[float]
    channel_mouth_r_mm: Optional[float]
    channel_mouth_xy: Optional[tuple]  # (x, y) canonical, caps only
    ring_xy: Optional[tuple]           # rim ring Kasa centre, caps only
    issues: List[str] = field(default_factory=list)

    @property
    def qualified(self) -> bool:
        return not self.issues


@dataclass
class LibraryQualification:
    root: Path
    records: List[FileRecord]
    findings: List[str]      # library-level findings (duplicates, empty drops)
    skipped: List[str]       # superseded/history files excluded from acceptance


def _revolution_error_z(mesh: trimesh.Trimesh) -> Optional[float]:
    """Trimmed self-similarity about canonical +z — the ``canonicalize_revolute``
    scoring recipe, re-run as verification on the FINISHED canonical frame."""
    from scipy.spatial import cKDTree

    tri = np.asarray(mesh.triangles, float)
    areas = np.asarray(mesh.area_faces, float)
    if len(tri) == 0 or areas.sum() <= 0:
        return None
    rng = np.random.default_rng(0)  # local generator: deterministic, no global state
    idx = rng.choice(len(tri), size=min(_REV_SAMPLES, len(tri) * 3), p=areas / areas.sum())
    u, w = rng.random((len(idx), 1)), rng.random((len(idx), 1))
    flip = (u + w) > 1.0
    u[flip], w[flip] = 1.0 - u[flip], 1.0 - w[flip]
    t = tri[idx]
    sub = t[:, 0] + u * (t[:, 1] - t[:, 0]) + w * (t[:, 2] - t[:, 0])
    sub = sub - sub.mean(axis=0)
    tree = cKDTree(sub)
    total = 0.0
    for ang in _REV_ANGLES_DEG:
        r = trimesh.transformations.rotation_matrix(np.radians(ang), [0.0, 0.0, 1.0])[:3, :3]
        d = np.sort(tree.query(sub @ r.T)[0])
        total += float(d[: int(len(d) * 0.6)].mean())
    return total / len(_REV_ANGLES_DEG)


def _ring_centre_xy(canonical: trimesh.Trimesh) -> Optional[tuple]:
    """Rim-ring Kasa centre in the canonical frame (recipe mirrors
    ``auto_flow._ring_centre_3d`` — the anchor of every ring-fixed instrument)."""
    v = np.asarray(canonical.vertices, float)
    rmax = float(np.percentile(np.linalg.norm(v[:, :2], axis=1), 97))
    ring = v[np.linalg.norm(v[:, :2], axis=1) > rmax - 0.4]
    if len(ring) < 20:
        return None
    uv = ring[:, :2]
    a = np.c_[2.0 * uv, np.ones(len(uv))]
    sol, *_ = np.linalg.lstsq(a, (uv ** 2).sum(axis=1), rcond=None)
    return (float(sol[0]), float(sol[1]))


def _qualify_file(path: Path, root: Path, kind: str) -> FileRecord:
    rel = path.relative_to(root).as_posix()
    raw = path.read_bytes()
    mesh = trimesh.load(path, force="mesh")
    issues: List[str] = []

    spec = parse_spec_filename(path.name) if kind == "cap" else None
    if kind == "cap" and spec is None:
        issues.append("filename does not parse as <model>-<variant>.stl")

    bodies = len(mesh.split(only_watertight=False))
    if bodies != 1:
        issues.append(f"{bodies} connected components (expected 1)")

    rev_err: Optional[float] = None
    mouth_r: Optional[float] = None
    mouth_xy = None
    ring_xy = None
    if len(mesh.vertices) >= 10 and len(mesh.faces) > 0:
        if kind == "cap":
            canonical, _ = canonicalize_revolute(mesh)
        else:
            canonical, _ = canonicalize_library(mesh)
        rev_err = _revolution_error_z(canonical)
        if rev_err is not None and rev_err > MAX_REVOLUTION_ERROR_MM:
            issues.append(
                f"canonical axis does NOT verify: revolution error "
                f"{rev_err:.3f}mm > {MAX_REVOLUTION_ERROR_MM}mm (healthy catalog 0.048-0.109)")
        if kind == "cap":
            channel = channel_from_boundary_loops(canonical)
            if channel is None:
                issues.append(
                    "no channel boundary loop (the loop-truth bore read fails; "
                    "boring would fall back to the estimator path)")
            else:
                mouth_r = float(channel.mouth_radius)
                mouth_xy = (float(channel.mouth_centre[0]), float(channel.mouth_centre[1]))
            ring_xy = _ring_centre_xy(canonical)
            if ring_xy is None:
                issues.append("rim ring unmeasurable (Kasa band < 20 points)")
        else:
            lumen = designed_lumen_radius(canonical)
            if lumen is None:
                issues.append(
                    "no readable designed-lumen record (export gate reports "
                    "channel_lumen_match=unknown for this vendor — C7 debt)")
            else:
                mouth_r = lumen
    else:
        issues.append(f"degenerate mesh ({len(mesh.vertices)} vertices)")

    return FileRecord(
        rel_path=rel,
        kind=kind,
        sha256=hashlib.sha256(raw).hexdigest(),
        size_bytes=len(raw),
        n_vertices=len(mesh.vertices),
        n_faces=len(mesh.faces),
        bodies=bodies,
        watertight=bool(mesh.is_watertight),
        spec_label=(spec.label if spec else None),
        revolution_error_mm=rev_err,
        channel_mouth_r_mm=mouth_r,
        channel_mouth_xy=mouth_xy,
        ring_xy=ring_xy,
        issues=issues,
    )


def qualify_library(root: "Path | str" = DEFAULT_LIBRARY) -> LibraryQualification:
    """Qualify every current STL under ``root`` (caps/ and construction/ trees).
    Directories named ``superseded*`` are historical drops — excluded from acceptance
    but listed, so the report shows what the exclusion hides."""
    root = Path(root)
    records: List[FileRecord] = []
    skipped: List[str] = []
    findings: List[str] = []
    for kind, sub in (("cap", "caps"), ("construction", "construction")):
        base = root / sub
        if not base.is_dir():
            findings.append(f"MISSING TREE: no `{sub}/` directory under the library root")
            continue
        for path in sorted(base.rglob("*.stl")):
            rel = path.relative_to(root).as_posix()
            if any(part.startswith("superseded") for part in path.relative_to(root).parts):
                skipped.append(rel)
                continue
            records.append(_qualify_file(path, root, kind))

    # duplicate detection across the whole drop — models AND vendors
    by_sha: Dict[str, List[FileRecord]] = {}
    for rec in records:
        by_sha.setdefault(rec.sha256, []).append(rec)
    for sha, recs in sorted(by_sha.items()):
        if len(recs) > 1:
            names = " == ".join(r.rel_path for r in recs)
            findings.append(
                f"DUPLICATE FILES (byte-identical, sha256 {sha[:12]}…): {names} — "
                "cross-system shared CAD; library provenance must be resolved with the vendor")
            for r in recs:
                r.issues.append(f"byte-identical to {len(recs) - 1} other file(s), "
                                f"sha256 {sha[:12]}…")
    if not records:
        findings.append("EMPTY DROP: no qualifying STL files found")
    return LibraryQualification(root=root, records=records, findings=findings, skipped=skipped)


def _fmt(x, nd=3, dash="—"):
    return dash if x is None else f"{x:.{nd}f}"


def render_markdown(q: LibraryQualification) -> str:
    n_ok = sum(1 for r in q.records if r.qualified)
    lines = [
        "# Library qualification report",
        "",
        f"Library root: `{q.root}`",
        f"Files qualified: **{n_ok}/{len(q.records)}** "
        f"({len(q.skipped)} superseded/historical files excluded)",
        "",
        "## Findings",
        "",
    ]
    if q.findings:
        lines += [f"- {f}" for f in q.findings]
    else:
        lines.append("- none")
    lines += [
        "",
        "## Per-file record",
        "",
        "| file | verdict | sha256 (12) | verts | bodies | watertight | rev err mm "
        "| channel r mm | channel xy | ring xy |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in q.records:
        verdict = "OK" if r.qualified else "FLAG"
        xy = "—" if r.channel_mouth_xy is None else \
            f"({r.channel_mouth_xy[0]:+.3f},{r.channel_mouth_xy[1]:+.3f})"
        ring = "—" if r.ring_xy is None else f"({r.ring_xy[0]:+.3f},{r.ring_xy[1]:+.3f})"
        lines.append(
            f"| {r.rel_path} | {verdict} | {r.sha256[:12]} | {r.n_vertices} | {r.bodies} "
            f"| {'yes' if r.watertight else 'no'} | {_fmt(r.revolution_error_mm)} "
            f"| {_fmt(r.channel_mouth_r_mm)} | {xy} | {ring} |")
    flagged = [r for r in q.records if not r.qualified]
    if flagged:
        lines += ["", "## Flags", ""]
        for r in flagged:
            for issue in r.issues:
                lines.append(f"- `{r.rel_path}`: {issue}")
    if q.skipped:
        lines += ["", "## Excluded (superseded/historical)", ""]
        lines += [f"- `{s}`" for s in q.skipped]
    lines += [
        "",
        "_Acceptance bounds: revolution error <= "
        f"{MAX_REVOLUTION_ERROR_MM}mm about the canonical axis (healthy catalog "
        "0.048-0.109, measured 2026-07-23); channel/ring reads per "
        "`domain/channel.py` envelopes. Watertightness is recorded, not judged: "
        "open shells are the catalog norm and their boundary loops are the channel "
        "truth source._",
        "",
    ]
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--library", type=Path, default=DEFAULT_LIBRARY,
                    help=f"library root (default {DEFAULT_LIBRARY})")
    ap.add_argument("--write", nargs="?", type=Path, const=DEFAULT_REPORT, default=None,
                    metavar="PATH",
                    help=f"also write the report (default path {DEFAULT_REPORT})")
    args = ap.parse_args(argv)
    if not args.library.is_dir():
        print(f"library root not found: {args.library}", file=sys.stderr)
        return 2
    q = qualify_library(args.library)
    report = render_markdown(q)
    print(report)
    if args.write is not None:
        args.write.parent.mkdir(parents=True, exist_ok=True)
        args.write.write_text(report)
        print(f"[written {args.write}]", file=sys.stderr)
    return 0 if all(r.qualified for r in q.records) and q.records else 1


if __name__ == "__main__":
    raise SystemExit(main())
