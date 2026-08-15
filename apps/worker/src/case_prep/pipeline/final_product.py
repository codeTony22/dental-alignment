"""The final product — ArTech's OWN export (client decision, 2026-07-04).

Instead of handing the recovered pose to an external CAD (the unvalidated RealGUIDE seam),
the pipeline assembles the deliverable itself: the vendor's construction part with the
screw-access channel bored along the implant axis, in the component's LOCAL frame — the
package emitter then poses it into the jaw world frame with the site's pose matrix and
writes the production set (``*-prosthesis_cad.stl`` + ``construction.json``).

The bore uses the SDF-CSG engine (occupancy SDF + marching cubes), so a non-watertight
vendor mesh still yields a watertight, manufacturable solid.

FRAME CONTRACT (review C1/C2): the vendor mesh is CANONICALIZED (centroid at the origin,
tallest principal axis on +z — the same convention the cap-template pose was fit in), so the
bore is guaranteed parallel to the implant axis under the site pose, from ANY vendor frame.
Because canonicalization's z-SIGN is data-derived, the part's up/down orientation for a
near-symmetric construction part — and the exact vertical SEATING against the implant
platform — still require the vendor's interface spec; the through-bore itself is
sign-agnostic. Neither is invented here.
"""
from __future__ import annotations

import hashlib
import math
from collections import OrderedDict
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import trimesh

from scipy.spatial import cKDTree

from case_prep.adapters.booleans import offset_surface, screw_channel
from case_prep.adapters.ingest import canonicalize_library
from case_prep.domain import design_rules
from case_prep.domain.circle_fit import fit_circle_xy_or_kasa
from case_prep.domain.channel import ChannelGeometry, channel_from_boundary_loops

DEFAULT_SCREW_RADIUS_MM = 1.0   # prosthetic screw-access channels run ~2mm diameter
_CHANNEL_OVERSHOOT_MM = 2.0     # bore past both faces so the channel is fully through
_SDF_PITCH_MM = 0.25

# GINGIVAL PROFILE OFFSET (client value, 2026-07-25). The emitted part is relieved by
# this much so it does not press into tissue — the same clearance the client's own
# flow calls the gingival profile offset. 0.0 disables the step entirely (the code path is then
# byte-identical to the pre-2026-07-25 build — pinned by contract test).
DEFAULT_GINGIVAL_OFFSET_MM = 0.20

# G1 REVERSIBILITY LEVER (master plan §7.4, autopsy 2026-07-23). True: when the caller
# supplies the cap CAD's loop-truth ChannelGeometry, the screw channel is bored at THAT
# channel's xy along THAT channel's axis, at the LIBRARY channel's own radius — the pose
# that carries the cap carries the bore to the same world position (§7.1: today's
# canonical-axis bore misses the cap channel by 0.36-0.42mm and the scanned recess by
# 0.60-0.84mm on all 3 measured real packages). False: today's canonical-axis behaviour,
# exactly — the vendor spec (C3) remains the final arbiter of the convention, so both
# modes stay emittable until it lands.
CHANNEL_AT_LIBRARY_TRUTH = True

# ---- as-built channel measurement envelope (G3). The delivered solid is watertight
# (marching cubes), so the channel is read from cross-section HOLE rings — the same
# circle evidence the library loop read uses, one topology level down. Constants carry
# their measured receipts (probes on the 3 live-demo packages, 2026-07-23):
_MEASURE_LEVELS = 11                 # sections across the mid 70% of the part height
_RING_MIN_PTS = 8                    # real section rings discretize to 40-200+ points
_RING_MAX_RADIAL_STD_MM = 0.10       # clean bore rings measure std 0.002-0.004; part/
#                                      bore merged (breached) outlines measure 0.24-0.44
_RING_RADIUS_RANGE_MM = (0.3, 2.6)   # screw-channel scale (delivered r 0.998-1.026;
#                                      DESS designed lumen 2.00)
_CHAIN_R_TOL_MM = 0.15               # one cylinder = one radius; the atlantis interior
#                                      ring r=1.22 next to the r=1.00 bore is excluded
_CHAIN_XY_TOL_MM = 0.35              # measured bore-ring xy scatter <= 0.06
_CHAIN_MIN_LEVELS = 3                # a channel is a STACK of rings, not one section
_CHAIN_MIN_ZSPAN_MM = 1.5            # ... spanning real height (measured 3.1-4.8)

# ---- achieved-clearance measurement (2026-07-25). The relief is an SDF round trip, so
# what the lab ASKS for and what the part CARRIES are different numbers (measured on the
# real parts at a requested 0.20: atlantis median 0.146, dess median 0.130). The emitted
# record must say the achieved figure out loud instead of echoing the request back.
_CLEARANCE_SAMPLES = 20000   # surface samples per side; the distribution, not one number
_CLEARANCE_SEED = 11         # seeded + RNG-state-restoring: the pinned pipeline stream
#                              feeding QC render / emission must be untouched


_CLEARANCE_METHOD = ("surface-sample nearest-distance, relieved product vs the "
                     "un-relieved reference product (same bore, no relief)")


