"""Adapter: per-site QC ACCEPTANCE renders (the difference-map convention a lab tech
accepts by — ZimVie difference-map / Control-X style).

Two PNGs per implant site, both drawn in the posed template's CANONICAL frame
(occlusal top-down), both REPORTING ONLY — nothing here may ever move a pose:

1. ``<case>-<tooth>-clockview.png`` — the rotational acceptance view: scan points near
   the cap colored by depth below the template top (viridis), the template's coded
   cutout cells overlaid (derived from the ``template_signature`` (theta, r) image —
   the same instrument production clocking reads), the posed bore centre (star), the
   scanned recess-void centre (X), and the row's clocking verdict as text.
2. ``<case>-<tooth>-deviation.png`` — the signed difference map: posed-template surface
   samples colored by signed distance to the nearest scan point (sign along the
   template's outward face normal; + = scan outside the surface), RdBu_r clamped to
   +/-0.5mm, with RMS/p90 over the cap-footprint inspection band. Like the fit_stats
   read-out, bore/recess samples are included as-is (the template has no surface for
   the scanner there — same convention as RealGUIDE's Registration Error dialog).

Determinism: the only sampling is seeded and SAVES/RESTORES the global RNG state
(pattern of ``template_signature``) — the pinned pipeline stream is untouched and two
runs read the same pose identically (byte-identity of the PNGs is not claimed)."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import trimesh
from scipy.spatial import cKDTree

from case_prep.domain.channel import channel_from_boundary_loops
from case_prep.domain.clock_signature import (N_R, N_THETA, R_HI, R_LO,
                                              TemplateSignature, scan_rim_centre,
                                              template_signature)

_DEV_SAMPLES = 12000          # posed-surface samples for the difference map
_DEV_CLAMP_MM = 0.5           # display clamp of the signed scale (industry default)
_DEPTH_CLAMP_MM = 2.5         # clock-view depth colour clamp
_FOOTPRINT_BAND_MM = 1.2      # inspection band below ztop (matches top-face read-outs)

# The signed-deviation DISPLAY SCALE, published so the interactive three-panel overlay
# draws its colorbar on exactly the scale the acceptance PNG prints — a colour must mean
# the same millimetres in both, or the two views quietly disagree in front of the doctor.
DEVIATION_CLAMP_MM = _DEV_CLAMP_MM
DEVIATION_COLORMAP = "RdBu_r"
DEVIATION_FOOTPRINT_BAND_MM = _FOOTPRINT_BAND_MM


def _crop_canonical(scan_pts_world: np.ndarray, pose_matrix: np.ndarray,
                    rmax: float) -> np.ndarray:
    """Scan points in the template's canonical frame, cropped around the cap axis
    (same 8mm-style crop as the production clocking pass)."""
    pose = np.asarray(pose_matrix, float)
    canon = (np.asarray(scan_pts_world, float) - pose[:3, 3]) @ pose[:3, :3]
    r = np.linalg.norm(canon[:, :2], axis=1)
    return canon[r < max(8.0, 2.0 * rmax)]


def _bore_centre_canon(template: trimesh.Trimesh) -> Optional[np.ndarray]:
    """Screw-channel mouth centre, canonical frame — the boundary-loop truth read
    (domain/channel.py), mirroring the pipeline's ``_template_bore_centre`` without
    importing the pipeline layer. The pre-2026-07-23 top-core centroid drew the star
    0.87-1.06mm from the real bore at ~174deg the wrong azimuth (hole-repelled
    centroid); it survives only as the loopless-mesh fallback, with its known
    4020/4030 cut-sensitivity — display marker only."""
    ch = channel_from_boundary_loops(template)
    if ch is not None:
        return ch.mouth_centre
    v = np.asarray(template.vertices, float)
    top = v[v[:, 2] > v[:, 2].max() - 1.0]
    if len(top) < 30:
        return None
    rmax = float(np.percentile(np.linalg.norm(top[:, :2], axis=1), 95))
    core = top[np.linalg.norm(top[:, :2], axis=1) < 0.45 * rmax]
    if len(core) < 10:
        return None
    return core.mean(axis=0)


def _scan_void_centre(canon: np.ndarray, ztop: float, rmax: float,
                      centre_xy: np.ndarray) -> Optional[np.ndarray]:
    """Occlusal centre of the scanned screw-recess dip about the scan's own rim centre —
    a DISPLAY read-out (deepest-anchor cluster, depth-gated); the defended estimator
    with the reachability gate lives in the pipeline and stays authoritative."""
    near = canon[np.linalg.norm(canon[:, :2] - centre_xy, axis=1) < 0.9 * rmax]
    if len(near) < 100:
        return None
    z_top = float(np.percentile(near[:, 2], 85))
    below = near[(near[:, 2] < z_top - 0.35)
                 & (np.linalg.norm(near[:, :2] - centre_xy, axis=1) < 0.6 * rmax)]
    if len(below) < 40:
        return None
    anchor = below[int(np.argmin(below[:, 2]))]
    cluster = below[np.linalg.norm(below[:, :2] - anchor[:2], axis=1) < 1.3]
    if len(cluster) < 30:
        return None
    if z_top - float(np.percentile(cluster[:, 2], 10)) < 0.8:
        return None  # dimple, not a recess
    return cluster[:, :2].mean(axis=0)


def deviation_at_points(scan_pts_canon: np.ndarray, points: np.ndarray,
                        normals: np.ndarray, template: trimesh.Trimesh
                        ) -> Tuple[np.ndarray, Dict[str, object]]:
    """THE deviation kernel: signed scan deviation at arbitrary points ON the template
    surface (canonical frame), with the footprint stats.

    Factored out 2026-07-25 so the PNG path and the interactive three-panel overlay read
    the SAME instrument: ``signed_deviation`` feeds it seeded surface SAMPLES, and
    ``vertex_deviation`` feeds it the template's own VERTICES. Same points in, same
    numbers out — that agreement is a behavioral test, not a comment.

    Sign = along the surface normal supplied for each point (+ = the nearest scan point
    lies outside the surface). Stats (RMS, p90 of |signed|) are taken over the
    cap-footprint inspection band: radial <= 1.05*rmax AND z >= ztop - 1.2 — the region a
    tech actually inspects; collar points buried under gingiva are excluded.
    REPORTING ONLY — callers must never feed this back into a pose."""
    pts = np.asarray(scan_pts_canon, float)
    points = np.asarray(points, float)
    normals = np.asarray(normals, float)
    stats: Dict[str, object] = {"rms_mm": None, "p90_mm": None,
                                "n_footprint": 0, "n_samples": int(len(points))}
    if len(pts) < 10:
        return np.full(len(points), np.nan), stats

    d, idx = cKDTree(pts).query(points)
    vec = pts[idx] - points
    side = np.sign(np.einsum("ij,ij->i", vec, normals))
    side[side == 0] = 1.0
    signed = side * d

    sig = template_signature(template)
    footprint = ((np.linalg.norm(points[:, :2], axis=1) <= 1.05 * sig.rmax)
                 & (points[:, 2] >= sig.ztop - _FOOTPRINT_BAND_MM))
    stats["n_footprint"] = int(footprint.sum())
    if stats["n_footprint"] >= 20:
        fp = signed[footprint]
        stats["rms_mm"] = float(np.sqrt(np.mean(fp ** 2)))
        stats["p90_mm"] = float(np.percentile(np.abs(fp), 90))
    return signed, stats


def signed_deviation(scan_pts_canon: np.ndarray, template: trimesh.Trimesh,
                     n_samples: int = _DEV_SAMPLES
                     ) -> Tuple[np.ndarray, np.ndarray, Dict[str, object]]:
    """Signed scan deviation at seeded posed-template surface samples (canonical frame) —
    the difference-map PNG's own read. Thin wrapper over ``deviation_at_points``: the
    only thing it adds is the seeded surface sampling (RNG state saved/restored)."""
    state = np.random.get_state()
    try:
        np.random.seed(7)
        samples, fidx = trimesh.sample.sample_surface(template, n_samples)
    finally:
        np.random.set_state(state)
    samples = np.asarray(samples, float)
    normals = np.asarray(template.face_normals, float)[np.asarray(fidx, int)]
    signed, stats = deviation_at_points(scan_pts_canon, samples, normals, template)
    return samples, signed, stats


def vertex_deviation(scan_pts_world: np.ndarray, pose_matrix: np.ndarray,
                     template: trimesh.Trimesh
                     ) -> Tuple[np.ndarray, np.ndarray, Dict[str, object]]:
    """PER-VERTEX signed deviation of the POSED template against the scan — the colouring
    the three-panel union view draws (client's library-selection flow, 2026-07-25).

    Returns ``(posed_vertices_world, signed_mm, stats)``: the template's vertices carried
    into the jaw-scan world frame by ``pose_matrix`` (so the caller can hand the web a
    mesh it can render as-is), one signed millimetre per vertex, and the SAME footprint
    stats dict the deviation PNG prints — both come out of ``deviation_at_points``, so the
    two views cannot drift apart. Deterministic: no sampling at all on this path.
    REPORTING ONLY."""
    sig = template_signature(template)
    crop = _crop_canonical(scan_pts_world, pose_matrix, sig.rmax)
    verts = np.asarray(template.vertices, float)
    normals = np.asarray(template.vertex_normals, float)
    signed, stats = deviation_at_points(crop, verts, normals, template)
    pose = np.asarray(pose_matrix, float)
    posed = verts @ pose[:3, :3].T + pose[:3, 3]
    return posed, signed, stats


def _rim_circle(ax, rmax: float) -> None:
    th = np.linspace(0.0, 2.0 * np.pi, 181)
    ax.plot(rmax * np.cos(th), rmax * np.sin(th), ls="--", c="gray", lw=0.8,
            label="template rim (rmax)")


def _finish_axes(ax, rmax: float, title: str) -> None:
    lim = 1.6 * max(rmax, 1.0)
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    ax.set_aspect("equal")
    ax.set_xlabel("template x (mm)")
    ax.set_ylabel("template y (mm)")
    ax.set_title(title, fontsize=10)
    handles, _ = ax.get_legend_handles_labels()
    if handles:
        ax.legend(loc="lower right", fontsize=7)


def _clocking_text(clocking: Optional[Dict[str, object]]) -> str:
    if not clocking:
        return "clocking: n/a (icp seat)"
    shift = clocking.get("notch_shift_deg")
    cons = clocking.get("consistency_deg")
    lines = ["notch residual: " + ("%+.1f deg" % shift if shift is not None
                                   else "no reading"),
             "evidence: %s" % clocking.get("evidence", "none"),
             "consistency: " + ("%.1f deg" % cons if cons is not None else "n/a")]
    if clocking.get("rotation_unverified"):
        lines.append("ROTATION UNVERIFIED")
    return "\n".join(lines)


def _render_clockview(path: Path, crop: np.ndarray, sig: TemplateSignature,
                      template: trimesh.Trimesh,
                      clocking: Optional[Dict[str, object]], title: str,
                      delivered_channel_xy: Optional[np.ndarray] = None) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6.4, 5.4), dpi=110)
    sel = crop[(crop[:, 2] > sig.ztop - _DEPTH_CLAMP_MM) & (crop[:, 2] < sig.ztop + 0.6)]
    sel = sel[np.linalg.norm(sel[:, :2], axis=1) < 1.35 * sig.rmax]
    if len(sel):
        depth = np.clip(sig.ztop - sel[:, 2], 0.0, _DEPTH_CLAMP_MM)
        order = np.argsort(depth)  # deepest drawn last: the dips must stay visible
        sc = ax.scatter(sel[order, 0], sel[order, 1], c=depth[order], s=2.5,
                        cmap="viridis", vmin=0.0, vmax=_DEPTH_CLAMP_MM, linewidths=0)
        fig.colorbar(sc, ax=ax, label="scan depth below template top (mm)")
    else:
        ax.text(0.5, 0.5, "no scan points near cap top", transform=ax.transAxes,
                ha="center", fontsize=9, color="gray")

    _rim_circle(ax, sig.rmax)
    if sig.image.shape[1]:
        # coded cutout cells straight from the clocking instrument's own image (row-
        # zero-meaned: positive = deeper than that radius's mean = a cutout dip)
        thr = max(0.12, 0.4 * float(np.nanmax(sig.image)))
        ii, jj = np.where(np.nan_to_num(sig.image, nan=-1.0) > thr)
        if len(ii):
            th = np.radians((ii + 0.5) * (360.0 / N_THETA))
            rr = (R_LO + (sig.rows[jj] + 0.5) * (R_HI - R_LO) / N_R) * sig.rmax
            ax.scatter(rr * np.cos(th), rr * np.sin(th), s=26, facecolors="none",
                       edgecolors="crimson", linewidths=0.9,
                       label="template coded cutouts")
            for tb in np.unique(ii):
                a = np.radians((tb + 0.5) * 360.0 / N_THETA)
                ax.plot([R_LO * sig.rmax * np.cos(a), R_HI * sig.rmax * np.cos(a)],
                        [R_LO * sig.rmax * np.sin(a), R_HI * sig.rmax * np.sin(a)],
                        c="crimson", alpha=0.25, lw=0.8)

    bore = _bore_centre_canon(template)
    bx, by = (float(bore[0]), float(bore[1])) if bore is not None else (0.0, 0.0)
    ax.scatter([bx], [by], marker="*", s=150, c="gold", edgecolors="k",
               linewidths=0.6, label="posed bore centre", zorder=5)
    if delivered_channel_xy is not None:
        # G4: the channel the patient actually receives — MEASURED from the emitted
        # part (final_product.measure_delivered_channel on the un-posed product),
        # drawn next to the library bore and the scanned void so acceptance judges
        # the deliverable, not an estimator (§7.3: before 2026-07-23 the delivered
        # channel was never rendered anywhere)
        dc = np.asarray(delivered_channel_xy, float)
        ax.scatter([float(dc[0])], [float(dc[1])], marker="P", s=120, c="deepskyblue",
                   edgecolors="k", linewidths=0.6,
                   label="delivered channel (as built)", zorder=6)
    if len(crop) >= 30:
        c0 = scan_rim_centre(crop, sig.ztop, sig.rmax)
        void = _scan_void_centre(crop, sig.ztop, sig.rmax, c0)
        if void is not None:
            ax.scatter([void[0]], [void[1]], marker="x", s=90, c="k", linewidths=1.6,
                       label="scanned recess void centre", zorder=5)

    ax.text(0.02, 0.98, _clocking_text(clocking), transform=ax.transAxes, va="top",
            fontsize=8, family="monospace",
            bbox={"boxstyle": "round", "facecolor": "white", "alpha": 0.85})
    _finish_axes(ax, sig.rmax, title)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def _render_deviation(path: Path, samples: np.ndarray, signed: np.ndarray,
                      stats: Dict[str, object], sig: TemplateSignature,
                      title: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6.4, 5.4), dpi=110)
    finite = np.isfinite(signed)
    if finite.any():
        s, v = samples[finite], signed[finite]
        order = np.argsort(s[:, 2])  # occlusal view: top-face samples drawn last
        sc = ax.scatter(s[order, 0], s[order, 1],
                        c=np.clip(v[order], -_DEV_CLAMP_MM, _DEV_CLAMP_MM), s=3.0,
                        cmap="RdBu_r", vmin=-_DEV_CLAMP_MM, vmax=_DEV_CLAMP_MM,
                        linewidths=0)
        fig.colorbar(sc, ax=ax,
                     label="signed deviation (mm), + = scan outside surface")
    else:
        ax.text(0.5, 0.5, "no scan points near cap — no deviation reading",
                transform=ax.transAxes, ha="center", fontsize=9, color="gray")

    _rim_circle(ax, sig.rmax)
    if stats["rms_mm"] is not None:
        note = ("cap footprint: RMS %.2f mm   p90 %.2f mm   (n=%d samples)"
                % (stats["rms_mm"], stats["p90_mm"], stats["n_footprint"]))
    else:
        note = "cap footprint: insufficient samples for RMS/p90"
    ax.text(0.02, 0.98, note, transform=ax.transAxes, va="top", fontsize=8,
            family="monospace",
            bbox={"boxstyle": "round", "facecolor": "white", "alpha": 0.85})
    _finish_axes(ax, sig.rmax, title)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


# --- ALIGNMENT PROOF (operator-adjusted poses only) -----------------------------------
# The audit block already records WHAT the operator did (implant.json -> ``adjustments``,
# plus the append-only run-history stream). This is the PICTURE of it: the posed part over
# the scan crop it was moved onto, occlusal + one oblique, with the provenance printed on
# the image itself so the PNG stands alone in a case folder. REPORTING ONLY, and emitted
# ONLY for a site an operator actually touched — a clean automatic run does not need it.

_PROOF_AZIMUTH_DEG = 35.0     # oblique view direction: enough to separate the part's
_PROOF_ELEVATION_DEG = 22.0   # flank from its top face without hiding either
_PROOF_MAX_TEMPLATE_PTS = 4000
_PROOF_MAX_SCAN_PTS = 20000


def _oblique(pts: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Axonometric projection of canonical-frame points: returns (u, v, depth) for a view
    from ``_PROOF_AZIMUTH_DEG`` / ``_PROOF_ELEVATION_DEG``. Deterministic and cheap — a
    projection, not a renderer (the package carries meshes for anyone who wants a real
    3D view; this is the acceptance snapshot)."""
    az, el = np.radians(_PROOF_AZIMUTH_DEG), np.radians(_PROOF_ELEVATION_DEG)
    x, y, z = pts[:, 0], pts[:, 1], pts[:, 2]
    along = x * np.cos(az) + y * np.sin(az)          # horizontal, toward the viewer
    u = -x * np.sin(az) + y * np.cos(az)             # screen right
    v = z * np.cos(el) - along * np.sin(el)          # screen up
    depth = along * np.cos(el) + z * np.sin(el)      # nearer = larger
    return u, v, depth


def _thin(pts: np.ndarray, cap: int) -> np.ndarray:
    """Deterministic thinning (evenly spaced indices — never a random subsample, so two
    renders of the same pose draw the same points)."""
    if len(pts) <= cap:
        return pts
    return pts[np.linspace(0, len(pts) - 1, cap).astype(int)]


def _provenance_text(adjustments: List[Dict[str, object]]) -> str:
    """The who/what/how-much block printed on the proof, straight from the record the
    site's implant.json carries — this renderer never derives an operation, a magnitude
    or an identity of its own."""
    if not adjustments:
        return "no operator adjustment recorded"
    lines = [f"operator adjustments: {len(adjustments)}"]
    for adj in adjustments[-3:]:
        lines.append("  %s  %s" % (adj.get("ts", "?"), adj.get("operation", "?")))
        who, how = adj.get("who"), adj.get("detail")
        if who:
            lines.append("    by: %s" % who)
        if how:
            lines.append("    %s" % how)
    if len(adjustments) > 3:
        lines.insert(1, "  (showing the last 3)")
    return "\n".join(lines)


def render_alignment_proof(case_id: str, tooth: int, scan_pts: np.ndarray,
                           pose_matrix: np.ndarray, template: trimesh.Trimesh,
                           adjustments: List[Dict[str, object]],
                           out_dir: "Path | str") -> Path:
    """Write ``<case>-<tooth>-alignment-proof.png``: the posed part over the scan crop,
    occlusal + one oblique, with the operator-adjustment provenance printed on it.

    ``scan_pts`` and ``pose_matrix`` must share ONE frame (jaw world, or the pipeline's
    site-local crowns frame — the drawing is done in the pose's own canonical frame, which
    is identical either way, so callers pass whichever they already hold). ``template`` is
    the library part in its canonical frame, exactly as ``render_site_qc`` takes it;
    ``adjustments`` is the site's append-only adjustment record. Fully deterministic: no
    sampling anywhere (the part is drawn from its own vertices, the scan from evenly
    spaced indices), so the pinned pipeline RNG stream is untouched by construction."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    sig = template_signature(template)
    crop = _thin(_crop_canonical(scan_pts, pose_matrix, sig.rmax), _PROOF_MAX_SCAN_PTS)
    tv = _thin(np.asarray(template.vertices, float), _PROOF_MAX_TEMPLATE_PTS)

    fig, (ax_occ, ax_obl) = plt.subplots(1, 2, figsize=(11.2, 5.2), dpi=110)

    near = crop[np.linalg.norm(crop[:, :2], axis=1) < 1.6 * sig.rmax]
    if len(near):
        ax_occ.scatter(near[:, 0], near[:, 1], s=2.0, c="0.55", linewidths=0,
                       label="scan (site crop)")
    ax_occ.scatter(tv[:, 0], tv[:, 1], s=2.0, c="tab:orange", linewidths=0,
                   label="posed part")
    _rim_circle(ax_occ, sig.rmax)
    _finish_axes(ax_occ, sig.rmax, "occlusal — posed part over the scan")

    su, sv, sd = _oblique(near if len(near) else crop)
    tu, tvv, td = _oblique(tv)
    order = np.argsort(sd)
    ax_obl.scatter(su[order], sv[order], s=2.0, c="0.55", linewidths=0,
                   label="scan (site crop)")
    order = np.argsort(td)
    ax_obl.scatter(tu[order], tvv[order], s=2.0, c="tab:orange", linewidths=0,
                   label="posed part")
    ax_obl.set_aspect("equal")
    ax_obl.set_xlabel("view right (mm)")
    ax_obl.set_ylabel("view up (mm)")
    ax_obl.set_title("oblique (az %.0f°, el %.0f°) — seating against the scan"
                     % (_PROOF_AZIMUTH_DEG, _PROOF_ELEVATION_DEG), fontsize=10)
    ax_obl.legend(loc="lower right", fontsize=7)

    fig.suptitle("%s tooth %s — alignment proof (operator-adjusted pose)"
                 % (case_id, tooth), fontsize=11)
    fig.text(0.01, 0.01, _provenance_text(adjustments), va="bottom", ha="left",
             fontsize=7.5, family="monospace",
             bbox={"boxstyle": "round", "facecolor": "white", "alpha": 0.85})
    fig.tight_layout(rect=(0.0, 0.16, 1.0, 0.96))
    path = out / ("%s-%s-alignment-proof.png" % (case_id, tooth))
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def site_deviation_stats(scan_pts_world: np.ndarray, pose_matrix: np.ndarray,
                         template: trimesh.Trimesh) -> Dict[str, object]:
    """The deviation-map SCALARS without any rendering: crop the scan into the posed
    template's canonical frame and run ``signed_deviation`` — the exact math the
    deviation PNG prints, factored out so the run row and the renderer share one
    source (panel-completion wave, master plan §8 item 12: the panel's
    ``deviation_rms_mm`` read "missing" while the PNG printed the number).
    RNG-state-safe (``signed_deviation`` saves/restores the global stream) and
    REPORTING ONLY. Returns the stats dict: rms_mm/p90_mm (None when the footprint
    is too sparse), n_footprint, n_samples."""
    sig = template_signature(template)
    crop = _crop_canonical(scan_pts_world, pose_matrix, sig.rmax)
    _, _, stats = signed_deviation(crop, template)
    return stats


def render_site_qc(case_id: str, tooth: int, scan_pts_world: np.ndarray,
                   pose_matrix: np.ndarray, template: trimesh.Trimesh,
                   clocking: Optional[Dict[str, object]],
                   out_dir: "Path | str",
                   delivered_channel_xy: Optional[np.ndarray] = None
                   ) -> Tuple[List[Path], Dict[str, object]]:
    """Write the two acceptance PNGs for one site; returns ``(paths, deviation_stats)``
    — the written paths (clock view first) plus the SAME stats dict the deviation map
    prints (rms_mm/p90_mm/n_footprint/n_samples), so the caller can stash the scalars
    into the run row without recomputing (they were render-only before 2026-07-24 —
    the panel's deviation_rms_mm read "missing" while the PNG showed the number).
    ``pose_matrix`` is the shipped canonical->world pose; ``clocking``
    is the site row's clocking dict (None on icp seats — rendered as such).
    ``delivered_channel_xy`` is the emitted product's AS-BUILT channel centre in the
    canonical frame — callers measure it from the delivered mesh itself
    (``final_product.measure_delivered_channel``, plain data here: an adapter must
    not import the pipeline layer) — drawn as its own marker so the clock view shows
    the deliverable next to the instruments; omitted, the view renders as before."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    sig = template_signature(template)
    crop = _crop_canonical(scan_pts_world, pose_matrix, sig.rmax)

    clock_path = out / ("%s-%s-clockview.png" % (case_id, tooth))
    _render_clockview(clock_path, crop, sig, template, clocking,
                      "%s tooth %s — clock view (template frame, occlusal)"
                      % (case_id, tooth),
                      delivered_channel_xy=delivered_channel_xy)

    samples, signed, stats = signed_deviation(crop, template)
    dev_path = out / ("%s-%s-deviation.png" % (case_id, tooth))
    _render_deviation(dev_path, samples, signed, stats, sig,
                      "%s tooth %s — signed deviation map (occlusal)"
                      % (case_id, tooth))
    return [clock_path, dev_path], stats
