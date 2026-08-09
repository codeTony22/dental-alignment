"""Catalog reads for the product: library groups, construction parts, the relief ceiling.

SECOND TRANCHE of the server.py lift (plan §3/AM-2 debt ledger). Supersedes, FOR THE
PRODUCT: ``GET /api/constructions`` (server.py:389-394), ``GET /api/library`` (518-525),
and the relief-ceiling read behind ``GET /api/relief-limit`` (397-470) together with the
membership-checked library loader ``_library_for`` (287-334). The demo keeps its own copies
behind the freeze.

Plain functions over ``case_prep.adapters`` + ``domain`` + ``pipeline.final_product`` —
no HTTP types, no endpoint state. Refusals are ``UnknownSelection`` (a LookupError): the
caller (the BFF) owns turning a refused selection into a 422 sentence; this layer owns
REFUSING it. The membership rules are the demo's, kept verbatim in spirit:

  - a construction part resolves by catalog MEMBERSHIP, never a path join on caller input
    (adapters/construction_catalog — the traversal refusal lives there);
  - an implant system must be a top-level directory NAME under ``library/caps`` (measured
    2026-07-25: joining caller input let ``zimmer-4.5/superseded-...`` load a whole archive
    and ``../caps/...`` ship a traversal string as the paid record's audit key);
  - an archived variant enters only because a human NAMED it — resolved through the full
    catalog (adapters/library_catalog) and handed to ``CapLibrary.load`` as an EXPLICIT
    extra part, never by widening a glob.

The relief ceiling itself is ``pipeline.final_product.max_safe_gingival_offset`` — a pure
measurement (0.5-1.3s cold per pair, a dict lookup warm; its bench cache is shared with
the run path, so a ceiling asked here also warms the run that follows).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

import numpy as np
import trimesh

from case_prep.adapters import construction_catalog, library_catalog
from case_prep.adapters.cap_library import CapLibrary, parse_spec_filename
from case_prep.domain import design_rules
from case_prep.domain.channel import channel_from_boundary_loops
from case_prep.pipeline.final_product import (DEFAULT_GINGIVAL_OFFSET_MM,
                                              max_safe_gingival_offset)


class UnknownSelection(LookupError):
    """A selection naming something the catalog does not carry. The message is the whole
    payload — one human sentence the BFF can serve verbatim as its 422 detail."""


def library_groups(data_root: Path) -> List[dict]:
    """The FULL cross-model part catalog (current + superseded + legacy, honestly
    flagged) — the read behind the product's system/variant pickers."""
    return library_catalog.catalog_groups(Path(data_root))


def construction_parts(data_root: Path) -> List[dict]:
    """Every vendor construction part on disk, as ``{vendor, filename, path_id, label,
    mesh_url}`` rows; the operator picks by ``path_id`` and the run uses exactly that
    file.

    ``mesh_url`` is added HERE, not in the shared adapter: ``construction_entries`` is
    served verbatim by the frozen demo's ``GET /api/constructions`` (server.py:394),
    which has no mesh route to honour the URL. The product's BFF does
    (``GET /api/constructions/{vendor}/{filename}/mesh``), so this product-only wrapper
    is where the row gains it — the same split ``library_catalog``'s cap rows already
    draw between the catalog build and its served ``mesh_url``."""
    return [{**row,
            "mesh_url": "/api/constructions/{}/{}/mesh".format(
                quote(row["vendor"], safe=""), quote(row["filename"], safe=""))}
           for row in construction_catalog.construction_entries(Path(data_root))]


def require_construction(data_root: Path, construction_path: str) -> Path:
    """The construction part's file, by catalog MEMBERSHIP — never a path join on caller
    input (the traversal refusal lives in adapters/construction_catalog; joining caller
    input is the measured 2026-07-25 escape). Raises ``UnknownSelection`` in the one
    sentence the BFF serves verbatim — the same refusal ``relief_ceiling`` gives, now
    with a single home so Intake's choices validation cannot drift from it."""
    resolved = construction_catalog.resolve_construction(Path(data_root), construction_path)
    if resolved is None:
        raise UnknownSelection(f"unknown construction part {construction_path!r} — pick "
                               f"one of the catalog's parts")
    return resolved


