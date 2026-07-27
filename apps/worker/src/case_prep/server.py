"""The live-demo API: the real pipeline behind a small FastAPI server for the React demo UI.

    make serve            # from apps/worker  ->  http://localhost:8000

Endpoints (contract shared with apps/web):
    GET  /api/cases                      -> every scan folder + NON-BINDING suggestions
    GET  /api/constructions              -> every vendor construction part on disk
    GET  /api/library                    -> the full cross-model cap catalog
    GET  /api/relief-limit               -> the MAXIMUM SAFE gingival relief for a chosen
                                            (construction part x cap variant) pair, so the
                                            ceiling is on screen BEFORE Process is pressed
    GET  /api/cases/{id}/scan            -> the input jaw STL
    POST /api/cases/{id}/propose         -> live cap-site proposals (cached after first run)
    POST /api/cases/{id}/run             -> the full automation, under the operator's
                                            EXPLICIT selection (model + construction_path)
    GET  /api/cases/{id}/sites/{t}/deviation -> the three-panel union view's colouring
    POST /api/cases/{id}/sites/{t}/best-fit -> operator-triggered best-fit refinement of
                                            the shipped pose, judged by the same
                                            certification gates as every operator move
    GET  /api/cases/{id}/files/{name}    -> emitted package files (STL/JSON)

THE LAB CHOOSES, THE SOFTWARE NEVER GUESSES (client directive 2026-07-25): nothing here
infers the implant system or the construction part from a folder or file NAME. Cases load
from their scan alone; the name match survives only as a suggestion the operator may
accept, and the run refuses to proceed on a selection it was not given.

Everything served is live pipeline output on the client's real scans; results are cached
in-memory + on disk so a demo re-run is instant (pre-warm with tools/warm_demo.py).
"""
from __future__ import annotations

import warnings

# numpy on macOS Accelerate raises spurious "encountered in matmul" warnings on valid
# data (verified: results correct) — same filter as cli.py / pyproject pytest config
warnings.filterwarnings("ignore", message=".*encountered in matmul.*")

import hashlib
import json
import time
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import trimesh
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, field_validator, model_validator
from scipy.spatial import cKDTree

from case_prep.adapters import construction_catalog, library_catalog
from case_prep.adapters.cap_detection import measure_rim_diameter
from case_prep.adapters.cap_library import CapLibrary, parse_spec_filename
from case_prep.adapters.output_package import register_package_files
from case_prep.adapters.qc_render import (DEVIATION_CLAMP_MM, DEVIATION_COLORMAP,
                                          DEVIATION_FOOTPRINT_BAND_MM,
                                          render_alignment_proof, site_deviation_stats,
                                          vertex_deviation)
from case_prep.domain import design_rules
from case_prep.domain.acceptance import evaluate_acceptance
from case_prep.domain.capture_gate import assess_capture
from case_prep.adapters.ingest import canonicalize_revolute
from case_prep.domain.channel import channel_from_boundary_loops
from case_prep.domain.clock_signature import (notch_reading, scan_rim_centre,
                                              template_signature, wrap_deg)
from case_prep.domain.part_features import (FEATURE_KINDS, MIN_LEVER_ARM_MM,
                                            PartAnnotation, PartFeature,
                                            auto_features, coded_feature_azimuths,
                                            feature_from_azimuth, feature_from_point,
                                            template_rim_centre)
from case_prep.pipeline.auto_flow import (ConfirmedSite, _BEST_FIT_CORR_DIST_MM,
                                          _cap_patch_roi, _crowns_frame,
                                          _fit_circle_xy, _posed_rim_centre,
                                          _refine_best_fit, _rim_agreement_mm,
                                          _ring_fixed_candidate, propose_sites,
                                          run_auto_case)
from case_prep.pipeline.final_product import (DEFAULT_GINGIVAL_OFFSET_MM,
                                              max_safe_gingival_offset)

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/real"
OUT = ROOT / "reports/live-demo"

def _discover_cases(data_root: Optional[Path] = None) -> Dict[str, dict]:
    """Doctor inputs LIVE in ``data/real/scans/<doctor>/`` — drop a folder with an STL in it
    and it appears in the demo. THAT IS THE WHOLE DISCOVERY RULE.

    NO INFERENCE (client directive 2026-07-25: "the lab chooses, the software never
    guesses"). Until today the implant MODEL was read out of the scan FOLDER NAME and the
    vendor CONSTRUCTION part was resolved by the name pattern
    ``library/construction/*/<model>-scanbody.stl`` — and a folder matching neither was
    SILENTLY DROPPED, so a real upload named ``patient-4471`` could never be opened. Both
    are gone: a case is discoverable from its scan alone.

    The name match survives ONLY as a non-binding default: ``suggested_model`` and
    ``suggested_construction`` (a construction-catalog ``path_id``) are hints the UI may
    preselect, and both may be None. The operator's explicit selection on the run request
    is what actually decides — see ``RunIn``. ``jaw`` is likewise a suggestion read off the
    scan's filename and overridable per run. An optional ``sites.json`` beside the scan
    supplies curated operator confirmations."""
    data = data_root or DATA
    caps_root = data / "library/caps"
    models = sorted((d.name for d in caps_root.iterdir() if d.is_dir()),
                    key=len, reverse=True) if caps_root.is_dir() else []
    cases: Dict[str, dict] = {}
    scans_root = data / "scans"
    if not scans_root.is_dir():
        return cases
    for folder in sorted(scans_root.iterdir()):
        if not folder.is_dir():
            continue
        stls = sorted(folder.glob("*.stl"))
        if not stls:
            continue  # nothing to load — the ONLY reason a folder is not a case
        # longest match wins (e.g. "neodent-gm" over "neodent"); None is fine
        model = next((m for m in models if m in folder.name), None)
        construction = (next(iter((data / "library/construction")
                                  .glob(f"*/{model}-scanbody.stl")), None)
                        if model else None)
        suggested_construction = (construction_catalog.path_id_of(data, construction)
                                  if construction is not None else None)
        scan = stls[0]
        jaw = "lower" if "lower" in scan.stem.lower() else "upper"
        sites_file = folder / "sites.json"
        suggested = (json.loads(sites_file.read_text())["suggested_sites"]
                     if sites_file.exists() else [])
        # the case id is the DOCTOR folder, not the model — several doctors can use the
        # same implant system (regression: model-keyed cases silently replaced each other)
        case_id = folder.name.replace("doctor-", "", 1) or folder.name
        cases[case_id] = {
            "id": case_id,
            "doctor": "Doctor " + " ".join(
                w.upper() if len(w) <= 2 else w.capitalize()
                for w in folder.name.replace("doctor-", "").replace("-", " ").split()),
            "jaw": jaw,
            "scan": scan,
            "data_root": data,
            # --- NON-BINDING DEFAULTS (never a gate; any of them may be None) ----------
            "suggested_model": model,
            "suggested_construction": suggested_construction,
            # in-process aliases kept for the preview endpoints' ``?model=`` fallback and
            # for reading pre-selection packages — a DEFAULT, never a selection
            "model": model,
            "vendor": (construction.parent.name if construction is not None else None),
            "caps": (caps_root / model) if model else None,
            "construction": construction,
            "suggested_sites": suggested,
        }
    return cases


CASES: Dict[str, dict] = _discover_cases()

app = FastAPI(title="ArTech case-prep live demo")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])

_cache: Dict[str, dict] = {}


MAX_MARKED_POINTS = 400  # matches the client's subsampling cap; enforced server-side too

# A gingival relief is a fraction of a millimetre; anything past this is a typo, not a
# clinical intent (the part would be eaten away). Bound, not a silent clamp.
_MAX_GINGIVAL_OFFSET_MM = 1.0


class SiteIn(BaseModel):
    tooth: int
    center: List[float]
    declared_variant: Optional[str] = None
    # RealGUIDE-style brush: the operator-painted cap patch (world coords); when present it
    # becomes the registration ROI directly — the strongest human-in-the-loop signal
    marked_points: Optional[List[List[float]]] = None
    # precise marks: cap centre + widest-rim point (world coords) — centre+radius from
    # the human, RealGUIDE registration-point style
    center_mark: Optional[List[float]] = None
    rim_mark: Optional[List[float]] = None
    # multi-point rim border (client spec 2026-07-14): several clicks around the cap's
    # visible border; the backend fits the rim circle through them
    rim_points: Optional[List[List[float]]] = None

    @field_validator("center_mark", "rim_mark")
    @classmethod
    def _mark_is_xyz(cls, v):
        if v is not None and len(v) != 3:
            raise ValueError("a mark must be an [x, y, z] triple")
        return v

    @field_validator("rim_points")
    @classmethod
    def _bounded_rim_points(cls, v):
        if v is None:
            return v
        if len(v) > 12:
            raise ValueError(f"rim_points is capped at 12 points, got {len(v)}")
        if any(len(p) != 3 for p in v):
            raise ValueError("rim_points must be [x, y, z] triples")
        return v

    @field_validator("marked_points")
    @classmethod
    def _bounded_patch(cls, v):
        if v is None:
            return v
        if len(v) > MAX_MARKED_POINTS:
            raise ValueError(f"marked_points is capped at {MAX_MARKED_POINTS} points, got {len(v)}")
        if any(len(p) != 3 for p in v):
            raise ValueError("marked_points must be [x, y, z] triples")
        return v


JAWS = ("upper", "lower")


class RunIn(BaseModel):
    """THE OPERATOR'S DECODING SELECTION (client directive 2026-07-25) plus the marked
    sites.

    ``model`` (the implant system), ``construction_path`` (a ``path_id`` from
    ``GET /api/constructions``) and the per-site ``declared_variant`` (the cap size) are
    the lab's choices, not the software's readings. ``model`` and ``construction_path``
    are REQUIRED by the run handler — omitted, the run refuses with a human message rather
    than falling back to the case's name-matched suggestion (that fallback is exactly the
    silent guess the directive removes; it survives only on the propose/preview paths).
    They are typed Optional here so the refusal is one clear 422 sentence about the
    DECODING SELECTION instead of pydantic's field-shaped complaint.

    ``jaw`` overrides the suggestion read off the scan filename."""

    sites: List[SiteIn]
    fresh: bool = False
    model: Optional[str] = None
    construction_path: Optional[str] = None
    jaw: Optional[str] = None
    # The tissue clearance the emitted construction part is relieved by; the client's
    # 0.20mm default lives in pipeline/final_product (one source of truth). It is an ASK,
    # not a guarantee: a pair that cannot take it is cut at its ceiling and the response's
    # ``gingival_relief`` block says so (GET /api/relief-limit answers it beforehand).
    gingival_offset_mm: float = DEFAULT_GINGIVAL_OFFSET_MM

    @field_validator("sites")
    @classmethod
    def _unique_teeth(cls, v):
        teeth = [s.tooth for s in v]
        dupes = sorted({t for t in teeth if teeth.count(t) > 1})
        if dupes:
            raise ValueError(f"duplicate tooth number(s) {dupes} — each site needs its own tooth")
        return v

    @field_validator("jaw")
    @classmethod
    def _known_jaw(cls, v):
        if v is not None and v not in JAWS:
            raise ValueError(f"jaw must be one of {', '.join(JAWS)}, got {v!r}")
        return v

    @field_validator("gingival_offset_mm")
    @classmethod
    def _sane_offset(cls, v):
        if not np.isfinite(v) or v < 0.0 or v > _MAX_GINGIVAL_OFFSET_MM:
            raise ValueError(f"gingival_offset_mm must be a clearance between 0 and "
                             f"{_MAX_GINGIVAL_OFFSET_MM}mm, got {v!r}")
        return float(v)


def _case(case_id: str) -> dict:
    if case_id not in CASES:
        raise HTTPException(404, f"unknown case {case_id!r}")
    return CASES[case_id]


def _data_root(cfg: dict) -> Path:
    """The data root this case was discovered under (tests monkeypatch DATA per-tree)."""
    return cfg.get("data_root") or DATA


def _scan_mesh(cfg: dict) -> trimesh.Trimesh:
    """The multi-MB scan, parsed once per process (plus its cached vertex normals)."""
    if "scan_mesh" not in cfg:
        cfg["scan_mesh"] = trimesh.load(cfg["scan"], force="mesh")
    return cfg["scan_mesh"]


def _library_for(cfg: dict, model: str,
                 variants: Optional[List[str]] = None) -> CapLibrary:
    """The chosen implant system's cap library, cached per (model, extra parts).

    ``variants`` are the variant ids the operator actually picked. Any of them that the
    top-level catalog does not carry is looked up in the FULL catalog
    (adapters/library_catalog — which lists the ``superseded-*`` archives) and handed to
    ``CapLibrary.load`` as an EXPLICIT extra part. CapLibrary's own glob stays top-level,
    so an archived part enters a run only because a human named it (client directive
    2026-07-25) — never because a glob widened."""
    data = _data_root(cfg)
    caps_root = data / "library/caps"
    # MEMBERSHIP, never a path join on caller input — the same rule the construction
    # catalog follows (adapters/construction_catalog.resolve_construction). Joining the
    # operator's ``model`` straight onto the caps root let a traversal escape it: measured
    # 2026-07-25, ``model="zimmer-4.5/superseded-2026-07-13"`` loaded the WHOLE archive as
    # a current system (defeating CapLibrary.load's top-level-only glob, which exists so an
    # archived part enters a run one explicitly-named part at a time) and
    # ``model="../caps/neodent-gm"`` shipped a package whose ``implant_model`` — the paid
    # record's audit key — was that traversal string. A directory NAME carries no separator,
    # so membership refuses both. Cheap directory scan, deliberately uncached: a system
    # dropped in while the server runs must appear.
    known = ({d.name for d in caps_root.iterdir() if d.is_dir()}
             if caps_root.is_dir() else set())
    if model not in known:
        raise HTTPException(422, f"unknown implant system {model!r} — pick one of the "
                                 f"systems listed by GET /api/library")
    caps_dir = caps_root / model
    top_level = {sp.variant for sp in
                 (parse_spec_filename(p.name) for p in caps_dir.glob("*.stl"))
                 if sp is not None}
    extra: Dict[str, Path] = {}
    for variant in sorted(set(variants or ())):
        if variant in top_level:
            continue
        path = library_catalog.catalog_mesh_path(data, model, variant)
        if path is None:
            raise HTTPException(422, f"{variant!r} is not a part of the {model!r} library "
                                     f"— pick a variant listed by GET /api/library")
        extra[variant] = path
    key = ("library", model) + tuple(sorted(extra))
    cache = cfg.setdefault("_libraries", {})
    if key not in cache:
        try:
            cache[key] = CapLibrary.load(caps_dir, extra=extra or None)
        except ValueError as exc:
            raise HTTPException(422, f"the {model!r} cap library could not be loaded: {exc}")
    return cache[key]


