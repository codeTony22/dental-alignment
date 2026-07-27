"""Clocking = the rotational index of the implant connection about its axis.

Derived purely from a rotation matrix using a deterministic reference frame built
from the axis, so ground-truth and recovered poses are compared on the same basis.
The scan body's flat (anti-rotation) feature has its outward normal along local +x,
so column 0 of the rotation is the flat normal in world coordinates.
"""
from __future__ import annotations

import numpy as np


def clocking_angle_deg(rotation: np.ndarray) -> float:
    R = np.asarray(rotation, dtype=float).reshape(3, 3)
    axis = R[:, 2] / np.linalg.norm(R[:, 2])  # local +z mapped to world = implant axis
    flat_normal = R[:, 0]  # local +x mapped to world = flat feature normal

    ref = np.array([0.0, 0.0, 1.0])
    if abs(float(axis @ ref)) > 0.9:
        ref = np.array([1.0, 0.0, 0.0])
    u = np.cross(ref, axis)
    u = u / np.linalg.norm(u)
    v = np.cross(axis, u)

    angle = np.degrees(np.arctan2(float(flat_normal @ v), float(flat_normal @ u)))
    return float(angle % 360.0)
