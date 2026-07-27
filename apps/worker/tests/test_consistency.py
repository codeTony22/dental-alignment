"""Multi-implant geometric consistency — replacing the no-op with a real, conservative check.

The gate's ``multi_implant_consistent`` signal previously reflected only the COUNT match; two
registered implants occupying the same space, or diverging beyond any clinical protocol, sailed
through. The check is deliberately conservative (it flags only impossible/implausible geometry,
never legitimate tilted-implant protocols like All-on-4 at ~30-45°), and every flag carries an
explainable reason — this feeds a clinical-safety gate.
"""
from __future__ import annotations

import pytest

from case_prep.domain.consistency import multi_implant_consistency
from case_prep.domain.geometry import Axis
from case_prep.domain.poses import Pose6DoF


def _pose(x, y, z, axis=(0, 0, 1.0)):
    return Pose6DoF(position=[float(x), float(y), float(z)],
                    axis=Axis.from_vector(list(axis)), clocking_degrees=None)


class TestMultiImplantConsistency:
    def test_single_implant_is_trivially_consistent(self):
        ok, reasons = multi_implant_consistency([_pose(0, 0, 0)])
        assert ok and reasons == []

    def test_spaced_parallel_implants_are_consistent(self):
        ok, reasons = multi_implant_consistency([_pose(0, 0, 0), _pose(10, 0, 0)])
        assert ok and reasons == []

    def test_overlapping_platforms_flag_with_reason(self):
        ok, reasons = multi_implant_consistency([_pose(0, 0, 0), _pose(2.0, 0, 0)])
        assert not ok
        assert any("2.0mm" in r and "spacing" in r for r in reasons)

    def test_allon4_style_tilt_is_allowed(self):
        # ~30-45° inter-implant divergence is a legitimate clinical protocol — never flag it
        tilted = _pose(12, 0, 0, axis=(0.64, 0, 0.77))  # ~40° off vertical
        ok, reasons = multi_implant_consistency([_pose(0, 0, 0), tilted])
        assert ok, reasons

    def test_extreme_axis_divergence_flags(self):
        sideways = _pose(12, 0, 0, axis=(1.0, 0, 0.2))  # ~79° off the neighbour's axis
        ok, reasons = multi_implant_consistency([_pose(0, 0, 0), sideways])
        assert not ok
        assert any("divergence" in r for r in reasons)

    def test_all_pairs_are_checked(self):
        poses = [_pose(0, 0, 0), _pose(10, 0, 0), _pose(11.5, 0, 0)]  # 2nd/3rd too close
        ok, reasons = multi_implant_consistency(poses)
        assert not ok and len(reasons) == 1

    def test_empty_is_consistent(self):
        assert multi_implant_consistency([]) == (True, [])


def test_loader_flags_identity_platform_transform(tmp_path):
    """The identity placeholder transform means the derived pose is the SCAN BODY's, not the
    implant platform's — the loader must say so (platform_transform_known=False)."""
    import json
    import numpy as np
    from case_prep.adapters.loader import load_case
    from case_prep.adapters.synthetic import SyntheticParams, generate_case

    generate_case(tmp_path, SyntheticParams(seed=1, n_implants=1))
    case = load_case(tmp_path)
    part = next(iter(case.library.values()))
    assert part.platform_transform_known  # synthetic writes a real -1.5mm z translation

    tf = tmp_path / "library" / "synthetic_sb" / "transform.json"
    tf.write_text(json.dumps({"scan_body_to_platform": np.eye(4).tolist()}))
    part2 = next(iter(load_case(tmp_path).library.values()))
    assert not part2.platform_transform_known


def test_derive_pose_contract_with_rotational_platform_transform():
    """CONTRACT (documented, not aspirational): _derive_pose honors the platform transform's
    TRANSLATION fully (platform position = registered transform applied to the local platform
    point), but the implant AXIS is the scan body's +z — i.e. the body and platform are assumed
    COAXIAL. Every system in the current catalog is coaxial; an angulated-interface system
    would need the axis composed through the platform rotation (flagged in the docstring)."""
    import numpy as np
    from case_prep.adapters.loader import LibraryPart
    from case_prep.domain.geometry import RigidTransform
    from case_prep.domain.poses import Retention
    from case_prep.pipeline.orchestrator import _derive_pose

    # platform transform WITH rotation (90deg about x) AND offset
    m = RigidTransform.from_axis_angle([1, 0, 0], 90.0).matrix.copy()
    m[:3, 3] = [0.0, 0.0, -2.0]
    part = LibraryPart(mesh=None, scan_body_to_platform=RigidTransform(m),
                       platform_transform_known=True)
    t = RigidTransform.from_translation([10.0, 5.0, 1.0])  # registered body pose

    pose = _derive_pose(t, part, Retention.CEMENT)
    assert np.allclose(pose.position, [10.0, 5.0, -1.0])   # translation fully honored
    assert np.allclose(pose.axis.direction, [0, 0, 1.0])   # axis = body +z (coaxial contract)
