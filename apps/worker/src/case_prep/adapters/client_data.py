"""THE CLIENT'S OWN DATA DROP — the only place this project spells their file names.

These are the real names of real bytes under ``data/real/`` (gitignored; present only on a
machine that has the drop). They are reproduced verbatim because they ADDRESS FILES: renaming
them here would simply fail to open, and renaming them on disk is the client's call, not ours —
it would orphan every drop already delivered and every archived report that points at one.

TRADEMARK NOTE (client directive 2026-07-25). Their vendor's product name is a registered mark
and must not appear in our product. Confining it to this module is how that is satisfied without
breaking their data: nothing else in the codebase types these strings, and NOTHING PRINTS THEM
IN THE INTERFACE — a legacy shelf is displayed under a neutral label
(``web/src/domain/librarySelection.catalogGroupLabels``), never under its folder name.

Every path is resolved lazily against the worker root, and callers are expected to skip (tests)
or refuse with a clear message (tools) when a file is absent.
"""
from __future__ import annotations

from pathlib import Path

# apps/worker/ — this file is src/case_prep/adapters/client_data.py
WORKER_ROOT = Path(__file__).resolve().parents[3]
DATA_REAL = WORKER_ROOT / "data" / "real"

# The legacy parts shelf: a pre-existing vendor library the client dropped alongside the
# current per-model shelves. Listed by the catalog as a `legacy` group, never selectable.
LEGACY_SHELF_DIR = DATA_REAL / "encode-library"
LEGACY_SHELF_CAD = LEGACY_SHELF_DIR / "encode_master.stl"

# The DG Code test case: the client's real upper-jaw scan, the scan body segmented out of it,
# and the final-scan variant.
DG_CASE_DIR = DATA_REAL / "dg-code-test"
DG_ARCH = DG_CASE_DIR / "Encode -Certain3i-4_1 AbutmentAlignmentScan-orig-upperjaw.stl"
DG_SCANBODY = DG_CASE_DIR / "Encode -Certain3i-4_1 -AbutmentAlignmentScanbody-upperjaw.stl"

#: Human-facing name for the drop — safe to print, unlike the paths above.
DG_CASE_LABEL = "DG Code / Certain 3i"
LEGACY_SHELF_LABEL = "legacy shelf"