def require_library_model(data_root: Path, model: str) -> None:
    """Refuse any implant SYSTEM that is not a top-level directory NAME under
    ``library/caps`` — the demo's ``_library_for`` membership rule (its first check,
    same sentence), split out so slice 5a's system declaration can ask WITHOUT loading
    a single mesh: declaring a system happens before any physics is wanted, and a
    directory-name check keeps the traversal refusal (a name carries no separator)
    while costing one ``iterdir``. Legacy ``*-library`` shelves are honestly LISTED by
    the catalog but are not caps models — a run could never load one as a system."""
    caps_root = Path(data_root) / "library/caps"
    known = ({d.name for d in caps_root.iterdir() if d.is_dir()}
             if caps_root.is_dir() else set())
    if model not in known:
        raise UnknownSelection(f"unknown implant system {model!r} — pick one of the "
                               f"systems the library catalog lists")


def require_variant(data_root: Path, model: str, variant: str) -> Path:
    """Refuse any variant that is not an entry of the named system's catalog — by the
    catalog's own entry id (adapters/library_catalog), so archived parts stay
    declarable exactly one explicit name at a time and nothing resolves by glob or
    path join. Judges the MODEL first (same door as ``require_library_model``): a
    legacy shelf's entries must not slip in under a model name no run could load.
    Returns the entry's mesh file (same contract as ``require_construction``) so the
    BFF's part-mesh endpoint (slice 5b, pane 1) serves exactly the catalog's file —
    never a path assembled from caller input."""
    data = Path(data_root)
    require_library_model(data, model)
    path = library_catalog.catalog_mesh_path(data, model, variant)
    if path is None:
        raise UnknownSelection(f"{variant!r} is not a part of the {model!r} library "
                               f"— pick a variant the library catalog lists")
    return path


@lru_cache(maxsize=96)
def _variant_canonical_stl_cached(path_str: str) -> bytes:
    """The canonicalized template's STL bytes — cached per resolved catalog file
    (the catalog is immutable per deploy). ``canonicalize_revolute`` is the SAME
    door ``CapLibrary`` loads every template through, applied to the file
    ``require_variant`` resolved — so archived ids canonicalize exactly like
    current ones, by the file the catalog names."""
    from case_prep.adapters.ingest import canonicalize_revolute

    mesh = trimesh.load_mesh(path_str)
    local, _ = canonicalize_revolute(mesh)
    return local.export(file_type="stl")


def variant_canonical_stl(data_root: Path, model: str, variant: str) -> bytes:
    """One catalog cap as CANONICAL STL bytes — the frame every other actor speaks.

    THE FRAME DEFECT THIS CLOSES (measured 2026-08-09): the mesh endpoint used to
    stream the vendor file VERBATIM, but the worker's pair fold reads part clicks
    as canonical, and raw→canonical is a per-part translation of 0.21-0.59mm in xy
    and 2.3-4.7mm in z across the catalog. Every click on pane 1's part was
    therefore recorded in the wrong frame: ghosts and auto-mark landmarks drew
    2.4-4.8mm off the features (the client's "the tool doesn't mark the proper
    holes", literally), and the parallax injected up to ±22° of clock error on
    some variants. Serving the canonical mesh makes pane 1's clicks, the fold,
    the ghosts and the landmarks ONE frame — the run's own.

    Resolution stays catalog membership: ``require_variant`` first (the 404
    wording), then the same ``_library_for``/``template`` door the run loads
    through — never a re-derived canonicalization."""
    path = require_variant(Path(data_root), model, variant)
    return _variant_canonical_stl_cached(str(path))


