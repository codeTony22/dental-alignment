"""The vendor CONSTRUCTION-part catalog — every construction STL the lab can choose from.

Client directive 2026-07-25 ("the lab chooses, the software never guesses"): the construction
part used to be NAME-RESOLVED from the implant model (``library/construction/*/<model>-
scanbody.stl``) and a case whose folder name matched nothing was silently dropped. Name
matching is gone. This adapter lists what is ON DISK — every ``*.stl`` under
``<data>/library/construction/<vendor>/`` — and resolves the operator's chosen ``path_id``
back to a file. Nothing is inferred from a model, a doctor, or a folder name.

``path_id`` is ``<vendor>/<filename>`` — the catalog's own stable handle. Resolution is
membership-checked against the scan (never a path join on caller input), so a traversal or
an absolute path cannot escape the construction root.

Deterministic: sorted vendors, sorted filenames. Cheap (a directory walk, no mesh parsing),
so it is NOT cached — a construction part dropped in while the server runs must appear.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

CONSTRUCTION_SUBDIR = "library/construction"


def _label(vendor: str, stem: str) -> str:
    """Human-readable one-liner for the picker: ``atlantis — zimmer-4.5-scanbody``."""
    return f"{vendor} — {stem}"


def construction_entries(data_root: Path) -> List[dict]:
    """Every construction part on disk, as ``{vendor, filename, path_id, label}`` rows."""
    root = Path(data_root) / CONSTRUCTION_SUBDIR
    rows: List[dict] = []
    if not root.is_dir():
        return rows
    for vendor_dir in sorted((d for d in root.iterdir() if d.is_dir()),
                             key=lambda d: d.name):
        for stl in sorted(vendor_dir.glob("*.stl")):
            rows.append({
                "vendor": vendor_dir.name,
                "filename": stl.name,
                "path_id": f"{vendor_dir.name}/{stl.name}",
                "label": _label(vendor_dir.name, stl.stem),
            })
    return rows


def construction_index(data_root: Path) -> Dict[str, Path]:
    """``path_id`` -> absolute file, built from the same scan the listing serves."""
    root = Path(data_root) / CONSTRUCTION_SUBDIR
    return {row["path_id"]: root / row["vendor"] / row["filename"]
            for row in construction_entries(data_root)}


def resolve_construction(data_root: Path, path_id: str) -> Optional[Path]:
    """The file behind a chosen ``path_id``, or None for anything not in the catalog.
    Membership lookup only — caller input is never joined onto the root."""
    return construction_index(data_root).get(str(path_id))


def vendor_of(path_id: str) -> str:
    """The vendor segment of a ``path_id`` — the value the package records as ``vendor``."""
    return str(path_id).split("/", 1)[0]


def path_id_of(data_root: Path, path: Path) -> Optional[str]:
    """The ``path_id`` a known construction file is listed under, or None when the file
    does not sit in the catalog (used to express a name-matched DEFAULT SUGGESTION in the
    same handle the operator's explicit pick uses)."""
    target = Path(path).resolve()
    for pid, candidate in construction_index(data_root).items():
        if candidate.resolve() == target:
            return pid
    return None