def _construction_for(cfg: dict, path_id: str) -> trimesh.Trimesh:
    """The chosen vendor construction part, cached per path_id. Resolution is a catalog
    MEMBERSHIP lookup (adapters/construction_catalog) — no name matching, no path join on
    caller input."""
    path = construction_catalog.resolve_construction(_data_root(cfg), path_id)
    if path is None:
        raise HTTPException(422, f"unknown construction part {path_id!r} — pick one of "
                                 f"the parts listed by GET /api/constructions")
    cache = cfg.setdefault("_constructions", {})
    if path_id not in cache:
        cache[path_id] = trimesh.load(path, force="mesh")
    return cache[path_id]


def _shipped_model(cfg: dict, rec: dict) -> str:
    """The implant system a SHIPPED record was produced under. The run recorded the
    operator's explicit choice in ``implant.json``; the case's name-matched suggestion is
    only the last-ditch reading for packages emitted before selection existed."""
    model = rec.get("implant_model") or cfg.get("suggested_model")
    if model is None:
        raise HTTPException(409, f"the shipped record for case {cfg['id']!r} names no "
                                 f"implant model — cannot re-pose")
    return model


@app.get("/")
def root():
    """A bare visit to the API port gets pointed at the demo, not a 404."""
    return {
        "service": "ArTech case-prep live demo API",
        "demo_ui": "http://localhost:5173",
        "cases": "/api/cases",
        "api_docs": "/docs",
        "how_to_run": "docs/RUN-DEMO.md",
    }


@app.get("/api/cases")
def list_cases():
    """Every scan folder that holds an STL — no case is withheld for lacking a name match.
    ``suggested_model`` / ``suggested_construction`` / ``jaw`` are DEFAULTS the UI may
    preselect; the run takes the operator's explicit selection (client directive
    2026-07-25)."""
    return [{"id": c["id"], "doctor": c["doctor"], "jaw": c["jaw"],
             "vendor": c["vendor"],
             "suggested_model": c["suggested_model"],
             "suggested_construction": c["suggested_construction"],
             "scan_filename": Path(c["scan"]).name,
             "scan_url": f"/api/cases/{c['id']}/scan",
             "suggested_sites": c["suggested_sites"]} for c in CASES.values()]


@app.get("/api/constructions")
def list_constructions():
    """Every vendor CONSTRUCTION part on disk — the operator picks one by ``path_id`` and
    the run uses exactly that file. Replaces the old ``*/<model>-scanbody.stl`` name match,
    which silently dropped any case whose model did not spell a filename."""
    return construction_catalog.construction_entries(DATA)


# --- THE RELIEF CEILING, BEFORE THE OPERATOR COMMITS ----------------------------------
# Client escalation 2026-07-25: "end-to-end automation must complete". The thin-wall export
# gate is right to refuse a part whose channel wall collapsed, but it answers AFTER the
# whole pipeline has run. This endpoint moves the answer to SELECTION time: pick a
# construction part and a cap variant, and the UI can show the maximum relief that pair can
# take before Process is ever pressed.
#
# It is a pure measurement — nothing is emitted, nothing is cached to disk, the run is not
# touched. Cost: 0.5-1.2s cold on the real vendor parts (measured across all 24 catalog
# pairs), a dict lookup warm; the pipeline's own bench cache is shared, so a query here also
# warms the run that follows.

# a selection-time query is case-independent — it needs the catalog, not a scan. This
# stand-in cfg gives it the same cached library/construction loaders the run path uses.
_RELIEF_CFG: Dict[str, object] = {"id": "relief-limit", "data_root": DATA}


@app.get("/api/relief-limit")
def relief_limit(construction_path: str, model: str, variant: str):
    """The maximum gingival relief a (construction part x cap variant) pair can be cut
    with and still pass the export gate — asked BEFORE processing.

    ``max_safe_mm`` is a 0.01mm-grid value, always rounded DOWN. ``limited_by`` names the
    condition that closes the ceiling: ``wall`` (the relief would thin a channel wall that
    is already under the 0.50mm rule), ``channel`` (the as-built screw channel becomes
    unmeasurable), ``seal`` (the part is left fragmented/unsealed), or ``none`` (nothing
    broke up to ``searched_to_mm`` — the search stops there and does not extrapolate).

    ``shippable_at_zero: false`` is the one case a ceiling cannot rescue: the part is not
    manufacturable even with no relief at all, and the export gate HARD BLOCKS it. Every
    other pair completes — at ``max_safe_mm`` when the request exceeds it, with the clamp
    reported on the run response, every site row and the package audit.

    MEASURED, the whole catalog at the client's 0.20mm default: 15 of 24 pairs cannot take
    it. Every atlantis/zimmer-4.5-scanbody pair ceilings at 0.06-0.15mm; on
    dess/neodent-gm-scanbody the CAP decides (5020 -> 0.05, 5030 -> 0.09, 6030 -> 0.47).
    That is the number this endpoint exists to put in front of the operator."""
    t0 = time.time()
    if construction_catalog.resolve_construction(DATA, construction_path) is None:
        raise HTTPException(422, f"unknown construction part {construction_path!r} — pick "
                                 f"one of the parts listed by GET /api/constructions")
    library = _library_for(_RELIEF_CFG, model, [variant])
    spec = next((s for s in library.specs if s.variant == variant), None)
    if spec is None:
        raise HTTPException(422, f"{variant!r} is not a part of the {model!r} library — "
                                 f"pick a variant listed by GET /api/library")
    construction_mesh = _construction_for(_RELIEF_CFG, construction_path)
    channel = channel_from_boundary_loops(library.template(spec))
    limit = max_safe_gingival_offset(construction_mesh, library_channel=channel,
                                     report_at_mm=DEFAULT_GINGIVAL_OFFSET_MM)
    at_default = limit.reading_at(DEFAULT_GINGIVAL_OFFSET_MM)
    return {
        "construction_path": construction_path,
        "vendor": construction_catalog.vendor_of(construction_path),
        "model": model,
        "variant": variant,
        "max_safe_mm": limit.max_safe_mm,
        "requested_default_mm": DEFAULT_GINGIVAL_OFFSET_MM,
        "default_is_safe": limit.max_safe_mm >= DEFAULT_GINGIVAL_OFFSET_MM,
        "limited_by": limit.limited_by,
        "wall_mm_at_zero": limit.wall_mm_at_zero,
        "wall_mm_at_default": (at_default or {}).get("min_wall_mm"),
        "channel_measurable_at_zero": limit.channel_measurable_at_zero,
        "channel_measurable_at_default": bool((at_default or {}).get("measurable")),
        "shippable_at_zero": limit.shippable_at_zero,
        "min_wall_rule_mm": design_rules.MIN_WALL_MM,
        "searched_to_mm": limit.searched_to_mm,
        "resolution_mm": limit.resolution_mm,
        # honest cache receipt: 0 new probes means every reading came from a warm bench
        "probes": limit.probes,
        "cached": limit.probes == 0,
        "duration_s": round(time.time() - t0, 2),
        "note": limit.note,
    }


@app.get("/api/cases/{case_id}/library")
def library_variants(case_id: str, model: Optional[str] = None):
    """The RealGUIDE-parity picker: the doctor chooses from a model's size variants
    (always the full top-level catalog — 6 per model today) BEFORE alignment; dims let the
    UI show diameter x height like RealGUIDE's Information panel. ``?model=`` names the
    implant system explicitly; omitted, the case's non-binding suggestion fills in (and a
    case with no suggestion says so instead of guessing)."""
    cfg = _case(case_id)
    model = model or cfg.get("suggested_model")
    if model is None:
        raise HTTPException(409, f"case {case_id!r} has no suggested implant system — "
                                 f"name one with ?model= (see GET /api/library)")
    lib = _library_for(cfg, model)
    dims = lib.variant_dimensions()
    return [{"model": model,
             "variant": sp.variant,
             "rim_diameter_mm": (round(dims[sp.variant][0], 2) if sp.variant in dims else None),
             "height_mm": (round(dims[sp.variant][1], 2) if sp.variant in dims else None),
             "mesh_url": f"/api/cases/{case_id}/library/{sp.variant}/mesh?model={model}"}
            for sp in sorted(lib.specs, key=lambda x: x.variant)]


@app.get("/api/cases/{case_id}/library/{variant}/mesh")
def library_mesh(case_id: str, variant: str, model: Optional[str] = None):
    """The library part itself, for the side-by-side preview next to the scanned cap."""
    cfg = _case(case_id)
    model = model or cfg.get("suggested_model")
    if model is None:
        raise HTTPException(409, f"case {case_id!r} has no suggested implant system — "
                                 f"name one with ?model=")
    caps_dir = _data_root(cfg) / "library/caps" / model
    path = next(iter(pathlib_glob(caps_dir, variant)), None)
    if path is None:
        # the archived parts live one directory down; the catalog knows their ids
        path = library_catalog.catalog_mesh_path(_data_root(cfg), model, variant)
    if path is None:
        raise HTTPException(404, f"no {variant!r} in the {model} library")
    return FileResponse(path, media_type="model/stl", filename=path.name)


def pathlib_glob(caps_dir, variant):
    # the catalog convention: <model>-<variant>.stl (data/real/README.md)
    return sorted(Path(caps_dir).glob(f"*-{variant}.stl"))


@app.get("/api/library")
def full_library():
    """The FULL cross-model part catalog, case-independent (client ask 2026-07-23: "show me
    ALL of these caps, classified — even the superseded ones — and let me choose neodent-gm
    or zimmer-4.5"). Groups = model dirs under library/caps plus any legacy ``*-library``
    dir near it; per-entry flags (superseded / legacy / unloadable / duplicate-with-named-
    counterpart) are computed honestly from the bytes on disk — see adapters/library_catalog."""
    return library_catalog.catalog_groups(DATA)


@app.get("/api/library/{model}/{entry_id}/mesh")
def full_library_mesh(model: str, entry_id: str):
    """One catalog entry's STL, case-independently — same serving contract as the per-case
    part-mesh endpoint above (model/stl FileResponse) so the viewer treats them identically."""
    path = library_catalog.catalog_mesh_path(DATA, model, entry_id)
    if path is None:
        raise HTTPException(404, f"no {entry_id!r} in the {model!r} library catalog")
    return FileResponse(path, media_type="model/stl", filename=path.name)


# --- MARKED FEATURES ON THE LIBRARY PART ----------------------------------------------
# The client's 2026-07-24 ask, half one: "mark the holes/trenches in the LIBRARY part".
# A part is marked ONCE per variant and the annotation is reused by every case that ships
# it — that is the productization point (mark the catalog, not each scan). The annotation
# is SEEDED from the machine's own reading (domain/part_features.auto_features), so the
# operator confirms or corrects a reading rather than starting from a blank part; DELETE
# reverts to that seed. Nothing here poses anything — these endpoints only describe the
# part. The rotation they enable is judged by the same gates as every other operator
# proposal (align-to-correspondence, below).

MAX_PART_FEATURES = 12  # a catalog cap reads 1-3 coded trenches + the channel


def _annotation_path(model: str, variant: str) -> Path:
    """``data/real/library/annotations/<model>/<variant>.json``. Both segments are
    catalog-validated by the caller before they reach here (the id came out of the
    catalog scan, so it can carry no separator and no traversal)."""
    return DATA / "library/annotations" / model / f"{variant}.json"


@lru_cache(maxsize=None)
def _canonical_template(path_str: str) -> trimesh.Trimesh:
    """One catalog STL in the canonical frame — the SAME construction CapLibrary.load
    applies, so a feature azimuth read here is the azimuth a seated site's template
    carries. Cached unbounded (the catalog is finite and immutable): an EVICTED template
    could be collected and its id reused, and clock_signature's signature cache is keyed
    by ``id(template)`` — a bounded cache would eventually hand out a stale signature."""
    local, _ = canonicalize_revolute(trimesh.load(path_str, force="mesh"))
    return local


def _catalog_template(model: str, variant: str) -> trimesh.Trimesh:
    path = library_catalog.catalog_mesh_path(DATA, model, variant)
    if path is None:
        raise HTTPException(404, f"no {variant!r} in the {model!r} library catalog")
    return _canonical_template(str(path))


def _load_annotation(model: str, variant: str) -> Optional[PartAnnotation]:
    """The persisted operator annotation, or None when the part has never been marked.
    A corrupt file is a 500, never a silent fall-back to the auto seed — the operator's
    marks are a clinical input and their disappearance must be loud."""
    path = _annotation_path(model, variant)
    if not path.exists():
        return None
    try:
        return PartAnnotation.from_dict(json.loads(path.read_text()))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(500, f"the stored annotation for {model}/{variant} is "
                                 f"unreadable ({exc}) — delete it to revert to auto")


def _seeded_annotation(model: str, variant: str,
                       template: trimesh.Trimesh) -> "tuple":
    """(annotation, auto_seeded) — the persisted marks when they exist, otherwise the
    machine's own reading of the part."""
    stored = _load_annotation(model, variant)
    if stored is not None:
        return stored, False
    return PartAnnotation(model=model, variant=variant,
                          features=auto_features(template)), True


def _features_payload(ann: PartAnnotation, auto_seeded: bool) -> dict:
    return {"model": ann.model, "variant": ann.variant, "auto_seeded": auto_seeded,
            "revised_at": ann.revised_at,
            "features": [f.to_dict() for f in ann.features]}


