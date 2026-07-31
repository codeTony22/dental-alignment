"""THE PRE-RUN PREVIEW FOR THE PRODUCT'S DECLARE — case_prep.application.preview.

Plan §4 Declare / §7 slice 5b: the three live panes need the union pane's colouring
BEFORE any run exists. This module is the next tranche of the server.py lift (copy-debt
ledger row 7): the demo's ``_deviation_payload`` + ``preview_site_alignment``
(server.py:1068-1156, 1176-1257), restated as a pure derivation over
``case_prep.pipeline``/``adapters`` — no HTTP types, no serve-time cache, no persistent
preview directory (a scratch dir lives and dies inside the call). Refusals raise; the
BFF owns the transport.

Synthetic tests pin the REFUSALS (they fire before any mesh is parsed — milliseconds).
The full seat needs a real scan and library and is real-tree + slow-marked, exactly like
detection's own end-to-end walk. The PAYLOAD SHAPE is pinned there against the demo's
field list VERBATIM: the product's copied deviationColormap/pane code renders this dict,
and a silently divergent key would be a blank pane, not a type error.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from case_prep.application.adjust import load_site, site_clicks
from case_prep.application.cases import CaseRecord, discover_cases
from case_prep.application.catalog import UnknownSelection
from case_prep.application.preview import (PreviewRefused, PreviewSelection,
                                           measured_rim_centre_world, preview_site)
from case_prep.domain.clock_signature import canon_point_to_world, template_signature
from case_prep.domain.part_features import MIN_LEVER_ARM_MM

REAL = Path(__file__).resolve().parents[1] / "data" / "real"
real_only = pytest.mark.skipif(not (REAL / "library").is_dir(),
                               reason="real data tree not present")

# a private, already-shipped run (test_adjust.py's own warmed fixture): reading its
# scan/pose/template needs no ICP, no detection, no `run_auto_case` pass — just the
# bytes already on disk — so the cross-check below is fast even though it exercises
# real fleet geometry, not a synthetic identity.
PRODUCT = Path(__file__).resolve().parents[1] / "reports" / "product"
WARMED_CASE = "295811960-neodent-gm"
WARMED_RUN = PRODUCT / WARMED_CASE / "runs" / "20260728-224101-47bb54"
WARMED_TOOTH = 29
warmed_only = pytest.mark.skipif(
    not (REAL / "library").is_dir() or not WARMED_RUN.is_dir(),
    reason="real data tree / warmed product run not present")


def _case(tmp_path: Path, sites=()) -> CaseRecord:
    return CaseRecord(
        id="case-x", doctor="Doctor X", jaw="upper",
        scan=tmp_path / "scan.stl", data_root=tmp_path,
        suggested_model=None, suggested_construction=None,
        suggested_sites=tuple(sites))


def _selection(**overrides) -> PreviewSelection:
    values = dict(model="neodent-gm",
                  construction_path="dess/neodent-gm-scanbody.stl",
                  variant="5020", jaw=None, gingival_offset_mm=0.2)
    values.update(overrides)
    return PreviewSelection(**values)


class TestRefusals:
    """Each refusal fires in order, BEFORE the multi-second physics it precedes —
    asking about an impossible preview must never cost a mesh parse."""

    def test_a_tooth_the_case_has_no_site_for_refuses(self, tmp_path):
        case = _case(tmp_path, sites=[{"tooth": 4, "center": [0.0, 0.0, 0.0]}])
        with pytest.raises(PreviewRefused) as exc:
            preview_site(case, _selection(), tooth=31)
        assert "tooth 31" in str(exc.value)

    def test_a_site_without_a_centre_refuses(self, tmp_path):
        case = _case(tmp_path, sites=[{"tooth": 4, "center": None}])
        with pytest.raises(PreviewRefused) as exc:
            preview_site(case, _selection(), tooth=4)
        assert "tooth 4" in str(exc.value)

    def test_an_unknown_model_refuses_in_catalog_words(self, tmp_path):
        # the membership rule is catalog.py's (_library_for) — judged on directory
        # names before the scan is ever parsed, so this refusal is instant
        (tmp_path / "library/caps").mkdir(parents=True)
        case = _case(tmp_path, sites=[{"tooth": 4, "center": [0.0, 0.0, 0.0]}])
        with pytest.raises(UnknownSelection) as exc:
            preview_site(case, _selection(model="no-such-system"), tooth=4)
        assert "unknown implant system" in str(exc.value)


@real_only
@pytest.mark.slow  # parses the real scan + library and seats one site end to end
class TestPreviewOnTheRealTree:
    def test_the_payload_is_the_demos_shape_exactly(self):
        case = next(c for c in discover_cases(REAL) if c.id == "neodent-gm")
        payload = preview_site(case, _selection(), tooth=13)
        # THE WIRE CONTRACT: the demo's _deviation_payload keys plus the preview
        # endpoint's "seat" block — identical, because the copied deviationColormap/
        # pane-framing code was written against exactly this dict
        assert set(payload) == {
            "case_id", "tooth", "implant_model", "variant", "frame", "units",
            "pose", "n_points", "points", "faces", "deviation_mm", "scale",
            "stats", "vertex_footprint_points", "reporting_only", "preview", "seat",
            "clock_reference",
        }
        assert payload["case_id"] == "neodent-gm"
        assert payload["tooth"] == 13
        assert payload["variant"] == "5020"
        assert payload["units"] == "mm"
        assert payload["preview"] is True
        assert payload["reporting_only"] is True
        # the pose block is what the panes FRAME with (the exact-axis story)
        assert set(payload["pose"]) == {"axis", "x_axis", "origin"}
        assert all(len(payload["pose"][k]) == 3 for k in payload["pose"])
        # a renderable mesh with one signed millimetre (or None) per point
        assert payload["n_points"] == len(payload["points"]) == len(payload["deviation_mm"])
        assert payload["n_points"] > 0
        assert len(payload["faces"]) > 0
        assert set(payload["scale"]) == {
            "clamp_mm", "min_mm", "max_mm", "colormap", "sign_convention",
            "data_min_mm", "data_max_mm", "footprint_band_mm",
        }
        assert set(payload["stats"]) == {"rms_mm", "p90_mm", "n_footprint",
                                         "n_samples", "source"}
        assert payload["stats"]["rms_mm"] is not None
        assert set(payload["seat"]) == {"seat_method", "rim_agreement_mm", "fit"}
        assert payload["seat"]["seat_method"] is not None
        # plan §10-F: the scan-side lever guard's own reference, beside the pose —
        # Declare carries the same field Adjust's seated payload does (test_adjust.py)
        assert set(payload["clock_reference"]) == {"rim_centre", "min_lever_mm"}
        assert len(payload["clock_reference"]["rim_centre"]) == 3
        assert payload["clock_reference"]["min_lever_mm"] == MIN_LEVER_ARM_MM

    def test_nothing_persists_anywhere_a_later_read_could_find(self):
        # the demo kept OUT/<case>/preview; the product's preview is a pure derivation
        # (ledger row 7): its scratch directory dies inside the call, so no path under
        # the case's tree or the worker's reports can serve a stale preview later
        case = next(c for c in discover_cases(REAL) if c.id == "neodent-gm")
        before = sorted(p for p in case.scan.parent.rglob("*"))
        preview_site(case, _selection(), tooth=13)
        assert sorted(p for p in case.scan.parent.rglob("*")) == before
        assert not (REAL / "preview").exists()


@warmed_only
@pytest.mark.slow
class TestMeasuredRimCentreAgreesWithAdjust:
    """plan §10-F: ``measured_rim_centre_world`` exists because a PRE-RUN preview has
    no shipped record to build ``application.adjust``'s cached ``SiteContext`` from —
    it rebuilds the crowns-local frame fresh instead of reusing one. That is only
    safe if the fresh rebuild reads the IDENTICAL point ``adjust.site_clicks`` does
    for the same scan and pose; a frame mismatch here would be invisible in either
    module alone (both would look internally consistent) and would only surface as
    Declare and Adjust silently disagreeing about where an operator's mark sits
    relative to the guard's own bound.

    Proved on the warmed run's REAL scan and REAL shipped pose (not a synthetic
    identity transform, which cannot exercise ``_crowns_frame``'s actual PCA/normal
    read on real mesh noise) by calling the two INDEPENDENT code paths — this
    module's fresh reconstruction and ``adjust``'s cached-context read — over the
    exact same bytes and comparing the result."""

    def test_the_fresh_reconstruction_matches_the_cached_sitecontext_read(self):
        case = next(c for c in discover_cases(REAL) if c.id == WARMED_CASE)
        ctx = load_site(case, WARMED_RUN, WARMED_TOOTH)

        # the ADJUST path: the frame cached on SiteContext at load_site time
        sig = template_signature(ctx.template)
        clicks = site_clicks(ctx, sig)
        pose_world = np.asarray(ctx.record["pose_matrix"], float)
        adjust_side = canon_point_to_world(clicks.rim_centre_xy, sig.ztop, pose_world)

        # the PREVIEW path: no SiteContext at all — rebuilt from the scan and the
        # pose alone, exactly what a pre-run preview has
        preview_side = measured_rim_centre_world(
            ctx.scan_points, _scan_normals_for(case), pose_world, ctx.template)

        assert preview_side == pytest.approx(adjust_side.tolist(), abs=1e-6)


def _scan_normals_for(case: CaseRecord) -> np.ndarray:
    """The same normals ``load_site`` reads (``_scan_mesh(case.scan).vertex_normals``)
    — a tiny local import to avoid reaching into ``application.detection``'s private
    ``_scan_mesh`` from the test module's top level for what is otherwise a one-line
    need."""
    from case_prep.application.detection import _scan_mesh
    return np.asarray(_scan_mesh(case.scan).vertex_normals, float)
