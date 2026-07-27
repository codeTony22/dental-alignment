"""Pre-export design-rule gate (G5, master plan §7.4) — industry-parity checks run on
the EMITTED production part before it leaves the building.

The industry guarantees the screw channel by construction plus pre-export rule gates
(3Shape blocks export on channel-angle and wall-thickness violations; exocad caps
angulated screw channels at 20 deg unless the implant library says otherwise — master
plan §7.2/§7.3). This module is our copy of that gate, measured on the DELIVERABLE
mesh itself — the autopsy's core conviction is that no instrument ever measured the
emitted part (the delivered channel today is bored at HALF the vendor's designed lumen
radius, 2.00mm erased and re-bored at r=1.0, and nothing flagged it).

Four rules, each reported as (rule, value, bound, verdict, message):

- ``channel_lumen_match`` — the emitted channel's radius vs the vendor part's designed
  lumen (read from the construction CAD's own boundary loops). value = emitted radius,
  bound = designed radius. The halved-lumen defect (1.0 vs 2.00) must flag here.
- ``min_wall_thickness`` — thinnest material between the channel wall and any other
  surface in the same cross-section. value = min wall, bound = required minimum.
- ``channel_angulation`` — emitted channel axis vs the local +z (the implant axis
  under the site pose). value = degrees, bound = the per-library maximum
  (default 20 deg, the exocad convention).
- ``seal_census`` — the emitted part must be one watertight body (marching-cubes
  output is; a fine-pitch SDF seal failure fragments or empties it — recorded
  gotcha). value = body count, bound = 1.

Verdicts: ``pass`` | ``flag`` (advisory — reported, never blocks) | ``unknown``
(the input carries no measurable record — e.g. a watertight vendor CAD with no
boundary-loop lumen record, or an unmeasurable channel axis) | ``fail`` (CATASTROPHIC —
the only verdict a caller may fail closed on; reserved for a part that is not
manufacturable at all). A channel-less product is a FLAG, not a fail: cement-retained
designs legitimately have no screw channel (Retention.CEMENT exists), so absence is
surfaced for a human, not blocked on.

All measurements are deterministic (plane sections + least squares; no sampling, no
RNG) and stay in the part's LOCAL canonical frame — the same frame the package pose
carries into the jaw, so channel-vs-+z here IS channel-vs-implant-axis there.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import trimesh

from case_prep.domain.channel import channel_from_boundary_loops

VERDICT_PASS = "pass"
VERDICT_FLAG = "flag"
VERDICT_UNKNOWN = "unknown"
VERDICT_FAIL = "fail"
_SEVERITY = {VERDICT_PASS: 0, VERDICT_UNKNOWN: 1, VERDICT_FLAG: 2, VERDICT_FAIL: 3}

MAX_CHANNEL_ANGLE_DEG = 20.0  # exocad's ASC default absent a library maximum (§7.2)
MIN_WALL_MM = 0.5             # 3Shape-parity minimum wall around the channel (§7.3)
LUMEN_MATCH_RTOL = 0.15       # SDF boring at pitch 0.25 lands within ~5% of the asked
#                               radius (measured 0.995-0.998 for r=1.0); 15% separates
#                               quantization from the 50% halved-lumen defect
_SECTION_FRACTIONS = (0.25, 0.4, 0.5, 0.6, 0.75)  # avoid the rounded SDF end faces
_CHANNEL_RADIUS_RANGE_MM = (0.3, 3.0)  # screw-channel scale (mirrors domain/channel.py)
_MAX_SECTION_RADIAL_STD_MM = 0.15      # SDF sections measure <= 0.028; 5x envelope
_MIN_SECTION_LOOP_POINTS = 12


@dataclass(frozen=True)
class RuleCheck:
    """One design rule's outcome. ``bound`` is the rule's reference number (the
    designed lumen radius, the wall minimum, the angle maximum, the body count)."""

    rule: str
    value: Optional[float]
    bound: Optional[float]
    verdict: str
    message: str


@dataclass
class ProductChannel:
    """The screw channel as measured on the emitted part's cross-sections.
    (Plain dataclass: numpy fields make ``frozen=True`` a false promise.)"""

    radius_mm: float                 # mean channel radius across measured sections
    centres: np.ndarray              # (n, 3) per-section channel circle centres
    axis: Optional[np.ndarray]       # (3,) unit direction, None when < 2 sections
    min_wall_mm: Optional[float]     # thinnest channel-to-surface material, if measurable
    n_sections: int                  # sections in which the channel was found


def _closed_loops_at(mesh: trimesh.Trimesh, z: float) -> List[np.ndarray]:
    """Closed cross-section polylines at height ``z`` (open fragments dropped: a wall
    reading needs the full ring)."""
    try:
        section = mesh.section(plane_origin=[0.0, 0.0, z], plane_normal=[0.0, 0.0, 1.0])
    except Exception:
        return []
    if section is None:
        return []
    loops = []
    for polyline in section.discrete:
        pts = np.asarray(polyline, float)
        if len(pts) >= _MIN_SECTION_LOOP_POINTS and np.linalg.norm(pts[0] - pts[-1]) < 1e-6:
            loops.append(pts[:-1])  # drop the duplicated closing vertex
    return loops


def _point_in_loop(pt_xy: np.ndarray, loop_xy: np.ndarray) -> bool:
    """Ray-cast point-in-polygon (+x crossings), vectorized over the loop's edges."""
    a = loop_xy
    b = np.roll(loop_xy, -1, axis=0)
    straddles = (a[:, 1] > pt_xy[1]) != (b[:, 1] > pt_xy[1])
    dy = b[:, 1] - a[:, 1]
    dy[dy == 0.0] = 1e-30
    x_cross = a[:, 0] + (pt_xy[1] - a[:, 1]) * (b[:, 0] - a[:, 0]) / dy
    return bool(np.count_nonzero(straddles & (x_cross > pt_xy[0])) % 2)