@dataclass(frozen=True)
class AchievedClearance:
    """What the gingival relief ACTUALLY removed, mm — the distance distribution from the
    relieved product's surface to the un-relieved reference product's surface (the same
    surface-sample nearest-distance read the offset evidence was taken with).

    p10/p90 are the reported spread, not min/max: over 20k samples the extremes are single
    outliers (the shared bore walls sit at ~0 by construction). min/max ride along as raw
    facts so a reader can see that, but the honest summary is median with p10/p90.

    ``requested_mm`` IS THE RELIEF THE PART WAS CUT WITH, which is the lab's ask unless the
    relief clamp fired (2026-07-25). When it did, the same audit block carries
    ``gingival_offset_requested_mm`` (the ask), ``gingival_offset_applied_mm`` (= this
    number) and ``clamped: true`` — so the pair is never ambiguous. The key keeps its name
    deliberately: it is on the wire to the web panel and in every emitted manifest, and
    renaming a live field to fix a reading that is already disambiguated beside it would
    cost more than it buys."""

    requested_mm: float
    achieved_median_mm: float
    achieved_p10_mm: float
    achieved_p90_mm: float
    achieved_min_mm: float
    achieved_max_mm: float
    n_samples: int

    def as_json(self) -> dict:
        return {"requested_mm": round(self.requested_mm, 4),
                "achieved_median_mm": round(self.achieved_median_mm, 4),
                "achieved_p10_mm": round(self.achieved_p10_mm, 4),
                "achieved_p90_mm": round(self.achieved_p90_mm, 4),
                "achieved_min_mm": round(self.achieved_min_mm, 4),
                "achieved_max_mm": round(self.achieved_max_mm, 4),
                "n_samples": int(self.n_samples),
                # the record says HOW it was measured in words, so a downstream reader
                # never has to assume which surfaces the number compares
                "method": _CLEARANCE_METHOD}


@dataclass
class DeliveredChannel:
    """The AS-BUILT screw channel of an emitted product, canonical frame, mm — measured
    from the delivered mesh itself, never inferred from the template or the estimator
    chain it is meant to judge (§7.3: no instrument measured the deliverable before)."""

    centre: np.ndarray   # (3,) channel axis point at the measured stack's mid height
    radius: float        # mean ring radius across the stack
    axis: np.ndarray     # (3,) unit direction (+z-ward), from the ring-centre drift
    n_levels: int        # sections that contributed a qualifying ring
    z_span: float        # height covered by the stack


def _kasa_circle(xy: np.ndarray) -> Tuple[np.ndarray, float]:
    """Least-squares circle (centre, radius) — Taubin, Kasa if Taubin refuses."""
    fit = fit_circle_xy_or_kasa(xy)
    if fit is not None:
        return fit
    c = np.asarray(xy, float).mean(axis=0)
    return c, 0.0


def _inside_loop(pt: np.ndarray, poly: np.ndarray) -> bool:
    """Even-odd ray cast of 2D ``pt`` against closed polygon ``poly`` (n,2). A loop
    CENTRE test is fooled by concentric rings (the outer ring's centre lies inside the
    bore ring), so nesting depth below is probed with a loop VERTEX instead."""
    x, y = float(pt[0]), float(pt[1])
    px, py = poly[:, 0], poly[:, 1]
    qx, qy = np.roll(px, -1), np.roll(py, -1)
    crossing = (py > y) != (qy > y)
    with np.errstate(divide="ignore", invalid="ignore"):
        xint = px + (y - py) * (qx - px) / (qy - py)
    return int(np.sum(crossing & (x < xint))) % 2 == 1


def measure_delivered_channel(mesh: trimesh.Trimesh) -> Optional[DeliveredChannel]:
    """Measure the as-built screw channel of a delivered (watertight) product in its
    canonical frame: cross-section the solid, keep rings at ODD nesting depth (material
    holes — depth is probed with a ring vertex, see ``_inside_loop``), demand circle
    quality, then require a radius- and xy-consistent stack of rings spanning real
    height. None when no stack qualifies — refused, never guessed (a breached or absent
    channel must read as absent, not as some other ring). Deterministic: plane sections
    only, no sampling, no RNG."""
    v = np.asarray(mesh.vertices, float)
    if len(v) < 4 or len(mesh.faces) < 4:
        return None
    z0, z1 = float(v[:, 2].min()), float(v[:, 2].max())
    if z1 - z0 < _CHAIN_MIN_ZSPAN_MM:
        return None
    rows: List[Tuple[float, float, float, float]] = []  # (z, cx, cy, r)
    for f in np.linspace(0.15, 0.85, _MEASURE_LEVELS):
        z = z0 + f * (z1 - z0)
        try:
            sec = mesh.section(plane_origin=[0.0, 0.0, z], plane_normal=[0.0, 0.0, 1.0])
        except Exception:
            continue
        if sec is None:
            continue
        loops = []
        for d in sec.discrete:
            p = np.asarray(d, float)
            if len(p) > 2 and np.allclose(p[0], p[-1]):
                p = p[:-1]
            if len(p) >= _RING_MIN_PTS:
                loops.append(p)
        for i, li in enumerate(loops):
            depth = sum(_inside_loop(li[0, :2], lj[:, :2])
                        for j, lj in enumerate(loops) if j != i)
            if depth % 2 == 0:
                continue  # outer boundary or island — not a hole wall
            c, r = _kasa_circle(li[:, :2])
            if float(np.linalg.norm(li[:, :2] - c, axis=1).std()) > _RING_MAX_RADIAL_STD_MM:
                continue
            if not (_RING_RADIUS_RANGE_MM[0] <= r <= _RING_RADIUS_RANGE_MM[1]):
                continue
            rows.append((z, float(c[0]), float(c[1]), r))
    if not rows:
        return None
    arr = np.array(rows, float)

    best = None
    for seed in arr:
        sel = arr[(np.abs(arr[:, 3] - seed[3]) <= _CHAIN_R_TOL_MM)
                  & (np.linalg.norm(arr[:, 1:3] - seed[1:3], axis=1) <= _CHAIN_XY_TOL_MM)]
        zs = np.unique(sel[:, 0])
        span = float(zs.max() - zs.min()) if len(zs) else 0.0
        score = (len(zs), span, -float(sel[:, 3].mean()))
        if len(zs) >= _CHAIN_MIN_LEVELS and span >= _CHAIN_MIN_ZSPAN_MM \
                and (best is None or score > best[0]):
            best = (score, sel)
    if best is None:
        return None
    chain = best[1]
    # axis from the ring-centre drift across height (near +z for every catalog part)
    sx = np.polyfit(chain[:, 0], chain[:, 1], 1)[0]
    sy = np.polyfit(chain[:, 0], chain[:, 2], 1)[0]
    axis = np.array([sx, sy, 1.0], float)
    axis /= float(np.linalg.norm(axis))
    zmid = float((chain[:, 0].min() + chain[:, 0].max()) / 2.0)
    centre = np.array([float(np.interp(zmid, chain[:, 0], chain[:, 1])),
                       float(np.interp(zmid, chain[:, 0], chain[:, 2])), zmid])
    return DeliveredChannel(centre=centre, radius=float(chain[:, 3].mean()), axis=axis,
                            n_levels=int(len(np.unique(chain[:, 0]))),
                            z_span=float(chain[:, 0].max() - chain[:, 0].min()))


