"""The product's own case discovery: a scan folder with an STL is a case, full stop.

FIRST TRANCHE of the server.py lift (plan §3/AM-2 debt ledger). Supersedes, FOR THE
PRODUCT, server.py's ``_discover_cases`` + module-level ``CASES`` (lines 86-154) and the
row shape of ``GET /api/cases`` (lines 374-386). The demo keeps its own copy behind the
freeze — same rules, separately owned — so a product change here can never reach the
demo's data plane, and the demo's runbook stays valid word for word.

THE RULES, restated from first principles (client directive 2026-07-25: "the lab chooses,
the software never guesses"):

  - Discovery is ``<data_root>/scans/<folder>/*.stl``, EXTENSION CASE IGNORED. A folder
    with no STL is the ONLY thing that is not a case — a folder matching no library name
    is still a case (the patient-4471 regression: name-gated discovery silently dropped
    real uploads). If a folder holds several STLs the first by name is the case's scan
    and the rest are ignored; the product's worklist says so in as many words
    (apps/product domain/worklist.SCAN_ARRIVAL), because a silent half-import of a
    two-arch export is the failure a lab cannot see.
  - Everything else is a NON-BINDING suggestion the UI may preselect: ``suggested_model``
    (longest library-directory name found inside the folder name — "neodent-gm" must beat
    "neodent"), ``suggested_construction`` (the construction-catalog ``path_id`` of the
    name-matched vendor part), ``jaw`` (read off the scan filename), and the optional
    curated ``sites.json`` beside the scan. Any of them may be absent; the RUN acts only
    on the operator's explicit selection, which the BFF re-validates.
  - Discovery reads names and directory shape ONLY — no mesh is parsed, so a 20-scan
    morning's worklist appears instantly. Mesh loading/caching is a concern of whoever
    runs the physics, never of the read model.

Unlike the demo's mutable per-case cfg dict (which doubles as the server's response and
mesh cache), the product hands out FROZEN records: facts about the tree, safe to share
across requests and sessions.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from case_prep.adapters import construction_catalog

JAWS = ("upper", "lower")


@dataclass(frozen=True)
class CaseRecord:
    """One discovered case: identity + the scan + non-binding suggestions. Immutable —
    a read model hands out facts, not a cache."""

    id: str
    doctor: str
    jaw: str                                   # a SUGGESTION read off the scan filename
    scan: Path
    data_root: Path
    suggested_model: Optional[str]             # library-directory name, or None
    suggested_construction: Optional[str]      # construction-catalog path_id, or None
    suggested_sites: Tuple[dict, ...] = field(default_factory=tuple)


def _doctor_label(folder_name: str) -> str:
    """``doctor-neodent-gm`` -> ``Doctor Neodent GM`` — the demo's worklist label rule.

    ``removeprefix``, not ``replace``: see ``_case_id``. A folder called
    ``patient-doctor-4471`` reads back as written."""
    words = folder_name.removeprefix("doctor-").replace("-", " ").split()
    return "Doctor " + " ".join(w.upper() if len(w) <= 2 else w.capitalize() for w in words)


def _case_id(folder_name: str) -> str:
    """The case id is the DOCTOR folder minus a LEADING ``doctor-`` — not the model:
    several doctors can use the same implant system (demo regression: model-keyed cases
    replaced each other).

    2026-07-31: this was ``replace("doctor-", "", 1)``, which strips the first occurrence
    anywhere, so ``patient-doctor-4471`` became ``patient-4471``. The id keys
    ``reports/product/<case>/runs/…``, so the immutable run directory stopped carrying the
    folder's own name, and the worklist's scan-arrival panel — which tells operators a
    LEADING ``doctor-`` is stripped — predicted an id the system did not use."""
    return folder_name.removeprefix("doctor-") or folder_name


def discover_cases(data_root: Path) -> List[CaseRecord]:
    """Every case under ``<data_root>/scans``, sorted by folder name (deterministic
    worklist order). Cheap directory walk, deliberately uncached: a scan dropped in while
    the service runs must appear on the next read."""
    data = Path(data_root)
    caps_root = data / "library/caps"
    # longest name first so the most specific system wins the substring match
    models = (sorted((d.name for d in caps_root.iterdir() if d.is_dir()),
                     key=len, reverse=True) if caps_root.is_dir() else [])
    scans_root = data / "scans"
    cases: List[CaseRecord] = []
    if not scans_root.is_dir():
        return cases
    for folder in sorted(scans_root.iterdir()):
        if not folder.is_dir():
            continue
        # NOT ``folder.glob("*.stl")``: that glob is case-sensitive on POSIX, and a
        # scanner that exported ``UPPER_JAW.STL`` (routine) made the whole folder
        # invisible — no case, no row, no diagnostic (found 2026-07-31). Extension case
        # is an accident of the exporting tool, never a statement about the file.
        # Sorted case-insensitively so "the first STL by name", the rule the worklist
        # publishes to operators, means what someone reading the folder means by it;
        # the exact name breaks ties so the order is total and reload-stable.
        stls = sorted((p for p in folder.iterdir()
                       if p.is_file() and p.suffix.lower() == ".stl"),
                      key=lambda p: (p.name.lower(), p.name))
        if not stls:
            continue  # nothing to load — the ONLY reason a folder is not a case
        model = next((m for m in models if m in folder.name), None)
        construction_file = (next(iter((data / "library/construction")
                                       .glob(f"*/{model}-scanbody.stl")), None)
                             if model else None)
        suggested_construction = (
            construction_catalog.path_id_of(data, construction_file)
            if construction_file is not None else None)
        # One folder is one case, so one scan: the first by name wins and the rest are
        # ignored. Stated in the worklist's arrival panel rather than resolved silently —
        # the alternative (minting a case per STL) would split one patient's two arches
        # into two unrelated cases, which is a worse lie than the one the copy admits.
        scan = stls[0]
        jaw = "lower" if "lower" in scan.stem.lower() else "upper"
        sites_file = folder / "sites.json"
        suggested_sites = (tuple(json.loads(sites_file.read_text())["suggested_sites"])
                           if sites_file.exists() else ())
        cases.append(CaseRecord(
            id=_case_id(folder.name),
            doctor=_doctor_label(folder.name),
            jaw=jaw,
            scan=scan,
            data_root=data,
            suggested_model=model,
            suggested_construction=suggested_construction,
            suggested_sites=suggested_sites,
        ))
    return cases
