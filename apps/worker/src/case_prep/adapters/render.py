"""Best-effort 3D visualization of a recovered case — so a human can *see* what the
pipeline did: the scan, where each implant was localized, the recovered axis, and the
ground-truth axis next to it. Uses matplotlib's Agg backend (Open3D offscreen rendering
is unavailable on this arm64 build). A render failure never breaks a run.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence

import numpy as np


class ImplantViz:
    """Everything needed to draw one implant: recovered + ground-truth pose, gate, errors."""

    def __init__(self, tooth, retention, position, axis, gate_passed,
                 position_error_mm, axis_error_deg, gt_position=None, gt_axis=None):
        self.tooth = tooth
        self.retention = retention
        self.position = np.asarray(position, float)
        self.axis = np.asarray(axis, float)
        self.gate_passed = gate_passed
        self.position_error_mm = position_error_mm
        self.axis_error_deg = axis_error_deg
        self.gt_position = None if gt_position is None else np.asarray(gt_position, float)
        self.gt_axis = None if gt_axis is None else np.asarray(gt_axis, float)


_PASS = "#0a7d28"
_FLAG = "#b00020"
_AXIS_LEN = 5.0  # mm drawn each way along the implant axis


def render_comparison(mesh_paths: dict, out_path) -> Optional[Path]:
    """Four-panel view of the comparison artifacts so the boolean relationships are
    visible at a glance: input+generated overlaid, the intersection (AND), the difference,
    and the modifications delta. Best-effort."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt  # noqa: F401
        import trimesh
    except Exception:
        return None
    try:
        def pts(p, n=2500):
            m = trimesh.load(p, force="mesh")
            v = np.asarray(m.vertices)
            return v[np.linspace(0, len(v) - 1, min(n, len(v))).astype(int)] if len(v) else v

        fig = plt.figure(figsize=(13, 3.6))
        panels = [
            ("input + generated", [("input", "#c9ccd6"), ("generated", "#b00020")]),
            ("intersection (AND)", [("intersection", "#0a7d28")]),
            ("difference (original − generated)", [("difference", "#185fa5")]),
            ("modifications (auto − truth)", [("modifications", "#ba7517")]),
        ]
        for i, (title, layers) in enumerate(panels, 1):
            ax = fig.add_subplot(1, 4, i, projection="3d")
            for key, color in layers:
                if key in mesh_paths and Path(mesh_paths[key]).exists():
                    p = pts(mesh_paths[key])
                    if len(p):
                        ax.scatter(p[:, 0], p[:, 1], p[:, 2], s=1, c=color, alpha=0.5, linewidths=0)
            ax.set_title(title, fontsize=8)
            ax.set_xticks([]); ax.set_yticks([]); ax.set_zticks([])
        fig.suptitle("Comparison artifacts — the five files a human inspects", fontsize=11, fontweight="bold")
        fig.tight_layout()
        out = Path(out_path)
        fig.savefig(out, dpi=120)
        plt.close(fig)
        return out
    except Exception:
        return None


def render_csg_slices(grid_before, values_before, values_after, title, out_path) -> Optional[Path]:
    """Render a 2D slice of the signed-distance field before/after a boolean, with the
    zero-level contour (the surface) highlighted. The clearest way to *see* SDF-CSG: the
    channel appears as a carved-out region of the field. Best-effort."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return None
    try:
        ny = grid_before.shape[1]
        xs = grid_before.coords[:, ny // 2, :, 0]
        zs = grid_before.coords[:, ny // 2, :, 2]
        sb = values_before[:, ny // 2, :]
        sa = values_after[:, ny // 2, :]
        lim = float(np.percentile(np.abs(sb), 95)) or 1.0

        fig, axes = plt.subplots(1, 2, figsize=(11, 4.6))
        for ax, field, sub in ((axes[0], sb, "before"), (axes[1], sa, "after — channel bored")):
            ax.contourf(xs, zs, field, levels=24, cmap="RdBu", vmin=-lim, vmax=lim)
            ax.contour(xs, zs, field, levels=[0.0], colors="k", linewidths=1.6)
            ax.set_title(sub, fontsize=10)
            ax.set_aspect("equal", "box")
            ax.set_xlabel("x (mm)"); ax.set_ylabel("z (mm)")
        fig.suptitle(title, fontsize=12, fontweight="bold")
        fig.tight_layout()
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, dpi=110)
        plt.close(fig)
        return out
    except Exception:
        return None


def render_scenario(
    scan_points: np.ndarray,
    implants: Sequence[ImplantViz],
    title: str,
    out_path,
    max_points: int = 4000,
) -> Optional[Path]:
    """Render a 3D perspective + a top-down XY view. Returns the PNG path, or None on failure."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt  # noqa: F401  (registers 3d projection)
    except Exception:
        return None

    try:
        pts = np.asarray(scan_points, float)
        if len(pts) > max_points:
            idx = np.linspace(0, len(pts) - 1, max_points).astype(int)
            pts = pts[idx]

        fig = plt.figure(figsize=(12, 5.2))
        ax3d = fig.add_subplot(1, 2, 1, projection="3d")
        axxy = fig.add_subplot(1, 2, 2)

        ax3d.scatter(pts[:, 0], pts[:, 1], pts[:, 2], s=1, c="#c9ccd6", alpha=0.35, linewidths=0)
        axxy.scatter(pts[:, 0], pts[:, 1], s=1, c="#c9ccd6", alpha=0.4, linewidths=0)

        for im in implants:
            color = _PASS if im.gate_passed else _FLAG
            p, a = im.position, im.axis / (np.linalg.norm(im.axis) or 1.0)
            seg = np.vstack([p - a * _AXIS_LEN, p + a * _AXIS_LEN])
            # recovered axis (solid, gate-coloured)
            ax3d.plot(seg[:, 0], seg[:, 1], seg[:, 2], c=color, lw=2.5)
            ax3d.scatter(*p, c=color, s=36, depthshade=False)
            axxy.plot(seg[:, 0], seg[:, 1], c=color, lw=2.5)
            axxy.scatter(p[0], p[1], c=color, s=30)
            label = f"#{im.tooth} {'PASS' if im.gate_passed else 'FLAG'} " \
                    f"{im.position_error_mm:.02f}mm/{im.axis_error_deg:.01f}°"
            axxy.annotate(label, (p[0], p[1]), textcoords="offset points",
                          xytext=(6, 6), fontsize=8, color=color)
            # ground-truth axis (dashed grey) for visual comparison
            if im.gt_position is not None and im.gt_axis is not None:
                g, ga = im.gt_position, im.gt_axis / (np.linalg.norm(im.gt_axis) or 1.0)
                gseg = np.vstack([g - ga * _AXIS_LEN, g + ga * _AXIS_LEN])
                ax3d.plot(gseg[:, 0], gseg[:, 1], gseg[:, 2], c="#444", lw=1.0, ls="--")
                axxy.plot(gseg[:, 0], gseg[:, 1], c="#444", lw=1.0, ls="--")

        ax3d.set_title("recovered pose (solid = gate, dashed = ground truth)", fontsize=9)
        ax3d.set_xlabel("x"); ax3d.set_ylabel("y"); ax3d.set_zlabel("z")
        axxy.set_title("top-down (XY)", fontsize=9)
        axxy.set_xlabel("x"); axxy.set_ylabel("y"); axxy.set_aspect("equal", "datalim")
        fig.suptitle(title, fontsize=12, fontweight="bold")
        fig.tight_layout()

        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, dpi=110)
        plt.close(fig)
        return out
    except Exception:
        return None