def measure_achieved_clearance(reference: trimesh.Trimesh, relieved: trimesh.Trimesh,
                               requested_mm: float,
                               n_samples: int = _CLEARANCE_SAMPLES) -> AchievedClearance:
    """THE achieved-clearance instrument: how far the relieved surface actually sits
    inside the un-relieved one (median/p10/p90 of the surface-to-surface distance).

    Same read the offset evidence was taken with (``test_final_product``'s clearance
    assertion): seeded surface samples on each solid, nearest-neighbour distance from the
    relieved samples to the reference surface. Both solids carry the SAME bore, so the
    channel walls contribute ~0 and pull the p10 down — that is the honest shape of the
    distribution and is reported as such, not trimmed away to flatter it.

    Deterministic: the RNG is seeded and the global state is SAVED/RESTORED (the
    ``template_signature``/``signed_deviation`` pattern), so the pinned pipeline stream is
    untouched and two runs read the same pair identically."""
    state = np.random.get_state()
    try:
        np.random.seed(_CLEARANCE_SEED)
        base = np.asarray(trimesh.sample.sample_surface(reference, n_samples)[0], float)
        probe = np.asarray(trimesh.sample.sample_surface(relieved, n_samples)[0], float)
    finally:
        np.random.set_state(state)
    d = cKDTree(base).query(probe)[0]
    return AchievedClearance(requested_mm=float(requested_mm),
                             achieved_median_mm=float(np.median(d)),
                             achieved_p10_mm=float(np.percentile(d, 10)),
                             achieved_p90_mm=float(np.percentile(d, 90)),
                             achieved_min_mm=float(d.min()),
                             achieved_max_mm=float(d.max()),
                             n_samples=int(len(probe)))


