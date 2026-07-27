"""The LIBRARY PART's marked features (client ask 2026-07-24: "mark the holes/trenches
in the LIBRARY part").

Pinned here: the auto-seed reads every one of the 12 real catalog variants (coded
trenches + the screw channel), it is deterministic and RNG-neutral, an operator click
reconciles with the machine's own reading inside the calibrated snap windows and is kept
verbatim outside them, and a concentric landmark is refused as a rotation anchor. The
real-catalog assertions skip when the library is absent on this machine — the same
convention as tests/test_channel.py.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import trimesh

from case_prep.adapters.ingest import canonicalize_revolute
from case_prep.domain.clock_signature import template_signature, wrap_deg
from case_prep.domain.part_features import (FEATURE_KINDS, MIN_LEVER_ARM_MM,
                                            SNAP_AZIMUTH_DEG, SNAP_RADIUS_MM,
                                            PartAnnotation, PartFeature, auto_features,
                                            coded_band_radius_mm,
                                            coded_feature_azimuths, feature_from_azimuth,
                                            feature_from_point, operator_feature_id,
                                            template_rim_centre)

LIB_ROOT = Path(__file__).parents[1] / "data/real/library/caps"
# the CURRENT catalog: 6 variants per model, superseded archives excluded (they are a
# different generation of the same part and carry their own annotations)
CATALOG = [("neodent-gm", v) for v in ("4020", "4030", "5020", "5030", "6020", "6030")]
CATALOG += [("zimmer-4.5", v) for v in ("6020", "6030", "7020", "7030", "8020", "8030")]

_TEMPLATES: dict = {}


def _template(model: str, variant: str) -> trimesh.Trimesh:
    """One catalog part in the canonical frame, memoized across the module (the
    canonicalization + 120k-point signature sampling is the expensive part)."""
    key = (model, variant)
    if key not in _TEMPLATES:
        path = LIB_ROOT / model / f"{model}-{variant}.stl"
        if not path.exists():
            pytest.skip(f"catalog part {model}/{variant} not present on this machine")
        _TEMPLATES[key] = canonicalize_revolute(trimesh.load(path, force="mesh"))[0]
    return _TEMPLATES[key]


def _point_at(template, azimuth_deg: float, radius_mm: float, z_mm: float = None):
    """A canonical-frame point at an exactly-known azimuth/radius about the part's rim
    centre — the inverse of feature_from_point's own mapping."""
    c = template_rim_centre(template)
    a = np.radians(azimuth_deg)
    if z_mm is None:
        z_mm = float(np.asarray(template.vertices, float)[:, 2].max())
    return [float(c[0] + radius_mm * np.cos(a)),
            float(c[1] + radius_mm * np.sin(a)), float(z_mm)]