def _channel_loop_in(loops: List[np.ndarray]) -> Optional[Tuple[np.ndarray, float, int]]:
    """(centre 3D, radius, loop index) of the channel circle in one section: a ROUND
    closed loop at screw scale whose centre lies INSIDE another loop (a channel is an
    interior feature — a lone outer silhouette never qualifies; a CONCENTRIC round
    silhouette does, its centre lying inside the bore loop, which is why innermost
    (smallest) wins when several qualify — never drop the ``min``)."""
    candidates = []
    for i, pts in enumerate(loops):
        centre = pts.mean(axis=0)
        radial = np.linalg.norm(pts[:, :2] - centre[:2], axis=1)
        radius = float(radial.mean())
        lo, hi = _CHANNEL_RADIUS_RANGE_MM
        if not (lo <= radius <= hi) or float(radial.std()) > _MAX_SECTION_RADIAL_STD_MM:
            continue
        enclosed = any(
            j != i and _point_in_loop(centre[:2], other[:, :2])
            for j, other in enumerate(loops)
        )
        if enclosed:
            candidates.append((centre, radius, i))
    if not candidates:
        return None
    return min(candidates, key=lambda c: c[1])


def measure_product_channel(product: trimesh.Trimesh) -> Optional[ProductChannel]:
    """Find and measure the screw channel on the emitted part via horizontal
    cross-sections; None when no section shows a channel (sealed bore, or a
    channel-less design)."""
    if len(product.faces) == 0 or len(product.vertices) < 3:
        return None
    z = np.asarray(product.vertices, float)[:, 2]
    z_lo, z_hi = float(z.min()), float(z.max())
    if z_hi - z_lo <= 0.0:
        return None
    centres: List[np.ndarray] = []
    radii: List[float] = []
    walls: List[float] = []
    for frac in _SECTION_FRACTIONS:
        loops = _closed_loops_at(product, z_lo + frac * (z_hi - z_lo))
        found = _channel_loop_in(loops)
        if found is None:
            continue
        centre, radius, idx = found
        centres.append(centre)
        radii.append(radius)
        channel_pts = loops[idx][:, :2]
        others = [lp[:, :2] for j, lp in enumerate(loops) if j != idx]
        if others:
            other_pts = np.vstack(others)
            # loops are ON the surfaces, so the closest cross-loop pair IS the wall
            d = np.linalg.norm(channel_pts[:, None, :] - other_pts[None, :, :], axis=2)
            walls.append(float(d.min()))
    if not centres:
        return None
    axis = None
    if len(centres) >= 2:
        c = np.asarray(centres, float)
        sx = np.polyfit(c[:, 2], c[:, 0], 1)[0]
        sy = np.polyfit(c[:, 2], c[:, 1], 1)[0]
        axis = np.array([sx, sy, 1.0])
        axis = axis / float(np.linalg.norm(axis))
    return ProductChannel(
        radius_mm=float(np.mean(radii)),
        centres=np.asarray(centres, float),
        axis=axis,
        min_wall_mm=(min(walls) if walls else None),
        n_sections=len(centres),
    )


def designed_lumen_radius(construction_canonical: trimesh.Trimesh) -> Optional[float]:
    """The vendor construction part's own designed channel radius, read from its
    boundary loops (the CAD's zero-noise record — DESS carries a 2.00mm lumen).

    Tries BOTH z-signs: canonicalization's z-sign is data-derived and explicitly
    untrusted (final_product.py frame contract), and a designed opening is a valid
    lumen record whichever end of the part it opens at. None when no loop qualifies
    (a watertight or out-of-envelope CAD) — callers report ``unknown``, never guess."""
    read = channel_from_boundary_loops(construction_canonical)
    if read is None:
        flipped = construction_canonical.copy()
        flipped.apply_transform(
            trimesh.transformations.rotation_matrix(np.pi, [1.0, 0.0, 0.0]))
        read = channel_from_boundary_loops(flipped)
    return None if read is None else float(read.mouth_radius)


