"""The final product — OUR OWN export (client pivot, 2026-07-04): the vendor
construction part with the screw-access channel bored where the LIBRARY says the
channel is, carried by the measured pose (G1, master plan §7.4; autopsy 2026-07-23).

DELIBERATE CONTRACT CHANGE (2026-07-23). The tests this file replaces asserted
bore-wall vertices at radial ~1.0 FROM THE ORIGIN — they enforced the §7.1 defect:
the delivered channel sat exactly on the canonical axis, missing the cap CAD's true
channel by 0.36-0.42mm and the scanned recess by 0.60-0.84mm on all 3 measured real
packages, at half the DESS part's designed lumen diameter (r=1.0 vs 2.00), and no
instrument would ever have caught it (§7.3). New contract: with the cap's loop-truth
``ChannelGeometry`` supplied, the channel follows the LIBRARY (position, axis AND
radius); ``CHANNEL_AT_LIBRARY_TRUTH = False`` restores the old behaviour exactly
(the vendor spec, C3, stays the arbiter of the convention).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import trimesh
from scipy.spatial import cKDTree

import case_prep.pipeline.final_product as final_product
from case_prep.adapters.synthetic import make_scan_body_mesh
from case_prep.domain.channel import ChannelGeometry
from case_prep.pipeline.final_product import (DEFAULT_GINGIVAL_OFFSET_MM,
                                              build_final_product,
                                              measure_delivered_channel)


def _library_channel(mouth_xy=(-0.35, -0.05), radius=1.1) -> ChannelGeometry:
    """A cap-CAD-shaped channel truth: off-axis straight channel, +z axis — the
    catalog shape (mouth r 1.078-1.152, 0.205-0.587mm off the canonical axis)."""
    return ChannelGeometry(
        mouth_centre=np.array([mouth_xy[0], mouth_xy[1], 8.0]),
        mouth_radius=float(radius),
        base_centre=np.array([mouth_xy[0], mouth_xy[1], 1.0]),
        base_radius=2.2,
        axis=np.array([0.0, 0.0, 1.0]))


def _round_body() -> trimesh.Trimesh:
    """A revolute construction body (open shell, like a vendor CAD) with real wall
    margin around an off-axis bore. The D-flat synthetic scan body is NOT used for
    position-contract tests: its anti-rotation flat sits at x=0.4, so any realistic
    bore BREACHES it (an open groove) and the measurement rightly refuses —
    that behaviour is pinned separately in TestMeasureDeliveredChannel."""
    shell = trimesh.creation.cylinder(radius=2.5, height=8.0, sections=48)
    keep = shell.face_normals[:, 2] < 0.9  # open the top, vendor-CAD style
    return trimesh.Trimesh(shell.vertices, shell.faces[keep], process=False)


class TestBuildFinalProduct:
    @pytest.mark.slow
    def test_bores_a_watertight_channelled_solid(self):
        part = make_scan_body_mesh()
        product = build_final_product(part, screw_radius_mm=1.0)
        assert product.is_watertight               # manufacturable solid
        assert product.volume < part.volume        # material removed by the bore

    @pytest.mark.slow
    def test_channel_follows_library_channel_axis(self):
        # REWRITE of test_channel_runs_the_full_height (§7.4 G1). Old behaviour: the
        # channel was asserted at radial ~1.0 about the ORIGIN — the canonical axis,
        # which the autopsy measured 0.36-0.42mm from the cap CAD's true channel on
        # every real package. New behaviour: the bore lands on the library channel's
        # xy carried by the shared canonical frame, within the plan's 0.05mm gate
        # (measured 0.004mm at SDF pitch 0.25).
        ch = _library_channel()
        product = build_final_product(_round_body(), library_channel=ch)
        assert product.is_watertight
        m = measure_delivered_channel(product)
        assert m is not None, "no as-built channel found in the delivered solid"
        gap = float(np.linalg.norm(m.centre[:2] - ch.mouth_centre[:2]))
        assert gap <= 0.05, (
            f"as-built channel {m.centre[:2]} is {gap:.3f}mm from the library "
            f"channel {ch.mouth_centre[:2]} — the §7.1 defect was 0.36-0.42mm")
        assert m.z_span > 4.0, "channel does not run the body height"
        assert abs(m.radius - ch.mouth_radius) <= 0.1

    @pytest.mark.slow
    def test_channel_radius_is_the_librarys_not_the_fixed_bore(self):
        # C7's first fix (§7.1 finding 3): the fixed r=1.0 bore was HALF the DESS
        # part's designed lumen diameter (r=2.00). New behaviour: the bore uses the
        # library channel's own mouth radius; the vendor part's designed lumen is
        # READ from its boundary loops and RECORDED (G5's design-rule case), but NOT
        # used as the bore radius — measured 2026-07-23: boring the DESS part at
        # r=2.00 on the cap's off-axis xy leaves 16.1mm^3 in 2 disconnected bodies
        # (destroyed) vs 79.1mm^3 sound at the library radius.
        ch = _library_channel(mouth_xy=(0.0, 0.0), radius=1.4)
        product = build_final_product(_round_body(), screw_radius_mm=1.0,
                                      library_channel=ch)
        m = measure_delivered_channel(product)
        assert m is not None
        assert abs(m.radius - 1.4) <= 0.12, (
            f"as-built radius {m.radius:.3f} != library channel radius 1.4 — "
            f"the fixed-1.0 C7 bore is back?")
        meta = product.metadata["channel"]
        assert meta["mode"] == "library_truth"
        assert abs(meta["vendor_lumen_radius_mm"] - 2.5) <= 0.05, \
            "vendor part's own lumen radius not read/recorded from its loops"

    @pytest.mark.slow
    def test_flag_off_restores_canonical_axis_behaviour_exactly(self, monkeypatch):
        # THE REVERSIBILITY LEVER: with CHANNEL_AT_LIBRARY_TRUTH=False the product is
        # BYTE-IDENTICAL to the legacy build even when a channel is supplied — the
        # vendor interface spec (C3) has not landed, so the old convention must stay
        # emittable, deliberately, not as drift.
        part = make_scan_body_mesh()
        legacy = build_final_product(part, screw_radius_mm=1.0)
        monkeypatch.setattr(final_product, "CHANNEL_AT_LIBRARY_TRUTH", False)
        off = build_final_product(part, screw_radius_mm=1.0,
                                  library_channel=_library_channel())
        assert np.array_equal(np.asarray(off.vertices), np.asarray(legacy.vertices))
        assert np.array_equal(np.asarray(off.faces), np.asarray(legacy.faces))
        assert off.metadata["channel"]["mode"] == "canonical_axis"

    @pytest.mark.slow
    def test_product_is_centered_on_the_component_origin_all_axes(self):
        # the pose maps the CANONICAL (centroid-origin) frame to world, so the product must
        # be centroid-centred on ALL axes — an xy-only check hid a systematic axial seating
        # error (review C2)
        part = make_scan_body_mesh()
        part.apply_translation([30.0, -12.0, 5.0])  # vendor file arrives off-origin
        product = build_final_product(part, screw_radius_mm=1.0)
        assert np.linalg.norm(np.asarray(product.vertices).mean(axis=0)) < 0.5

    @pytest.mark.slow
    def test_arbitrary_vendor_frame_still_bores_at_the_library_channel(self):
        # REWRITE of the review-C1 regression: a vendor mesh arriving ROTATED must not
        # yield a sideways or displaced screw channel. Canonicalization puts the part
        # back on +z first, so the library-truth bore lands on the SAME canonical xy
        # from ANY input frame (the old assertion checked radial ~1.0 about the origin
        # — the defect-enforcing form).
        ch = _library_channel()
        part = _round_body()
        part.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
        part.apply_translation([12.0, 7.0, -30.0])
        product = build_final_product(part, library_channel=ch)
        assert product.is_watertight
        v = np.asarray(product.vertices, float)
        assert (v[:, 2].max() - v[:, 2].min()) > 6.0  # tallest axis back on z
        m = measure_delivered_channel(product)
        assert m is not None
        assert float(np.linalg.norm(m.centre[:2] - ch.mouth_centre[:2])) <= 0.05

    @pytest.mark.slow
    def test_input_mesh_is_not_mutated(self):
        part = make_scan_body_mesh()
        before = np.asarray(part.vertices).copy()
        build_final_product(part, screw_radius_mm=1.0,
                            library_channel=_library_channel())
        assert np.allclose(np.asarray(part.vertices), before)


class TestGingivalProfileOffset:
    """The client's gingival profile offset (2026-07-25): the emitted part carries a
    controlled clearance where it meets tissue. 0.20mm is the client's own value and the
    default; 0.0 must reproduce the pre-offset geometry BYTE-IDENTICALLY, so the change is
    a lever the lab holds and not drift nobody can undo."""

    def test_the_client_value_is_the_default(self):
        assert DEFAULT_GINGIVAL_OFFSET_MM == 0.20

    @pytest.mark.slow
    def test_zero_offset_is_byte_identical_to_the_pre_offset_build(self):
        """THE REVERSIBILITY CONTRACT, against the OLD BUILD ITSELF — not against another
        call of the new one. The pre-2026-07-25 path (canonicalize the capped shell, then
        bore) is transcribed here; at 0.0 the offset step must not run AT ALL, because a
        marching-cubes round trip that "should" be a no-op is not one (measured on the
        real DESS part: an offset of 0.0 still inflates it 106.2 -> 109.6 mm^3)."""
        from case_prep.adapters.booleans import screw_channel
        from case_prep.adapters.ingest import canonicalize_library
        from case_prep.pipeline.final_product import (_CHANNEL_OVERSHOOT_MM,
                                                      _SDF_PITCH_MM,
                                                      _cap_open_boundaries)

        vendor_mesh = _round_body()
        ch = _library_channel()
        part, _ = canonicalize_library(_cap_open_boundaries(vendor_mesh))
        z = np.asarray(part.vertices, float)[:, 2]
        mid = float((z.max() + z.min()) / 2.0)
        legacy = screw_channel(
            part,
            position=[float(ch.mouth_centre[0]), float(ch.mouth_centre[1]), mid],
            axis=[float(a) for a in ch.axis], radius=float(ch.mouth_radius),
            length=float(z.max() - z.min()) + 2.0 * _CHANNEL_OVERSHOOT_MM,
            pitch=_SDF_PITCH_MM)

        now = build_final_product(vendor_mesh, library_channel=ch,
                                  gingival_offset_mm=0.0)
        assert np.array_equal(np.asarray(now.vertices), np.asarray(legacy.vertices))
        assert np.array_equal(np.asarray(now.faces), np.asarray(legacy.faces))
        assert now.metadata["gingival_offset"]["applied"] is False
        assert now.metadata["gingival_offset"]["mode"] == "none"
        assert now.metadata["gingival_offset"]["offset_mm"] == 0.0

    @pytest.mark.slow
    def test_the_client_offset_measurably_relieves_the_part(self):
        # the whole point: at 0.20 the delivered surface must sit INSIDE the 0.0 surface
        # by a real, measurable amount — not a rounding difference
        part = _round_body()
        ch = _library_channel()
        plain = build_final_product(part, library_channel=ch, gingival_offset_mm=0.0)
        relieved = build_final_product(part, library_channel=ch,
                                       gingival_offset_mm=0.20)
        assert not np.array_equal(np.asarray(relieved.vertices),
                                  np.asarray(plain.vertices))
        assert relieved.is_watertight
        assert relieved.volume < plain.volume - 1.0, (
            f"0.20mm relief removed only {plain.volume - relieved.volume:.3f}mm^3 — "
            f"the offset is not reaching the geometry")
        # the achieved clearance, measured surface-to-surface (the SDF round trip at
        # pitch 0.25 lands short of the asked 0.20 — pinned as a range, said out loud)
        base = trimesh.sample.sample_surface(plain, 20000)[0]
        probe = trimesh.sample.sample_surface(relieved, 20000)[0]
        gap = float(np.median(cKDTree(np.asarray(base, float))
                              .query(np.asarray(probe, float))[0]))
        assert 0.08 <= gap <= 0.22, f"achieved clearance {gap:.3f}mm is not the asked 0.20"
        assert relieved.metadata["gingival_offset"]["applied"] is True
        assert relieved.metadata["gingival_offset"]["offset_mm"] == 0.20
        assert relieved.metadata["gingival_offset"]["mode"] == \
            "uniform_inward_surface_offset"     # honesty: not gingiva-only

    @pytest.mark.slow
    def test_the_relief_does_not_widen_the_screw_channel(self):
        # ORDER CONTRACT: the relief is applied BEFORE the bore. Relieving afterwards
        # would open the channel by the same 0.20mm and break G1's library-truth radius
        # (measured miss 0.001-0.018mm) — the delivered radius must stay the library's.
        ch = _library_channel(mouth_xy=(0.0, 0.0), radius=1.2)
        relieved = build_final_product(_round_body(), library_channel=ch,
                                       gingival_offset_mm=0.20)
        m = measure_delivered_channel(relieved)
        assert m is not None
        assert abs(m.radius - 1.2) <= 0.12, (
            f"as-built channel radius {m.radius:.3f} drifted from the library's 1.2 — "
            f"is the relief being applied after the bore?")

    def test_zero_offset_records_no_achieved_reading_rather_than_a_zero(self):
        # honesty: with no relief step there is nothing to measure — the record says
        # None, it does not report a measured 0.0 that was never measured
        product = build_final_product(_round_body(), library_channel=_library_channel(),
                                      gingival_offset_mm=0.0)
        relief = product.metadata["gingival_offset"]
        assert relief["achieved"] is None
        assert relief["pre_offset"] is None and relief["post_offset"] is None

    @pytest.mark.slow
    def test_the_achieved_clearance_is_measured_and_recorded(self):
        """THE HONESTY FIX (2026-07-25): the record must carry what the relief ACTUALLY
        removed, not echo the request back. The SDF round trip lands short of the ask —
        measured on the real vendor parts at a requested 0.20: atlantis median 0.146,
        dess median 0.128 — so a record that only said "0.20" was overstating the
        clearance the patient receives by ~35%."""
        product = build_final_product(_round_body(), library_channel=_library_channel(),
                                      gingival_offset_mm=0.20)
        achieved = product.metadata["gingival_offset"]["achieved"]
        assert achieved["requested_mm"] == 0.20
        assert achieved["n_samples"] == 20000
        # plausible: a real, sub-requested clearance — not 0, not the ask parroted back
        assert 0.05 < achieved["achieved_median_mm"] < 0.20
        assert (achieved["achieved_p10_mm"] <= achieved["achieved_median_mm"]
                <= achieved["achieved_p90_mm"])
        # the un-relieved reference's own channel read rides along — the pre/post pair
        # the emitter's fail-closed relief gate needs
        assert product.metadata["gingival_offset"]["pre_offset"]["measurable"] is True
        assert product.metadata["gingival_offset"]["post_offset"]["measurable"] is True

    @pytest.mark.slow
    def test_the_clearance_measurement_is_deterministic_and_rng_neutral(self):
        # it samples surfaces, so it MUST seed and restore: two builds must agree, and
        # the global stream the pipeline's pinned stages draw from must be untouched
        part, ch = _round_body(), _library_channel()
        np.random.seed(4)
        before = np.random.rand(3).tolist()
        np.random.seed(4)
        a = build_final_product(part, library_channel=ch, gingival_offset_mm=0.20)
        after = np.random.rand(3).tolist()
        b = build_final_product(part, library_channel=ch, gingival_offset_mm=0.20)
        assert after == before, "the build consumed the caller's RNG stream"
        assert (a.metadata["gingival_offset"]["achieved"]
                == b.metadata["gingival_offset"]["achieved"])

    def test_a_negative_offset_is_refused(self):
        # a negative offset would GROW the part into the tissue — refused, not clamped
        with pytest.raises(ValueError, match="into the tissue"):
            build_final_product(_round_body(), gingival_offset_mm=-0.1)

    @pytest.mark.slow
    def test_a_relief_that_fragments_the_part_fails_the_export_closed(self, tmp_path):
        # The relief is a PROPOSAL the G5 gate still judges. make_scan_body_mesh's
        # anti-rotation flat sits 0.4mm off the axis, so the client's 0.20mm relief eats
        # through it and leaves 3 disconnected bodies — the export must fail CLOSED with
        # nothing written, never quietly ship a fragmented part or quietly reduce the
        # relief the lab asked for.
        from case_prep.adapters.output_package import emit_case_package
        from case_prep.adapters.output_package import SitePackageSpec

        product = build_final_product(make_scan_body_mesh(), screw_radius_mm=1.0,
                                      gingival_offset_mm=0.20)
        assert product.body_count > 1
        spec = SitePackageSpec(tooth=8, implant_model="certain", variant_code="4.1",
                               vendor="dess", pose_matrix=np.eye(4), scan_coverage=0.5,
                               advisory=True)
        body = make_scan_body_mesh()
        with pytest.raises(ValueError, match="package NOT emitted"):
            emit_case_package("frag", trimesh.creation.box(extents=[20, 20, 4]), "upper",
                              [(spec, body, body)], tmp_path,
                              final_product_mesh={8: product})
        assert not (tmp_path / "frag-8-prosthesis_cad.stl").exists()


class TestMeasureDeliveredChannel:
    def test_refuses_an_unbored_solid(self):
        # honesty: no hole -> no channel reading, never a guess
        assert measure_delivered_channel(
            trimesh.creation.cylinder(radius=2.5, height=8.0, sections=48)) is None

    @pytest.mark.slow
    def test_refuses_a_breached_channel(self):
        # the synthetic scan body's anti-rotation flat sits at x=0.4, so the legacy
        # origin bore (r=1.0) cuts THROUGH the flat: an open groove, not a channel.
        # The measurement must refuse it — a groove read as a channel would hide
        # exactly the wall-breach failure G5's gate exists for.
        product = build_final_product(make_scan_body_mesh(), screw_radius_mm=1.0)
        assert measure_delivered_channel(product) is None


@pytest.mark.slow
def test_auto_flow_emits_the_production_set(tmp_path):
    """End-to-end: with product generation on (the default), the package contains the
    production files — the billable final product, made by US, no external CAD handoff."""
    from case_prep.adapters.cap_library import CapLibrary
    from case_prep.adapters.real_case import build_embedded_case
    from case_prep.adapters.synthetic import make_gingiva_arch
    from case_prep.domain.cap_catalog import CapSpec
    from case_prep.pipeline.auto_flow import ConfirmedSite, run_auto_case

    np.random.seed(0)
    arch_path = tmp_path / "arch.stl"
    make_gingiva_arch(np.random.default_rng(0)).export(arch_path)
    cad_path = tmp_path / "cap.stl"
    make_scan_body_mesh().export(cad_path)
    case = tmp_path / "case"
    gt = build_embedded_case(arch_path, cad_path, case, n_implants=1, seed=1)
    scan = trimesh.load(case / "scan.stl", force="mesh")
    lib = CapLibrary.single(CapSpec("certain", "4.1"),
                            trimesh.load(case / "library/certain3i_4_1/mesh.stl",
                                         force="mesh"))

    out = tmp_path / "out"
    # gingival_offset_mm=0.0 DELIBERATELY (2026-07-25): the stand-in construction body is
    # make_scan_body_mesh, whose anti-rotation flat sits 0.4mm off the axis — the r=1.0
    # origin bore already cuts through it (pinned in TestMeasureDeliveredChannel), so the
    # client's 0.20mm relief fragments this FIXTURE into 3 bodies and the G5 gate rightly
    # fails the export closed. That interaction is pinned in its own test below; this one
    # is about the production set being emitted at all.
    summary = run_auto_case(
        case_id="prod", scan=scan, library=lib,
        construction_mesh=make_scan_body_mesh(), vendor="dess",
        confirmed=[ConfirmedSite(tooth=8, center=tuple(map(float, gt.poses[0].position)))],
        jaw_label="upper", out_dir=out, gingival_offset_mm=0.0)

    files = {p.name for p in out.iterdir()}
    assert "prod-8-prosthesis_cad.stl" in files       # the final product mesh
    assert "prod-8-construction.json" in files        # its CAM sidecar
    assert summary["sites"][0]["production"]["screw_channel_radius_mm"] == 1.0
    # the relief the part was actually cut with is a row fact AND rides in the paid record
    assert summary["sites"][0]["production"]["gingival_offset_mm"] == 0.0
    rec = json.loads((out / "prod-8-implant.json").read_text())
    assert rec["audit"]["gingival_offset_mm"] == 0.0
    # nothing was relieved, so nothing was measured — None, not a fabricated 0.0
    assert summary["sites"][0]["gingival_offset"] is None
    assert "gingival_clearance" not in rec["audit"]


@pytest.mark.slow
def test_the_real_run_records_the_achieved_clearance_not_just_the_ask(tmp_path):
    """END-TO-END on the real dess part at the client's 0.20mm default: the run row AND
    the paid record must carry what the relief MEASURES, next to what was asked for.

    This is the honesty fix (2026-07-25): the pipeline used to record "gingival_offset_mm:
    0.20" and nothing else, while the delivered part carries a median ~0.13mm — the record
    was overstating the patient's clearance by roughly a third."""
    from case_prep.adapters.cap_library import CapLibrary
    from case_prep.pipeline.auto_flow import ConfirmedSite, run_auto_case

    root = Path(__file__).resolve().parents[1] / "data/real"
    if not (root / "scans/doctor-295811960-neodent-gm").exists():
        pytest.skip("real arch not present")
    out = tmp_path / "out"
    summary = run_auto_case(
        case_id="clr", scan=trimesh.load(
            root / "scans/doctor-295811960-neodent-gm/lower_jaw.stl", force="mesh"),
        library=CapLibrary.load(root / "library/caps/neodent-gm"),
        construction_mesh=trimesh.load(
            root / "library/construction/dess/neodent-gm-scanbody.stl", force="mesh"),
        vendor="dess", confirmed=[ConfirmedSite(29, (12.3, 9.8, 19.4))],
        jaw_label="lower", out_dir=out, render_qc=False,
        gingival_offset_mm=0.20)

    row = summary["sites"][0]
    assert row["production"]["gingival_offset_mm"] == 0.20     # what the lab asked
    achieved = row["gingival_offset"]                          # what the part carries
    assert achieved["requested_mm"] == 0.20
    assert 0.05 < achieved["achieved_median_mm"] < 0.20
    assert (achieved["achieved_p10_mm"] <= achieved["achieved_median_mm"]
            <= achieved["achieved_p90_mm"])
    assert achieved["method"], "the row must say HOW the clearance was measured"

    rec = json.loads((out / "clr-29-implant.json").read_text())
    assert rec["audit"]["gingival_clearance"] == achieved
    manifest = json.loads((out / "clr-manifest.json").read_text())
    assert manifest["gingival_clearance"] == [{"tooth": 29, **achieved}]


@pytest.mark.slow
def test_open_shell_vendor_cad_still_yields_a_full_solid():
    """Real vendor CADs arrive as OPEN shells (no base) — the SDF must not hollow them to a
    fragment (measured failure: 0.1 mm^3 from the real DESS part before boundary capping)."""
    shell = trimesh.creation.cylinder(radius=2.5, height=8.0, sections=48)
    # knock the bottom cap off -> an open shell like a vendor scan-body CAD
    keep = shell.face_normals[:, 2] > -0.9
    open_shell = trimesh.Trimesh(shell.vertices, shell.faces[keep], process=False)
    assert not open_shell.is_watertight

    product = build_final_product(open_shell, screw_radius_mm=1.0)
    assert product.is_watertight
    assert product.volume > 80.0  # a real solid (cylinder ~157 mm^3 minus the ~25 mm^3 bore)
    assert product.extents.max() > 7.0  # full height preserved, not a collapsed fragment