class TestAutoSeedOnTheRealCatalog:
    @pytest.mark.parametrize("model,variant", CATALOG)
    def test_every_variant_yields_coded_features_and_a_channel(self, model, variant):
        """The seed is what the operator is asked to confirm — on every real part it
        must already say something: at least one coded trench plus the CAD's own screw
        channel. A blank seed would push the operator back to a blank page."""
        features = auto_features(_template(model, variant))
        trenches = [f for f in features if f.kind == "trench"]
        channels = [f for f in features if f.kind == "channel"]
        assert len(trenches) >= 1, f"{model}/{variant} seeded no coded feature"
        assert len(channels) == 1, f"{model}/{variant} seeded {len(channels)} channels"
        assert all(f.kind in FEATURE_KINDS for f in features)
        assert all(f.source == "auto" for f in features)
        ids = [f.id for f in features]
        assert len(set(ids)) == len(ids), f"{model}/{variant} seeded duplicate ids {ids}"
        # ids are positional over the AZIMUTH-SORTED trenches: trench-01 names the same
        # cutout in every session, which is what makes a persisted annotation reusable
        assert [f.id for f in trenches] == [f"trench-{i + 1:02d}"
                                            for i in range(len(trenches))]
        assert [f.azimuth_deg for f in trenches] == sorted(f.azimuth_deg
                                                           for f in trenches)
        assert all(-180.0 <= f.azimuth_deg <= 180.0 for f in features)

    @pytest.mark.parametrize("model,variant", CATALOG)
    def test_trenches_have_a_lever_arm_and_the_channel_does_not(self, model, variant):
        """Measured 2026-07-25 over the whole catalog: trench radii 1.43-2.19mm, channel
        mouth eccentricity 0.017-0.112mm. The bore is CONCENTRIC — it names the axis, not
        a clock angle — so it is seeded and listed but can never anchor a rotation."""
        for f in auto_features(_template(model, variant)):
            if f.kind == "channel":
                assert f.radius_mm < MIN_LEVER_ARM_MM, \
                    f"{model}/{variant} channel eccentricity {f.radius_mm:.3f}mm — an " \
                    f"off-axis bore would be a real clock feature; re-derive the rule"
                assert f.defines_rotation is False
            else:
                assert f.radius_mm >= MIN_LEVER_ARM_MM
                assert f.defines_rotation is True

    def test_multi_feature_cap_is_the_ambiguity_this_flow_removes(self):
        """zimmer-4.5-7030 carries THREE trenches (measured -177.0 / -136.0 / -0.1) —
        the case where align-to-mark's nearest-match can bind the operator's click to
        the wrong cutout. The seed must name all three so the operator can pick."""
        trenches = [f for f in auto_features(_template("zimmer-4.5", "7030"))
                    if f.kind == "trench"]
        assert [round(f.azimuth_deg, 1) for f in trenches] == [-177.0, -136.0, -0.1]

    @pytest.mark.parametrize("model,variant", CATALOG)
    def test_deterministic_across_calls_and_rng_state_preserved(self, model, variant):
        """House determinism rule: this may be called mid-pipeline, whose downstream
        stages depend on the pinned RNG stream."""
        template = _template(model, variant)
        np.random.seed(7)
        before = np.random.get_state()
        first = auto_features(template)
        second = auto_features(template)
        after = np.random.get_state()
        assert [f.to_dict() for f in first] == [f.to_dict() for f in second]
        for e, g in zip(before, after):
            assert np.array_equal(e, g), \
                "auto_features perturbed the global RNG stream"

    def test_a_freshly_loaded_copy_reads_the_same_part(self):
        """A persisted annotation is only reusable if the ids and azimuths survive a
        reload — the signature cache is keyed by mesh identity, so a second load must
        not read a different part."""
        first = auto_features(_template("zimmer-4.5", "7030"))
        fresh = canonicalize_revolute(trimesh.load(
            LIB_ROOT / "zimmer-4.5/zimmer-4.5-7030.stl", force="mesh"))[0]
        assert [f.to_dict() for f in auto_features(fresh)] == \
            [f.to_dict() for f in first]

    def test_coded_azimuths_agree_with_the_seed(self):
        """Single source of truth: the azimuth list align-to-mark matches against IS the
        seed's trench azimuths (the reading was moved out of server.py into this
        module precisely so the two can never drift)."""
        template = _template("zimmer-4.5", "7030")
        seeded = [f.azimuth_deg for f in auto_features(template) if f.kind == "trench"]
        assert coded_feature_azimuths(template_signature(template)) == \
            pytest.approx(seeded)

    def test_a_featureless_part_seeds_nothing_rather_than_guessing(self):
        """A plain cylinder has no coded relief and no boundary loops — the honest seed
        is empty, never an invented landmark."""
        assert auto_features(trimesh.creation.cylinder(radius=3.0, height=2.0,
                                                       sections=64)) == []


