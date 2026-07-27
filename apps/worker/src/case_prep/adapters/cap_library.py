"""Filesystem cap library + library-driven cap detection.

The library is a directory of healing-cap/scan-body CADs named ``<type>-<diameter>.stl``
(e.g. ``certain-4.1.stl``, ``tsv-4.5.stl``). ``detect_caps`` template-matches EVERY library
entry along the arch (the proven discriminator: a cap fits its template ~0.65, a tooth ~0.2)
and resolves the candidates into distinct sites — count + center + type in one pass, with no
type pre-declared by the doctor.

Stand-in note: until the client provides per-type CADs, a single-template library (e.g. the
the vendor ``certain`` CAD) detects caps of that family; unknown families surface as low-fitness
flags rather than silent misses.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import trimesh

from case_prep.adapters import open3d_engine as engine
from case_prep.adapters.ingest import canonicalize_revolute
from case_prep.domain.poses import Retention
from case_prep.domain.cap_catalog import CandidateMatch, CapSite, CapSpec, CapType, resolve_sites

# lowercase-only by policy, matching the lowercase ``*.stl`` glob in ``CapLibrary.load`` —
# one consistent rule instead of a case-insensitive parser feeding a case-sensitive glob
_NAME = re.compile(r"^(?P<model>[a-z0-9]+(?:-[a-z0-9.]+)*?)-(?P<variant>\d+(?:\.\d+)?)\.stl$")
_MIN_TEMPLATE_VERTICES = 10  # a degenerate STL would SVD into garbage in canonicalization


def parse_spec_filename(name: str) -> Optional[CapSpec]:
    """``certain-4.1.stl`` -> CapSpec('certain', '4.1'); ``neodent-gm-5020.stl`` ->
    CapSpec('neodent-gm', '5020') — the LAST hyphen-number is the size variant, everything
    before it the model. None for anything else."""
    m = _NAME.match(name)
    if not m:
        return None
    return CapSpec(m.group("model"), m.group("variant"))


def _native_dims(mesh: trimesh.Trimesh) -> "tuple":
    """(rim diameter, height) in the file's NATIVE frame — cap CADs arrive axis-aligned
    (z = cap axis). Must run BEFORE canonicalization: PCA reorients squat variants whose
    radial spread exceeds their height."""
    v = np.asarray(mesh.vertices, float)
    c = v - v.mean(axis=0)
    dia = float(2 * np.percentile(np.linalg.norm(c[:, :2], axis=1), 97))
    return dia, float(np.ptp(v[:, 2]))


@dataclass
class CapLibrary:
    """The catalog of known cap templates, each canonicalized to the engine's local frame.
    (Plain dataclass: ``frozen=True`` over a Dict field is a false promise — it is neither
    hashable nor deeply immutable — review finding.)"""

    _templates: Dict[CapSpec, trimesh.Trimesh]
    _dims: Dict[CapSpec, "tuple"] = None  # spec -> (rim diameter, height), native frame
    # Whether this library's parts seat RIM-FIRST (healing caps) or by ICP (scan
    # bodies). Set by CONSTRUCTION: a directory catalog of <model>-<variant> caps is a
    # healing-cap library by contract (load() sets True); None = decide geometrically
    # (the single-template stand-in path). Aspect ratio alone cannot decide — with
    # correctly-canonicalized axes a narrow-tall 4030 cap (ratio 0.70) reads MORE
    # scan-body-like than the real vendor scan body (0.97); the old wider-than-tall
    # heuristic only ever separated them because the tilted frames inflated cap widths
    # (found 2026-07-15 when the axis fix silently flipped neodent to ICP seating).
    _rim_seatable: "Optional[bool]" = None

    @classmethod
    def load(cls, directory: "Path | str",
             extra: "Optional[Dict[str, Path]]" = None) -> "CapLibrary":
        """The model's CURRENT catalog: the TOP-LEVEL ``<model>-<variant>.stl`` files only.
        Subdirectories (the ``superseded-YYYY-MM-DD/`` archives) are deliberately NOT
        globbed — widening the glob would silently fold archived parts into every case's
        auto-identification candidate set and collide with the current same-named variant.

        ``extra`` is the EXPLICIT escape hatch (client directive 2026-07-25, "the lab
        chooses, the software never guesses"): ``{variant_label: stl_path}`` naming a part
        the operator picked OUTSIDE the top level — e.g.
        ``{"superseded-2026-07-13--6020": .../superseded-2026-07-13/zimmer-4.5-6020.stl}``,
        the catalog's own entry id (adapters/library_catalog). Nothing is discovered here:
        the caller names both the label and the file, so the current catalog semantics are
        unchanged for every caller that passes nothing."""
        templates: Dict[CapSpec, trimesh.Trimesh] = {}
        dims: Dict[CapSpec, tuple] = {}
        model_of_dir: Optional[str] = None

        def _ingest(spec: CapSpec, path: Path, shown: str) -> None:
            if spec in templates:  # e.g. certain-4.1.stl vs certain-4.10.stl both parse to 4.1
                raise ValueError(f"duplicate cap template for {spec.label}: {shown}")
            mesh = trimesh.load(path, force="mesh")
            if len(mesh.vertices) < _MIN_TEMPLATE_VERTICES:
                raise ValueError(f"cap template {shown} is degenerate "
                                 f"({len(mesh.vertices)} vertices)")
            dims[spec] = _native_dims(mesh)
            local, _ = canonicalize_revolute(mesh)
            templates[spec] = local

        for path in sorted(Path(directory).glob("*.stl")):
            spec = parse_spec_filename(path.name)
            if spec is None:
                continue
            model_of_dir = model_of_dir or spec.model
            _ingest(spec, path, path.name)
        for label, path in sorted((extra or {}).items()):
            path = Path(path)
            # the model comes from the directory's own parts (or the file's name) — an
            # explicit pick never renames the family it belongs to
            named = parse_spec_filename(path.name)
            model = model_of_dir or (named.model if named is not None else None)
            if model is None:
                raise ValueError(f"cannot place {label!r} ({path.name}) in a model family "
                                 f"— {directory} holds no <model>-<variant>.stl parts")
            _ingest(CapSpec(model, label), path, f"{label} ({path})")
        if not templates:
            raise ValueError(f"no cap templates (<type>-<diameter>.stl) found in {directory}")
        return cls(templates, dims, True)

    @classmethod
    def single(cls, spec: CapSpec, mesh: trimesh.Trimesh) -> "CapLibrary":
        """A one-template library (the stand-in path until per-type CADs arrive)."""
        dims = {spec: _native_dims(mesh)}
        local, _ = canonicalize_revolute(mesh)
        return cls({spec: local}, dims)

    @property
    def rim_seatable(self) -> bool:
        """True when this library's parts seat rim-first (healing caps). Constructed
        catalogs say so explicitly (see _rim_seatable's doc); stand-ins fall back to
        the wider-than-tall geometry test that historically separated squat caps from
        tall scan bodies."""
        if self._rim_seatable is not None:
            return self._rim_seatable
        votes = []
        for sp in self.specs:
            e = self._templates[sp].bounds[1] - self._templates[sp].bounds[0]
            votes.append(1.0 if max(e[0], e[1]) >= 1.2 * e[2] else 0.0)
        return bool(votes) and float(np.median(votes)) >= 0.5

    @property
    def specs(self) -> List[CapSpec]:
        return list(self._templates)

    def template(self, spec: CapSpec) -> trimesh.Trimesh:
        return self._templates[spec]

    def variant_dimensions(self) -> Dict[str, "tuple"]:
        """variant label -> (rim diameter, height) in mm, native frame — the classification
        table for measured-diameter variant identification."""
        return {spec.variant: d for spec, d in (self._dims or {}).items()}


def detect_caps_clinical(scan_points: np.ndarray, library: CapLibrary,
                         normals: Optional[np.ndarray] = None,
                         max_sites: int = 8,
                         max_void_ratio: float = 0.7,
                         min_coverage: float = 0.5) -> List[CapSite]:
    """Clinical healing-cap detection: geometry proposes, the library disposes.

    Low-profile caps cannot be separated from tissue artifacts by local geometry alone
    (measured across two real arches: cap and false-positive feature ranges overlap), so the
    rim-slab stack (``cap_detection.find_cap_sites``) runs RECALL-oriented as a candidate
    generator, and each candidate is confirmed by a 2D rule measured across both real arches
    (no single scalar separates): (a) the candidate's VOID RATIO <= max_void_ratio — a palate
    slope has no real recess (measured 0.79 vs caps 0.37-0.62); and (b) the registered
    template's SCAN-COVERAGE >= min_coverage — the fraction of the isolated ROI the template
    explains; an interproximal embrasure fakes the ring but one cap template cannot cover two
    tooth flanks (measured 0.43 vs caps 0.56-0.83). Whole-template ICP fitness is recorded but
    does NOT gate: scans capture only a cap's exposed top, so full-CAD fitness is structurally
    low (~0.3-0.45) for real caps. Margins are thin (n=5 labeled sites, 2 arches) — clinical
    use stays behind ADVISORY mode. Registration snaps the center and identifies the variant,
    so this returns the client-flow answer: how many caps, where, and which type."""
    from case_prep.adapters.cap_detection import crown_up_axis, find_cap_sites

    pts = np.asarray(scan_points, dtype=float)
    candidates = find_cap_sites(pts, max_sites=max_sites, normals=normals)
    if not candidates:
        return []

    # localize/register assume a CROWNS-UP (z-occlusal) frame; doctor scans arrive in arbitrary
    # scanner frames, so run the confirmation in the normalized frame and map centers back.
    # (Feeding raw-frame points silently yields loc=None for every candidate — measured.)
    a = crown_up_axis(pts, normals)
    t0 = np.cross(a, [0.0, 0.0, 1.0])
    if np.linalg.norm(t0) < 1e-6:
        t0 = np.array([1.0, 0.0, 0.0])
    t0 /= np.linalg.norm(t0)
    frame = np.c_[t0, np.cross(a, t0), a]          # right-handed; local = (p-origin)@frame
    origin = pts.mean(axis=0)
    L = (pts - origin) @ frame
    Ln = np.asarray(normals, float) @ frame if normals is not None else None

    from scipy.spatial import cKDTree

    matches: List[CandidateMatch] = []
    for cand in candidates:
        if cand.void_ratio > max_void_ratio:
            continue  # no real recess (palate-slope class)
        seed_local = frame.T @ (np.asarray(cand.center) - origin)
        loc = engine.localize_from_seed(L, seed_local, normals=Ln)
        if loc is None:
            continue
        roi = np.asarray(loc.roi_points, float)
        for spec in library.specs:
            transform, conf = engine.register(loc, library.template(spec), Retention.CEMENT)
            sampled, _ = trimesh.sample.sample_surface(library.template(spec), 2500)
            world_t = np.asarray(sampled, float) @ transform.rotation.T + transform.translation
            coverage = float((cKDTree(world_t).query(roi)[0] < 0.35).mean())
            if coverage >= min_coverage:
                world = origin + frame @ transform.apply(np.zeros(3))
                matches.append(CandidateMatch(
                    spec=spec,
                    center=tuple(float(x) for x in world),
                    fitness=coverage))  # ranking signal = coverage (see docstring)
    return resolve_sites(matches)


def detect_caps(scan_points: np.ndarray, library: CapLibrary,
                normals: Optional[np.ndarray] = None, max_sites: int = 8) -> List[CapSite]:
    """Answer the client-flow question: how many healing caps, where, and which type.

    Runs the proven template-matcher (``engine.auto_localize``) once per library template, then
    merges all candidates via the domain's ``resolve_sites`` — the best-fitting template at each
    location identifies the cap type; distinct locations give the count.
    """
    candidates: List[CandidateMatch] = []
    for spec in library.specs:
        detections = engine.auto_localize(
            scan_points, library.template(spec), max_bodies=max_sites, normals=normals)
        candidates.extend(
            CandidateMatch(
                spec=spec,
                center=tuple(float(x) for x in det.transform.apply(np.zeros(3))),
                fitness=det.fitness,
            )
            for det in detections
        )
    return resolve_sites(candidates)
