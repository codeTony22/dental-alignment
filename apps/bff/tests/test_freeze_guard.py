"""THE FREEZE GUARD — slice 1's exit criterion (plan §3, grill AM-2).

The static half lives in test_boundaries (no forbidden import, no demo path literal).
This is the BEHAVIOURAL half: exercise every BFF endpoint against the REAL data tree and
prove the frozen demo's output directory is byte-identical before and after. path+size+
mtime is not enough — an in-place rewrite of a QC PNG (the demo server does exactly that
on its own paths) preserves all three, so files are CONTENT-hashed: sha256 for anything
under 1MB, path+size for the big meshes (a truncated-write regression still changes size;
a same-size in-place rewrite of a multi-MB STL is not a failure mode the BFF can produce
without also failing the import boundary).

Runs on the real tree (skips when absent) and takes real seconds: the detail resource
reads relief ceilings for every declared variant, which probes the actual vendor parts
(warm-cached in-process thereafter).
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bff.config import default_settings
from bff.main import create_app

REPO = Path(__file__).resolve().parents[3]
# the literal is legitimate HERE: the static boundary test forbids it in src/ (the code
# that could act on it), while this test exists precisely to watch that directory
FROZEN_OUT = REPO / "apps" / "worker" / "reports" / "live-demo"
_HASH_CAP_BYTES = 1_000_000


def _snapshot(root: Path):
    entries = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        size = path.stat().st_size
        digest = (hashlib.sha256(path.read_bytes()).hexdigest()
                  if size < _HASH_CAP_BYTES else None)
        entries.append((str(path.relative_to(root)), size, digest))
    return entries


@pytest.mark.skipif(not FROZEN_OUT.is_dir() or not default_settings().data_root.is_dir(),
                    reason="frozen demo output / real data tree not present")
def test_every_bff_endpoint_leaves_the_frozen_demo_byte_identical():
    before = _snapshot(FROZEN_OUT)
    assert before, "an empty snapshot would prove nothing"

    client = TestClient(create_app())  # the real defaults: the same tree the demo serves
    assert client.get("/health").json()["ok"] is True
    rows = client.get("/api/case-sessions").json()
    assert rows, "the real tree has cases; an empty worklist would prove nothing"
    for row in rows:
        detail = client.get(f"/api/case-sessions/{row['id']}")
        assert detail.status_code == 200, detail.text
    assert client.get("/api/case-sessions/no-such-case").status_code == 404

    assert _snapshot(FROZEN_OUT) == before