def evaluate_site_rules(
    product: trimesh.Trimesh,
    construction_canonical: Optional[trimesh.Trimesh] = None,
    designed_lumen_mm: Optional[float] = None,
    max_channel_angle_deg: float = MAX_CHANNEL_ANGLE_DEG,
    min_wall_mm: float = MIN_WALL_MM,
) -> List[RuleCheck]:
    """Run all four export rules on one site's emitted part. ``designed_lumen_mm``
    pins the lumen reference directly (the vendor-spec arbiter's slot, C7); absent
    that, it is read from ``construction_canonical``'s boundary loops."""
    checks: List[RuleCheck] = []
    channel = measure_product_channel(product)
    if designed_lumen_mm is None and construction_canonical is not None:
        designed_lumen_mm = designed_lumen_radius(construction_canonical)

    # 1. channel radius vs the vendor's designed lumen
    if channel is None:
        checks.append(RuleCheck(
            "channel_lumen_match", None, designed_lumen_mm, VERDICT_FLAG,
            "no channel found in the emitted part (sealed bore — the SDF fine-pitch "
            "seal hazard — or a channel-less/cement-retained design); human review",
        ))
    elif designed_lumen_mm is None:
        checks.append(RuleCheck(
            "channel_lumen_match", channel.radius_mm, None, VERDICT_UNKNOWN,
            f"emitted channel r={channel.radius_mm:.3f}mm; vendor CAD carries no "
            "readable lumen record to compare against (C7 vendor-spec debt)",
        ))
    else:
        mismatch = abs(channel.radius_mm - designed_lumen_mm) / designed_lumen_mm
        ok = mismatch <= LUMEN_MATCH_RTOL
        checks.append(RuleCheck(
            "channel_lumen_match", channel.radius_mm, designed_lumen_mm,
            VERDICT_PASS if ok else VERDICT_FLAG,
            (f"emitted channel r={channel.radius_mm:.3f}mm matches the designed lumen "
             f"r={designed_lumen_mm:.3f}mm" if ok else
             f"emitted channel r={channel.radius_mm:.3f}mm vs designed lumen "
             f"r={designed_lumen_mm:.3f}mm ({mismatch:.0%} off — the vendor's channel "
             "was erased/re-bored; C7)"),
        ))

    # 2. minimum wall thickness around the channel
    if channel is None or channel.min_wall_mm is None:
        checks.append(RuleCheck(
            "min_wall_thickness", None, min_wall_mm, VERDICT_UNKNOWN,
            "no measurable channel wall (no channel found in any cross-section)",
        ))
    else:
        ok = channel.min_wall_mm >= min_wall_mm
        checks.append(RuleCheck(
            "min_wall_thickness", channel.min_wall_mm, min_wall_mm,
            VERDICT_PASS if ok else VERDICT_FLAG,
            f"thinnest wall around the channel {channel.min_wall_mm:.2f}mm "
            f"({'meets' if ok else 'UNDER'} the {min_wall_mm:.2f}mm minimum)",
        ))

    # 3. channel angulation vs the library maximum
    if channel is None or channel.axis is None:
        checks.append(RuleCheck(
            "channel_angulation", None, max_channel_angle_deg, VERDICT_UNKNOWN,
            "channel axis unmeasurable (< 2 cross-sections carried the channel)",
        ))
    else:
        angle = float(np.degrees(np.arccos(np.clip(channel.axis[2], -1.0, 1.0))))
        ok = angle <= max_channel_angle_deg
        checks.append(RuleCheck(
            "channel_angulation", angle, max_channel_angle_deg,
            VERDICT_PASS if ok else VERDICT_FLAG,
            f"channel {angle:.1f} deg off the implant axis "
            f"({'within' if ok else 'OVER'} the {max_channel_angle_deg:.0f} deg library maximum)",
        ))

    # 4. seal census — the only rule allowed to fail closed
    if len(product.faces) == 0:
        checks.append(RuleCheck(
            "seal_census", 0.0, 1.0, VERDICT_FAIL,
            "emitted part is EMPTY (SDF seal failure) — not manufacturable",
        ))
    else:
        bodies = len(product.split(only_watertight=False))
        watertight = bool(product.is_watertight)
        ok = watertight and bodies == 1
        checks.append(RuleCheck(
            "seal_census", float(bodies), 1.0,
            VERDICT_PASS if ok else VERDICT_FAIL,
            ("one watertight body" if ok else
             f"{bodies} bodies, watertight={watertight} — fragmented or unsealed "
             "part is not manufacturable"),
        ))
    return checks


def worst_verdict(checks: List[RuleCheck]) -> str:
    """The site's overall verdict: fail > flag > unknown > pass."""
    return max((c.verdict for c in checks), key=lambda v: _SEVERITY[v], default=VERDICT_PASS)


def has_catastrophic(checks: List[RuleCheck]) -> bool:
    return any(c.verdict == VERDICT_FAIL for c in checks)


def checks_as_json(checks: List[RuleCheck]) -> List[Dict[str, object]]:
    """Plain-JSON rows for the package manifest's advisory block."""
    return [
        {"rule": c.rule, "value": c.value, "bound": c.bound,
         "verdict": c.verdict, "message": c.message}
        for c in checks
    ]