class TestFeatureFromPoint:
    def test_click_inside_both_windows_snaps_to_the_machine_reading(self):
        """A click 4° off trench-02 adopts that trench's ID AND geometry — an operator
        mark and the clock instrument must talk about the same cutout, to the degree."""
        template = _template("zimmer-4.5", "7030")
        auto = {f.id: f for f in auto_features(template)}
        target = auto["trench-02"]
        click = _point_at(template, target.azimuth_deg + 4.0, target.radius_mm + 0.3)
        mark = feature_from_point(template, click)
        assert mark.id == "trench-02"
        assert mark.azimuth_deg == pytest.approx(target.azimuth_deg)
        assert mark.radius_mm == pytest.approx(target.radius_mm)
        assert mark.z_mm == pytest.approx(target.z_mm)
        # source records WHO placed the mark; the id records what it agrees with
        assert mark.source == "operator"

    def test_click_outside_the_azimuth_window_keeps_the_operators_own_angle(self):
        template = _template("zimmer-4.5", "7030")
        target = next(f for f in auto_features(template) if f.id == "trench-02")
        az = target.azimuth_deg + SNAP_AZIMUTH_DEG + 3.0
        mark = feature_from_point(template, _point_at(template, az, target.radius_mm))
        assert mark.id == operator_feature_id(az)
        assert mark.id != "trench-02"
        assert mark.azimuth_deg == pytest.approx(wrap_deg(az))
        assert mark.source == "operator"

    def test_click_outside_the_radius_window_keeps_the_operators_own_angle(self):
        """Same azimuth as a trench but far off its band — the operator is marking
        something else (a rim feature, a bore edge), not confirming that trench."""
        template = _template("zimmer-4.5", "7030")
        target = next(f for f in auto_features(template) if f.id == "trench-02")
        r = target.radius_mm - (SNAP_RADIUS_MM + 0.2)
        mark = feature_from_point(template, _point_at(template, target.azimuth_deg, r))
        assert mark.id != "trench-02"
        assert mark.radius_mm == pytest.approx(r, abs=1e-6)

    def test_the_snap_window_cannot_reach_a_neighbouring_feature(self):
        """The whole point of the flow: a snap must never bind the operator to the wrong
        trench. The tightest catalog pair is 7030's -177.0/-136.0 (41° apart) and
        4030's -22.5/+1.0 (23.5°) — the 11° window stays inside every half-gap."""
        for model, variant in (("zimmer-4.5", "7030"), ("neodent-gm", "4030")):
            template = _template(model, variant)
            az = sorted(f.azimuth_deg for f in auto_features(template)
                        if f.kind == "trench")
            gaps = [abs(wrap_deg(b - a)) for a, b in zip(az, az[1:])]
            assert min(gaps) / 2.0 > SNAP_AZIMUTH_DEG, \
                f"{model}/{variant} half-gap {min(gaps) / 2.0:.1f}° is inside the " \
                f"{SNAP_AZIMUTH_DEG}° snap window — a snap could bind the wrong trench"

    def test_snapping_takes_the_nearest_qualifying_feature(self):
        template = _template("neodent-gm", "4030")
        auto = [f for f in auto_features(template) if f.kind == "trench"]
        a, b = auto[0], auto[1]  # -22.5 and +1.0 — 23.5° apart
        click_az = a.azimuth_deg + 0.4 * wrap_deg(b.azimuth_deg - a.azimuth_deg)
        mark = feature_from_point(template, _point_at(template, click_az, a.radius_mm))
        assert mark.id == a.id

    def test_a_click_at_the_axis_is_refused(self):
        template = _template("zimmer-4.5", "7030")
        centre = template_rim_centre(template)
        with pytest.raises(ValueError, match="no azimuth to mark"):
            feature_from_point(template, [float(centre[0]), float(centre[1]), 1.8])

    def test_a_click_off_the_part_is_refused(self):
        template = _template("zimmer-4.5", "7030")
        with pytest.raises(ValueError, match="not on this part"):
            feature_from_point(template, _point_at(template, 30.0, 40.0))

    def test_a_malformed_click_is_refused(self):
        template = _template("zimmer-4.5", "7030")
        with pytest.raises(ValueError, match="triple"):
            feature_from_point(template, [1.0, 2.0])
        with pytest.raises(ValueError, match="triple"):
            feature_from_point(template, [float("nan"), 0.0, 0.0])

    def test_kind_is_the_operators_to_choose_when_no_feature_is_snapped(self):
        template = _template("zimmer-4.5", "8020")
        target = next(f for f in auto_features(template) if f.kind == "trench")
        mark = feature_from_point(
            template, _point_at(template, target.azimuth_deg + 40.0, target.radius_mm),
            kind="flat")
        assert mark.kind == "flat"


