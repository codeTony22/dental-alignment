"""Pure SE(3) geometry for the case-prep domain.

No IO, no Open3D — just numpy. These are the primitives the registration
results are expressed in (an implant pose is a position + an axis, optionally
with a clocking angle), and the metrics layer measures error in these terms.
"""
from __future__ import annotations

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
