"""THE RELIEF CEILING — the maximum safe gingival offset, answered BEFORE the run.

THE CLIENT'S ESCALATION (2026-07-25): "the 0.20mm gingival relief ate the screw channel of
tooth 3 (atlantis/neodent-gm 5030) ... package NOT emitted — END-TO-END AUTOMATION MUST
COMPLETE." The thin-wall export block that produced that message is CORRECT and this suite
does not weaken it (its own tests live in test_output_package.TestGingivalReliefBlock and
still pass unchanged). What this suite pins is the three things built around it:

  1. the ceiling is MEASURABLE for a (construction part x cap variant) pair, cheaply
     enough to answer at selection time;
  2. ``GET /api/relief-limit`` puts that number in front of the operator BEFORE Process;
  3. a run whose requested relief exceeds the ceiling COMPLETES at the ceiling and says so
     in the response, every site row, the package audit and the manifest — refused as
     asked, completed at the safe value, stated everywhere. Never a silent substitution.

MEASURED RECEIPTS, the whole real catalog (2 construction parts x 12 caps = 24 pairs) at
the client's 0.20mm default — 15 of 24 cannot take it:

  atlantis/zimmer-4.5-scanbody   every cap ceilings at 0.06-0.15mm
                                 (neodent-gm 5030 -> 0.06, the client's own tooth-3 case;
                                  wall 0.028mm at zero relief)
  dess/neodent-gm-scanbody       the CAP decides: 5020 -> 0.05, 5030 -> 0.09,
                                 zimmer 8020 -> 0.05, but 4020/4030 -> 0.50 (nothing broke
                                 up to the search ceiling) and 6020/6030 -> 0.43/0.47

The driver is CAP SIZE, not vendor — which is why the answer has to be per PAIR and cannot
be a per-vendor constant.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import trimesh
from fastapi.testclient import TestClient

from case_prep.domain import design_rules
from case_prep.domain.channel import ChannelGeometry
from case_prep.pipeline.final_product import (DEFAULT_GINGIVAL_OFFSET_MM,
                                              LIMITED_BY_CHANNEL, LIMITED_BY_NONE,
                                              LIMITED_BY_SEAL, LIMITED_BY_WALL,
                                              MAX_GINGIVAL_SEARCH_MM, _limit_reason,
                                              clear_relief_cache,
                                              max_safe_gingival_offset,
                                              resolve_gingival_offset)

REAL = Path(__file__).resolve().parents[1] / "data" / "real"
ATLANTIS = "atlantis/zimmer-4.5-scanbody.stl"
DESS = "dess/neodent-gm-scanbody.stl"
real_only = pytest.mark.skipif(not (REAL / "library").is_dir(),
                               reason="real library not present")


# --- synthetic fixtures: small parts, so the SEARCH itself is what is being timed -------

def _open_cylinder(radius: float, height: float = 5.0) -> trimesh.Trimesh:
    """An open-shell revolute body, vendor-CAD style (no top face)."""
    shell = trimesh.creation.cylinder(radius=radius, height=height, sections=48)
    keep = shell.face_normals[:, 2] < 0.9
    return trimesh.Trimesh(shell.vertices, shell.faces[keep], process=False)


def _channel(radius: float, height: float = 5.0) -> ChannelGeometry:
    return ChannelGeometry(mouth_centre=np.array([0.0, 0.0, height / 2.0]),
                           mouth_radius=float(radius),
                           base_centre=np.array([0.0, 0.0, -height / 2.0]),
                           base_radius=float(radius),
                           axis=np.array([0.0, 0.0, 1.0]))


THIN_WALL_BODY = (1.5, 1.1)      # wall ~0.42mm at zero relief — under the 0.50mm rule
UNSHIPPABLE_BODY = (1.0, 1.4)    # the bore is wider than the part: nothing survives


@pytest.fixture(autouse=True)
def _cold_cache():
    """Every test measures a COLD search — a bench warmed by the previous test would hide
    both the cost and any error in the search itself."""
    clear_relief_cache()
    yield
    clear_relief_cache()


class TestTheCeilingMirrorsTheExportGate:
    """The ceiling is worth nothing if it judges by different rules than the gate. These
    pin the predicate against ``output_package._relief_block_reason`` rule for rule."""

    def test_a_relief_that_erases_the_channel_is_unsafe(self):
        pre = {"measurable": True, "min_wall_mm": 0.9, "offset_mm": 0.0}
        post = {"measurable": False, "min_wall_mm": None, "offset_mm": 0.20,
                "sealed": True}
        assert _limit_reason(pre, post) == LIMITED_BY_CHANNEL

    def test_a_relief_that_thins_an_already_undersized_wall_is_unsafe(self):
        under = design_rules.MIN_WALL_MM - 0.1
        pre = {"measurable": True, "min_wall_mm": under, "offset_mm": 0.0}
        post = {"measurable": True, "min_wall_mm": under - 0.05, "offset_mm": 0.20,
                "sealed": True}
        assert _limit_reason(pre, post) == LIMITED_BY_WALL

    def test_a_wall_that_crosses_the_rule_only_BECAUSE_of_the_relief_is_safe(self):
        # DELIBERATE, and inherited verbatim from the gate: the gate does NOT block a wall
        # that had margin to give before the relief (the dess 6030 row, 0.568 -> 0.330) —
        # that is the advisory design-rule flag's job. A ceiling that closed here would
        # refuse a configuration the gate happily ships.
        pre = {"measurable": True, "min_wall_mm": 0.568, "offset_mm": 0.0}
        post = {"measurable": True, "min_wall_mm": 0.330, "offset_mm": 0.20,
                "sealed": True}
        assert _limit_reason(pre, post) is None

    def test_a_relief_that_fragments_the_part_is_unsafe(self):
        # the G5 catastrophic rule (seal_census) is part of the ceiling on purpose: a
        # ceiling that clamped to a value which then failed CLOSED at emission would not
        # make the automation complete either
        pre = {"measurable": True, "min_wall_mm": 0.9, "offset_mm": 0.0}
        post = {"measurable": True, "min_wall_mm": 0.8, "offset_mm": 0.20,
                "sealed": False}
        assert _limit_reason(pre, post) == LIMITED_BY_SEAL

    def test_a_zero_relief_can_never_be_a_relief_violation(self):
        # ``_relief_block_reason`` returns early unless ``applied`` — mirrored here, so a
        # part whose wall is thin on its OWN is never blamed on a relief nobody applied
        pre = {"measurable": True, "min_wall_mm": 0.05, "offset_mm": 0.0}
        assert _limit_reason(pre, {**pre, "sealed": True}) is None


class TestMaxSafeOnSyntheticParts:
    def test_a_thin_walled_part_ceilings_at_zero_and_names_the_wall(self):
        r, cr = THIN_WALL_BODY
        limit = max_safe_gingival_offset(_open_cylinder(r), library_channel=_channel(cr))
        assert limit.limited_by == LIMITED_BY_WALL
        assert limit.max_safe_mm == 0.0, "a wall already under the rule has nothing to give"
        assert limit.wall_mm_at_zero < design_rules.MIN_WALL_MM
        assert limit.shippable_at_zero is True
        assert "under the 0.50mm rule" in limit.note

    def test_an_unshippable_part_is_not_clamped_into_shippability(self):
        # THE HARD-BLOCK CASE the client's requirement does NOT cover: this part is not
        # manufacturable even with no relief at all. The ceiling says so instead of
        # returning some number that would let a broken part through.
        r, cr = UNSHIPPABLE_BODY
        limit = max_safe_gingival_offset(_open_cylinder(r), library_channel=_channel(cr))
        assert limit.shippable_at_zero is False
        assert limit.limited_by == LIMITED_BY_SEAL
        assert limit.max_safe_mm == 0.0
        assert "unshippable at any gingival offset" in limit.note

    def test_a_warm_bench_answers_the_same_pair_without_probing_again(self):
        # this is what makes the endpoint answerable at SELECTION time on a live server
        r, cr = THIN_WALL_BODY
        body, channel = _open_cylinder(r), _channel(cr)
        cold = max_safe_gingival_offset(body, library_channel=channel)
        warm = max_safe_gingival_offset(_open_cylinder(r), library_channel=_channel(cr))
        assert cold.probes > 0
        assert warm.probes == 0, "the cache must key on CONTENT, not object identity"
        assert warm.max_safe_mm == cold.max_safe_mm
        assert warm.limited_by == cold.limited_by

    def test_the_search_is_a_measurement_and_behaves_like_one(self):
        """Three properties of ONE search, asserted together because they are one claim:
        a measurement mutates nothing it was handed, spends none of the caller's
        randomness, and lands on the published grid.

        The RNG property is load-bearing, not hygiene: the pipeline's pinned stages (QC
        render, emission) draw from the global stream AFTER this call, so a search that
        spent draws would silently move the poses of every downstream package."""
        r, cr = THIN_WALL_BODY
        body = _open_cylinder(r)
        vertices_before = np.asarray(body.vertices).copy()
        np.random.seed(4)
        stream_before = np.random.rand(3).tolist()
        np.random.seed(4)
        limit = max_safe_gingival_offset(body, library_channel=_channel(cr))
        assert np.random.rand(3).tolist() == stream_before
        assert np.allclose(np.asarray(body.vertices), vertices_before)
        assert limit.resolution_mm == 0.01
        assert limit.max_safe_mm == round(limit.max_safe_mm, 2)
        assert 0.0 <= limit.max_safe_mm <= MAX_GINGIVAL_SEARCH_MM


class TestResolveTheRunsOffset:
    def test_a_zero_request_is_never_clamped_and_costs_nothing(self):
        # FAST PATH, deliberate: a zero relief cannot trip a relief gate, so there is
        # nothing to clamp and no reason to pay for a search. This is also why every
        # existing 0.0 test in the suite is unaffected by this change.
        r, cr = THIN_WALL_BODY
        clamp = resolve_gingival_offset(_open_cylinder(r), 0.0,
                                        library_channel=_channel(cr))
        assert (clamp.applied_mm, clamp.clamped, clamp.clamp_reason) == (0.0, False, None)
        assert clamp.max_safe_mm is None, "no search was run — the record must not claim one"

    @pytest.mark.slow  # measured 1.1s — a thick-walled body means a deeper SDF grid
    def test_a_safe_request_is_applied_as_asked_without_searching_for_a_ceiling(self):
        clamp = resolve_gingival_offset(_open_cylinder(2.5, height=8.0), 0.20,
                                        library_channel=_channel(1.1, height=8.0))
        assert clamp.clamped is False
        assert clamp.applied_mm == 0.20
        assert clamp.clamp_reason is None
        assert clamp.max_safe_mm is None, "nobody asked for a ceiling; none is invented"

    def test_an_unsafe_request_is_refused_as_asked_and_completed_at_the_ceiling(self):
        r, cr = THIN_WALL_BODY
        clamp = resolve_gingival_offset(_open_cylinder(r), 0.20,
                                        library_channel=_channel(cr),
                                        part_label="dess/acme 5020")
        assert clamp.clamped is True
        assert clamp.requested_mm == 0.20
        assert clamp.applied_mm == clamp.max_safe_mm < 0.20
        reason = clamp.clamp_reason
        # the sentence must carry BOTH numbers, the part, and what to do — a clamp a human
        # cannot act on is a silent substitution wearing a label
        assert "dess/acme 5020" in reason
        assert "0.20mm" in reason and f"{clamp.applied_mm:.2f}mm" in reason
        assert "NOT at the 0.20mm requested" in reason
        assert clamp.wall_mm_at_zero is not None

    @pytest.mark.slow  # measured 6.0s — the full ladder to the 0.50mm ceiling
    def test_the_applied_wall_is_measured_at_the_applied_value(self):
        # regression: an earlier draft fell back to the ZERO-relief reading when the
        # bisection had not landed exactly on the grid value, reporting the un-relieved
        # wall as if it were the wall of the part that ships
        body, channel = _open_cylinder(2.5, height=8.0), _channel(1.1, height=8.0)
        limit = max_safe_gingival_offset(body, library_channel=channel)
        at_ceiling = limit.reading_at(limit.max_safe_mm)
        assert at_ceiling is not None, "the ceiling's own wall must be probed, not inherited"
        assert limit.wall_mm_at_max_safe == at_ceiling["min_wall_mm"]

    def test_a_negative_request_is_refused_not_clamped(self):
        with pytest.raises(ValueError, match="into the tissue"):
            resolve_gingival_offset(_open_cylinder(1.5), -0.1)


# --- THE TABLE: the number the client actually needs ----------------------------------

@real_only
class TestTheRealCatalogTable:
    """The measured ceiling per (construction part x cap variant). Bounds, not exact
    equalities: the search is deterministic but the SDF read is pitch-quantized, so these
    pin the DECISION (does the client's 0.20mm survive?) and the neighbourhood."""

    @pytest.mark.slow
    @pytest.mark.parametrize("construction,model,variant,expected,limited", [
        # the client's own tooth-3 refusal: atlantis part under a neodent 5030 cap
        (ATLANTIS, "neodent-gm", "5030", 0.06, LIMITED_BY_WALL),
        (ATLANTIS, "neodent-gm", "5020", 0.15, LIMITED_BY_CHANNEL),
        (ATLANTIS, "neodent-gm", "6020", 0.08, LIMITED_BY_WALL),
        (ATLANTIS, "zimmer-4.5", "7030", 0.08, LIMITED_BY_WALL),
        (ATLANTIS, "zimmer-4.5", "8030", 0.08, LIMITED_BY_WALL),
        # the dess part: the CAP decides, not the vendor
        (DESS, "neodent-gm", "4030", 0.50, LIMITED_BY_NONE),
        (DESS, "neodent-gm", "5020", 0.05, LIMITED_BY_WALL),
        (DESS, "neodent-gm", "5030", 0.09, LIMITED_BY_WALL),
        (DESS, "neodent-gm", "6030", 0.47, LIMITED_BY_CHANNEL),
        (DESS, "zimmer-4.5", "8020", 0.05, LIMITED_BY_WALL),
    ])
    def test_max_safe_per_pair(self, construction, model, variant, expected, limited):
        limit = _real_limit(construction, model, variant)
        assert limit.max_safe_mm == pytest.approx(expected, abs=0.02), (
            f"{construction} x {model}/{variant}: ceiling moved from the measured "
            f"{expected:.2f}mm to {limit.max_safe_mm:.2f}mm")
        assert limit.limited_by == limited
        assert limit.shippable_at_zero is True, "every catalog pair ships at zero relief"

    @pytest.mark.slow
    def test_the_client_default_is_unsafe_on_every_atlantis_pair(self):
        # THE FINDING, stated as a test: the 0.20mm default is not a property of the
        # vendor — it is unsafe on the whole atlantis construction part, whatever cap
        for variant in ("4020", "5020", "5030", "6030"):
            limit = _real_limit(ATLANTIS, "neodent-gm", variant)
            assert limit.max_safe_mm < DEFAULT_GINGIVAL_OFFSET_MM, (
                f"atlantis x neodent-gm/{variant} now takes the 0.20mm default — "
                f"the fleet finding this change rests on has moved")

    @pytest.mark.slow
    def test_cap_size_not_vendor_is_the_driver(self):
        # the same construction part, two caps: one cannot take 0.05, the other takes 0.47
        small = _real_limit(DESS, "neodent-gm", "5020")
        large = _real_limit(DESS, "neodent-gm", "6030")
        assert small.max_safe_mm < DEFAULT_GINGIVAL_OFFSET_MM <= large.max_safe_mm
        assert small.wall_mm_at_zero < design_rules.MIN_WALL_MM <= large.wall_mm_at_zero

    @pytest.mark.slow
    def test_a_cold_search_is_cheap_enough_to_answer_at_selection_time(self):
        import time
        t0 = time.time()
        _real_limit(ATLANTIS, "zimmer-4.5", "7030")
        elapsed = time.time() - t0
        assert elapsed < 3.0, (
            f"the ceiling took {elapsed:.1f}s — it is asked while an operator waits on a "
            f"dropdown; the measured budget is ~1.2s worst case on this catalog")


def _real_library(model: str):
    from case_prep.adapters.cap_library import CapLibrary
    return CapLibrary.load(REAL / "library/caps" / model)


def _real_limit(construction: str, model: str, variant: str):
    from case_prep.domain.channel import channel_from_boundary_loops
    library = _real_library(model)
    spec = next(s for s in library.specs if s.variant == variant)
    mesh = trimesh.load(REAL / "library/construction" / construction, force="mesh")
    return max_safe_gingival_offset(
        mesh, library_channel=channel_from_boundary_loops(library.template(spec)))


# --- THE ENDPOINT ---------------------------------------------------------------------

@real_only
class TestReliefLimitEndpoint:
    @pytest.mark.slow
    def test_it_answers_the_ceiling_for_a_pair_the_default_breaks(self):
        import case_prep.server as srv
        client = TestClient(srv.app)
        res = client.get("/api/relief-limit",
                         params={"construction_path": ATLANTIS, "model": "neodent-gm",
                                 "variant": "5030"})
        assert res.status_code == 200
        body = res.json()
        assert body["max_safe_mm"] == pytest.approx(0.06, abs=0.02)
        assert body["requested_default_mm"] == DEFAULT_GINGIVAL_OFFSET_MM
        assert body["default_is_safe"] is False
        assert body["limited_by"] == LIMITED_BY_WALL
        assert body["wall_mm_at_zero"] == pytest.approx(0.028, abs=0.01)
        # the client's own words: the channel is UNMEASURABLE after the 0.20mm relief
        assert body["channel_measurable_at_zero"] is True
        assert body["channel_measurable_at_default"] is False
        assert body["wall_mm_at_default"] is None
        assert body["shippable_at_zero"] is True
        assert body["min_wall_rule_mm"] == design_rules.MIN_WALL_MM
        assert body["note"]

    @pytest.mark.slow
    def test_it_says_when_the_default_is_safe(self):
        import case_prep.server as srv
        client = TestClient(srv.app)
        body = client.get("/api/relief-limit",
                          params={"construction_path": DESS, "model": "neodent-gm",
                                  "variant": "6030"}).json()
        assert body["default_is_safe"] is True
        assert body["max_safe_mm"] >= DEFAULT_GINGIVAL_OFFSET_MM
        assert body["wall_mm_at_default"] is not None

    @pytest.mark.slow
    def test_the_second_query_for_a_pair_is_served_from_the_warm_bench(self):
        import case_prep.server as srv
        client = TestClient(srv.app)
        params = {"construction_path": DESS, "model": "neodent-gm", "variant": "5020"}
        first = client.get("/api/relief-limit", params=params).json()
        second = client.get("/api/relief-limit", params=params).json()
        assert first["cached"] is False and first["probes"] > 0
        assert second["cached"] is True and second["probes"] == 0
        assert second["max_safe_mm"] == first["max_safe_mm"]

    def test_an_unknown_construction_part_is_a_422_naming_the_catalog(self):
        import case_prep.server as srv
        client = TestClient(srv.app)
        res = client.get("/api/relief-limit",
                         params={"construction_path": "nope/none.stl",
                                 "model": "neodent-gm", "variant": "5030"})
        assert res.status_code == 422
        assert "GET /api/constructions" in res.json()["detail"]

    def test_an_unknown_variant_is_a_422_naming_the_library(self):
        import case_prep.server as srv
        client = TestClient(srv.app)
        res = client.get("/api/relief-limit",
                         params={"construction_path": DESS, "model": "neodent-gm",
                                 "variant": "9999"})
        assert res.status_code == 422
        assert "GET /api/library" in res.json()["detail"]


# --- THE RUN: it must COMPLETE ---------------------------------------------------------

@real_only
@pytest.mark.slow
class TestTheRunCompletes:
    """The client's requirement, end to end on real data: a run at 0.20mm against a
    construction part that cannot take it EMITS A PACKAGE, at the safe value, loudly."""

    @staticmethod
    def _run(out: Path, construction: str, offset: float):
        from case_prep.adapters.cap_library import CapLibrary
        from case_prep.pipeline.auto_flow import ConfirmedSite, run_auto_case
        return run_auto_case(
            case_id="clamp",
            scan=trimesh.load(REAL / "scans/doctor-295811960-neodent-gm/lower_jaw.stl",
                              force="mesh"),
            library=CapLibrary.load(REAL / "library/caps/neodent-gm"),
            construction_mesh=trimesh.load(REAL / "library/construction" / construction,
                                           force="mesh"),
            vendor=construction.split("/")[0],
            confirmed=[ConfirmedSite(29, (12.3, 9.8, 19.4))],
            jaw_label="lower", out_dir=out, render_qc=False,
            gingival_offset_mm=offset)

    def test_a_run_at_the_client_default_on_a_part_that_cannot_take_it_completes(
            self, tmp_path):
        out = tmp_path / "out"
        summary = self._run(out, ATLANTIS, DEFAULT_GINGIVAL_OFFSET_MM)

        # 1. IT COMPLETED, and the production set is on disk — the whole point
        assert (out / "clamp-29-prosthesis_cad.stl").exists()
        assert (out / "clamp-29-construction.json").exists()

        # 2. the case-level verdict is the first thing a reader meets
        relief = summary["gingival_relief"]
        assert relief["clamped"] is True
        assert relief["gingival_offset_requested_mm"] == DEFAULT_GINGIVAL_OFFSET_MM
        applied = relief["gingival_offset_applied_mm"]
        assert 0.0 <= applied < DEFAULT_GINGIVAL_OFFSET_MM
        assert "REFUSED, not applied" in relief["note"]

        # 3. the ROW carries both numbers; ``gingival_offset_mm`` is the APPLIED one, so a
        #    consumer reading only that key reads what the part was cut with, never the ask
        production = summary["sites"][0]["production"]
        assert production["gingival_offset_requested_mm"] == DEFAULT_GINGIVAL_OFFSET_MM
        assert production["gingival_offset_applied_mm"] == applied
        assert production["gingival_offset_mm"] == applied
        assert production["clamped"] is True
        assert production["limited_by"] in (LIMITED_BY_WALL, LIMITED_BY_CHANNEL,
                                            LIMITED_BY_SEAL)
        assert "NOT at the 0.20mm requested" in production["clamp_reason"]

        # 4. the PAID RECORD carries both numbers — a lab must never have to infer it got
        #    a different relief than it asked for
        audit = json.loads((out / "clamp-29-implant.json").read_text())["audit"]
        assert audit["gingival_offset_requested_mm"] == DEFAULT_GINGIVAL_OFFSET_MM
        assert audit["gingival_offset_applied_mm"] == applied
        assert audit["gingival_offset_mm"] == applied
        assert audit["clamped"] is True

        # 5. and the MANIFEST — the file a lab opens first — announces it at the top
        manifest = json.loads((out / "clamp-manifest.json").read_text())
        rows = manifest["gingival_relief_clamped"]
        assert [r["tooth"] for r in rows] == [29]
        assert rows[0]["gingival_offset_applied_mm"] == applied
        assert "NOT at gingival_offset_requested_mm" in \
            manifest["gingival_relief_clamped_note"]

    def test_the_measured_clearance_is_taken_against_what_was_CUT(self, tmp_path):
        # honesty seam: ``achieved`` compares the delivered part to its own un-relieved
        # reference, so its ``requested_mm`` is the APPLIED relief. It must not silently
        # read as the lab's ask — the clamp trio sits in the same record to disambiguate.
        out = tmp_path / "out"
        summary = self._run(out, ATLANTIS, DEFAULT_GINGIVAL_OFFSET_MM)
        applied = summary["gingival_relief"]["gingival_offset_applied_mm"]
        achieved = summary["sites"][0]["gingival_offset"]
        assert achieved["requested_mm"] == applied
        assert achieved["achieved_median_mm"] <= applied
        manifest = json.loads((out / "clamp-manifest.json").read_text())
        assert "gingival_relief_clamped" in manifest["gingival_clearance_note"]

    def test_a_run_at_zero_is_unchanged_and_never_claims_a_clamp(self, tmp_path):
        out = tmp_path / "out"
        summary = self._run(out, ATLANTIS, 0.0)
        relief = summary["gingival_relief"]
        assert relief["clamped"] is False
        assert relief["gingival_offset_requested_mm"] == 0.0
        assert relief["gingival_offset_applied_mm"] == 0.0
        production = summary["sites"][0]["production"]
        assert production["gingival_offset_mm"] == 0.0
        assert production["clamp_reason"] is None
        # nothing was relieved, so nothing was measured — None, not a fabricated 0.0
        assert summary["sites"][0]["gingival_offset"] is None
        manifest = json.loads((out / "clamp-manifest.json").read_text())
        assert "gingival_relief_clamped" not in manifest

    def test_a_run_on_a_part_that_takes_the_default_is_not_clamped(self, tmp_path):
        out = tmp_path / "out"
        summary = self._run(out, DESS, DEFAULT_GINGIVAL_OFFSET_MM)
        relief = summary["gingival_relief"]
        assert relief["clamped"] is False
        assert relief["gingival_offset_applied_mm"] == DEFAULT_GINGIVAL_OFFSET_MM
        assert summary["sites"][0]["production"]["gingival_offset_mm"] == \
            DEFAULT_GINGIVAL_OFFSET_MM
        assert (out / "clamp-29-prosthesis_cad.stl").exists()


@pytest.mark.slow
def test_the_hard_block_still_fires_when_nothing_is_shippable(tmp_path):
    """THE GATE IS NOT WEAKENED. A product that is not manufacturable still fails the
    export CLOSED with nothing written — the clamp completes runs whose RELIEF was too
    ambitious, it does not launder a broken part into a package."""
    from case_prep.adapters.output_package import SitePackageSpec, emit_case_package
    from case_prep.adapters.synthetic import make_scan_body_mesh
    from case_prep.pipeline.final_product import build_final_product

    # the synthetic scan body's anti-rotation flat sits 0.4mm off the axis, so the client's
    # relief eats through it and leaves several disconnected bodies
    product = build_final_product(make_scan_body_mesh(), screw_radius_mm=1.0,
                                  gingival_offset_mm=DEFAULT_GINGIVAL_OFFSET_MM)
    assert product.body_count > 1
    spec = SitePackageSpec(tooth=8, implant_model="certain", variant_code="4.1",
                           vendor="dess", pose_matrix=np.eye(4), scan_coverage=0.5,
                           advisory=True)
    body = make_scan_body_mesh()
    out = tmp_path / "pkg"
    with pytest.raises(ValueError, match="package NOT emitted"):
        emit_case_package("frag", trimesh.creation.box(extents=[20, 20, 4]), "upper",
                          [(spec, body, body)], out, final_product_mesh={8: product})
    assert not out.exists(), "fail-closed still means NOTHING emitted"