class TestFeatureFromAzimuth:
    """A mark given as a bare AZIMUTH — what the UI re-sends for every mark it did not
    touch. It must reconcile with the machine's reading the same way a click does, or a
    plain re-save re-places the part's own features on the coded band's mid-radius."""

    @pytest.mark.parametrize("model,variant", CATALOG)
    def test_re_sending_the_auto_seed_by_azimuth_is_geometry_preserving(self, model,
                                                                        variant):
        """THE regression: the annotator sends every untouched mark back as an azimuth on
        save, so a save with no edits must return the part unchanged. Before this rule the
        CONCENTRIC channel came back with a fabricated ~2mm lever arm — defines_rotation
        flipped False -> True and the bore became a nameable rotation anchor, which is the
        one thing MIN_LEVER_ARM_MM exists to refuse."""
        template = _template(model, variant)
        for auto in auto_features(template):
            mark = feature_from_azimuth(template, auto.azimuth_deg, kind=auto.kind)
            assert mark.id == auto.id, "a re-sent mark must keep naming the same cutout"
            assert mark.kind == auto.kind
            assert mark.azimuth_deg == pytest.approx(auto.azimuth_deg)
            assert mark.radius_mm == pytest.approx(auto.radius_mm)
            assert mark.z_mm == pytest.approx(auto.z_mm)
            assert mark.defines_rotation is auto.defines_rotation
            assert mark.source == "operator"

    def test_the_channel_keeps_its_measured_lever_arm(self):
        template = _template("zimmer-4.5", "7030")
        bore = next(f for f in auto_features(template) if f.kind == "channel")
        assert bore.defines_rotation is False, "the 7030 bore is concentric — the premise"
        mark = feature_from_azimuth(template, bore.azimuth_deg, kind="channel")
        assert mark.radius_mm == pytest.approx(bore.radius_mm)
        assert mark.defines_rotation is False

    def test_an_azimuth_no_feature_claims_lands_on_the_coded_band(self):
        """A mark the machine has no reading for still needs a lever arm — the mid-radius
        of the band the codes actually occupy, not the axis."""
        template = _template("zimmer-4.5", "7030")
        far = min(abs(wrap_deg(60.0 - f.azimuth_deg)) for f in auto_features(template))
        assert far > SNAP_AZIMUTH_DEG, "60° must be clear of every 7030 feature"
        mark = feature_from_azimuth(template, 60.0, kind="flat")
        assert mark.id == operator_feature_id(60.0)
        assert mark.kind == "flat"
        assert mark.azimuth_deg == pytest.approx(60.0)
        assert mark.radius_mm == pytest.approx(coded_band_radius_mm(template))
        assert mark.defines_rotation is True

    def test_the_azimuth_window_cannot_reach_a_neighbouring_trench(self):
        """Without a radius the reconciliation is on azimuth alone — the window must
        still stay inside every inter-feature half-gap in the catalog."""
        template = _template("neodent-gm", "4030")
        a, b = [f for f in auto_features(template) if f.kind == "trench"][:2]
        midpoint = a.azimuth_deg + 0.5 * wrap_deg(b.azimuth_deg - a.azimuth_deg)
        assert feature_from_azimuth(template, midpoint).id not in (a.id, b.id)
        assert feature_from_azimuth(
            template, a.azimuth_deg + 0.4 * wrap_deg(b.azimuth_deg - a.azimuth_deg)
        ).id == a.id


class TestFeatureAndAnnotationRecords:
    def test_feature_round_trips_through_a_dict(self):
        f = PartFeature(id="trench-01", kind="trench", azimuth_deg=-136.0,
                        radius_mm=2.084, z_mm=1.808, source="auto")
        back = PartFeature.from_dict(f.to_dict())
        assert (back.id, back.kind, back.source) == ("trench-01", "trench", "auto")
        assert back.azimuth_deg == pytest.approx(-136.0)
        assert back.radius_mm == pytest.approx(2.084)
        assert back.z_mm == pytest.approx(1.808)

    def test_annotation_round_trips_and_finds_features_by_id(self):
        ann = PartAnnotation(
            model="zimmer-4.5", variant="7030", revised_at="2026-07-25T09:00:00",
            features=[PartFeature("trench-02", "trench", -136.0, 2.084, 1.808,
                                  "operator")])
        back = PartAnnotation.from_dict(ann.to_dict())
        assert back.model == "zimmer-4.5" and back.variant == "7030"
        assert back.revised_at == "2026-07-25T09:00:00"
        assert back.by_id("trench-02").azimuth_deg == pytest.approx(-136.0)
        assert back.by_id("nope") is None

    def test_azimuth_is_wrapped_into_the_canonical_half_turn(self):
        assert PartFeature("x", "trench", 200.0, 2.0, 1.0).azimuth_deg == \
            pytest.approx(-160.0)

    def test_duplicate_ids_are_a_contradiction_not_a_set(self):
        f = PartFeature("operator-045", "trench", 45.0, 2.0, 1.0, "operator")
        with pytest.raises(ValueError, match="duplicate feature id"):
            PartAnnotation(model="m", variant="v", features=[f, f])

    def test_unknown_kind_and_source_are_refused(self):
        with pytest.raises(ValueError, match="unknown feature kind"):
            PartFeature("x", "sprocket", 0.0, 2.0, 1.0)
        with pytest.raises(ValueError, match="source"):
            PartFeature("x", "trench", 0.0, 2.0, 1.0, source="the-vendor")

    def test_non_finite_geometry_is_refused(self):
        with pytest.raises(ValueError, match="finite"):
            PartFeature("x", "trench", float("nan"), 2.0, 1.0)

    def test_malformed_records_are_refused(self):
        with pytest.raises(ValueError, match="malformed part feature"):
            PartFeature.from_dict({"id": "x", "kind": "trench"})
        with pytest.raises(ValueError, match="malformed part annotation"):
            PartAnnotation.from_dict({"model": "m", "variant": "v"})

    def test_operator_ids_collide_only_for_the_same_mark(self):
        assert operator_feature_id(45.2) == operator_feature_id(44.8)   # one mark
        assert operator_feature_id(45.0) != operator_feature_id(47.0)
        assert operator_feature_id(-136.0) == operator_feature_id(224.0)  # wrapped
