"""The dental boolean operations (design 6.5), via SDF-CSG so they survive messy meshes:
screw-access channel (subtract), abutment post (union), cement gap (offset)."""
import numpy as np
import trimesh

from case_prep.adapters.booleans import add_abutment_post, offset_surface, screw_channel


def _solid_cylinder(radius=4.0, height=10.0):
    m = trimesh.creation.cylinder(radius=radius, height=height, sections=48)
    return m  # centred at origin, axis +z, watertight


def test_screw_channel_bores_a_hole_along_the_axis():
    block = _solid_cylinder()
    out = screw_channel(block, position=[0, 0, 0], axis=[0, 0, 1], radius=1.2, length=14.0, pitch=0.3)
    assert out.is_watertight
    assert out.volume < block.volume  # material removed
    # a point on the axis is now OUTSIDE the solid (inside the bore)
    assert not out.contains([[0.0, 0.0, 0.0]])[0]
    # a point in the wall is still inside
    assert out.contains([[3.0, 0.0, 0.0]])[0]


def test_abutment_post_union_adds_material():
    base = trimesh.creation.icosphere(subdivisions=3, radius=3.0)
    out = add_abutment_post(base, position=[0, 0, 0], axis=[0, 0, 1], radius=1.0, length=8.0, pitch=0.3)
    assert out.is_watertight
    assert out.volume > base.volume  # post added on top


def test_offset_inflates_the_surface():
    base = trimesh.creation.icosphere(subdivisions=3, radius=3.0)
    out = offset_surface(base, distance=0.5, pitch=0.2)
    assert out.is_watertight
    assert out.volume > base.volume


def test_screw_channel_is_robust_on_a_nonwatertight_mesh():
    block = _solid_cylinder()
    rng = np.random.default_rng(0)
    block.update_faces(rng.random(len(block.faces)) > 0.1)  # punch holes
    block.remove_unreferenced_vertices()
    assert not block.is_watertight
    out = screw_channel(block, position=[0, 0, 0], axis=[0, 0, 1], radius=1.2, length=14.0, pitch=0.3)
    assert out.is_watertight  # SDF-CSG closes the holes AND bores the channel
