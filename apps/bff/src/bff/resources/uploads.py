"""THE BROWSER UPLOAD (§10-AB.3, client 2026-08-02 — retiring §10-O.6's honest
refusal now that a real write path is decided).

THE STORAGE POLICY, whole: this module writes exactly one thing —
``data_root/scans/<folder>/<filename>`` — the same tree ``discover_cases`` reads.
An uploaded case is therefore indistinguishable from a lab-copied one, on purpose:
the folder name is the case identity (id, doctor label, system suggestion), the
filename suggests the jaw, and nothing here opens the mesh — detection reports on
readability in its own words, exactly as it does for every other scan. The upload
appears on the next worklist read because discovery is uncached by design.

The one write relaxes ``config.Settings.data_root``'s read-only posture by exactly
this route and nothing else: no session is minted (the product data plane is
untouched until the case is first worked), no existing folder is ever written into
(one folder per case, and the first STL by name is the scan — appending a second
file would silently change which file that is), and a refused or failed upload
removes the folder it created rather than leaving a half-case for discovery to find.

Deliberately mounted at ``/api/uploads``, not under ``/api/case-sessions``: this
creates a case in the scan tree, it is not an action on a session, and its body is
raw STL bytes — no request model, no status-shaped field to allowlist. The bytes
stream to a temporary name and rename into place, with the size cap enforced
DURING the stream so a runaway body is refused without being held in memory.
"""
from __future__ import annotations

import re
import shutil
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from case_prep.application.cases import discover_cases

router = APIRouter(prefix="/api/uploads", tags=["uploads"])

# Generous against the fleet (the largest real scan is ~42 MB) while refusing
# runaways: nothing legitimate is close to this.
MAX_UPLOAD_BYTES = 256 * 1024 * 1024

# One safe-name rule for both segments: the characters discovery's own rules read
# (model-substring match, doctor- prefix, jaw-from-filename are all plain-text),
# no leading dot (hidden files), no separators (traversal is refused by shape,
# not by sanitising). Kept deliberately narrow — a name this rule refuses is a
# name the runbook's folder conventions never produce.
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


class UploadedCaseView(BaseModel):
    """The DISCOVERED case, read back through the same ``discover_cases`` the
    worklist uses — what the next read will actually say, never an echo of the
    request. Read-only response; there is no request model at all."""

    case_id: str
    folder: str
    scan_filename: str
    doctor: str
    jaw: str
    suggested_model: Optional[str]
    scan_bytes: int


def _refuse(status_code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail=detail)


@router.post("/scans/{folder}/{filename}", response_model=UploadedCaseView,
             status_code=201)
async def upload_scan(folder: str, filename: str,
                      request: Request) -> UploadedCaseView:
    settings = request.app.state.settings
    if not _SAFE_NAME.match(folder):
        raise _refuse(422, f"the folder name '{folder}' is not usable — letters, "
                           "digits, dot, dash and underscore only, starting with "
                           "a letter or digit")
    if not _SAFE_NAME.match(filename) or not filename.lower().endswith(".stl"):
        raise _refuse(422, f"the scan filename '{filename}' is not usable — the "
                           "upload takes one STL file (discovery reads STL and "
                           "nothing else; convert a .ply first)")

    scans_root = settings.data_root / "scans"
    target_dir = scans_root / folder
    if target_dir.exists():
        raise _refuse(409, f"the case folder '{folder}' already exists — one "
                           "folder per case, and an existing case's scan is "
                           "never overwritten. Pick a new folder name.")

    scans_root.mkdir(parents=True, exist_ok=True)
    target_dir.mkdir()
    tmp_path = target_dir / (filename + ".uploading")
    written = 0
    try:
        with tmp_path.open("wb") as sink:
            async for chunk in request.stream():
                written += len(chunk)
                if written > MAX_UPLOAD_BYTES:
                    raise _refuse(
                        413,
                        f"the upload exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)}"
                        " MB cap — no real scan on this fleet is close to that",
                    )
                sink.write(chunk)
        if written == 0:
            raise _refuse(422, "the upload's body is empty — send the STL file's "
                               "bytes as the request body")
        tmp_path.rename(target_dir / filename)
    except BaseException:
        # a refused or failed upload leaves no half-case behind for discovery
        shutil.rmtree(target_dir, ignore_errors=True)
        raise

    for case in discover_cases(settings.data_root):
        if case.scan.parent.name == folder:
            return UploadedCaseView(
                case_id=case.id,
                folder=folder,
                scan_filename=case.scan.name,
                doctor=case.doctor,
                jaw=case.jaw,
                suggested_model=case.suggested_model,
                scan_bytes=case.scan.stat().st_size,
            )
    # unreachable by construction (the folder now holds an STL), but stated
    # rather than silently returning something else
    raise _refuse(500, "the uploaded case did not appear in discovery — the scan "
                       "root may have moved underneath this service")
