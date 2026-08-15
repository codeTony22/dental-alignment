"""Pure SE(3) geometry for the case-prep domain.

No IO, no Open3D — just numpy. These are the primitives the registration
results are expressed in (an implant pose is a position + an axis, optionally
with a clocking angle), and the metrics layer measures error in these terms.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

ArrayLike = "np.ndarray | list"


@dataclass(frozen=True)
class Axis:
    """A unit-length 3D direction. Construct via ``from_vector`` to normalize."""

    direction: np.ndarray

    @classmethod
    def from_vector(cls, vector) -> "Axis":
        v = np.asarray(vector, dtype=float).reshape(3)
        norm = float(np.linalg.norm(v))
        if norm < 1e-12:
            raise ValueError("Cannot build an Axis from a zero-length vector")
        return cls(direction=v / norm)

    def is_unit(self, tol: float = 1e-9) -> bool:
        return abs(float(np.linalg.norm(self.direction)) - 1.0) < tol

    def angle_to(self, other: "Axis") -> float:
        """Unsigned angle to another axis, in degrees, in [0, 180]."""
        dot = float(np.clip(np.dot(self.direction, other.direction), -1.0, 1.0))
        return float(np.degrees(np.arccos(dot)))


@dataclass(frozen=True)
class RigidTransform:
    """A 4x4 homogeneous SE(3) transform (rotation + translation)."""

    matrix: np.ndarray

    @classmethod
    def identity(cls) -> "RigidTransform":
        return cls(np.eye(4))

    @classmethod
    def from_translation(cls, translation) -> "RigidTransform":
        m = np.eye(4)
        m[:3, 3] = np.asarray(translation, dtype=float).reshape(3)
        return cls(m)

    @classmethod
    def from_rotation(cls, rotation: np.ndarray) -> "RigidTransform":
        m = np.eye(4)
        m[:3, :3] = np.asarray(rotation, dtype=float).reshape(3, 3)
        return cls(m)

    @classmethod
    def from_axis_angle(cls, axis, degrees: float) -> "RigidTransform":
        """Rotation of ``degrees`` about ``axis`` (Rodrigues' formula)."""
        k = Axis.from_vector(axis).direction
        theta = np.radians(degrees)
        kx, ky, kz = k
        K = np.array([[0, -kz, ky], [kz, 0, -kx], [-ky, kx, 0]])
        R = np.eye(3) + np.sin(theta) * K + (1 - np.cos(theta)) * (K @ K)
        return cls.from_rotation(R)

    @property
    def rotation(self) -> np.ndarray:
        return self.matrix[:3, :3]

    @property
    def translation(self) -> np.ndarray:
        return self.matrix[:3, 3]

    def apply(self, points: np.ndarray) -> np.ndarray:
        pts = np.asarray(points, dtype=float)
        single = pts.ndim == 1
        pts = np.atleast_2d(pts)
        out = pts @ self.rotation.T + self.translation
        return out[0] if single else out

    def compose(self, other: "RigidTransform") -> "RigidTransform":
        """``self.compose(other)`` applies ``other`` first, then ``self``."""
        return RigidTransform(self.matrix @ other.matrix)

    def inverse(self) -> "RigidTransform":
        R = self.rotation
        m = np.eye(4)
        m[:3, :3] = R.T
        m[:3, 3] = -R.T @ self.translation
        return RigidTransform(m)


# --- THE AXIS-LOCKED FIT (client ruling 2026-08-15) ---------------------------------------
#
# "Point pair tools should not only be rotating, also down or up, it needs to match the
# points where the user added them, because the user is pointing to the holes in the
# library and scan and matching it."
#
# An operator who clicks THE SAME FEATURE on the library part and on the scan has stated
# a 3-D correspondence. Reading only its azimuth throws away two thirds of what they
# said. This is the primitive that reads all of it — under one restriction:
#
#   THE PART MAY TURN ABOUT ITS OWN AXIS AND SLIDE. IT MAY NEVER TILT.
#
# WHY THE AXIS IS LOCKED, and not merely fitted with the rest (Umeyama over the same
# points is one line away — ``icp._kabsch`` — and is deliberately NOT what this does):
# two clicks at ±0.3mm scatter, 3mm apart, buy an unconstrained tilt of many degrees,
# and the implant's axis is the one direction of this pose that the whole downstream
# package stands on (the channel, the emergence, the relief). The seated axis is the
# pipeline's OWN measurement over thousands of scan points; a two-click correction to it
# would be a strictly worse estimator wearing the operator's authority. The clock and
# the position are the two things the automation cannot read and a human can, so those
# are the two this fit is allowed to move.
#
# WHAT THE ESTIMATOR IS. Least squares over the correspondences, subject to that
# restriction — minimize sum |Rz(theta) p_i + d - q_i|^2. The minimizer is closed form:
# d is fixed by the centroids for any theta, and theta then follows from the centred
# in-plane cross/dot sums. Two properties fall out of the centring and are worth naming
# because both are load-bearing here:
#
#   - THE CLOCK IS PIVOT-INDEPENDENT. Only the centred points enter it, so the parallax
#     that made a self-consistent pair ask for -17.1 degrees (plan section 10-AJ, two
#     different rim centres serving as two angle pivots) cannot enter this estimator at
#     all: there is no pivot to get wrong.
#   - INVERSE VARIANCE IS ALREADY IN IT. For iid click noise, correspondence i carries
#     clock information |p_i - centroid|^2 -- exactly the lever-squared weight
#     ``adjust.observation_weight`` assigns a single click -- and the cross/dot sums
#     weight each point by precisely that. The equal-weighting bug cannot reappear here
#     because there is nothing to weight by hand.
#
# The lever a clock is read over is therefore the spread of the part points ABOUT THEIR
# CENTROID, not about the rim centre: with the position free, only relative geometry
# says anything about rotation. ``clock_baseline_mm`` reports it so the caller can apply
# its own measured floor (the same one a span's direction is judged by).


# below this the centred cross/dot sums are numerically nothing (mm^2), so the angle
# they would name is floating-point residue rather than geometry
_CLOCK_INFORMATION_FLOOR_MM2 = 1e-12


@dataclass(frozen=True)
class AxisLockedFit:
    """What a set of 3-D correspondences asks a part to do, within one turn about its
    own axis and one slide.

    ``rotation_deg`` is CCW about +z of the frame the points are given in — so the
    caller expresses the correspondences in the part's CANONICAL frame, where the
    part's axis IS z. ``translation`` is in that same frame, in mm.

    ``residuals_mm`` is what each correspondence still misses by AFTER the fit, in the
    order given: the millimetres the operator can see between the point they clicked on
    the part and the point they clicked on the scan. It is a MEASUREMENT from two
    correspondences on (four parameters against six constraints) and a tautological
    zero from one — the caller decides what to say about that, and this returns the
    number either way.

    ``clock_baseline_mm`` is the in-plane spread of the SOURCE points about their own
    centroid, doubled so that two points report exactly their separation: the lever the
    rotation was read over. A short baseline means the angle is scatter, not signal."""

    rotation_deg: float
    translation: np.ndarray
    residuals_mm: np.ndarray
    clock_baseline_mm: float


def fit_axis_locked(source, target, *, allow_rotation: bool = True) -> AxisLockedFit:
    """The best turn-about-z-and-slide carrying ``source`` onto ``target``.

    ``allow_rotation=False`` fits the SLIDE ALONE (the centroid correspondence) and
    reports the turn it was forbidden to make as residual — the honest answer where a
    caller has decided the points carry no readable clock (one pair; a baseline under
    the caller's floor), and the reason a second estimator never had to be written for
    that rung.

    Raises ``ValueError`` on a malformed ask — mismatched counts, no correspondences,
    a non-finite coordinate. Operator input is validated by the application in the
    operator's own words long before it arrives here; reaching this with a NaN is a
    programming error, and returning a NaN pose would be worse than raising."""
    p = np.asarray(source, dtype=float)
    q = np.asarray(target, dtype=float)
    if p.ndim != 2 or p.shape[1:] != (3,) or q.shape != p.shape:
        raise ValueError(f"an axis-locked fit needs matching (n, 3) point sets — got "
                         f"{p.shape} and {q.shape}")
    if len(p) == 0:
        raise ValueError("an axis-locked fit needs at least one correspondence")
    if not (np.isfinite(p).all() and np.isfinite(q).all()):
        raise ValueError("an axis-locked fit needs finite coordinates on both halves")

    cp, cq = p.mean(axis=0), q.mean(axis=0)
    a, b = p - cp, q - cq
    # the lever the clock is read over: RMS in-plane spread about the centroid, doubled
    # so two correspondences report exactly the separation between them
    baseline = 2.0 * float(np.sqrt(np.mean((a[:, :2] ** 2).sum(axis=1))))
    cross = float((a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]).sum())
    dot = float((a[:, 0] * b[:, 0] + a[:, 1] * b[:, 1]).sum())
    # A SINGLE CORRESPONDENCE (and any degenerate set) lands here with both sums at
    # zero: atan2(0, 0) is 0.0 in IEEE, but a rotation that exists only because of a
    # floating-point convention is not a measurement. The floor makes the answer
    # explicit rather than incidental.
    turn = allow_rotation and math.hypot(cross, dot) > _CLOCK_INFORMATION_FLOOR_MM2
    theta = math.degrees(math.atan2(cross, dot)) if turn else 0.0
    c, s = math.cos(math.radians(theta)), math.sin(math.radians(theta))
    rot = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])
    translation = cq - rot @ cp
    residuals = np.linalg.norm(p @ rot.T + translation - q, axis=1)
    return AxisLockedFit(rotation_deg=float(theta), translation=translation,
                         residuals_mm=residuals, clock_baseline_mm=baseline)
