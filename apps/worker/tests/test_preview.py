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

import pytest

from case_prep.application.cases import CaseRecord, discover_cases
from case_prep.application.catalog import UnknownSelection
from case_prep.application.preview import (PreviewRefused, PreviewSelection,
                                           preview_site)

REAL = Path(__file__).resolve().parents[1] / "data" / "real"
real_only = pytest.mark.skipif(not (REAL / "library").is_dir(),
                               reason="real data tree not present")


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

    def test_nothing_persists_anywhere_a_later_read_could_find(self):
        # the demo kept OUT/<case>/preview; the product's preview is a pure derivation
        # (ledger row 7): its scratch directory dies inside the call, so no path under
        # the case's tree or the worker's reports can serve a stale preview later
        case = next(c for c in discover_cases(REAL) if c.id == "neodent-gm")
        before = sorted(p for p in case.scan.parent.rglob("*"))
        preview_site(case, _selection(), tooth=13)
        assert sorted(p for p in case.scan.parent.rglob("*")) == before
        assert not (REAL / "preview").exists()