class PartFeatureIn(BaseModel):
    """One operator mark on the library part: EITHER a 3D ``point`` clicked on the part
    (canonical frame — the frame the part-preview serves its mesh in), which snaps to the
    machine's own feature when it lands close enough, OR a bare ``azimuth_deg`` typed in.
    An azimuth-only mark is placed on the coded band's mid-radius (the radius the codes
    actually occupy) since a correspondence needs a lever arm."""
    kind: str = "trench"
    azimuth_deg: Optional[float] = None
    point: Optional[List[float]] = None

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, v):
        if v not in FEATURE_KINDS:
            raise ValueError(f"unknown feature kind {v!r} "
                             f"(known: {', '.join(FEATURE_KINDS)})")
        return v

    @field_validator("azimuth_deg")
    @classmethod
    def _finite_azimuth(cls, v):
        if v is not None and not np.isfinite(v):
            raise ValueError("azimuth_deg must be a finite number")
        return v

    @field_validator("point")
    @classmethod
    def _finite_xyz(cls, v):
        if v is None:
            return v
        if len(v) != 3:
            raise ValueError("point must be an [x, y, z] triple")
        if not all(np.isfinite(c) for c in v):
            raise ValueError("point coordinates must be finite numbers")
        return [float(c) for c in v]


class PartFeaturesIn(BaseModel):
    features: List[PartFeatureIn]

    @field_validator("features")
    @classmethod
    def _one_placement_each(cls, v):
        if not v:
            raise ValueError("a part annotation needs at least one feature — DELETE the "
                             "annotation to revert to the automatic reading")
        if len(v) > MAX_PART_FEATURES:
            raise ValueError(f"a part annotation is capped at {MAX_PART_FEATURES} "
                             f"features, got {len(v)}")
        for f in v:
            if (f.point is None) == (f.azimuth_deg is None):
                raise ValueError("each feature needs exactly one of point or azimuth_deg")
        return v


@app.get("/api/library/{model}/{variant}/features")
def library_features(model: str, variant: str):
    """The part's marked features — the persisted operator annotation, or the machine's
    own auto-seed when the part has never been marked (``auto_seeded`` says which)."""
    template = _catalog_template(model, variant)
    ann, auto_seeded = _seeded_annotation(model, variant, template)
    return _features_payload(ann, auto_seeded)


@app.put("/api/library/{model}/{variant}/features")
def put_library_features(model: str, variant: str, body: PartFeaturesIn):
    """Persist the operator's annotation for this part. Marks reconcile with the
    machine's own reading when they land inside the snap windows (same id, same
    geometry) — that is what keeps a human mark and the clock instrument talking about
    the same cutout, whether the mark arrived as a CLICK or as an AZIMUTH (the UI re-sends
    every untouched mark by azimuth on save, so an unreconciled azimuth would re-place the
    part's own features on the coded band's mid-radius — a fabricated lever arm that hands
    the CONCENTRIC screw bore a rotation anchor and renames every stable id)."""
    template = _catalog_template(model, variant)
    features: List[PartFeature] = []
    for raw in body.features:
        if raw.point is not None:
            try:
                feature = feature_from_point(template, raw.point, kind=raw.kind)
            except ValueError as exc:
                raise HTTPException(422, str(exc))
        else:
            feature = feature_from_azimuth(template, float(raw.azimuth_deg),
                                           kind=raw.kind)
        features.append(feature)
    try:
        ann = PartAnnotation(model=model, variant=variant, features=features,
                             revised_at=time.strftime("%Y-%m-%dT%H:%M:%S"))
    except ValueError as exc:
        # two marks landing on the same feature/azimuth is a contradiction, not a set
        raise HTTPException(422, str(exc))
    path = _annotation_path(model, variant)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(ann.to_dict(), indent=2))
    except OSError:
        raise HTTPException(500, f"could not persist the annotation for "
                                 f"{model}/{variant}")
    return _features_payload(ann, auto_seeded=False)


@app.delete("/api/library/{model}/{variant}/features")
def delete_library_features(model: str, variant: str):
    """Revert the part to the machine's own reading; ``reverted`` says whether an
    operator annotation was actually there to drop."""
    template = _catalog_template(model, variant)
    path = _annotation_path(model, variant)
    reverted = path.exists()
    if reverted:
        try:
            path.unlink()
        except OSError:
            raise HTTPException(500, f"could not drop the annotation for "
                                     f"{model}/{variant}")
    ann, auto_seeded = _seeded_annotation(model, variant, template)
    return {**_features_payload(ann, auto_seeded), "reverted": reverted}


@app.get("/api/cases/{case_id}/scan")
def get_scan(case_id: str):
    return FileResponse(_case(case_id)["scan"], media_type="model/stl",
                        filename=f"{case_id}-upper.stl")


# --- CAPTURE GATE (master plan §1 SCAN row / §8 item 11) ------------------------------
# INTAKE ADVISORY in the demo: cases arrive as folders (no upload flow yet), so the
# gate runs per case+site server-side and surfaces in the propose/run payloads for the
# UI to show BEFORE the operator invests marks. The master plan's fail-closed upload
# gate arrives with a real upload flow and will call assess_capture verbatim — nothing
# here changes pipeline behavior. Blocks are derived + cached with the case (memory +
# capture.json on disk), never folded into proposals.json/run.json (same serve-time
# layering as _with_verification).


def _capture_context(cfg: dict):
    """Per-case crowns-up local frame + xy tree for capture assessment, computed once
    per process (the same _crowns_frame the pipeline itself seats in)."""
    if "capture_ctx" not in cfg:
        scan = _scan_mesh(cfg)
        pts = np.asarray(scan.vertices, float)
        frame, origin, _ = _crowns_frame(pts, np.asarray(scan.vertex_normals, float))
        L = (pts - origin) @ frame
        cfg["capture_ctx"] = (frame, origin, L, cKDTree(L[:, :2]))
    return cfg["capture_ctx"]


def _capture_block(cfg: dict, case_id: str, centre_xy_local, rim_r_hint: float) -> dict:
    """One site's capture assessment, cached by (case, centre, hint)."""
    key = f"{centre_xy_local[0]:.2f},{centre_xy_local[1]:.2f}:{rim_r_hint:.2f}"
    cache_key = f"capture:{case_id}"
    store = _cache.get(cache_key)
    if store is None:
        disk = OUT / case_id / "capture.json"
        try:
            store = json.loads(disk.read_text()) if disk.exists() else {}
        except (OSError, json.JSONDecodeError):
            store = {}
        _cache[cache_key] = store
    if key not in store:
        _, _, L, _ = _capture_context(cfg)
        store[key] = assess_capture(L, centre_xy_local, rim_r_hint).to_dict()
        disk = OUT / case_id / "capture.json"
        try:
            disk.parent.mkdir(parents=True, exist_ok=True)
            disk.write_text(json.dumps(store))
        except OSError:
            pass  # the capture cache must never take down a request
    return store[key]


def _site_capture_inputs(cfg: dict, center, center_mark=None, rim_mark=None,
                         rim_points=None):
    """(centre_xy_local, rim_r_hint) for a confirmed/suggested site — the same
    centre+radius precedence run_auto_case applies (border-circle fit > centre+rim
    marks > measured rim > the 2.6mm crop fallback). The pair is passed to the gate
    AS GIVEN — capture assessment never re-centres a human mark."""
    frame, origin, L, xy_tree = _capture_context(cfg)
    if rim_points and len(rim_points) >= 3:
        P = (np.asarray(rim_points, float) - origin) @ frame
        fit = _fit_circle_xy(P[:, :2])
        if fit is not None:
            centre_xy, rim_r = fit
            return np.asarray(centre_xy, float), float(rim_r)
    world = np.asarray(center_mark if center_mark is not None else center, float)
    seed = frame.T @ (world - origin)
    if rim_mark is not None:
        rim_local = frame.T @ (np.asarray(rim_mark, float) - origin)
        return seed[:2], float(np.linalg.norm((rim_local - seed)[:2]))
    if rim_points:  # 1-2 border points: average radius about the centre
        P = (np.asarray(rim_points, float) - origin) @ frame
        return seed[:2], float(np.mean(np.linalg.norm(P[:, :2] - seed[:2], axis=1)))
    dia = measure_rim_diameter(L, xy_tree, seed)
    return seed[:2], (dia / 2.0 if dia else 2.6)


def _with_capture(cfg: dict, case_id: str, result: dict) -> dict:
    """Serve-time capture layer on a propose result: every proposal gains a
    ``capture`` block, and the case's curated suggested sites ride along as
    ``suggested_capture`` (the step-2/3 chips need them before any run)."""
    frame, origin, L, xy_tree = _capture_context(cfg)
    proposals = []
    for p in result.get("proposals") or []:
        seed = frame.T @ (np.asarray(p["center"], float) - origin)
        dia = measure_rim_diameter(L, xy_tree, seed)
        hint = dia / 2.0 if dia else 2.6
        proposals.append({**p, "capture": _capture_block(cfg, case_id, seed[:2], hint)})
    suggested = []
    for s in cfg.get("suggested_sites") or []:
        centre_xy, hint = _site_capture_inputs(
            cfg, s.get("center"), s.get("center_mark"), s.get("rim_mark"))
        suggested.append({"tooth": s.get("tooth"), "center": s.get("center"),
                          "capture": _capture_block(cfg, case_id, centre_xy, hint)})
    return {**result, "proposals": proposals, "suggested_capture": suggested}


def _run_sites_capture(cfg: dict, case_id: str, sites: List["SiteIn"]) -> dict:
    """tooth -> capture block for the sites a run was asked to align."""
    blocks = {}
    for s in sites:
        centre_xy, hint = _site_capture_inputs(cfg, s.center, s.center_mark,
                                               s.rim_mark, s.rim_points)
        blocks[str(s.tooth)] = _capture_block(cfg, case_id, centre_xy, hint)
    return blocks


@app.post("/api/cases/{case_id}/propose")
def propose(case_id: str, fresh: bool = False):
    cfg = _case(case_id)
    key = f"propose:{case_id}"
    disk = OUT / case_id / "proposals.json"
    if not fresh:
        if key in _cache:
            return {**_with_capture(cfg, case_id, _cache[key]), "cached": True}
        if disk.exists():
            _cache[key] = json.loads(disk.read_text())
            return {**_with_capture(cfg, case_id, _cache[key]), "cached": True}
    t0 = time.time()
    scan = _scan_mesh(cfg)
    props = propose_sites(np.asarray(scan.vertices, float),
                          normals=np.asarray(scan.vertex_normals, float))
    result = {"proposals": [{"center": list(p.center), "void_ratio": p.void_ratio,
                             "rim_below_cusps_mm": p.rim_below_cusps_mm} for p in props],
              "duration_s": round(time.time() - t0, 1)}
    _cache[key] = result
    disk.parent.mkdir(parents=True, exist_ok=True)
    disk.write_text(json.dumps(result))
    return {**_with_capture(cfg, case_id, result), "cached": False}