def _cap_open_boundaries(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Cover open boundary loops with fan caps. Vendor construction CADs arrive as OPEN
    shells (measured: the DESS part has a 64-edge open rim; fill_holes cannot close it) —
    an open base lets the SDF occupancy flood the interior and hollow the part to a
    fragment. The occupancy SDF only needs surface COVERAGE, not watertight topology, so
    appending simple fan caps over each boundary loop is sufficient and shape-preserving."""
    try:
        outline = mesh.outline()
        loops = outline.discrete
    except Exception:
        return mesh
    caps = []
    for loop in loops:
        pts = np.asarray(loop, float)
        if len(pts) < 3:
            continue
        centre = pts.mean(axis=0)
        n = len(pts)
        verts = np.vstack([pts, centre])
        faces = [[i, (i + 1) % n, n] for i in range(n)]
        caps.append(trimesh.Trimesh(vertices=verts, faces=faces, process=False))
    return trimesh.util.concatenate([mesh] + caps) if caps else mesh


def _bore(part: trimesh.Trimesh, screw_radius_mm: float,
          library_channel: Optional[ChannelGeometry], vendor_lumen_r: Optional[float],
          pitch: float) -> Tuple[trimesh.Trimesh, dict]:
    """Cut the screw-access channel through one (already canonicalized, possibly
    relieved) body and return it with its channel record. Factored out 2026-07-25 so the
    emitted part and its UN-RELIEVED reference — the achieved-clearance and thin-wall
    receipts below — are bored by the same code, never by two drifting transcriptions."""
    z = np.asarray(part.vertices, float)[:, 2]
    mid = float((z.max() + z.min()) / 2.0)
    length = float(z.max() - z.min()) + 2.0 * _CHANNEL_OVERSHOOT_MM

    position = [0.0, 0.0, mid]
    axis = [0.0, 0.0, 1.0]
    radius = screw_radius_mm
    mode = "canonical_axis"
    if CHANNEL_AT_LIBRARY_TRUTH and library_channel is not None:
        mouth = np.asarray(library_channel.mouth_centre, float)
        position = [float(mouth[0]), float(mouth[1]), mid]
        if library_channel.axis is not None:
            axis = [float(a) for a in library_channel.axis]
        radius = float(library_channel.mouth_radius)
        mode = "library_truth"

    product = screw_channel(part, position=position, axis=axis,
                            radius=radius, length=length, pitch=pitch)
    return product, {
        "mode": mode,
        "position_xy_mm": [float(position[0]), float(position[1])],
        "axis": [float(a) for a in axis],
        "radius_mm": float(radius),
        "vendor_lumen_radius_mm": vendor_lumen_r,
    }


def _channel_receipts(product: trimesh.Trimesh) -> dict:
    """The gate's OWN channel read on a product (``design_rules.measure_product_channel``
    — the instrument the G5 rules are scored with, so a pre/post comparison compares like
    with like). ``measurable`` False means no cross-section carried a channel at all."""
    ch = design_rules.measure_product_channel(product)
    if ch is None:
        return {"measurable": False, "radius_mm": None, "min_wall_mm": None}
    return {"measurable": True,
            "radius_mm": round(float(ch.radius_mm), 4),
            "min_wall_mm": (round(float(ch.min_wall_mm), 4)
                            if ch.min_wall_mm is not None else None)}


def build_final_product(construction_mesh: trimesh.Trimesh,
                        screw_radius_mm: float = DEFAULT_SCREW_RADIUS_MM,
                        pitch: float = _SDF_PITCH_MM,
                        library_channel: Optional[ChannelGeometry] = None,
                        gingival_offset_mm: float = DEFAULT_GINGIVAL_OFFSET_MM
                        ) -> trimesh.Trimesh:
    """The final product in the component's CANONICAL frame (centroid origin, axis on +z —
    matching the frame the site pose maps to world), with the screw-access channel bored
    fully through.

    CHANNEL POSITION (G1, master plan §7.4; deliberate change 2026-07-23). When
    ``library_channel`` — the identified cap CAD's loop-truth read
    (``domain.channel.channel_from_boundary_loops``) — is supplied and
    ``CHANNEL_AT_LIBRARY_TRUTH`` is True, the channel is bored at the CAP channel's xy
    along its axis: cap and product share the canonical frame and the one site pose
    poses both (output_package), so the bore lands in world exactly where the cap CAD
    says the screw goes. Old behaviour (still the fallback, and exact under the flag
    or when no channel is passed): position [0,0,mid], axis +z, radius
    ``screw_radius_mm`` — measured on 3 real packages missing the cap channel by
    0.36-0.42mm and the scanned recess by 0.60-0.84mm (§7.1).

    CHANNEL RADIUS in library-truth mode = ``library_channel.mouth_radius`` (catalog
    1.078-1.152mm) — the cap CAD's own screw-access radius — replacing the fixed
    r=1.0 (C7). NOT the vendor part's lumen radius: boring the DESS part's designed
    r=2.00 lumen at the cap's off-axis xy was MEASURED to destroy the part (16.1mm^3
    in 2 disconnected bodies vs 79.1mm^3 sound at the library radius, 2026-07-23) —
    that radius-vs-lumen mismatch is recorded per part in
    ``product.metadata['channel']['vendor_lumen_radius_mm']`` and is G5's design-rule
    case plus the C3/C7 vendor-spec ask, not silently absorbed here.

    GINGIVAL PROFILE OFFSET (``gingival_offset_mm``, default
    ``DEFAULT_GINGIVAL_OFFSET_MM`` = 0.20 — the client's own value, 2026-07-25). The
    canonicalized part is relieved INWARD by this much (``booleans.offset_surface`` with a
    negative distance) BEFORE the channel is bored, so the emitted part carries a
    controlled clearance where it meets tissue. Order matters and is deliberate: relieving
    AFTER the bore would widen the screw channel by the same amount and break the G1
    library-truth radius contract (measured miss 0.001-0.018mm), so the bore is cut at the
    library radius into the already-relieved body.

    HONESTY: this is a UNIFORM inward surface offset, not a gingiva-only one — the tissue
    boundary on the construction part is not in any spec this pipeline has (C3), so the
    relief is applied to the whole surface and SAID SO in
    ``product.metadata['gingival_offset']['mode']`` rather than claimed as an emergence-
    profile-restricted offset. ``gingival_offset_mm=0.0`` skips the step entirely: the code
    path, and therefore the emitted geometry, is byte-identical to the pre-offset build.
    A negative value is refused — that would GROW the part into the tissue.

    ACHIEVED CLEARANCE + THIN-WALL RECEIPTS (2026-07-25). When a relief IS applied the
    UN-RELIEVED reference product is built too — the same body, the same bore, no relief —
    and two measurements are recorded under ``metadata['gingival_offset']``:

    - ``achieved``: what the relief actually removed (``measure_achieved_clearance``).
      The honesty fix for a record that echoed the REQUEST back: measured on the real
      parts at a requested 0.20, the atlantis part carries median 0.146 (p10 0.031, p90
      0.260) and the dess part median 0.130 (p10 0.031, p90 0.239).
    - ``pre_offset``/``post_offset``: the gate's own channel read
      (``design_rules.measure_product_channel``) on each product, so the emitter can tell
      whether the RELIEF is what destroyed the channel evidence or thinned an
      already-non-compliant wall — the fail-closed condition in
      ``output_package.emit_case_package``. Measured on atlantis/zimmer-4.5-scanbody: wall
      0.224mm at offset 0, and at 0.20 the as-built channel becomes UNMEASURABLE.

    The reference build costs one more SDF pass (measured ~0.1s on both real parts) and
    touches nothing that is emitted."""
    if not np.isfinite(gingival_offset_mm) or gingival_offset_mm < 0.0:
        raise ValueError(f"gingival_offset_mm must be a finite clearance >= 0, got "
                         f"{gingival_offset_mm!r} — a negative offset would grow the "
                         f"part into the tissue")
    part, _ = canonicalize_library(_cap_open_boundaries(construction_mesh))
    vendor_lumen_r: Optional[float] = None
    if CHANNEL_AT_LIBRARY_TRUTH and library_channel is not None:
        # the vendor part's own designed lumen, read from ITS boundary loops (before
        # capping seals them) — recorded so the G5 gate can flag radius-vs-lumen
        own_part, _ = canonicalize_library(construction_mesh)
        own = channel_from_boundary_loops(own_part)
        vendor_lumen_r = float(own.mouth_radius) if own is not None else None

    relief = float(gingival_offset_mm)
    offset_record: dict = {
        "offset_mm": relief,
        "applied": bool(relief > 0.0),
        "mode": "uniform_inward_surface_offset" if relief > 0.0 else "none",
        "note": ("relief applied to the WHOLE part surface — the tissue-facing boundary "
                 "is not in any vendor spec this pipeline has (C3)"),
        "achieved": None,
        "pre_offset": None,
        "post_offset": None,
    }
    if relief == 0.0:
        product, channel_record = _bore(part, screw_radius_mm, library_channel,
                                        vendor_lumen_r, pitch)
    else:
        reference, _ = _bore(part, screw_radius_mm, library_channel, vendor_lumen_r,
                             pitch)
        # inward (negative distance) = material removed = clearance against tissue
        product, channel_record = _bore(
            offset_surface(part, -relief, pitch=pitch),
            screw_radius_mm, library_channel, vendor_lumen_r, pitch)
        offset_record["achieved"] = measure_achieved_clearance(
            reference, product, relief).as_json()
        offset_record["pre_offset"] = _channel_receipts(reference)
        offset_record["post_offset"] = _channel_receipts(product)
    product.metadata["channel"] = channel_record
    product.metadata["gingival_offset"] = offset_record
    return product


# =====================================================================================
# THE RELIEF CEILING — max safe gingival offset, answered BEFORE the run
# =====================================================================================
# DELIBERATE CHANGE (2026-07-25, client escalation "END-TO-END AUTOMATION MUST COMPLETE").
#
# THE MEASURED PROBLEM. The thin-wall export block (``output_package._relief_block_reason``,
# shipped this morning) is correct and stays exactly as it is — it refuses to ship a part
# whose screw-channel wall collapsed. But it fires at EMISSION, after the whole pipeline
# has run, and on the warm fleet run it fired on 4 of 9 cases at the client's chosen 0.20mm
# default, across BOTH vendors. The driver is CAP SIZE, not vendor: dess/neodent-gm 5020
# fails exactly like the atlantis parts, while neodent-gm 6020/6030 pass. The client's own
# report names ``atlantis/neodent-gm 5030`` — the atlantis construction part under a
# neodent cap — as the tooth-3 refusal.
#
# THE FIX IS NOT A WEAKER GATE. It is knowing the ceiling for a (construction part x cap
# variant) pair BEFORE the operator commits, and completing the run at that ceiling while
# saying so in every record. Nothing here relaxes ``_relief_block_reason``: this search
# evaluates the SAME conditions on probe geometry, plus the G5 ``seal_census`` catastrophe
# (a relief that fragments the part), because a ceiling that clamps to a value which then
# fails catastrophically would not make the automation complete either.
#
# COST (measured on the real vendor parts, this machine): canonicalize 0.004s, one bore
# 0.03-0.06s, one channel read 0.01s, one inward offset 0.045s -> ~0.09s per probe. Across
# all 24 catalog pairs a COLD ceiling costs 7-14 probes, 0.53-1.17s — a pair whose wall is
# already thin answers fastest (the ladder fails on its first step), one that survives to
# the search ceiling costs the most. Benches (the canonicalized part + every probe already
# taken) are cached per (mesh bytes, channel, radius, pitch), so the second question about
# a pair is a dict lookup. That is what makes this answerable at SELECTION time instead of
# after the pipeline. The RUN pays less: a requested offset that is safe costs 2 probes and
# never searches for a ceiling nobody asked for.
MAX_GINGIVAL_SEARCH_MM = 0.50      # the search ceiling: past this it is not a relief
_RELIEF_COARSE_STEP_MM = 0.05      # coarse ladder; the first FAILING step brackets the top
_RELIEF_RESOLUTION_MM = 0.01       # bisection floor — the answer is a 0.01mm grid value
_RELIEF_BENCH_CACHE_MAX = 32       # (construction x cap) pairs kept warm; LRU. A bench
#                                    retains the canonicalized part (measured 0.33-0.78MB
#                                    on the real vendor CADs) and its readings, so a full
#                                    cache costs ~25MB — the whole catalog is 24 pairs

LIMITED_BY_NONE = "none"           # nothing broke up to the search ceiling
LIMITED_BY_CHANNEL = "channel"     # the relief erased the as-built channel (rule (a))
LIMITED_BY_WALL = "wall"           # it thinned an already-undersized wall (rule (b))
LIMITED_BY_SEAL = "seal"           # it left an unmanufacturable part (G5 seal_census)

_relief_benches: "OrderedDict[str, _ReliefBench]" = OrderedDict()


def _is_sealed(product: Optional[trimesh.Trimesh]) -> bool:
    """The G5 ``seal_census`` rule, evaluated directly on a probe product: one watertight
    body. Transcribed rather than routed through ``evaluate_site_rules`` because the search
    needs ONLY the catastrophic rule and must not pay for the lumen/angulation reads."""
    if product is None or len(product.faces) == 0:
        return False
    return bool(product.is_watertight) and len(product.split(only_watertight=False)) == 1


def _limit_reason(reference: dict, reading: dict) -> Optional[str]:
    """Which export condition a candidate relief violates, or None when the part would
    still emit. Rules (a) and (b) are ``output_package._relief_block_reason`` verbatim —
    if that gate is ever changed, this must change with it or the ceiling starts lying."""
    if not reading["sealed"]:
        return LIMITED_BY_SEAL
    if reading["offset_mm"] <= 0.0:
        return None  # no relief was applied — the relief gate cannot fire (``applied``)
    if reference["measurable"] and not reading["measurable"]:
        return LIMITED_BY_CHANNEL
    pre_wall, post_wall = reference["min_wall_mm"], reading["min_wall_mm"]
    if (pre_wall is not None and post_wall is not None
            and pre_wall < design_rules.MIN_WALL_MM
            and post_wall < design_rules.MIN_WALL_MM and post_wall < pre_wall):
        return LIMITED_BY_WALL
    return None


class _ReliefBench:
    """One (construction part x cap channel) pair, set up once and probed many times.

    Holds the canonicalized body and every probe already taken (offset -> the gate's own
    channel receipts + the seal verdict). Probes are memoized, so a bisection that revisits
    a step, a run that follows an endpoint query, and a second site on the same variant all
    cost nothing. Products are NOT retained — only their readings, so a warm bench is a few
    hundred bytes."""

    def __init__(self, construction_mesh: trimesh.Trimesh, screw_radius_mm: float,
                 library_channel: Optional[ChannelGeometry], pitch: float) -> None:
        self._part, _ = canonicalize_library(_cap_open_boundaries(construction_mesh))
        self._screw_radius_mm = float(screw_radius_mm)
        self._library_channel = library_channel
        self._pitch = float(pitch)
        self._readings: Dict[float, dict] = {}
        self.probes = 0  # cumulative probes actually computed on this bench

    def at(self, offset_mm: float) -> dict:
        """The reading at one relief: ``{offset_mm, measurable, radius_mm, min_wall_mm,
        sealed}``. The bore mirrors ``build_final_product`` exactly (relief FIRST, then the
        library-truth bore) — the vendor-lumen record is skipped because it is metadata
        only and never touches geometry."""
        key = round(float(offset_mm), 4)
        hit = self._readings.get(key)
        if hit is not None:
            return hit
        self.probes += 1
        reading = {"offset_mm": key, "measurable": False, "radius_mm": None,
                   "min_wall_mm": None, "sealed": False}
        try:
            body = (self._part if key <= 0.0
                    else offset_surface(self._part, -key, pitch=self._pitch))
            if len(body.faces) == 0:
                raise ValueError("the relief consumed the whole part")
            product, _ = _bore(body, self._screw_radius_mm, self._library_channel,
                               None, self._pitch)
            reading.update(_channel_receipts(product))
            reading["sealed"] = _is_sealed(product)
        except Exception:
            # A relief the SDF cannot turn back into a solid IS the unmanufacturable
            # outcome (``sealed`` stays False, so the caller reads it as unsafe). Caught
            # here deliberately: a CEILING QUERY must never take down the run it exists to
            # let complete — the refusal is the answer, not the exception.
            pass
        self._readings[key] = reading
        return reading

    def taken(self) -> Tuple[dict, ...]:
        return tuple(self._readings[k] for k in sorted(self._readings))


def _channel_key(channel: Optional[ChannelGeometry]) -> tuple:
    if channel is None:
        return ()
    mouth = np.asarray(channel.mouth_centre, float)
    axis = (tuple(np.round(np.asarray(channel.axis, float), 6))
            if channel.axis is not None else ())
    return (round(float(mouth[0]), 6), round(float(mouth[1]), 6),
            round(float(channel.mouth_radius), 6)) + axis


def _bench_key(construction_mesh: trimesh.Trimesh, screw_radius_mm: float,
               library_channel: Optional[ChannelGeometry], pitch: float) -> str:
    """Content key for the bench cache. Hashes the mesh BYTES rather than trusting a
    caller-supplied path id: the same construction file is loaded by the server, the CLI
    and the pipeline through three different objects, and a path key would miss all but
    one of them (measured on a real mesh: ~3ms to digest, against ~90ms per probe saved)."""
    h = hashlib.sha256()
    h.update(np.ascontiguousarray(np.asarray(construction_mesh.vertices,
                                             dtype=np.float64)).tobytes())
    h.update(np.ascontiguousarray(np.asarray(construction_mesh.faces,
                                             dtype=np.int64)).tobytes())
    h.update(repr((round(float(screw_radius_mm), 6), round(float(pitch), 6),
                   _channel_key(library_channel),
                   bool(CHANNEL_AT_LIBRARY_TRUTH))).encode())
    return h.hexdigest()


def _bench_for(construction_mesh: trimesh.Trimesh, screw_radius_mm: float,
               library_channel: Optional[ChannelGeometry], pitch: float,
               cache: bool = True) -> "_ReliefBench":
    if not cache:
        return _ReliefBench(construction_mesh, screw_radius_mm, library_channel, pitch)
    key = _bench_key(construction_mesh, screw_radius_mm, library_channel, pitch)
    bench = _relief_benches.get(key)
    if bench is None:
        bench = _ReliefBench(construction_mesh, screw_radius_mm, library_channel, pitch)
        _relief_benches[key] = bench
        while len(_relief_benches) > _RELIEF_BENCH_CACHE_MAX:
            _relief_benches.popitem(last=False)
    else:
        _relief_benches.move_to_end(key)
    return bench


def clear_relief_cache() -> None:
    """Drop every warm bench (tests that time the search, and any process that swaps the
    catalog under a long-lived server)."""
    _relief_benches.clear()


@dataclass(frozen=True)
class ReliefLimit:
    """The largest gingival relief a (construction part x cap variant) pair can take and
    still EMIT, plus the reason it stops there.

    ``max_safe_mm`` is on a 0.01mm grid and always ROUNDED DOWN — a ceiling that overstates
    by a hundredth of a millimetre is a ceiling that ships a blocked part. ``limited_by``
    names the condition that closed it: ``wall``/``channel`` are the two export-gate rules,
    ``seal`` is the G5 catastrophe, ``none`` means nothing broke up to ``searched_to_mm``
    (so the true ceiling may be higher — the search stops, it does not extrapolate).

    ``shippable_at_zero`` False is the genuinely unshippable part: no relief, not even
    none at all, yields a manufacturable solid. That case still HARD BLOCKS at export."""

    max_safe_mm: float
    limited_by: str
    wall_mm_at_zero: Optional[float]
    wall_mm_at_max_safe: Optional[float]
    channel_measurable_at_zero: bool
    shippable_at_zero: bool
    searched_to_mm: float
    resolution_mm: float
    probes: int
    readings: Tuple[dict, ...]
    note: str

    def reading_at(self, offset_mm: float) -> Optional[dict]:
        key = round(float(offset_mm), 4)
        return next((r for r in self.readings if r["offset_mm"] == key), None)

    def as_json(self) -> dict:
        return {"max_safe_mm": self.max_safe_mm,
                "limited_by": self.limited_by,
                "wall_mm_at_zero": self.wall_mm_at_zero,
                "wall_mm_at_max_safe": self.wall_mm_at_max_safe,
                "channel_measurable_at_zero": self.channel_measurable_at_zero,
                "shippable_at_zero": self.shippable_at_zero,
                "searched_to_mm": self.searched_to_mm,
                "resolution_mm": self.resolution_mm,
                "probes": self.probes,
                "note": self.note}


def _mm(value: Optional[float]) -> str:
    return "unmeasurable" if value is None else f"{value:.3f}mm"


def _limit_note(limited_by: str, max_safe: float, searched_to: float,
                wall_at_zero: Optional[float], first_fail: Optional[float]) -> str:
    wall = _mm(wall_at_zero)
    if limited_by == LIMITED_BY_SEAL and max_safe <= 0.0:
        return ("this part does not yield one watertight body even with NO relief — it is "
                "unshippable at any gingival offset, and the export gate blocks it")
    if limited_by == LIMITED_BY_NONE:
        return (f"no relief up to the {searched_to:.2f}mm search ceiling breaks the export "
                f"gate (channel wall {wall} at zero relief); the true ceiling may be higher "
                f"— the search stops there, it does not extrapolate")
    at = f"{first_fail:.2f}mm" if first_fail is not None else "the next step"
    if limited_by == LIMITED_BY_WALL:
        return (f"the channel wall is already {wall} at zero relief — under the "
                f"{design_rules.MIN_WALL_MM:.2f}mm rule, so there is no margin to give: at "
                f"{at} the wall thins further and the export gate refuses the part "
                f"(max safe {max_safe:.2f}mm)")
    if limited_by == LIMITED_BY_CHANNEL:
        return (f"at {at} the as-built screw channel becomes UNMEASURABLE — no instrument "
                f"could accept the delivered part (channel wall {wall} at zero relief; "
                f"max safe {max_safe:.2f}mm)")
    return (f"at {at} the relief leaves a fragmented or unsealed part, which is not "
            f"manufacturable (max safe {max_safe:.2f}mm)")


def max_safe_gingival_offset(construction_mesh: trimesh.Trimesh,
                             library_channel: Optional[ChannelGeometry] = None,
                             screw_radius_mm: float = DEFAULT_SCREW_RADIUS_MM,
                             pitch: float = _SDF_PITCH_MM,
                             ceiling_mm: float = MAX_GINGIVAL_SEARCH_MM,
                             report_at_mm: Optional[float] = DEFAULT_GINGIVAL_OFFSET_MM,
                             cache: bool = True) -> ReliefLimit:
    """THE CEILING: the largest relief this (construction part x cap channel) pair can be
    cut with and still leave a part the export gate emits.

    SEARCH. A reference probe at 0.0 fixes the pre-relief channel read the gate compares
    against (its rule (b) needs it), then a coarse ladder in ``_RELIEF_COARSE_STEP_MM``
    steps climbs until the FIRST failing step, then a bisection between the last passing
    and first failing step closes to ``_RELIEF_RESOLUTION_MM``. Cost: 1 + <=10 + ~3 probes
    at ~0.09s each — measured 0.5-1.3s cold on the real vendor parts, and a dict lookup
    warm (the bench cache is keyed on the mesh bytes + the channel).

    FIRST FAILURE WINS, deliberately. The relief-vs-wall relation is monotone on every
    catalog part measured, but the search does not RELY on that: it reports the first step
    that breaks the gate and never raises the ceiling because some larger step happened to
    pass again. A ceiling is a promise, so it is closed at the first evidence against it
    and rounded DOWN to the 0.01mm grid.

    ``report_at_mm`` guarantees a reading at one extra offset (default: the client's 0.20mm)
    even when the ladder stopped below it — that is the ``wall_mm_at_default`` the operator
    is shown next to the ceiling. ``ceiling_mm`` caps the ladder: the run path passes the
    REQUESTED offset, because nothing above the ask is worth probing.

    This never mutates the input mesh and never emits anything — it is a measurement."""
    ceiling = max(0.0, MAX_GINGIVAL_SEARCH_MM if ceiling_mm is None else float(ceiling_mm))
    bench = _bench_for(construction_mesh, screw_radius_mm, library_channel, pitch,
                       cache=cache)
    before = bench.probes
    reference = bench.at(0.0)

    if not reference["sealed"]:
        # THE HARD-BLOCK CASE: not a relief problem at all. Nothing is clamped into
        # shippability here — the export gate still refuses this part.
        limit = ReliefLimit(
            max_safe_mm=0.0, limited_by=LIMITED_BY_SEAL,
            wall_mm_at_zero=reference["min_wall_mm"],
            wall_mm_at_max_safe=reference["min_wall_mm"],
            channel_measurable_at_zero=bool(reference["measurable"]),
            shippable_at_zero=False, searched_to_mm=0.0,
            resolution_mm=_RELIEF_RESOLUTION_MM, probes=bench.probes - before,
            readings=bench.taken(),
            note=_limit_note(LIMITED_BY_SEAL, 0.0, 0.0, reference["min_wall_mm"], None))
        return limit

    lo = 0.0                      # largest relief KNOWN to pass
    hi: Optional[float] = None    # smallest relief KNOWN to fail
    limited_by = LIMITED_BY_NONE
    step = _RELIEF_COARSE_STEP_MM
    # the ladder ALWAYS ends on the ceiling itself, even when the ceiling is off the 0.05
    # grid: the run path passes the requested offset as the ceiling, and skipping it would
    # leave a clamped run reporting ``limited_by: none`` — a refusal with no named reason
    ladder = [round(i * step, 4) for i in range(1, int(ceiling / step + 1e-9) + 1)]
    if not ladder or ladder[-1] < ceiling - 1e-9:
        ladder.append(round(ceiling, 4))
    for candidate in ladder:
        reason = _limit_reason(reference, bench.at(candidate))
        if reason is None:
            lo = candidate
            continue
        hi, limited_by = candidate, reason
        break

    if hi is not None:
        while hi - lo > _RELIEF_RESOLUTION_MM + 1e-9:
            mid = round((lo + hi) / 2.0, 4)
            if mid <= lo or mid >= hi:
                break
            reason = _limit_reason(reference, bench.at(mid))
            if reason is None:
                lo = mid
            else:
                hi, limited_by = mid, reason

    max_safe = math.floor(lo / _RELIEF_RESOLUTION_MM + 1e-9) * _RELIEF_RESOLUTION_MM
    max_safe = round(max(0.0, max_safe), 2)
    if report_at_mm is not None and float(report_at_mm) > 0.0:
        bench.at(float(report_at_mm))
    # the wall AT the ceiling is measured, not inherited: bisection rarely lands exactly on
    # the 0.01mm grid value, and falling back to the zero-relief reading would report the
    # un-relieved wall as if it were the wall of the part the ceiling ships (one probe)
    at_max = bench.at(max_safe) if max_safe > 0.0 else reference
    return ReliefLimit(
        max_safe_mm=max_safe,
        limited_by=limited_by,
        wall_mm_at_zero=reference["min_wall_mm"],
        wall_mm_at_max_safe=(at_max or reference)["min_wall_mm"],
        channel_measurable_at_zero=bool(reference["measurable"]),
        shippable_at_zero=True,
        searched_to_mm=round(ceiling, 4),
        resolution_mm=_RELIEF_RESOLUTION_MM,
        probes=bench.probes - before,
        readings=bench.taken(),
        note=_limit_note(limited_by, max_safe, ceiling, reference["min_wall_mm"], hi))


@dataclass(frozen=True)
class ReliefClamp:
    """What the run ACTUALLY cut, next to what the lab ASKED for.

    This is refused-as-asked + completed-at-the-safe-value + stated everywhere, NOT a
    silent substitution: ``clamped`` True with ``clamp_reason`` spelling out the part, both
    numbers and the condition, carried into the run response, every site row and the
    package audit. A reader who looks at only one of the two numbers still sees the truth,
    because ``applied_mm`` is the one every record labels as what the part was cut with."""

    requested_mm: float
    applied_mm: float
    clamped: bool
    clamp_reason: Optional[str]
    limited_by: str
    max_safe_mm: Optional[float]        # None: not searched (the ask already passed)
    wall_mm_at_zero: Optional[float]
    wall_mm_at_requested: Optional[float]
    wall_mm_at_applied: Optional[float]

    def as_json(self) -> dict:
        return {"gingival_offset_requested_mm": round(self.requested_mm, 4),
                "gingival_offset_applied_mm": round(self.applied_mm, 4),
                "clamped": self.clamped,
                "clamp_reason": self.clamp_reason,
                "limited_by": self.limited_by,
                "max_safe_mm": self.max_safe_mm,
                "wall_mm_at_zero": self.wall_mm_at_zero,
                "wall_mm_at_requested": self.wall_mm_at_requested,
                "wall_mm_at_applied": self.wall_mm_at_applied}


def resolve_gingival_offset(construction_mesh: trimesh.Trimesh,
                            requested_mm: float,
                            library_channel: Optional[ChannelGeometry] = None,
                            screw_radius_mm: float = DEFAULT_SCREW_RADIUS_MM,
                            pitch: float = _SDF_PITCH_MM,
                            part_label: str = "this part") -> ReliefClamp:
    """The RUN's relief decision: the requested offset when it is safe, the pair's ceiling
    when it is not — and never silently.

    THE CLIENT'S REQUIREMENT (2026-07-25): "end-to-end automation must complete". A run at
    an offset this pair cannot take used to die at emission with the package NOT emitted;
    it now completes at the ceiling and reports the clamp structurally everywhere. What has
    NOT changed: the export gate, which still refuses a thin-walled part, and still hard
    blocks the part that fails even at 0.0.

    FAST PATH, deliberately: ``requested_mm == 0`` probes NOTHING (a zero relief cannot
    trip a relief gate, so there is nothing to clamp and no reason to pay for a search),
    and a requested offset that PASSES its own probe returns after two probes (~0.15s)
    without searching for a ceiling nobody asked for. The full search runs only on the
    runs that would otherwise have been refused."""
    requested = float(requested_mm)
    if not np.isfinite(requested) or requested < 0.0:
        raise ValueError(f"gingival_offset_mm must be a finite clearance >= 0, got "
                         f"{requested_mm!r} — a negative offset would grow the part "
                         f"into the tissue")
    if requested == 0.0:
        return ReliefClamp(0.0, 0.0, False, None, LIMITED_BY_NONE, None, None, None, None)

    bench = _bench_for(construction_mesh, screw_radius_mm, library_channel, pitch)
    reference = bench.at(0.0)
    asked = bench.at(requested)
    if _limit_reason(reference, asked) is None:
        return ReliefClamp(requested, requested, False, None, LIMITED_BY_NONE, None,
                           reference["min_wall_mm"], asked["min_wall_mm"],
                           asked["min_wall_mm"])

    limit = max_safe_gingival_offset(construction_mesh, library_channel=library_channel,
                                     screw_radius_mm=screw_radius_mm, pitch=pitch,
                                     ceiling_mm=requested, report_at_mm=None)
    applied = min(requested, limit.max_safe_mm)
    # measured at the value the part is ACTUALLY cut with — see the same guard in
    # ``max_safe_gingival_offset``: an inherited zero-relief wall here would be a fiction
    at_applied = (bench.at(applied) if applied > 0.0 else reference)
    what = {LIMITED_BY_CHANNEL: "the as-built screw channel becomes UNMEASURABLE",
            LIMITED_BY_WALL: (f"it thins a channel wall that is already under the "
                              f"{design_rules.MIN_WALL_MM:.2f}mm rule "
                              f"({_mm(reference['min_wall_mm'])} at zero relief)"),
            LIMITED_BY_SEAL: "the part is left fragmented or unsealed"}.get(
                limit.limited_by, "the export gate refuses the part")
    advice = ("This pair can take NO relief at all: re-run with the relief disabled "
              "(0.00mm), or choose a construction part with more wall." if applied <= 0.0
              else f"Re-run at {applied:.2f}mm or lower to ask for what you get, or choose "
                   f"a construction part with more wall.")
    reason = (f"the {requested:.2f}mm gingival relief the lab asked for is NOT safe on "
              f"{part_label}: at {requested:.2f}mm {what}. The package was emitted at the "
              f"maximum safe relief for this construction-part/cap pair, "
              f"{applied:.2f}mm — NOT at the {requested:.2f}mm requested. {advice}")
    return ReliefClamp(requested_mm=requested, applied_mm=applied, clamped=True,
                       clamp_reason=reason, limited_by=limit.limited_by,
                       max_safe_mm=limit.max_safe_mm,
                       wall_mm_at_zero=reference["min_wall_mm"],
                       wall_mm_at_requested=asked["min_wall_mm"],
                       wall_mm_at_applied=at_applied["min_wall_mm"])