@lru_cache(maxsize=96)
def _variant_top_png_cached(path_str: str) -> bytes:
    """The rendered bytes behind ``variant_top_png``, keyed on the resolved catalog
    file — the catalog is immutable per deploy, so one render per part per process."""
    import io

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection

    mesh = trimesh.load_mesh(path_str)
    tris = np.asarray(mesh.triangles, float)
    normals = np.asarray(mesh.face_normals, float)
    # painter's algorithm straight down the canonical +z (the occlusal face — the
    # view the client's comp shows): farthest faces first, top faces last
    order = np.argsort(tris[:, :, 2].mean(axis=1))
    tris = tris[order]
    normals = normals[order]
    light = np.array([0.35, -0.3, 0.9])
    light /= np.linalg.norm(light)
    lam = np.clip(normals @ light, 0.15, 1.0)
    # the viewer's own healing-cap green (packages/viewer palette `cap: 0x2fa75f`)
    base = np.array([0x2F, 0xA7, 0x5F], float) / 255.0
    cols = np.clip(base[None, :] * (0.35 + 0.75 * lam[:, None]), 0, 1)
    fig, ax = plt.subplots(figsize=(3.0, 3.0), dpi=110)
    ax.add_collection(PolyCollection(tris[:, :, :2], facecolors=cols,
                                     edgecolors="none"))
    r = float(np.abs(tris[:, :, :2]).max()) * 1.06
    ax.set_xlim(-r, r)
    ax.set_ylim(-r, r)
    ax.set_aspect("equal")
    ax.set_axis_off()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", transparent=True,
                bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)
    return buf.getvalue()


def variant_top_png(data_root: Path, model: str, variant: str) -> bytes:
    """A top-view render of one catalog cap (client 2026-08-09: the variant cards
    should show the part "like the panes do" — a PNG of the library top). Resolution
    is catalog membership through ``require_variant``, exactly the mesh endpoint's
    door; the render is the canonical occlusal view in the viewer's cap green."""
    path = require_variant(Path(data_root), model, variant)
    return _variant_top_png_cached(str(path))


@lru_cache(maxsize=16)
def _construction_mesh(path_str: str) -> trimesh.Trimesh:
    """The vendor part's mesh, parsed once per process (multi-MB CAD files)."""
    return trimesh.load(path_str, force="mesh")


@lru_cache(maxsize=16)
def _library(data_root_str: str, model: str,
             extra_items: Tuple[Tuple[str, str], ...]) -> CapLibrary:
    """The chosen system's cap library, cached per (tree, model, explicitly-named extras).
    Cache key is strings/tuples only so lru_cache can hold it."""
    caps_dir = Path(data_root_str) / "library/caps" / model
    extra = {variant: Path(p) for variant, p in extra_items}
    return CapLibrary.load(caps_dir, extra=extra or None)


def _library_for(data_root: Path, model: str,
                 variants: Optional[List[str]] = None) -> CapLibrary:
    """Membership-checked library load (the demo's ``_library_for`` rule, lifted).
    A directory NAME carries no separator, so membership refuses both the archive
    traversal and the ``../`` escape; archived variants resolve through the full catalog
    one explicitly-named part at a time."""
    data = Path(data_root)
    caps_root = data / "library/caps"
    known = ({d.name for d in caps_root.iterdir() if d.is_dir()}
             if caps_root.is_dir() else set())
    if model not in known:
        raise UnknownSelection(f"unknown implant system {model!r} — pick one of the "
                               f"systems the library catalog lists")
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
            raise UnknownSelection(f"{variant!r} is not a part of the {model!r} library "
                                   f"— pick a variant the library catalog lists")
        extra[variant] = path
    try:
        return _library(str(data), model, tuple(sorted((v, str(p)) for v, p in extra.items())))
    except ValueError as exc:
        raise UnknownSelection(f"the {model!r} cap library could not be loaded: {exc}")


def relief_ceiling(data_root: Path, construction_path: str, model: str,
                   variant: str) -> dict:
    """The maximum gingival relief a (construction part x cap variant) pair can be cut
    with and still pass the export gate — asked BEFORE any work is invested (the demo's
    ``GET /api/relief-limit`` read, lifted; the numbers all come from
    ``max_safe_gingival_offset``, this function only assembles them).

    Pure measurement: nothing is emitted, nothing is written. The dict is JSON-ready so
    the BFF can shape it per response without re-touching physics."""
    data = Path(data_root)
    construction_file = require_construction(data, construction_path)
    library = _library_for(data, model, [variant])
    spec = next((s for s in library.specs if s.variant == variant), None)
    if spec is None:
        raise UnknownSelection(f"{variant!r} is not a part of the {model!r} library — "
                               f"pick a variant the library catalog lists")
    channel = channel_from_boundary_loops(library.template(spec))
    limit = max_safe_gingival_offset(_construction_mesh(str(construction_file)),
                                     library_channel=channel,
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
        "note": limit.note,
    }
