"""THE LIBRARY PART RESOURCE (plan §7 slice 5b): one catalog entry's STL, streamed for
the Declare panes' pane 1.

Read-only, case-independent — the analogue of the case-scan stream, with the same
serving contract (model/stl FileResponse) so the viewer package treats both alike. The
detail payload's catalog rows already carry ``mesh_url`` pointing here (the worker's
catalog writes it), so the UI follows a served URL instead of assembling one.

Resolution is CATALOG MEMBERSHIP through ``application.catalog.require_variant`` — the
model must be a real caps system and the variant one of ITS catalog's entries, by the
catalog's own id; archived parts serve one explicitly-named id at a time and no caller
string is ever joined onto a path (the traversal refusals live in the catalog, one
home). A miss is a 404 in the catalog's wording: the path names a part that is not
there — nothing about asking was malformed.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from case_prep.application.catalog import UnknownSelection, require_variant

from ..config import Settings

router = APIRouter(prefix="/api/library", tags=["library"])


@router.get("/{model}/{variant}/mesh")
def library_mesh(model: str, variant: str, request: Request) -> FileResponse:
    settings: Settings = request.app.state.settings
    try:
        path = require_variant(settings.data_root, model, variant)
    except UnknownSelection as exc:
        raise HTTPException(404, str(exc))
    # "model/stl" for the same reason the scan stream states it: FileResponse would
    # otherwise guess application/octet-stream, which tells the viewer nothing.
    return FileResponse(path, media_type="model/stl", filename=path.name)