def _append_run_history(case_id: str, body: RunIn, result: dict, cached: bool) -> None:
    """EVERY alignment attempt is kept for post-hoc analysis (client ask 2026-07-14:
    'keep the attempts so we can analyse what went wrong'): the exact inputs as sent
    (marks, brush, declared variant), the per-site outcome rows (seat method, metrics,
    identified variant, gate), and whether the result came from cache. One JSON line
    per attempt in reports/live-demo/run-history.jsonl."""
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "case_id": case_id,
           "cached": cached, "fresh": body.fresh,
           # the operator's DECODING SELECTION as sent (2026-07-25) — a shipped part must
           # always be traceable to the library/construction/relief a human chose
           "selection": {"model": body.model,
                         "construction_path": body.construction_path,
                         "jaw": body.jaw,
                         "gingival_offset_mm": body.gingival_offset_mm},
           "sites_in": [s.model_dump() for s in body.sites],
           "sites_out": (result.get("summary") or {}).get("sites"),
           "duration_s": result.get("duration_s")}
    try:
        OUT.mkdir(parents=True, exist_ok=True)
        with (OUT / "run-history.jsonl").open("a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
    except OSError:
        pass  # history must never take down a run


def _with_verification(result: dict) -> dict:
    """Serve-time doctor-verification layer on a run result: every site row gains its
    ``acceptance`` evaluation (the acceptance-numbers catalog judged against the row —
    derived, so it is recomputed per response and never persisted into run.json or the
    history stream). ``doctor_confirmation`` rides along untouched where the confirm
    endpoint persisted it. Pure shallow rebuild — the cached dict is never mutated."""
    summary = result.get("summary") or {}
    sites = [{**row, "acceptance": evaluate_acceptance(row)}
             for row in (summary.get("sites") or [])]
    return {**result, "summary": {**summary, "sites": sites}}


def _required_selection(case_id: str, body: RunIn) -> "tuple":
    """THE DECODING SELECTION GATE (client directive 2026-07-25: "the lab chooses, the
    software never guesses"). The run refuses — one 422, in words an operator can act on —
    unless the implant system AND the construction part were explicitly named. The case's
    name-matched suggestion is deliberately NOT used as a fallback here: that fallback is
    the guess being removed. Returns (model, construction_path_id, jaw)."""
    missing = []
    if not body.model:
        missing.append("the implant system (\"model\", e.g. from GET /api/library)")
    if not body.construction_path:
        missing.append("the construction part (\"construction_path\", a path_id from "
                       "GET /api/constructions)")
    if missing:
        cfg = CASES.get(case_id) or {}
        hint = ""
        if cfg.get("suggested_model") or cfg.get("suggested_construction"):
            hint = (f" (this case suggests model="
                    f"{cfg.get('suggested_model')!r}, construction_path="
                    f"{cfg.get('suggested_construction')!r} — a suggestion only; send it "
                    f"back explicitly to use it)")
        raise HTTPException(422, "the library selection is incomplete: choose "
                                 + " and ".join(missing)
                                 + ". The software will not pick one for you." + hint)
    return body.model, body.construction_path, body.jaw


def _run_cache_key(case_id: str, body: RunIn, model: str, construction_path: str,
                   jaw: str) -> str:
    """The run cache key. Hashed — a painted patch would otherwise embed thousands of
    floats in an in-memory dict key that lives for the process lifetime. The SELECTION is
    part of it: the same marks against a different cap library, construction part, jaw or
    relief are a DIFFERENT run and must never be served from another selection's cache."""
    payload = json.dumps({"sites": [s.model_dump() for s in body.sites],
                          "model": model, "construction_path": construction_path,
                          "jaw": jaw,
                          "gingival_offset_mm": body.gingival_offset_mm},
                         sort_keys=True)
    return f"run:{case_id}:{hashlib.sha256(payload.encode()).hexdigest()}"


@app.post("/api/cases/{case_id}/run")
def run(case_id: str, body: RunIn):
    cfg = _case(case_id)
    model, construction_path, jaw_in = _required_selection(case_id, body)
    jaw = jaw_in or cfg["jaw"]
    key = _run_cache_key(case_id, body, model, construction_path, jaw)
    disk = OUT / case_id / "run.json"
    # per-site capture-gate blocks (intake ADVISORY — see the capture section above):
    # derived at serve time on every response, cached with the case, never persisted
    # into run.json
    capture = _run_sites_capture(cfg, case_id, body.sites)
    if not body.fresh:
        if key in _cache:
            _append_run_history(case_id, body, _cache[key], cached=True)
            return {**_with_verification(_cache[key]), "capture": capture,
                    "cached": True}
        if disk.exists():
            saved = json.loads(disk.read_text())
            if saved.get("_key") == key:
                _cache[key] = saved
                _append_run_history(case_id, body, saved, cached=True)
                return {**_with_verification(saved), "capture": capture,
                        "cached": True}
    t0 = time.time()
    scan = _scan_mesh(cfg)
    # THE OPERATOR'S PICKS, resolved as given: the chosen system's library (carrying any
    # archived variant they explicitly named) and the chosen construction file
    library = _library_for(cfg, model,
                           [s.declared_variant for s in body.sites if s.declared_variant])
    construction_mesh = _construction_for(cfg, construction_path)
    # the automation's own proposals (cached) ride along for the human-vs-machine comparison
    prop_disk = OUT / case_id / "proposals.json"
    props = ([p["center"] for p in json.loads(prop_disk.read_text())["proposals"]]
             if prop_disk.exists() else None)
    try:
        summary = run_auto_case(
            case_id=case_id, scan=scan, library=library,
            construction_mesh=construction_mesh,
            vendor=construction_catalog.vendor_of(construction_path),
            confirmed=[ConfirmedSite(s.tooth, tuple(s.center), s.declared_variant,
                                     s.marked_points, s.center_mark, s.rim_mark,
                                     rim_points=s.rim_points)
                       for s in body.sites],
            jaw_label=jaw, out_dir=OUT / case_id / "package", proposals=props,
            gingival_offset_mm=body.gingival_offset_mm,
            # the interactive server surfaces the per-site pose-stability confidence (the
            # battery leaves it off for speed); results are cached by payload hash so the
            # K-re-seat bootstrap runs once per unique run
            compute_confidence=True)
    except ValueError as exc:
        # The pipeline's REFUSALS travel as ValueError with a human message — the export
        # gates ("package NOT emitted": a catastrophic design-rule violation, or a
        # gingival relief that ate the screw channel) and "no confirmed site could be
        # aligned". They are answers to the operator, not server faults, so they reach
        # the UI as a 409 with the words the gate wrote (2026-07-25: the relief gate's
        # "re-run with a smaller gingival offset" is only actionable if it is READ).
        raise HTTPException(409, str(exc))
    result = {"_key": key, "summary": summary,
              # the selection this result was produced under, echoed back verbatim so the
              # UI's acknowledgment panel shows what the operator actually authorized.
              # ``gingival_offset_mm`` here stays the ASK — this block is the authorization
              # record, not the outcome; what was actually cut is ``gingival_relief``.
              "selection": {"model": model, "construction_path": construction_path,
                            "vendor": construction_catalog.vendor_of(construction_path),
                            "jaw": jaw,
                            "gingival_offset_mm": body.gingival_offset_mm,
                            "variants": {str(s.tooth): s.declared_variant
                                         for s in body.sites}},
              # THE RELIEF OUTCOME, at the TOP of the response (2026-07-25). Mirrors
              # ``summary.gingival_relief`` deliberately: the run now completes at the safe
              # ceiling when the ask is unsafe, and a UI must not have to dig into the
              # per-site rows to discover it got a different number than it asked for.
              "gingival_relief": summary.get("gingival_relief"),
              "files_base": f"/api/cases/{case_id}/files/",
              "duration_s": round(time.time() - t0, 1)}
    _cache[key] = result
    disk.write_text(json.dumps(result, default=str))
    _append_run_history(case_id, body, result, cached=False)
    return {**_with_verification(result), "capture": capture, "cached": False}


@app.get("/api/cases/{case_id}/files/{name}")
def get_file(case_id: str, name: str):
    _case(case_id)
    path = (OUT / case_id / "package" / name).resolve()
    if not str(path).startswith(str((OUT / case_id / "package").resolve())) or not path.exists():
        raise HTTPException(404, name)
    media = "model/stl" if name.endswith(".stl") else "application/json"
    # no-store (client fix 2026-07-14): package files are OVERWRITTEN on every run at
    # the SAME URL — a browser-cached STL from an earlier run showed a stale sideways
    # seat while the results table displayed fresh metrics
    return FileResponse(path, media_type=media, filename=name,
                        headers={"Cache-Control": "no-store"})


# --- THREE-PANEL VERIFY: the union view's deviation colouring -------------------------
# The client's library-selection dialog (2026-07-25) puts three panels in front of the
# operator before Process is allowed: the LIBRARY part, the SCANNED cap, and the UNION
# overlay COLOURED BY DEVIATION. The first two are meshes the web already fetches
# (/api/cases/{id}/library/{variant}/mesh and the package's aligned-cap STL). This is the
# third: the posed library cap's per-vertex signed deviation against the scan, in the jaw
# world frame, plus the scale bounds so the UI's colorbar reads the same millimetres the
# acceptance PNG prints. REPORTING ONLY — it is the same instrument
# (adapters/qc_render.deviation_at_points) the difference map uses, never a second opinion.

_DEVIATION_ROUND = 4  # mm/coordinate precision on the wire; the read itself is unrounded


@app.get("/api/cases/{case_id}/sites/{tooth}/deviation")
def site_deviation(case_id: str, tooth: int):
    """Per-vertex signed deviation of the seated cap against the scan (jaw world frame).

    Returns the posed cap as a renderable mesh (``points`` + ``faces``) with one signed
    millimetre per point, the display ``scale`` (the acceptance PNG's own clamp/colormap),
    and the site's published footprint ``stats`` — the SAME RMS/p90 the difference map
    prints and the run row carries, never a vertex-weighted re-derivation of them. Cached
    per (case, tooth, pose) — an operator rotation changes the pose and therefore the key,
    so a nudged site re-reads rather than serving the pre-nudge colouring."""
    cfg = _case(case_id)
    _pkg, _implant_path, rec, template, _frame, _origin, _L, _t_now = \
        _load_rotation_site(case_id, tooth)
    pose = np.asarray(rec["pose_matrix"], float)
    key = ("deviation", case_id, tooth,
           hashlib.sha256(pose.tobytes()).hexdigest()[:16])
    if key in _cache:
        return _cache[key]

    scan = _scan_mesh(cfg)
    payload = _deviation_payload(case_id, tooth, np.asarray(scan.vertices, float),
                                 pose, template,
                                 implant_model=rec.get("implant_model"),
                                 variant=rec.get("variant_code"))
    _cache[key] = payload
    return payload


def _deviation_payload(case_id: str, tooth: int, scan_pts: np.ndarray,
                       pose: np.ndarray, template: trimesh.Trimesh,
                       implant_model, variant, preview: bool = False) -> dict:
    """The union pane's whole wire payload for ONE seated pose — extracted (2026-07-26) so
    the SHIPPED read (``site_deviation``) and the PRE-RUN PREVIEW
    (``preview_site_alignment``) are the same instrument on the same scale. Two payload
    builders would be two colourings, and the operator would be verifying one thing before
    Process and reading another after it."""
    posed, signed, vertex_stats = vertex_deviation(scan_pts, pose, template)
    # THE ACCEPTANCE SCALARS ARE THE PNG'S OWN, not a re-derivation over the CAD's
    # vertices. Both aggregates come out of the same kernel, but a CAD mesh is dense at
    # features and sparse on flat walls while the PNG samples the surface by AREA — on a
    # real site the two footprint RMSs differ (measured cap7030 tooth 29: 0.361 vertex-
    # weighted vs 0.427 area-uniform). One site must have ONE published RMS, so the panel
    # is served the number the difference map and the run row already publish; the
    # vertex-set coverage rides alongside under its own name, hidden from nobody.
    png_stats = site_deviation_stats(scan_pts, pose, template)
    finite = np.isfinite(signed)
    payload = {
        "case_id": case_id,
        "tooth": tooth,
        "implant_model": implant_model,
        "variant": variant,
        "frame": "jaw-scan world frame",
        "units": "mm",
        # THE SEATED CAP'S OWN FRAME (2026-07-26, client: "the middle panel ... and the
        # composition in the verify section are not placed to look in the front of the cap,
        # rather the back of it. The first panel is proper view").
        #
        # Pane 1 shows a library part in its canonical frame, so the viewer can aim down its
        # file +z exactly. Panes 2/3 show the SEATED cap, whose axis is wherever the implant
        # went — and the client had no way to know it, so it aimed down the jaw's occlusal
        # direction instead. Measured across this fleet that proxy sits 6.2°-42.0° off the
        # real axis (median ~13°), which is the mismatch the client saw.
        #
        # A client-side axis-of-revolution fit was tried and REFUSED on evidence: over the 12
        # catalog parts it read 0.39°-3.48° on ten and 26.9°/48.3° on zimmer-4.5 7030/8030 (a
        # cap is not a pure surface of revolution — flat top, bore, coded cutout). This is the
        # pose the run actually shipped, so it is exact by construction and cannot fail.
        #
        # x_axis rides along because it is what makes the three panes COMPARABLE: with a
        # shared up-vector the coded cutout appears at the same clock angle in every pane,
        # which is the whole point of putting them side by side.
        "pose": {
            "axis": [round(float(v), 6) for v in pose[:3, 2]],
            "x_axis": [round(float(v), 6) for v in pose[:3, 0]],
            "origin": [round(float(v), 6) for v in pose[:3, 3]],
        },
        "n_points": int(len(posed)),
        "points": np.round(posed, _DEVIATION_ROUND).tolist(),
        "faces": np.asarray(template.faces, int).tolist(),
        "deviation_mm": [None if not ok else round(float(v), _DEVIATION_ROUND)
                         for v, ok in zip(signed, finite)],
        "scale": {
            # the colorbar bounds: clamp/colormap shared with the acceptance PNG, plus
            # what this site's data actually spans (so the UI can say "clamped")
            "clamp_mm": float(DEVIATION_CLAMP_MM),
            "min_mm": -float(DEVIATION_CLAMP_MM),
            "max_mm": float(DEVIATION_CLAMP_MM),
            "colormap": DEVIATION_COLORMAP,
            "sign_convention": "+ = scan outside the cap surface",
            "data_min_mm": (round(float(signed[finite].min()), _DEVIATION_ROUND)
                            if finite.any() else None),
            "data_max_mm": (round(float(signed[finite].max()), _DEVIATION_ROUND)
                            if finite.any() else None),
            "footprint_band_mm": float(DEVIATION_FOOTPRINT_BAND_MM),
        },
        # the site's published acceptance numbers — identical to the deviation PNG's and
        # to the run row's deviation_rms_mm/deviation_p90_mm
        "stats": {
            "rms_mm": (round(float(png_stats["rms_mm"]), 3)
                       if png_stats.get("rms_mm") is not None else None),
            "p90_mm": (round(float(png_stats["p90_mm"]), 3)
                       if png_stats.get("p90_mm") is not None else None),
            "n_footprint": int(png_stats.get("n_footprint") or 0),
            "n_samples": int(png_stats.get("n_samples") or 0),
            "source": "area-uniform surface samples (the acceptance difference map)",
        },
        # how much of the COLOURED mesh falls in the inspection band — a coverage
        # read-out for the panel, never a second acceptance number
        "vertex_footprint_points": int(vertex_stats.get("n_footprint") or 0),
        "reporting_only": True,
        # TRUE when this colouring came from the PRE-RUN preview seat rather than from a
        # shipped package — the UI captions the pane accordingly. Nothing else differs:
        # same alignment pass, same instrument, same scale.
        "preview": bool(preview),
    }
    return payload


# --- PRE-RUN ALIGNMENT PREVIEW -------------------------------------------------------
# THE VERIFICATION MUST WORK ON THE FIRST PASS (client, 2026-07-26). The three-panel
# verify exists to be read BEFORE Process, but its union pane could only ever show a
# SHIPPED pose — so on a case nobody had processed yet the pane said "no seated result
# for this site", which is precisely the moment the operator most needs to see whether
# the part they chose matches the cap that was scanned.
#
# This is the missing read, and it is deliberately NOT a second alignment: it runs the
# SAME ``run_auto_case`` pass the run does, for ONE site, with the product emission, the
# QC renders and the pose-stability bootstrap turned off (measured: 3.5s on a real case
# vs ~30-60s for a full run). Nothing it produces is shippable and nothing it writes is
# reachable — it works in its own ``preview/`` directory, never touches ``package/`` or
# ``run.json``, and the response says ``preview: true``.
#
# It is therefore not a bypass of the run gate either: no package is emitted, no run row
# is recorded, and the acknowledgment the operator signs still governs Process.

_PREVIEW_DIRNAME = "preview"


@app.post("/api/cases/{case_id}/sites/{tooth}/preview-alignment")
def preview_site_alignment(case_id: str, tooth: int, body: RunIn):
    """Seat ONE marked site's chosen cap and return its deviation colouring, with nothing
    shipped — the union pane's read before any run.

    The body is the very same ``RunIn`` the run takes (the operator's selection plus the
    marked sites), so the preview is produced from EXACTLY the inputs Process would use;
    the only thing this endpoint adds is which ``tooth`` to seat. The selection gate is
    the run's own (``_required_selection``): with no implant system or construction part
    named there is nothing to preview, and the refusal is the same sentence.

    Cached per (case, tooth, selection, that site's marks) — stepping between sites and
    back re-reads nothing, and moving a mark invalidates the read it describes."""
    cfg = _case(case_id)
    model, construction_path, jaw_in = _required_selection(case_id, body)
    jaw = jaw_in or cfg["jaw"]
    site = next((s for s in body.sites if s.tooth == tooth), None)
    if site is None:
        raise HTTPException(422, f"tooth {tooth} is not among the marked sites sent — "
                                 f"nothing to preview")
    if not site.declared_variant:
        raise HTTPException(422, f"tooth {tooth} has no declared cap variant — choose one "
                                 f"before previewing the alignment")
    payload = json.dumps({"tooth": tooth, "site": site.model_dump(), "model": model,
                          "construction_path": construction_path, "jaw": jaw,
                          "gingival_offset_mm": body.gingival_offset_mm},
                         sort_keys=True)
    key = f"preview:{case_id}:{hashlib.sha256(payload.encode()).hexdigest()}"
    if not body.fresh and key in _cache:
        return _cache[key]

    scan = _scan_mesh(cfg)
    library = _library_for(cfg, model, [site.declared_variant])
    construction_mesh = _construction_for(cfg, construction_path)
    out_dir = OUT / case_id / _PREVIEW_DIRNAME
    try:
        summary = run_auto_case(
            case_id=case_id, scan=scan, library=library,
            construction_mesh=construction_mesh,
            vendor=construction_catalog.vendor_of(construction_path),
            confirmed=[ConfirmedSite(site.tooth, tuple(site.center),
                                     site.declared_variant, site.marked_points,
                                     site.center_mark, site.rim_mark,
                                     rim_points=site.rim_points)],
            jaw_label=jaw, out_dir=out_dir, proposals=None,
            gingival_offset_mm=body.gingival_offset_mm,
            # nothing is shipped from a preview: no bored product, no QC renders, no
            # stability bootstrap — this is a POSE, read once and thrown away
            generate_product=False, render_qc=False, compute_confidence=False,
            emit_package=False)
    except ValueError as exc:
        # the pipeline's own refusals ("no confirmed site could be aligned") — an answer
        # to the operator, in the words the gate wrote, exactly as the run surfaces them
        raise HTTPException(409, str(exc))

    implant_path = out_dir / f"{case_id}-{tooth}-implant.json"
    if not implant_path.exists():
        raise HTTPException(409, f"tooth {tooth} could not be seated from the marks sent "
                                 f"— re-mark the cap and try again")
    rec = json.loads(implant_path.read_text())
    variant = rec.get("variant_code")
    spec = next((sp for sp in library.specs if sp.variant == variant), None)
    if spec is None:
        raise HTTPException(409, f"previewed variant {variant!r} is not in the current "
                                 f"{model} library")
    row = next((r for r in (summary.get("sites") or []) if r.get("tooth") == tooth), None)
    result = _deviation_payload(
        case_id, tooth, np.asarray(scan.vertices, float),
        np.asarray(rec["pose_matrix"], float), library.template(spec),
        implant_model=rec.get("implant_model") or model, variant=variant, preview=True)
    # The two numbers the operator judges a seat by, from the SAME row the results table
    # would print after Process — so the preview is comparable to what follows it.
    result["seat"] = {
        "seat_method": (row or {}).get("seat_method"),
        "rim_agreement_mm": (row or {}).get("rim_agreement_mm"),
        "fit": (row or {}).get("fit"),
    }
    _cache[key] = result
    return result


# --- OPERATOR ROTATION NUDGE at the review gate --------------------------------------
# The industry-canonical human backstop for weak/unverified clocking (the exocad/
# Automate in-browser correction pattern): the operator PROPOSES a rotation about the
# seated part's own axis; the same ring-fixed kinematics and certification gates that
# judge the pipeline's own clocking judge the proposal. A nudge that fails them is
# refused with the reason — the gates are never bypassed, and every attempt (applied
# or refused) lands in run-history.jsonl.

_NUDGE_MAX_STEP_DEG = 45.0        # a nudge is a correction, not a re-seat
_NUDGE_STABILITY_BOUND_MM = 0.35  # _ring_fixed_candidate excess bound (winner-pass adoption)
_NUDGE_FACE_MEAN_BOUND_MM = 0.4   # face-mean degradation allowance (_clock_gates_ok)
_NUDGE_P90_BOUND_MM = 1.5         # the certification guards' top-face p90 limit
_NUDGE_BAND_REFUSAL_MM = 1.6      # rim-band >= 1.6-and-worsening refusal


class NudgeIn(BaseModel):
    """One operator rotation step, degrees CCW about the seated part's own axis.
    ``reset`` restores the pipeline's own certified pose (delta_deg is ignored)."""
    delta_deg: float = 0.0
    reset: bool = False

    @field_validator("delta_deg")
    @classmethod
    def _bounded_step(cls, v):
        if not np.isfinite(v) or abs(v) > _NUDGE_MAX_STEP_DEG:
            raise ValueError(f"delta_deg must be a finite step within "
                             f"±{_NUDGE_MAX_STEP_DEG:.0f}°")
        return v


def _append_nudge_history(case_id: str, tooth: int, delta_deg: float,
                          cumulative_deg, outcome: str,
                          detail: Optional[str] = None,
                          clocking: Optional[dict] = None) -> None:
    """Same append-only provenance stream as _append_run_history — one JSON line per
    nudge attempt, applied or refused, so post-hoc analysis sees the operator's hand."""
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "case_id": case_id,
           "event": "nudge-rotation", "tooth": tooth,
           "delta_deg": round(float(delta_deg), 1),
           "cumulative_deg": (round(float(cumulative_deg), 1)
                              if cumulative_deg is not None else None),
           "outcome": outcome}
    if detail:
        rec["detail"] = detail
    if clocking:
        rec["clocking"] = clocking
    try:
        OUT.mkdir(parents=True, exist_ok=True)
        with (OUT / "run-history.jsonl").open("a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
    except OSError:
        pass  # history must never take down a request


def _refuse_nudge(case_id: str, tooth: int, delta_deg: float, reason: str):
    msg = f"rotation {delta_deg:+.1f}° refused: {reason}"
    _append_nudge_history(case_id, tooth, delta_deg, None, outcome="refused",
                          detail=msg)
    raise HTTPException(409, msg)


def _read_clock_at(L: np.ndarray, template: trimesh.Trimesh,
                   t_ref: np.ndarray, t_at: np.ndarray):
    """Coded-cutout residual at pose ``t_at`` (site-local frame), with the scan's rim
    centre estimated ONCE at ``t_ref`` and mapped through as a physical point — the
    winner pass's own protocol (re-estimating per pose breaks two-pose consistency,
    measured; see clock_signature's module doc)."""
    sig = template_signature(template)
    crop = L[np.linalg.norm(L[:, :2] - t_ref[:2, 3], axis=1) < 8.0]
    canon0 = (crop - t_ref[:3, 3]) @ t_ref[:3, :3]
    c0 = scan_rim_centre(canon0, sig.ztop, sig.rmax)
    c_phys = t_ref[:3, :3] @ np.array([c0[0], c0[1], sig.ztop]) + t_ref[:3, 3]
    canon1 = (crop - t_at[:3, 3]) @ t_at[:3, :3]
    c1 = ((c_phys - t_at[:3, 3]) @ t_at[:3, :3])[:2]
    return notch_reading(canon1, sig, c1)


def _update_run_row(case_id: str, tooth: int, notch,
                    nudge_fields: Optional[dict] = None,
                    extra: Optional[dict] = None):
    """Fold the post-adjustment instrument reading and the operator audit into the case's
    cached run row (disk + in-memory), so a page reload shows the adjusted state, not the
    pre-adjustment table. Returns the row's clocking dict for the response.

    ``nudge_fields`` is the operator-ROTATION bookkeeping; None leaves the row's existing
    block alone (2026-07-25: a manual best-fit is a 6-DoF move, not a clock nudge — it
    must not overwrite the site's cumulative rotation with a number it did not apply).
    ``extra`` are further row blocks (e.g. the best-fit's own read-out)."""
    notch_fields = {
        "notch_shift_deg": (round(notch.shift_deg, 1)
                            if notch.shift_deg is not None else None),
        "notch_corr": round(notch.corr, 3),
        "notch_prominence": round(notch.prominence, 3),
    }
    clocking = dict(notch_fields)
    disk = OUT / case_id / "run.json"
    if disk.exists():
        try:
            saved = json.loads(disk.read_text())
        except (OSError, json.JSONDecodeError):
            saved = None
        if saved:
            for row in (saved.get("summary") or {}).get("sites") or []:
                if row.get("tooth") == tooth:
                    row["clocking"] = {**(row.get("clocking") or {}), **notch_fields}
                    if nudge_fields is not None:
                        row["nudge"] = nudge_fields
                    row.update(extra or {})
                    clocking = row["clocking"]
            try:
                disk.write_text(json.dumps(saved, default=str))
            except OSError:
                pass  # the response still carries the fresh reading
            if saved.get("_key"):
                _cache[saved["_key"]] = saved
    return clocking


def _load_rotation_site(case_id: str, tooth: int):
    """Shared context for the operator-rotation endpoints (nudge-rotation and
    align-to-mark): the shipped record and its library template, plus the site-local
    (crowns) frame and the shipped pose expressed within it — the same frame the
    winner pass judged the pose in (_crowns_frame is deterministic on the scan, so
    the round trip is exact)."""
    cfg = _case(case_id)
    pkg = OUT / case_id / "package"
    implant_path = pkg / f"{case_id}-{tooth}-implant.json"
    if not implant_path.exists():
        raise HTTPException(404, f"tooth {tooth} has no shipped pose for case "
                                 f"{case_id!r} — run the automation first")
    rec = json.loads(implant_path.read_text())
    # the model comes from the SHIPPED RECORD, not from a folder-name match: the run was
    # made under an explicit operator selection and implant.json carries it
    model = _shipped_model(cfg, rec)
    variant = rec.get("variant_code")
    scan = _scan_mesh(cfg)
    library = _library_for(cfg, model, [variant] if variant else None)
    spec = next((sp for sp in library.specs if sp.variant == variant), None)
    if spec is None:
        raise HTTPException(409, f"shipped variant {variant!r} is not "
                                 f"in the current {model} library — cannot re-pose")
    template = library.template(spec)
    pts = np.asarray(scan.vertices, float)
    frame, origin, _axis = _crowns_frame(pts, np.asarray(scan.vertex_normals, float))
    L = (pts - origin) @ frame
    W = np.asarray(rec["pose_matrix"], float)
    t_now = np.eye(4)
    t_now[:3, :3] = frame.T @ W[:3, :3]
    t_now[:3, 3] = frame.T @ (W[:3, 3] - origin)
    return pkg, implant_path, rec, template, frame, origin, L, t_now


def _certification_gates(template: trimesh.Trimesh, L: np.ndarray, t_now: np.ndarray,
                         cand: np.ndarray, refuse) -> None:
    """THE certification bounds every operator pose change is judged by — the exact
    winner-pass math (_clock_gates_ok in auto_flow): face-mean +0.4, top-face p90 1.5
    ride-off, rim-band >= 1.6-and-worsening. ``refuse(reason)`` must raise.

    Factored out of ``_judge_rotation`` (2026-07-25) so the manual BEST-FIT — a 6-DoF
    move, which has no ring-fixed kinematics to form — is judged by the same bounds as
    the rotation endpoints, from one implementation. Nothing about the rotation path
    changed: ``_judge_rotation`` still forms its ring-fixed candidate and clears the
    stability bound first, then calls this."""
    # The ROI stand-in is the 8mm site crop the clock reading itself uses (the run's
    # localization ROI is not persisted; every gate is relative — before vs after over
    # the SAME point set — so the stand-in judges the same degradation the winner pass
    # would).
    tv = np.asarray(template.vertices, float)
    tpv = tv[tv[:, 2] > tv[:, 2].max() - 1.2]
    if len(tpv) > 400:
        tpv = tpv[np.linspace(0, len(tpv) - 1, 400).astype(int)]
    crop = L[np.linalg.norm(L[:, :2] - t_now[:2, 3], axis=1) < 8.0]
    if len(tpv) < 30 or len(crop) < 40:
        # FAIL CLOSED: with too few points the face/p90/band gates cannot be
        # judged — an unjudgeable proposal is refused, never adopted on the
        # stability bound alone ("the gates are never bypassed")
        refuse(f"too few scan points near the site to judge the "
               f"certification gates ({len(crop)} in the 8mm crop)")
    crop_tree = cKDTree(crop)

    def _face_mean(m):
        return float(crop_tree.query(tpv @ m[:3, :3].T + m[:3, 3])[0].mean())

    def _top_p90(m):
        return float(np.percentile(
            crop_tree.query(tpv @ m[:3, :3].T + m[:3, 3])[0], 90))

    d0, d1 = _face_mean(t_now), _face_mean(cand)
    if d1 > d0 + _NUDGE_FACE_MEAN_BOUND_MM:
        refuse(f"the top face would pull off the scan "
               f"({d0:.2f} → {d1:.2f}mm mean, bound "
               f"+{_NUDGE_FACE_MEAN_BOUND_MM}mm)")
    p0, p1 = _top_p90(t_now), _top_p90(cand)
    if p1 > _NUDGE_P90_BOUND_MM and p1 > p0 + 0.02:
        refuse(f"the part would ride off on one side (top-face p90 "
               f"{p0:.2f} → {p1:.2f}mm, limit {_NUDGE_P90_BOUND_MM}mm)")
    # rim-band anchor from the CURRENT pose: the ring-fixed kinematics hold
    # the measured rim centre still, so the same anchor is valid at both poses.
    # A 6-DoF best-fit may slide the rim off that anchor, which can only make this
    # comparison HARSHER — a conservative gate, never a permissive one.
    ac = _posed_rim_centre(template, t_now)
    ar = float(np.percentile(np.linalg.norm(tv[:, :2], axis=1), 97))
    if ac is not None:
        bv0 = _rim_agreement_mm(L, ac, ar, template, t_now)
        bv1 = _rim_agreement_mm(L, ac, ar, template, cand)
        if (bv0 is not None and bv1 is not None
                and bv1 >= _NUDGE_BAND_REFUSAL_MM and bv1 > bv0 + 0.02):
            refuse(f"the rim band would leave the scan "
                   f"({bv0:.2f} → {bv1:.2f}mm, refusal at "
                   f"{_NUDGE_BAND_REFUSAL_MM}mm-and-worsening)")


def _judge_rotation(template: trimesh.Trimesh, L: np.ndarray, t_now: np.ndarray,
                    applied: float, refuse):
    """One operator rotation proposal through the FULL judging path the rotation
    endpoints share: ring-fixed candidate formation, the stability bound, then
    ``_certification_gates``. ``refuse(reason)`` must raise (every caller 409s with its
    own audit line); (candidate_pose, stability_excess_mm) returns only when every gate
    passes."""
    rf = _ring_fixed_candidate(template, t_now[:3, :3], t_now[:3, 3],
                               float(np.radians(applied)))
    if rf is None:
        refuse("the part's rim ring is unmeasurable — a ring-fixed "
               "rotation cannot be formed for this site")
    cand, excess = rf
    if excess > _NUDGE_STABILITY_BOUND_MM:
        refuse(f"ring-fixed stability excess {excess:.2f}mm exceeds the "
               f"{_NUDGE_STABILITY_BOUND_MM}mm certification bound — the "
               f"rim cannot hold this rotation still")
    _certification_gates(template, L, t_now, cand, refuse)
    return cand, excess


def _reemit_site(pkg: Path, case_id: str, tooth: int, rec: dict,
                 template: trimesh.Trimesh, frame: np.ndarray, origin: np.ndarray,
                 cand: np.ndarray) -> Path:
    """Compose the site-local candidate back to the jaw-world frame and re-emit the
    site's shipped geometry — the aligned-cap STL the viewer loads — updating ``rec``'s
    pose fields in place (the caller adds its own blocks and persists implant.json).
    The construction/scanbody deliverables re-pose on the next full run; an operator
    adjustment corrects the cap-alignment record at the review gate."""
    W_new = np.eye(4)
    W_new[:3, :3] = frame @ cand[:3, :3]
    W_new[:3, 3] = origin + frame @ cand[:3, 3]
    posed = template.copy()
    posed.apply_transform(W_new)
    cap_path = pkg / f"{case_id}-{tooth}-healingcap-aligned.stl"
    cap_path.write_bytes(posed.export(file_type="stl"))
    rec["pose_matrix"] = W_new.tolist()
    rec["position"] = W_new[:3, 3].tolist()
    rec["axis"] = W_new[:3, 2].tolist()
    return cap_path


def _finish_adjustment(pkg: Path, case_id: str, tooth: int, implant_path: Path,
                       rec: dict, template: trimesh.Trimesh, L: np.ndarray,
                       cand: np.ndarray, cap_path: Path, operation: str,
                       detail: str) -> List[str]:
    """The common TAIL of every adopted operator adjustment: append the provenance entry
    to the site's append-only ``adjustments`` record, persist implant.json, render the
    ALIGNMENT PROOF, and re-hash the rewritten files into the package manifest.

    The proof (``<case>-<tooth>-alignment-proof.png``) exists only for sites a human
    actually moved — a clean automatic run never produces one, and nothing here runs on
    the run path. Manifest registration also repairs a real gap: an adjustment rewrites
    the cap STL and implant.json in place, so their emission-time hashes went stale
    (``output_package.register_package_files``). A package with no manifest (emitted
    before the manifest existed) is left alone rather than 500ing the adjustment.
    Returns the file names the endpoint reports."""
    rec.setdefault("adjustments", []).append({
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "operation": operation,
        # this API authenticates nobody. Recording "operator" AND saying that the identity
        # was never captured is the honest record; a name here would be invented.
        "who": "operator (this API captures no identity)",
        "detail": detail,
    })
    implant_path.write_text(json.dumps(rec, indent=2))
    # the proof is drawn in the SITE-LOCAL frame (points and pose share it) — the same
    # canonical picture the world-frame pair would give, without rebuilding the cloud
    proof = render_alignment_proof(case_id, tooth, L, cand, template,
                                   rec["adjustments"], pkg)
    names = [cap_path.name, implant_path.name, proof.name]
    manifest = pkg / f"{case_id}-manifest.json"
    if manifest.exists():
        register_package_files(manifest, [pkg / n for n in names])
    return names


def _adopt_rotation(pkg: Path, case_id: str, tooth: int, implant_path: Path,
                    rec: dict, template: trimesh.Trimesh, frame: np.ndarray,
                    origin: np.ndarray, L: np.ndarray, t_now: np.ndarray,
                    cand: np.ndarray, applied: float, cumulative: float,
                    base_pose: np.ndarray, operation: str = "nudge-rotation"):
    """ADOPTED ROTATION: re-emit the site's shipped record, then re-read the coded-cutout
    residual at the new pose (the codes are the arbiter the operator is steering toward —
    the UI shows "-1.8° — aligned"), fold reading + audit into the cached run row, and
    write the provenance + alignment proof. Returns (clocking, nudge_fields, files)."""
    cap_path = _reemit_site(pkg, case_id, tooth, rec, template, frame, origin, cand)
    nudge_fields = {"operator_delta_deg": round(applied, 1),
                    "cumulative_deg": round(cumulative, 1)}
    rec["nudge"] = {**nudge_fields, "base_pose_matrix": base_pose.tolist()}
    notch = _read_clock_at(L, template, t_now, cand)
    clocking = _update_run_row(case_id, tooth, notch, nudge_fields)
    files = _finish_adjustment(
        pkg, case_id, tooth, implant_path, rec, template, L, cand, cap_path, operation,
        f"rotated {applied:+.1f}° about the part axis "
        f"(cumulative {cumulative:+.1f}°)")
    return clocking, nudge_fields, files


@app.post("/api/cases/{case_id}/sites/{tooth}/nudge-rotation")
def nudge_rotation(case_id: str, tooth: int, body: NudgeIn):
    pkg, implant_path, rec, template, frame, origin, L, t_now = \
        _load_rotation_site(case_id, tooth)

    nudge_state = rec.get("nudge") or {}
    base_pose = np.asarray(nudge_state.get("base_pose_matrix")
                           or rec["pose_matrix"], float)
    prior_cum = float(nudge_state.get("cumulative_deg") or 0.0)

    excess = None
    if body.reset:
        # the base pose is the pipeline's own certified output — restoring it
        # verbatim needs no re-judging
        applied, cumulative = -prior_cum, 0.0
        cand = np.eye(4)
        cand[:3, :3] = frame.T @ base_pose[:3, :3]
        cand[:3, 3] = frame.T @ (base_pose[:3, 3] - origin)
    else:
        applied = float(body.delta_deg)
        cumulative = prior_cum + applied
        cand, excess = _judge_rotation(
            template, L, t_now, applied,
            lambda reason: _refuse_nudge(case_id, tooth, applied, reason))

    clocking, nudge_fields, files = _adopt_rotation(
        pkg, case_id, tooth, implant_path, rec, template, frame, origin, L,
        t_now, cand, applied, cumulative, base_pose,
        operation="nudge-rotation-reset" if body.reset else "nudge-rotation")
    _append_nudge_history(case_id, tooth, applied, cumulative, outcome="applied",
                          clocking=clocking)
    return {"tooth": tooth,
            "applied_delta_deg": round(applied, 1),
            "cumulative_deg": round(cumulative, 1),
            "stability_excess_mm": (round(excess, 3) if excess is not None else None),
            "clocking": clocking,
            "nudge": nudge_fields,
            "files": files}


# --- ALIGN-TO-MARKED-TRENCH at the review gate ----------------------------------------
# The operator marks the cap's CODED CUTOUT/trench on the scan (the screw hole itself is
# invisible — a smooth dome — but the coded trench IS visible; phase2a report §3b/§7) and
# the server rotates the seated cap so its nearest code feature lands on that mark. The
# rotation is a PROPOSAL through the exact nudge machinery — ring-fixed kinematics, the
# stability bound, and the certification gates all judge it; a refusal is a 409 with the
# reason, and every attempt (applied or refused) lands in run-history.jsonl. This is the
# operator backstop for weak-evidence sites (rotation_unverified / evidence none) and a
# manual override elsewhere — never a bypass.

_MARK_MAX_DISTANCE_MM = 15.0  # a trench mark belongs ON the site, not across the arch


class AlignToMarkIn(BaseModel):
    """The operator's click on the scanned coded trench, world coordinates on the
    scan mesh (the same frame the ⊕/◐ mark tools deliver)."""
    point: List[float]

    @field_validator("point")
    @classmethod
    def _finite_xyz(cls, v):
        if len(v) != 3:
            raise ValueError("point must be an [x, y, z] triple")
        if not all(np.isfinite(c) for c in v):
            raise ValueError("point coordinates must be finite numbers")
        return [float(c) for c in v]


def _append_align_mark_history(case_id: str, tooth: int, delta_deg: float,
                               cumulative_deg, outcome: str,
                               point: List[float], click_az: float, matched,
                               detail: Optional[str] = None,
                               clocking: Optional[dict] = None) -> None:
    """Same append-only provenance stream as the run/nudge histories — one JSON line
    per align-to-mark attempt, applied or refused, carrying the operator's click and
    the feature match so post-hoc analysis can replay the geometry."""
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "case_id": case_id,
           "event": "align-to-mark", "tooth": tooth,
           "point": [round(float(c), 3) for c in point],
           "click_azimuth_deg": round(float(click_az), 1),
           "matched_feature_azimuth_deg": (round(float(matched), 1)
                                           if matched is not None else None),
           "applied_delta_deg": round(float(delta_deg), 1),
           "cumulative_deg": (round(float(cumulative_deg), 1)
                              if cumulative_deg is not None else None),
           "outcome": outcome}
    if detail:
        rec["detail"] = detail
    if clocking:
        rec["clocking"] = clocking
    try:
        OUT.mkdir(parents=True, exist_ok=True)
        with (OUT / "run-history.jsonl").open("a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
    except OSError:
        pass  # history must never take down a request


def _refuse_align_mark(case_id: str, tooth: int, delta_deg: float,
                       point: List[float], click_az: float, matched, reason: str):
    msg = f"align-to-mark rotation {delta_deg:+.1f}° refused: {reason}"
    _append_align_mark_history(case_id, tooth, delta_deg, None, outcome="refused",
                               point=point, click_az=click_az, matched=matched,
                               detail=msg)
    raise HTTPException(409, msg)


@app.post("/api/cases/{case_id}/sites/{tooth}/align-to-mark")
def align_to_mark(case_id: str, tooth: int, body: AlignToMarkIn):
    pkg, implant_path, rec, template, frame, origin, L, t_now = \
        _load_rotation_site(case_id, tooth)

    point = np.asarray(body.point, float)
    site_pos = np.asarray(rec["pose_matrix"], float)[:3, 3]
    dist = float(np.linalg.norm(point - site_pos))
    if dist > _MARK_MAX_DISTANCE_MM:
        raise HTTPException(422, f"the mark is {dist:.1f}mm from tooth {tooth}'s seated "
                                 f"cap — click the coded trench on the cap itself "
                                 f"(within {_MARK_MAX_DISTANCE_MM:.0f}mm)")

    sig = template_signature(template)
    features = coded_feature_azimuths(sig)  # domain/part_features: one source of truth
    if not features:
        raise HTTPException(409, f"the {rec.get('variant_code')!r} template carries no "
                                 f"coded relief — there is no code feature to align to "
                                 f"a mark")

    # The click's azimuth about the MEASURED rim centre — the ring-fixed invariant the
    # nudge/gates hold still: map the world click into the site-local frame, then into
    # the pose's canonical frame, and measure about the same once-estimated scan rim
    # centre the clock reading itself uses. The template's feature azimuths are about
    # its own rim centre — the identical centre convention the e8 correlation compares
    # its two images under.
    crop = L[np.linalg.norm(L[:, :2] - t_now[:2, 3], axis=1) < 8.0]
    canon = (crop - t_now[:3, 3]) @ t_now[:3, :3]
    c0 = scan_rim_centre(canon, sig.ztop, sig.rmax)
    p_local = frame.T @ (point - origin)
    p_canon = (p_local - t_now[:3, 3]) @ t_now[:3, :3]
    click_az = float(np.degrees(np.arctan2(p_canon[1] - c0[1], p_canon[0] - c0[0])))

    # Minimal rotation aligning the NEAREST code feature to the click: rotating the
    # part CCW by delta moves a feature at azimuth f to azimuth f+delta in the scan's
    # frame, so delta = click_az - f (wrapped), minimized over the features.
    deltas = [(abs(wrap_deg(click_az - f)), wrap_deg(click_az - f), f)
              for f in features]
    _absd, applied, matched = min(deltas)

    nudge_state = rec.get("nudge") or {}
    base_pose = np.asarray(nudge_state.get("base_pose_matrix")
                           or rec["pose_matrix"], float)
    prior_cum = float(nudge_state.get("cumulative_deg") or 0.0)
    cumulative = prior_cum + applied

    cand, excess = _judge_rotation(
        template, L, t_now, applied,
        lambda reason: _refuse_align_mark(case_id, tooth, applied, body.point,
                                          click_az, matched, reason))
    clocking, nudge_fields, files = _adopt_rotation(
        pkg, case_id, tooth, implant_path, rec, template, frame, origin, L,
        t_now, cand, applied, cumulative, base_pose, operation="align-to-mark")
    _append_align_mark_history(case_id, tooth, applied, cumulative, outcome="applied",
                               point=body.point, click_az=click_az, matched=matched,
                               clocking=clocking)
    return {"tooth": tooth,
            "applied_delta_deg": round(applied, 1),
            "cumulative_deg": round(cumulative, 1),
            "stability_excess_mm": (round(excess, 3) if excess is not None else None),
            "clocking": clocking,
            "nudge": nudge_fields,
            "matched_feature_azimuth_deg": round(matched, 1),
            "click_azimuth_deg": round(click_az, 1),
            "files": files}


# --- ALIGN-TO-CORRESPONDENCE at the review gate ---------------------------------------
# The client's 2026-07-24 ask, whole: the operator marks a feature on the LIBRARY PART and
# the SAME feature on the SCAN, and the server rotates the seated cap so the named pairs
# meet. This is align-to-mark with the ambiguity removed: nearest-match binds a click to
# whichever code feature happens to be closest — wrong by a whole inter-feature gap on the
# 2-3-feature caps (zimmer-4.5-7030 reads three trenches) and unusable where the automatic
# reader has no evidence at all. Naming the feature is the industry fallback (ZimVie
# the industry's 3 dots on the codes; Medit's 3 corresponding points).
#
# The rotation is still a PROPOSAL: the same ring-fixed kinematics, the same stability
# bound, the same certification gates, the same notch re-read and re-emit, the same
# append-only audit. More than one pair adds a QC number the operator can read — the
# best-fit rotation's per-pair residual in millimetres ("your marks agree to X mm").
#
# FREE POINTS (client ask 2026-07-26: "only let me mark one point of the trench, but the
# other software adds to like the picture I once gave you"): a pair may name an ARBITRARY
# canonical-frame point on the part instead of a feature id. On catalogs whose detector
# reads a single rotation-defining feature (zimmer-4.5/6020: trench-01 only — the channel
# sits 0.075mm from the axis and is correctly non-rotational) the feature-only contract
# stranded the operator at one pair while the part visibly carries a second cutout. A
# free point is measured about the same rim centre a feature azimuth is named about, so
# it steers ROTATION ONLY through the identical judged path — marks never drag the pose.

_CORRESPONDENCE_MAX_PAIRS = 8


class CorrespondencePairIn(BaseModel):
    """One operator correspondence. The PART half is EITHER a feature of the library part
    (by id, from ``GET /api/library/{model}/{variant}/features``) OR ``part_point`` — an
    ARBITRARY canonical-frame click on the part itself (client ask 2026-07-26: RealGUIDE
    lets the operator click free numbered points, and on catalogs whose detector reads a
    single rotation-defining feature the feature-only contract stranded them at one pair).
    ``scan_point`` is where the operator sees that same spot on the SCAN, in world
    coordinates on the scan mesh. Exactly one of the two part halves per pair."""
    feature_id: Optional[str] = None
    part_point: Optional[List[float]] = None
    scan_point: List[float]

    @field_validator("scan_point", "part_point")
    @classmethod
    def _finite_xyz(cls, v, info):
        if v is None:
            return v
        if len(v) != 3:
            raise ValueError(f"{info.field_name} must be an [x, y, z] triple")
        if not all(np.isfinite(c) for c in v):
            raise ValueError(f"{info.field_name} coordinates must be finite numbers")
        return [float(c) for c in v]

    @model_validator(mode="after")
    def _one_part_half(self):
        if (self.feature_id is None) == (self.part_point is None):
            raise ValueError("each pair needs exactly one of feature_id or part_point")
        return self


class AlignToCorrespondenceIn(BaseModel):
    pairs: List[CorrespondencePairIn]


def _append_correspondence_history(case_id: str, tooth: int, delta_deg: float,
                                   cumulative_deg, outcome: str, pairs: List[dict],
                                   residuals: List[dict],
                                   residual_rms_mm: Optional[float] = None,
                                   detail: Optional[str] = None,
                                   clocking: Optional[dict] = None) -> None:
    """Same append-only provenance stream as the run/nudge/align-to-mark histories — one
    JSON line per attempt, applied or refused, carrying every pair the operator named and
    the residual each one ended up with, so the geometry can be replayed."""
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "case_id": case_id,
           "event": "align-to-correspondence", "tooth": tooth,
           "pairs": pairs, "residuals": residuals,
           "residual_rms_mm": (round(float(residual_rms_mm), 3)
                               if residual_rms_mm is not None else None),
           "applied_delta_deg": round(float(delta_deg), 1),
           "cumulative_deg": (round(float(cumulative_deg), 1)
                              if cumulative_deg is not None else None),
           "outcome": outcome}
    if detail:
        rec["detail"] = detail
    if clocking:
        rec["clocking"] = clocking
    try:
        OUT.mkdir(parents=True, exist_ok=True)
        with (OUT / "run-history.jsonl").open("a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
    except OSError:
        pass  # history must never take down a request


def _site_click_azimuth(L: np.ndarray, sig, t_now: np.ndarray, frame: np.ndarray,
                        origin: np.ndarray):
    """(azimuth_of(point) -> deg, rim_centre_xy) for this site — the align-to-mark click
    mapping, factored so one pair and many pairs measure identically: world click ->
    site-local -> the pose's canonical frame, azimuth about the SCAN's own once-estimated
    rim centre (the centre convention the template's feature azimuths and the e8
    correlation both use)."""
    crop = L[np.linalg.norm(L[:, :2] - t_now[:2, 3], axis=1) < 8.0]
    canon = (crop - t_now[:3, 3]) @ t_now[:3, :3]
    c0 = scan_rim_centre(canon, sig.ztop, sig.rmax)

    def azimuth_of(point_world: np.ndarray) -> float:
        p_local = frame.T @ (np.asarray(point_world, float) - origin)
        p_canon = (p_local - t_now[:3, 3]) @ t_now[:3, :3]
        return float(np.degrees(np.arctan2(p_canon[1] - c0[1], p_canon[0] - c0[0])))

    return azimuth_of, c0


@app.post("/api/cases/{case_id}/sites/{tooth}/align-to-correspondence")
def align_to_correspondence(case_id: str, tooth: int, body: AlignToCorrespondenceIn):
    if not body.pairs:
        raise HTTPException(422, "name at least one correspondence — a feature of the "
                                 "part and where you see it on the scan")
    if len(body.pairs) > _CORRESPONDENCE_MAX_PAIRS:
        raise HTTPException(422, f"a correspondence is capped at "
                                 f"{_CORRESPONDENCE_MAX_PAIRS} pairs, got "
                                 f"{len(body.pairs)}")
    # The duplicate check names FEATURES only: one part feature cannot sit at two places
    # on the scan, but several free points are legal by construction — each one IS its
    # own spot on the part (client ask 2026-07-26).
    named = [p.feature_id for p in body.pairs if p.feature_id is not None]
    dupes = sorted({i for i in named if named.count(i) > 1})
    if dupes:
        raise HTTPException(422, f"feature(s) {dupes} are named twice — one part feature "
                                 f"cannot sit at two places on the scan")

    cfg = _case(case_id)
    pkg, implant_path, rec, template, frame, origin, L, t_now = \
        _load_rotation_site(case_id, tooth)
    variant = rec.get("variant_code")
    # the model the run actually shipped under (explicit selection), not a folder-name read
    model = rec.get("implant_model") or cfg.get("suggested_model")
    ann, _auto_seeded = _seeded_annotation(model, str(variant), template)
    known = ", ".join(f.id for f in ann.features) or "none"
    # Free points measure their azimuth about the SAME rim centre every feature azimuth
    # is named about (domain/part_features.template_rim_centre) — that identity is what
    # lets a free pair ride the feature pair's rotation math unchanged.
    centre = (template_rim_centre(template)
              if any(p.part_point is not None for p in body.pairs) else None)

    site_pos = np.asarray(rec["pose_matrix"], float)[:3, 3]
    # (label, part_azimuth_deg, lever_radius_mm, scan_point, audit_record) per pair —
    # feature pairs and free points are indistinguishable past this loop.
    resolved: List["tuple"] = []
    free_count = 0
    for pair in body.pairs:
        if pair.feature_id is not None:
            feature = ann.by_id(pair.feature_id)
            if feature is None:
                raise HTTPException(422, f"{pair.feature_id!r} is not a marked feature "
                                         f"of {model}/{variant} (known: {known})")
            if not feature.defines_rotation:
                raise HTTPException(422, f"{feature.id!r} sits {feature.radius_mm:.2f}mm "
                                         f"from the part's rim centre — inside "
                                         f"{MIN_LEVER_ARM_MM}mm it names the axis, not a "
                                         f"clock angle, and cannot anchor a rotation")
            label, azimuth, radius = feature.id, feature.azimuth_deg, feature.radius_mm
            audit = {"feature_id": feature.id,
                     "scan_point": [round(float(c), 3) for c in pair.scan_point]}
        else:
            # FREE POINT: the positional label ("point-1", "point-2" in click order) is
            # this pair's identity in the response and on the provenance stream, and the
            # audit record carries the part click itself so run-history.jsonl stays
            # replayable without the annotation.
            free_count += 1
            label = f"point-{free_count}"
            off = np.asarray(pair.part_point, float)[:2] - centre
            radius = float(np.linalg.norm(off))
            if radius < MIN_LEVER_ARM_MM:
                raise HTTPException(422, f"{label!r} sits {radius:.2f}mm from the "
                                         f"part's rim centre — inside "
                                         f"{MIN_LEVER_ARM_MM}mm it names the axis, not a "
                                         f"clock angle, and cannot anchor a rotation")
            azimuth = float(np.degrees(np.arctan2(off[1], off[0])))
            audit = {"label": label,
                     "part_point": [round(float(c), 3) for c in pair.part_point],
                     "scan_point": [round(float(c), 3) for c in pair.scan_point]}
        point = np.asarray(pair.scan_point, float)
        dist = float(np.linalg.norm(point - site_pos))
        if dist > _MARK_MAX_DISTANCE_MM:
            raise HTTPException(422, f"the mark for {label!r} is {dist:.1f}mm from "
                                     f"tooth {tooth}'s seated cap — click the feature on "
                                     f"the cap itself (within "
                                     f"{_MARK_MAX_DISTANCE_MM:.0f}mm)")
        resolved.append((label, azimuth, radius, point, audit))

    sig = template_signature(template)
    azimuth_of, _c0 = _site_click_azimuth(L, sig, t_now, frame, origin)

    # Rotating the part CCW by delta carries a feature at canonical azimuth f to f+delta
    # in the scan's frame, so each pair asks for delta_i = click_i - f_i (wrapped). With
    # one pair that IS the rotation; with several, the least-squares rotation over the
    # angular residuals is their CIRCULAR MEAN (the angle minimising the sum of squared
    # wrapped residuals — atan2 of the summed unit vectors, which a plain arithmetic mean
    # would get wrong across the +/-180 seam).
    clicks = [azimuth_of(pt) for _lbl, _az, _r, pt, _audit in resolved]
    deltas = [wrap_deg(click - azimuth)
              for (_lbl, azimuth, _r, _pt, _audit), click in zip(resolved, clicks)]
    rad = np.radians(deltas)
    applied = float(np.degrees(np.arctan2(float(np.sin(rad).sum()),
                                          float(np.cos(rad).sum()))))
    residuals = []
    for (label, azimuth, radius, _point, _audit), click, delta in zip(resolved, clicks,
                                                                      deltas):
        res_deg = wrap_deg(delta - applied)
        residuals.append({
            # a free point's label rides the same identity key as a feature id — one
            # residual shape on the wire and on the provenance stream
            "feature_id": label,
            "feature_azimuth_deg": round(azimuth, 1),
            "click_azimuth_deg": round(click, 1),
            "delta_deg": round(delta, 1),
            "residual_deg": round(res_deg, 2),
            # the arc the mark misses by AT THE MARK'S OWN RADIUS — the millimetres
            # the operator can judge, not an abstract angle
            "residual_mm": round(abs(np.radians(res_deg)) * radius, 3)})
    rms = float(np.sqrt(np.mean([r["residual_mm"] ** 2 for r in residuals])))
    audit_pairs = [audit for _lbl, _az, _r, _pt, audit in resolved]

    nudge_state = rec.get("nudge") or {}
    base_pose = np.asarray(nudge_state.get("base_pose_matrix")
                           or rec["pose_matrix"], float)
    cumulative = float(nudge_state.get("cumulative_deg") or 0.0) + applied

    def _refuse(reason: str):
        msg = f"align-to-correspondence rotation {applied:+.1f}° refused: {reason}"
        _append_correspondence_history(case_id, tooth, applied, None, outcome="refused",
                                       pairs=audit_pairs, residuals=residuals,
                                       residual_rms_mm=rms, detail=msg)
        raise HTTPException(409, msg)

    cand, excess = _judge_rotation(template, L, t_now, applied, _refuse)
    clocking, nudge_fields, files = _adopt_rotation(
        pkg, case_id, tooth, implant_path, rec, template, frame, origin, L,
        t_now, cand, applied, cumulative, base_pose,
        operation="align-to-correspondence")
    _append_correspondence_history(case_id, tooth, applied, cumulative,
                                   outcome="applied", pairs=audit_pairs,
                                   residuals=residuals, residual_rms_mm=rms,
                                   clocking=clocking)
    return {"tooth": tooth,
            "applied_delta_deg": round(applied, 1),
            "cumulative_deg": round(cumulative, 1),
            "stability_excess_mm": (round(excess, 3) if excess is not None else None),
            "clocking": clocking,
            "nudge": nudge_fields,
            "pairs": residuals,
            "residual_rms_mm": round(rms, 3),
            "files": files}


# --- MANUAL BEST-FIT at the review gate -----------------------------------------------
# The industry's post-processing step (RealGUIDE/exocad/3Shape all follow a human's coarse
# alignment with a dense best-fit over the selected surface), here as an OPERATOR-TRIGGERED
# pass on the SHIPPED pose. It runs the pipeline's own refinement — auto_flow's
# ``_refine_best_fit``, not a second transcription of it — so the trust region (<=1.2mm,
# <=8 deg) and the monotonic-improvement rule that keep the historical trimmed-ICP failure
# (wandering into ridge-wall basins that score well) out of the winner pass keep it out of
# here too. It is a 6-DoF move, so the certification bounds that guard the winner passes
# judge the candidate: the SAME ``_certification_gates`` the nudge/align/correspondence
# paths clear (there is no ring-fixed candidate to form — a best-fit is not a rotation —
# so the ring stability bound does not apply and is not faked).
#
# A refusal is a 409 with the reason and NO file touched; an adoption re-emits the site
# record, re-reads the codes, and lands in run-history.jsonl like every other adjustment.

_BEST_FIT_DEFAULT_DIAMETER_MM = 0.3
_BEST_FIT_MIN_DIAMETER_MM = 0.05
# ceiling = 2 * the winner pass's own correspondence cutoff (auto_flow's
# _BEST_FIT_CORR_DIST_MM = 1.0mm): the operator may run the refinement as tight as they
# like, but may not open the correspondence wider than the automatic pass ever does
_BEST_FIT_MAX_DIAMETER_MM = 2.0 * _BEST_FIT_CORR_DIST_MM
_BEST_FIT_SEED = 23  # _refine_best_fit samples the template surface; seeded + restored
#                      here so the OPERATOR path is deterministic (the winner pass's own
#                      stream is untouched — the state is put back)


class BestFitIn(BaseModel):
    """``matching_diameter_mm`` is the operator's correspondence search DIAMETER, the
    dial the dental-CAD best-fit dialogs expose.

    MAPPING, stated out loud: ``domain.icp.trimmed_icp``'s ``max_corr_dist`` is a
    RADIUS — a source point pairs with the nearest scan point only if it lies within
    that distance. A search DIAMETER of d therefore maps to a cutoff of ``d / 2``.
    Small values are a final polish (they refuse when the shipped pose is already the
    best fit inside that band — an honest "nothing to gain", not a failure); the
    ceiling is the winner pass's own cutoff, doubled.

    ``apply=False`` MEASURES ONLY: the refinement runs and the certification gates still
    judge it (a refusal is the same 409), but nothing on disk is touched — the operator
    sees what the move would be before committing to it. It is a preview, never a
    weaker gate: a candidate that cannot be adopted cannot be previewed as adoptable
    either."""

    matching_diameter_mm: float = _BEST_FIT_DEFAULT_DIAMETER_MM
    apply: bool = True

    @field_validator("matching_diameter_mm")
    @classmethod
    def _bounded_diameter(cls, v):
        if not np.isfinite(v) or not (_BEST_FIT_MIN_DIAMETER_MM <= v
                                      <= _BEST_FIT_MAX_DIAMETER_MM):
            raise ValueError(f"matching_diameter_mm must be between "
                             f"{_BEST_FIT_MIN_DIAMETER_MM} and "
                             f"{_BEST_FIT_MAX_DIAMETER_MM}mm, got {v!r}")
        return float(v)


def _append_best_fit_history(case_id: str, tooth: int, matching_diameter_mm: float,
                             outcome: str, move: Optional[dict] = None,
                             detail: Optional[str] = None,
                             clocking: Optional[dict] = None,
                             applied: bool = True,
                             kind: Optional[str] = None) -> None:
    """Same append-only provenance stream as the run/nudge/align histories — one JSON
    line per best-fit attempt, applied or refused, carrying the dial the operator set and
    the move it produced, so the geometry can be replayed. ``kind`` distinguishes the one
    refusal that is really a confirmation ("already_optimal", client ask 2026-07-26)
    without changing the outcome taxonomy — the pose was still not touched."""
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "case_id": case_id,
           "event": "best-fit", "tooth": tooth,
           "matching_diameter_mm": round(float(matching_diameter_mm), 3),
           "correspondence_cutoff_mm": round(float(matching_diameter_mm) / 2.0, 3),
           "move": move, "outcome": outcome, "applied": bool(applied)}
    if detail:
        rec["detail"] = detail
    if clocking:
        rec["clocking"] = clocking
    if kind:
        rec["kind"] = kind
    try:
        OUT.mkdir(parents=True, exist_ok=True)
        with (OUT / "run-history.jsonl").open("a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
    except OSError:
        pass  # history must never take down a request


def _refuse_best_fit(case_id: str, tooth: int, matching_diameter_mm: float, reason: str,
                     move: Optional[dict] = None, applied: bool = True):
    msg = (f"best-fit at a {matching_diameter_mm:.2f}mm matching diameter refused: "
           f"{reason}")
    _append_best_fit_history(case_id, tooth, matching_diameter_mm, outcome="refused",
                             move=move, detail=msg, applied=applied)
    raise HTTPException(409, msg)


def _pose_move(t_now: np.ndarray, cand: np.ndarray) -> dict:
    """How far a 6-DoF candidate moved the part: the ORIGIN shift in mm and the rotation
    angle in degrees — the two numbers an operator can judge (the trust region inside
    ``_refine_best_fit`` is stated in the same units)."""
    rel = cand[:3, :3] @ t_now[:3, :3].T
    angle = float(np.degrees(np.arccos(np.clip((np.trace(rel) - 1.0) / 2.0, -1.0, 1.0))))
    return {"translation_mm": round(float(np.linalg.norm(cand[:3, 3] - t_now[:3, 3])), 4),
            "rotation_deg": round(angle, 3)}


def _fit_residual(patch: np.ndarray, points: np.ndarray, cutoff: float) -> dict:
    """The fit's own support and residual at a pose: how many ROI scan points fall INSIDE
    the matching band of the posed part (``n_matched``), and the RMS/max of those matched
    distances. Points beyond the band are excluded on purpose — they are the surface the
    operator's matching diameter says not to fit to, and averaging them in would report a
    number about the crop rather than about the fit."""
    d = cKDTree(points).query(patch)[0]
    matched = d[d <= cutoff]
    return {"n_matched": int(matched.size),
            "rms_mm": (round(float(np.sqrt(np.mean(matched ** 2))), 4)
                       if matched.size else None),
            "max_mm": round(float(matched.max()), 4) if matched.size else None}


@app.post("/api/cases/{case_id}/sites/{tooth}/best-fit")
def best_fit(case_id: str, tooth: int, body: BestFitIn):
    pkg, implant_path, rec, template, frame, origin, L, t_now = \
        _load_rotation_site(case_id, tooth)
    diameter = float(body.matching_diameter_mm)
    cutoff = diameter / 2.0

    sig = template_signature(template)
    # the ROI is the pipeline's OWN auto-brush around the shipped pose (auto_flow's
    # _cap_patch_roi — a ball at rim height), not a fresh crop invented here: the
    # refinement must see the surface the winner pass fitted, or "the same refinement"
    # is a claim and not a fact
    patch = _cap_patch_roi(L, t_now[:2, 3], rim_radius_mm=float(sig.rmax))
    if patch is None:
        _refuse_best_fit(case_id, tooth, diameter,
                         "too little scan surface around the seated part to fit against")

    tv = np.asarray(template.vertices, float)
    if len(tv) > 4000:
        tv = tv[np.linspace(0, len(tv) - 1, 4000).astype(int)]

    def _fit_mean_mm(m: np.ndarray) -> float:
        """Mean scan-to-part distance over the ROI, read from the template's own
        VERTICES — a deterministic read-out of the same quantity ``_refine_best_fit``
        judges on its seeded surface samples (reported, never the adoption criterion)."""
        return float(cKDTree(tv @ m[:3, :3].T + m[:3, 3]).query(patch)[0].mean())

    state = np.random.get_state()
    reject_reasons: list = []
    try:
        np.random.seed(_BEST_FIT_SEED)
        cand = _refine_best_fit(patch, template, t_now, max_corr_dist=cutoff,
                                on_reject=reject_reasons.append)
    finally:
        np.random.set_state(state)
    if cand is None:
        # A None wears TWO faces and only one is a pass (review 2026-07-26). A
        # TRUST-REGION exit means ICP found only a different basin — nothing proved the
        # certified pose optimal in this band — so it refuses like every real refusal;
        # a green "already optimal" here would invite the wider search that makes the
        # basin escape MORE likely.
        if "trust-region" in reject_reasons:
            _refuse_best_fit(case_id, tooth, diameter,
                             "the refinement left the trust region (>1.2mm or >8° "
                             "from the certified seat) — a different basin, not a "
                             "refinement; try a TIGHTER matching diameter")
        # A CONFIRMATION, NOT A FAILURE (client ask 2026-07-26): "no strict improvement"
        # at this cutoff means the certified pose already IS the best fit in the band the
        # operator asked about. The status stays 409 (nothing changed, nothing to adopt)
        # but THIS branch alone carries a machine-readable detail so the UI can render a
        # pass with a one-click wider search — every other refusal in this file stays a
        # plain sentence, because every other refusal really is one.
        suggested = min(_BEST_FIT_MAX_DIAMETER_MM, 2.0 * diameter)
        if suggested > diameter:
            msg = (f"the certified pose is already the best fit within this matching "
                   f"diameter — nothing to correct at Ø{diameter:.2f}mm; widen to "
                   f"search further")
        else:
            # at the operator ceiling the doubled suggestion caps to the dial itself:
            # "widen" would be a lie and the UI's one-click widen re-ran the identical
            # search forever (review 2026-07-26) — say the band IS the widest instead
            msg = (f"the certified pose is already the best fit within this matching "
                   f"diameter — nothing to correct at Ø{diameter:.2f}mm, and this is "
                   f"the widest matching band the tool searches")
        _append_best_fit_history(case_id, tooth, diameter, outcome="refused",
                                 detail=msg, kind="already_optimal")
        raise HTTPException(409, {"kind": "already_optimal", "message": msg,
                                  "matching_diameter_mm": round(diameter, 3),
                                  "suggested_diameter_mm": round(suggested, 3)})
    move = _pose_move(t_now, cand)
    # THE GATES RUN EVEN FOR A PREVIEW: a candidate that cannot be adopted must not be
    # shown to the operator as adoptable either.
    _certification_gates(
        template, L, t_now, cand,
        lambda reason: _refuse_best_fit(case_id, tooth, diameter, reason, move=move,
                                        applied=body.apply))

    before, after = _fit_mean_mm(t_now), _fit_mean_mm(cand)
    fit = {"roi_mean_before_mm": round(before, 4), "roi_mean_after_mm": round(after, 4),
           "matching_diameter_mm": round(diameter, 3),
           "correspondence_cutoff_mm": round(cutoff, 3), **move,
           **_fit_residual(patch, tv @ cand[:3, :3].T + cand[:3, 3], cutoff),
           "rim_agreement_mm": None}
    anchor = _posed_rim_centre(template, cand)
    if anchor is not None:
        band = _rim_agreement_mm(
            L, anchor, float(np.percentile(np.linalg.norm(tv[:, :2], axis=1), 97)),
            template, cand)
        fit["rim_agreement_mm"] = round(band, 4) if band is not None else None

    if not body.apply:
        # MEASURE ONLY: judged, reported, and NOT written. The audit line records the
        # attempt like any other so a preview is never invisible in the provenance.
        _append_best_fit_history(case_id, tooth, diameter, outcome="measured", move=move,
                                 applied=False)
        return {"tooth": tooth, "applied": False, "best_fit": fit, "clocking": None,
                "nudge": {k: v for k, v in (rec.get("nudge") or {}).items()
                          if k != "base_pose_matrix"} or None,
                "files": [], **fit}

    # THE BASE POSE — the pipeline's own certified output, captured before the pose
    # fields are overwritten. A best-fit is NOT a clock nudge, so it adds no rotation
    # bookkeeping of its own; it must still ANCHOR the base pose, or a later ``reset``
    # would "restore" the best-fitted pose it was meant to undo.
    nudge_state = rec.get("nudge") or {}
    base_pose = np.asarray(nudge_state.get("base_pose_matrix") or rec["pose_matrix"],
                           float)
    cap_path = _reemit_site(pkg, case_id, tooth, rec, template, frame, origin, cand)
    rec["best_fit"] = fit
    rec["nudge"] = {**nudge_state, "base_pose_matrix": base_pose.tolist()}
    notch = _read_clock_at(L, template, t_now, cand)
    clocking = _update_run_row(case_id, tooth, notch, extra={"best_fit": fit})
    files = _finish_adjustment(
        pkg, case_id, tooth, implant_path, rec, template, L, cand, cap_path, "best-fit",
        f"best-fit at a {diameter:.2f}mm matching diameter: moved "
        f"{move['translation_mm']:.3f}mm / {move['rotation_deg']:.2f}°, ROI mean "
        f"{before:.3f} → {after:.3f}mm")
    _append_best_fit_history(case_id, tooth, diameter, outcome="applied", move=move,
                             clocking=clocking)
    return {"tooth": tooth, "applied": True, "best_fit": fit, "clocking": clocking,
            # the site's rotation bookkeeping as it stands, unchanged by this pass (the
            # base-pose matrix stays in the record; the wire carries the read-outs)
            "nudge": {k: v for k, v in rec["nudge"].items()
                      if k != "base_pose_matrix"} or None,
            "files": files,
            # the fit read-outs also ride FLAT at the top level — the numbers a UI shows
            # next to the dial, without reaching into a nested block
            **fit}


# --- DOCTOR CONFIRMATION at the verification panel ------------------------------------
# The doctor's manual sign-off on a site's alignment numbers (client ask 2026-07-23:
# "expose the verification data points so the doctor can manually confirm them"). A
# confirmation is a RECORDED HUMAN JUDGMENT layered on top of the pipeline's output —
# it NEVER changes a pose, a gate computation, or a shipped artifact. Re-confirming or
# retracting updates the record; every attempt lands in run-history.jsonl (the same
# append-only provenance stream as runs and nudges).

_CONFIRM_NOTE_MAX_CHARS = 500


class ConfirmAlignmentIn(BaseModel):
    """The doctor's sign-off: ``confirmed=True`` records it, ``confirmed=False``
    retracts it. The optional note is the doctor's own words, kept verbatim."""
    confirmed: bool
    note: Optional[str] = None

    @field_validator("note")
    @classmethod
    def _bounded_note(cls, v):
        if v is None:
            return v
        v = v.strip()
        if len(v) > _CONFIRM_NOTE_MAX_CHARS:
            raise ValueError(f"note is capped at {_CONFIRM_NOTE_MAX_CHARS} characters, "
                             f"got {len(v)}")
        return v or None


def _append_confirmation_history(case_id: str, tooth: int, confirmation: dict,
                                 acceptance_overall: Optional[str]) -> None:
    """One JSON line per confirm/retract, with the acceptance overall band AT THE TIME
    of the doctor's judgment — post-hoc analysis sees what the numbers said when the
    human signed."""
    rec = {"ts": confirmation["ts"], "case_id": case_id, "event": "confirm-alignment",
           "tooth": tooth, "confirmed": confirmation["confirmed"],
           "note": confirmation["note"], "acceptance_overall": acceptance_overall}
    try:
        OUT.mkdir(parents=True, exist_ok=True)
        with (OUT / "run-history.jsonl").open("a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
    except OSError:
        pass  # history must never take down a request


@app.post("/api/cases/{case_id}/sites/{tooth}/confirm-alignment")
def confirm_alignment(case_id: str, tooth: int, body: ConfirmAlignmentIn):
    _case(case_id)
    disk = OUT / case_id / "run.json"
    saved = None
    if disk.exists():
        try:
            saved = json.loads(disk.read_text())
        except (OSError, json.JSONDecodeError):
            saved = None
    if not saved:
        raise HTTPException(404, f"case {case_id!r} has no run result — run the "
                                 f"automation first")
    row = next((r for r in (saved.get("summary") or {}).get("sites") or []
                if r.get("tooth") == tooth), None)
    if row is None:
        raise HTTPException(404, f"tooth {tooth} has no aligned site in case "
                                 f"{case_id!r} — run the automation first")
    confirmation = {"confirmed": body.confirmed, "note": body.note,
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
    row["doctor_confirmation"] = confirmation
    try:
        disk.write_text(json.dumps(saved, default=str))
    except OSError:
        raise HTTPException(500, "could not persist the confirmation record")
    if saved.get("_key"):
        _cache[saved["_key"]] = saved
    # provenance carries what the acceptance numbers said at sign-off time (derived
    # read-out only — the confirmation itself never feeds back into any computation)
    overall = evaluate_acceptance(row)["overall"]["band"]
    _append_confirmation_history(case_id, tooth, confirmation, overall)
    return {"tooth": tooth, "doctor_confirmation": confirmation,
            "acceptance_overall": overall}
