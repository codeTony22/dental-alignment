"""The FULL cross-model part-library catalog for the demo's library browser.

The per-case endpoints serve one model's caps for one doctor; the client's 2026-07-23 ask is
the whole shelf: "show me ALL of these caps, classified — even the superseded ones — and let
me choose neodent-gm or zimmer-4.5 in the UI." This scans ``<data>/library/caps/<model>/``
(current parts), every subdirectory inside a model dir (the ``superseded-YYYY-MM-DD/``
archives — flagged, never hidden), and any legacy ``*-library`` directory near ``library/``
(flagged ``legacy``, or ``unloadable`` when trimesh cannot read the file, again listed
rather than hidden). Those legacy directories are client-named; see adapters/client_data.py.

Flags are computed honestly from the bytes on disk: ``duplicate`` means this file's sha256
matches another catalog file — the counterpart is NAMED in ``duplicate_of`` (the known
finding this must surface: zimmer-4.5's 6020/6030 STLs are byte-identical to neodent-gm's).

The scan hashes every mesh file, so it runs once per process per data root (lru_cache);
ordering is deterministic (sorted directories, current-then-superseded within a model).
"""
from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

import trimesh

from case_prep.adapters.cap_library import _native_dims, parse_spec_filename

# entry id -> absolute file path, keyed per (model group, entry id) — the mesh endpoint's index
CatalogIndex = Dict[Tuple[str, str], Path]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _try_dims(path: Path) -> Optional[Tuple[float, float]]:
    """(rim diameter, height) in mm via the same native-frame measurement the per-case
    catalog uses (`_native_dims`), or None when the file cannot be read as a real mesh —
    the caller's honest ``unloadable`` signal, never an exception."""
    try:
        mesh = trimesh.load(path, force="mesh")
        vertices = getattr(mesh, "vertices", None)
        if vertices is None or len(vertices) < 3:
            return None
        return _native_dims(mesh)
    except BaseException:  # trimesh raises a zoo of types on garbage input
        return None


def _entry(model: str, path: Path, rel_name: str, base_flags: List[str]) -> dict:
    spec = parse_spec_filename(path.name)
    variant = spec.variant if spec is not None else path.stem
    label = spec.label if spec is not None else path.stem
    dims = _try_dims(path)
    flags = list(base_flags)
    if dims is None:
        # an unreadable legacy file is "unloadable", not "legacy" — list it, don't dress it up
        flags = [f for f in flags if f != "legacy"] + ["unloadable"]
    return {
        "variant": variant,
        "label": label,
        "rim_diameter_mm": round(dims[0], 2) if dims is not None else None,
        "height_mm": round(dims[1], 2) if dims is not None else None,
        "filename": rel_name,
        "sha256": _sha256(path),
        "flags": flags,
        "duplicate_of": [],
        "_path": str(path),  # stripped before serving; feeds the mesh-endpoint index
    }


def _entry_id(entry: dict, subdir: Optional[str], used: set) -> str:
    """A deterministic, unique-within-the-model id for the mesh URL: the plain variant for
    current parts (so /api/library/neodent-gm/6020/mesh reads naturally), ``<subdir>--<variant>``
    for archived ones, falling back to the sanitized relative filename on any collision."""
    candidate = entry["variant"] if subdir is None else f"{subdir}--{entry['variant']}"
    if candidate in used:
        candidate = entry["filename"].replace("/", "--").rsplit(".stl", 1)[0]
    used.add(candidate)
    return candidate


def _legacy_dirs(data_root: Path) -> List[Path]:
    """Legacy/superseded LIBRARY directories near caps/ — any ``*-library`` directory that is
    a sibling of ``library/`` (where the real legacy shelf sits) or inside it. The client owns
    those directory names; see adapters/client_data.py."""
    candidates = []
    for parent in (data_root, data_root / "library"):
        if parent.is_dir():
            candidates.extend(
                d for d in parent.iterdir() if d.is_dir() and d.name.endswith("-library"))
    return sorted(set(candidates), key=lambda d: d.name)


