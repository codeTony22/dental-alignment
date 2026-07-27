"""Real-file comparison demo: take the doctor's real input scan + the scan body, run our
pipeline, and compare WHAT WE GENERATE (the recovered scan-body placement) against the
REFERENCE (the true scan body, from the segmented file). Emits real STL artifacts and a
render with the error made visible.

Honest scope: with no clean library CAD or platform transform yet, "what we generate" is
the segmented body re-registered to the arch — so this measures how well registration
recovers a known placement on real geometry, and shows the gap the library CAD will close.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import trimesh

from case_prep.adapters import open3d_engine as engine
from case_prep.adapters.booleans import mesh_boolean
from case_prep.adapters.ingest import canonicalize_library
from case_prep.domain.geometry import Axis
from case_prep.domain.metrics import axis_error_deg, position_error_mm
from case_prep.domain.poses import Retention


def _render(arch_pts, true_pts, our_pts, pos_err, axis_err, conf, out_path) -> Optional[Path]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return None
    try:
        a = arch_pts[np.linspace(0, len(arch_pts) - 1, 5000).astype(int)]
        fig = plt.figure(figsize=(13, 4.6))
        ax = fig.add_subplot(1, 3, 1, projection="3d")
        ax.scatter(a[:, 0], a[:, 1], a[:, 2], s=1, c="#d7d9e0", alpha=0.3, linewidths=0)
        ax.scatter(true_pts[:, 0], true_pts[:, 1], true_pts[:, 2], s=4, c="#0a7d28", alpha=0.7, linewidths=0, label="reference (true)")
        ax.scatter(our_pts[:, 0], our_pts[:, 1], our_pts[:, 2], s=4, c="#b00020", alpha=0.7, linewidths=0, label="generated (ours)")
        ax.set_title("real arch + true (green) vs ours (red)", fontsize=9)
        ax.legend(fontsize=7, loc="upper right")
        c = true_pts.mean(0)
        for axx in (ax,):
            axx.set_xlim(c[0] - 12, c[0] + 12); axx.set_ylim(c[1] - 12, c[1] + 12); axx.set_zlim(c[2] - 12, c[2] + 12)

        ax2 = fig.add_subplot(1, 3, 2, projection="3d")
        ax2.scatter(true_pts[:, 0], true_pts[:, 1], true_pts[:, 2], s=5, c="#0a7d28", alpha=0.6, linewidths=0)
        ax2.scatter(our_pts[:, 0], our_pts[:, 1], our_pts[:, 2], s=5, c="#b00020", alpha=0.6, linewidths=0)
        ax2.set_title("scan-body overlay (zoom)", fontsize=9)

        ax3 = fig.add_subplot(1, 3, 3)
        ax3.axis("off")
        ax3.text(0.05, 0.8, "Generated vs reference", fontsize=12, fontweight="bold")
        ax3.text(0.05, 0.60, f"position error:  {pos_err:.2f} mm", fontsize=11)
        ax3.text(0.05, 0.48, f"axis error:      {axis_err:.1f}°", fontsize=11)
        ax3.text(0.05, 0.36, f"ICP fitness:     {conf.icp_fitness:.2f}", fontsize=11)
        ax3.text(0.05, 0.24, f"surface RMSE:    {conf.inlier_rmse_mm:.3f} mm", fontsize=11)
        ax3.text(0.05, 0.05, "clinical target <0.1mm — gap closes with the\nclean library CAD + defined axis", fontsize=9, color="#666")

        fig.suptitle("REAL Certain 3i — our output vs the reference scan body", fontsize=12, fontweight="bold")
        fig.tight_layout()
        out = Path(out_path); fig.savefig(out, dpi=115); plt.close(fig)
        return out
    except Exception:
        return None


def run_real_demo(scan_path, scanbody_path, out_dir) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    arch = trimesh.load(scan_path, force="mesh")
    sb = trimesh.load(scanbody_path, force="mesh")
    arch_pts = np.asarray(arch.vertices, float)

    lib_local, placement = canonicalize_library(sb)
    true_pos = placement.translation
    true_axis = Axis.from_vector(placement.rotation @ np.array([0.0, 0.0, 1.0]))

    # operator seeds on the body; we register the (canonical) library back onto the arch
    seed = true_pos + true_axis.direction * 4.0
    loc = engine.localize_from_seed(arch_pts, seed, radius=6.0)
    transform, conf = engine.register(loc, lib_local, Retention.CEMENT)

    ours = lib_local.copy(); ours.apply_transform(transform.matrix)   # what we generate
    reference = sb.copy()                                              # the true scan body

    paths = {}
    for key, mesh in (("01_input_arch", arch), ("02_reference_true_scanbody", reference),
                      ("03_generated_ours", ours)):
        p = out / f"{key}.stl"; mesh.export(p); paths[key] = p
    try:
        mesh_boolean(ours, reference, "intersection", 0.2).export(out / "04_overlap_AND.stl")
        mesh_boolean(ours, reference, "difference", 0.2).export(out / "05_error_ours_minus_true.stl")
    except Exception:
        pass

    pos_err = position_error_mm(transform.apply(lib_local.vertices.mean(0)), true_pos)
    axis_err = axis_error_deg(Axis.from_vector(transform.rotation @ np.array([0.0, 0.0, 1.0])), true_axis)
    render = _render(arch_pts, np.asarray(reference.vertices), np.asarray(ours.vertices),
                     pos_err, axis_err, conf, out / "real_demo.png")
    return {"position_error_mm": pos_err, "axis_error_deg": axis_err,
            "icp_fitness": conf.icp_fitness, "rmse_mm": conf.inlier_rmse_mm,
            "render": render, "artifacts": paths}
