"""Screw-channel geometry read from a template's open BOUNDARY LOOPS — the CAD's own
zero-noise record of where the channel is (G2, master plan §7.4; autopsy 2026-07-23).

The catalog cap CADs carry the channel EXACTLY: each template has two open boundary
loops — the bore MOUTH (measured r 1.078-1.152mm, within 0.03mm of the template top)
and the BASE OPENING (r 1.753-2.261mm, at the template bottom) — and both are perfect
circles (radial std <= 0.0023mm about the fitted centre, planar z std <= 0.0023mm,
measured across all 12 variants). The two loops share xy to <= 0.001mm (fitted
centres): one straight channel, near-parallel to the canonical axis. Reading them is
pure topology (``trimesh.outline``) plus a least-squares circle fit, so the read is
deterministic, needs no sampling, no RNG, and no IO.

This module exists because the surface-centroid bore estimate was POISONED: a hole
contributes no vertices, so a top-core centroid is repelled from the bore — measured
0.87-1.06mm from the loop truth at ~174deg the wrong azimuth, on every variant. The
loop read supersedes it wherever a loop exists.

Envelope (each constant carries its measured receipt; refuse outside it rather than
guess):
- loops with fewer than 24 points carry too little evidence (real loops: 221-328);
- a channel circle is FLAT (z std <= 0.10mm) and ROUND (radial std <= 0.08mm about
  the fitted centre; worst catalog loop measures 0.0023);
- the mouth opens at the TOP: within 2.0mm of the template's z-max (measured <= 0.03);
- a mouth/base pair is claimed only when concentric to <= 0.30mm (measured <= 0.001)
  and separated by > 0.5mm of height — otherwise the mouth is returned alone and the
  axis stays None (an axis across a non-concentric pair would be a silent guess; the
  vendor spec, not this reader, arbitrates angulated-channel systems).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np
import trimesh

_MIN_LOOP_POINTS = 24          # real channel loops discretize to 221-328 points
_MAX_RADIAL_STD_MM = 0.08      # measured catalog max 0.0023 about the FITTED centre
#                                (0.052 about the vertex mean was the mean's own bias
#                                 on the non-uniformly discretized zimmer-7030 mouth)
_MAX_PLANE_STD_MM = 0.10       # measured catalog max 0.0023
_MOUTH_TOP_PROXIMITY_MM = 2.0  # measured mouth-to-top gap <= 0.03
_MAX_MOUTH_BASE_XY_MM = 0.30   # measured mouth/base xy disagreement <= 0.001 (fitted)
_MIN_MOUTH_BASE_DZ_MM = 0.5    # mouth and base are distinct heights (measured 3.35-5.44)
_MOUTH_RADIUS_RANGE_MM = (0.3, 3.0)  # screw-channel scale: catalog mouths 1.078-1.152,
#                                      DESS construction lumen 2.00


@dataclass
class ChannelGeometry:
    """The channel as the CAD's boundary loops state it, canonical frame, mm.

    ``axis`` points +z-ward and exists only when a concentric base loop pairs with
    the mouth; ``base_*`` are None when no loop qualifies as the same channel's other
    end. (Plain dataclass: numpy fields make ``frozen=True`` a false promise — same
    review finding as CapLibrary.)"""

    mouth_centre: np.ndarray          # (3,) channel mouth circle centre
    mouth_radius: float
    base_centre: Optional[np.ndarray]  # (3,) base opening circle centre, or None
    base_radius: Optional[float]
    axis: Optional[np.ndarray]         # (3,) unit direction, or None


def _circle_read(loop_pts: np.ndarray) -> Optional[Tuple[np.ndarray, float]]:
    """(centre 3D, radius) when the polyline is a flat, round, well-sampled circle;
    None otherwise. The xy centre is the least-squares (Kasa) circle fit — the
    project's standard — NOT the vertex mean: a non-uniformly discretized loop biases
    the mean off the true centre (measured on the zimmer-7030 mouth 2026-07-23: mean
    0.079mm from the fitted centre, radial std 0.052 about the mean vs 0.002 about
    the fit — the loop is a perfect circle; the mean was not its centre, and the
    autopsy's published truth xy is the FITTED read)."""
    p = np.asarray(loop_pts, float)
    if len(p) >= 2 and np.array_equal(p[0], p[-1]):
        p = p[:-1]  # closed polylines repeat the first vertex
    if len(p) < _MIN_LOOP_POINTS:
        return None
    if float(p[:, 2].std()) > _MAX_PLANE_STD_MM:
        return None
    A = np.c_[2.0 * p[:, :2], np.ones(len(p))]
    sol, *_ = np.linalg.lstsq(A, (p[:, :2] ** 2).sum(axis=1), rcond=None)
    cxy = sol[:2]
    radial = np.linalg.norm(p[:, :2] - cxy, axis=1)
    if float(radial.std()) > _MAX_RADIAL_STD_MM:
        return None
    centre = np.array([float(cxy[0]), float(cxy[1]), float(p[:, 2].mean())])
    return centre, float(radial.mean())


def channel_from_boundary_loops(mesh: trimesh.Trimesh) -> Optional[ChannelGeometry]:
    """Read the screw channel from ``mesh``'s open boundary loops; None when no loop
    qualifies (watertight, degenerate, or out-of-envelope geometry — callers fall
    back or refuse, they never get a guess)."""
    if len(mesh.faces) == 0 or len(mesh.vertices) < 3:
        return None
    outline = mesh.outline()
    if len(outline.entities) == 0:
        return None  # watertight: no boundary at all (``discrete`` chokes on empty)
    circles: List[Tuple[np.ndarray, float]] = []
    for loop in outline.discrete:
        read = _circle_read(loop)
        if read is not None:
            circles.append(read)
    if not circles:
        return None
    circles.sort(key=lambda cr: float(cr[0][2]))
    mouth_centre, mouth_radius = circles[-1]
    z_top = float(np.asarray(mesh.vertices, float)[:, 2].max())
    if z_top - float(mouth_centre[2]) > _MOUTH_TOP_PROXIMITY_MM:
        return None  # the highest circle is nowhere near the top — not a mouth
    lo, hi = _MOUTH_RADIUS_RANGE_MM
    if not (lo <= mouth_radius <= hi):
        return None  # not screw-channel scale

    base_centre: Optional[np.ndarray] = None
    base_radius: Optional[float] = None
    axis: Optional[np.ndarray] = None
    if len(circles) > 1:
        cand_centre, cand_radius = circles[0]
        dz = float(mouth_centre[2] - cand_centre[2])
        xy_gap = float(np.linalg.norm((mouth_centre - cand_centre)[:2]))
        if dz > _MIN_MOUTH_BASE_DZ_MM and xy_gap <= _MAX_MOUTH_BASE_XY_MM:
            base_centre, base_radius = cand_centre, cand_radius
            span = mouth_centre - cand_centre
            axis = span / float(np.linalg.norm(span))
    return ChannelGeometry(mouth_centre=mouth_centre, mouth_radius=mouth_radius,
                           base_centre=base_centre, base_radius=base_radius,
                           axis=axis)