def _mark_duplicates(groups: List[dict], ids: Dict[int, Tuple[str, str]]) -> None:
    """Flag every entry whose bytes appear elsewhere in the catalog, naming the counterparts
    as ``model/id``. Flagging ALL members of a sha256 group keeps the read symmetric — the
    doctor sees the finding from whichever tab they are on."""
    by_sha: Dict[str, List[dict]] = {}
    for group in groups:
        for entry in group["variants"]:
            by_sha.setdefault(entry["sha256"], []).append(entry)
    for members in by_sha.values():
        if len(members) < 2:
            continue
        for entry in members:
            entry["flags"] = entry["flags"] + ["duplicate"]
            entry["duplicate_of"] = [
                "{}/{}".format(*ids[id(other)]) for other in members if other is not entry]


def build_catalog(data_root: Path) -> Tuple[List[dict], CatalogIndex]:
    """Scan the whole library once: (JSON-ready group list, (model, id) -> file index)."""
    groups: List[dict] = []
    caps_root = data_root / "library" / "caps"
    if caps_root.is_dir():
        for model_dir in sorted((d for d in caps_root.iterdir() if d.is_dir()),
                                key=lambda d: d.name):
            used: set = set()
            entries: List[Tuple[dict, str]] = []  # (entry, id)
            for stl in sorted(model_dir.glob("*.stl")):
                entry = _entry(model_dir.name, stl, stl.name, [])
                entries.append((entry, _entry_id(entry, None, used)))
            for subdir in sorted((d for d in model_dir.iterdir() if d.is_dir()),
                                 key=lambda d: d.name):
                for stl in sorted(subdir.glob("*.stl")):
                    entry = _entry(model_dir.name, stl, f"{subdir.name}/{stl.name}",
                                   ["superseded"])
                    entries.append((entry, _entry_id(entry, subdir.name, used)))
            if entries:
                groups.append({"model": model_dir.name, "legacy": False,
                               "_entries": entries})
    for legacy_dir in _legacy_dirs(data_root):
        used = set()
        entries = []
        for stl in sorted(legacy_dir.glob("*.stl")):
            entry = _entry(legacy_dir.name, stl, stl.name, ["legacy"])
            entries.append((entry, _entry_id(entry, None, used)))
        if entries:
            groups.append({"model": legacy_dir.name, "legacy": True, "_entries": entries})

    # ids assigned above are only known here — hand them to the duplicate pass by identity
    ids: Dict[int, Tuple[str, str]] = {}
    for group in groups:
        for entry, entry_id in group["_entries"]:
            ids[id(entry)] = (group["model"], entry_id)
        group["variants"] = [entry for entry, _ in group["_entries"]]
    _mark_duplicates(groups, ids)

    index: CatalogIndex = {}
    for group in groups:
        for entry, entry_id in group.pop("_entries"):
            index[(group["model"], entry_id)] = Path(entry.pop("_path"))
            entry["id"] = entry_id
            entry["mesh_url"] = "/api/library/{}/{}/mesh".format(
                quote(group["model"], safe=""), quote(entry_id, safe=""))
            # the SERVED thumbnail URL (client 2026-08-09: variant cards show the
            # part's top view) — composed here beside mesh_url for the same
            # reason: the UI follows served URLs, it never assembles library paths
            entry["top_url"] = "/api/library/{}/{}/top.png".format(
                quote(group["model"], safe=""), quote(entry_id, safe=""))
    return groups, index


@lru_cache(maxsize=8)
def _catalog(data_root_str: str) -> Tuple[List[dict], CatalogIndex]:
    return build_catalog(Path(data_root_str))


def catalog_groups(data_root: Path) -> List[dict]:
    """The cached, deterministic catalog for GET /api/library."""
    return _catalog(str(data_root))[0]


def catalog_mesh_path(data_root: Path, model: str, entry_id: str) -> Optional[Path]:
    """The STL behind one catalog entry, or None for anything not in the catalog."""
    return _catalog(str(data_root))[1].get((model, entry_id))
