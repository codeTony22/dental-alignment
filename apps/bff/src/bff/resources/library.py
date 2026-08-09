"""THE LIBRARY PART RESOURCE (plan §7 slice 5b) and THE CONSTRUCTION PART RESOURCE
(plan §10-M2): one catalog entry's STL, streamed for the Declare panes' pane 1 and the
Construction library page's part preview respectively.

Read-only, case-independent — the analogue of the case-scan stream, with the same
serving contract (model/stl FileResponse) so the viewer package treats both alike. The
detail payload's catalog rows already carry ``mesh_url`` pointing here (the worker's
catalog writes it), so the UI follows a served URL instead of assembling one.

Resolution is CATALOG MEMBERSHIP — for caps, through ``application.catalog.
require_variant`` (the model must be a real caps system and the variant one of ITS
catalog's entries, by the catalog's own id; archived parts serve one explicitly-named
id at a time); for construction parts, through ``application.catalog.
require_construction`` (the ``{vendor}/{filename}`` segments are reassembled into a
``path_id`` STRING and looked up in a dict — never joined onto a path). No caller
string is ever joined onto a path in either case (the traversal refusals live in the
catalog, one home). A miss is a 404 in the catalog's wording: the path names a part
that is not there — nothing about asking was malformed.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response

from case_prep.application.catalog import (UnknownSelection, require_construction,
                                           require_variant, variant_top_png)

from ..config import Settings

router = APIRouter(prefix="/api/library", tags=["library"])
constructions_router = APIRouter(prefix="/api/constructions", tags=["library"])


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


@router.get("/{model}/{variant}/top.png")
def library_top(model: str, variant: str, request: Request) -> Response:
    """The variant's top-view thumbnail (client 2026-08-09: the shelf cards show the
    part). Same membership door as the mesh route — ``variant_top_png`` resolves
    through ``require_variant`` and renders the catalog's own file; nothing here is
    a path. Cached per process behind the application layer."""
    settings: Settings = request.app.state.settings
    try:
        png = variant_top_png(settings.data_root, model, variant)
    except UnknownSelection as exc:
        raise HTTPException(404, str(exc))
    return Response(content=png, media_type="image/png")


@constructions_router.get("/{vendor}/{filename}/mesh")
def construction_mesh(vendor: str, filename: str, request: Request) -> FileResponse:
    settings: Settings = request.app.state.settings
    # the path_id is the catalog's own two-segment handle (<vendor>/<filename>) —
    # reassembled as a STRING KEY for the membership lookup, never a filesystem join
    path_id = f"{vendor}/{filename}"
    try:
        path = require_construction(settings.data_root, path_id)
    except UnknownSelection as exc:
        raise HTTPException(404, str(exc))
    return FileResponse(path, media_type="model/stl", filename=path.name)
