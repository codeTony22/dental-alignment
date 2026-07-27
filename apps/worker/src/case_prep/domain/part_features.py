"""The LIBRARY PART's marked features — the operator's half of a manual correspondence.

Client ask 2026-07-24 (with screenshots): "we need a flow where we can mark the
holes/trenches in the LIBRARY part, and also mark the corresponding holes/trenches in
the SCAN. Like this we can guarantee proper rotation and alignment." This is the
industry's manual-correspondence fallback (the coded-cap standard: the operator clicks 3 dots ON
the codes; Medit: manual 3-corresponding-point) — docs/research/doctor-inputs-research.md.

WHAT THIS FIXES. ``align-to-mark`` already rotates the seated cap so its NEAREST code
feature lands on the operator's scan click. Nearest-match is ambiguous the moment a cap
carries more than one code: zimmer-4.5-7030 reads three trenches at -177.0 / -136.0 /
-0.1 deg (measured over the catalog, this module's own reader), so a click 30 deg off
binds to the wrong trench and the part ships rotated by the inter-feature gap. Naming
the feature removes the ambiguity — and it works where the automatic code reader has NO
evidence at all (cap7030's half-occluded ring, zimmer t7), because the correspondence is
supplied by the human instead of correlated out of the scan.

WHAT A FEATURE IS. A ``PartFeature`` is a landmark on the part in its CANONICAL frame
(the frame ``adapters.ingest.canonicalize_revolute`` puts every template in — +z = the
revolution axis), named by its AZIMUTH about the part's own rim centre. The azimuth is
the whole rotational content; ``radius_mm`` is the lever arm that turns an angular
disagreement into millimetres the operator can judge, and ``z_mm`` names the plane the
feature is read in.

AUTO-SEED, NOT A BLANK PAGE. ``auto_features`` seeds the annotation from instruments the
pipeline already trusts, so the operator confirms a reading instead of inventing one:
- the CODED features from ``clock_signature.template_signature`` — the informative-row
  deep-cell clustering that ``align-to-mark`` was deriving inline in server.py (moved
  here verbatim, single source of truth: the endpoint now imports it);
- the SCREW CHANNEL from ``domain.channel`` — the CAD's own boundary-loop truth.
  Measured across all 12 catalog variants the mouth is CONCENTRIC with the rim centre
  (eccentricity 0.017-0.112mm), so the channel names the AXIS, not a clock angle: it is
  seeded because the operator sees the bore and expects it in the list, and it is
  excluded from correspondence by the lever-arm rule below rather than by a special
  case.

Everything here is deterministic and RNG-neutral (``template_signature`` saves and
restores the global state; the channel read and the rim-centre fit are pure algebra).
No IO: annotations serialize to plain dicts and the server owns the files.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

import numpy as np
import trimesh

from case_prep.domain.channel import channel_from_boundary_loops
from case_prep.domain.clock_signature import (N_R, R_HI, R_LO, TemplateSignature,
                                              _kasa, template_signature, wrap_deg)

# The ubiquitous language of a marked part. "trench" is the coded cutout the lab tech
# reads rotation from; "notch" and "flat" are the other vendor keying styles the same
# correspondence math serves; "channel" is the screw bore.
FEATURE_KINDS = ("trench", "notch", "flat", "channel")

# SNAP TOLERANCE — an operator click on the part reconciles with the machine's own
# reading when it lands inside BOTH windows; outside either, their exact azimuth is
# kept (the machine does not get to overrule the human's eye).
#   azimuth 11 deg: the smallest inter-feature gap measured across the catalog is 23.5
#     deg (neodent-gm-4030, trenches at -22.5 and +1.0), so a half-gap of 11.75 deg is
#     the point beyond which a snap could reach a NEIGHBOUR. 11 stays inside it — a
#     snap can never bind the operator to the wrong trench, which is the exact failure
#     this whole flow exists to remove. (The signature's own theta bin is 3 deg, so 11
#     is still ~4 bins of slack for a hand-placed click.)
#   radius 0.8mm: the coded band is r in [0.42, 0.80]*rmax, i.e. 0.79-1.56mm wide across
#     the catalog (rmax 2.09-4.10mm) — half-width 0.40-0.78mm. 0.8mm is that largest
#     half-width, so a click anywhere on the coded band of ANY catalog cap reconciles
#     with the feature it landed on, while a click down the bore (r <= 1.15mm against
#     measured trench radii of 1.43-2.19mm) stays out. On the smallest caps the window
#     also reaches the rim, which is the intended read: a click at a trench's azimuth is
#     that trench whether the operator caught the cutout or its rim edge. The AZIMUTH
#     window, not the radial one, is what stops a snap binding the wrong feature.
SNAP_AZIMUTH_DEG = 11.0
SNAP_RADIUS_MM = 0.8

# LEVER ARM — a landmark this close to the part's rim centre (its measured axis) has no
# azimuth worth rotating to: at 0.5mm a full 10 deg of rotation moves it 0.09mm, inside
# the scan's own noise. Every catalog channel measures 0.017-0.112mm and is therefore
# correctly refused as a correspondence anchor (it is still seeded, listed and drawn —
# see the module doc).
MIN_LEVER_ARM_MM = 0.5

# A click that is not on the part cannot be a feature of it. The bound is the part's own
# measured extent plus a 0.5mm hand-tolerance — exact, not a guessed multiple of rmax.
CLICK_SLACK_MM = 0.5


@dataclass
class PartFeature:
    """One landmark on the library part, canonical frame.

    ``azimuth_deg`` is measured CCW about the part's rim centre (the SAME centre
    convention ``template_signature`` unwraps its (theta, r) image about, so a feature
    azimuth and a clock reading are directly comparable — that is what lets the
    correspondence rotation reuse the align-to-mark math unchanged).
    ``radius_mm`` is the landmark's radial distance from that centre — its lever arm.
    ``source`` records WHO placed the mark: "auto" (the machine's own reading) or
    "operator" (a human click, possibly snapped to an auto feature — see
    ``feature_from_point``)."""

    id: str
    kind: str
    azimuth_deg: float
    radius_mm: float
    z_mm: float
    source: str = "auto"

    def __post_init__(self) -> None:
        if self.kind not in FEATURE_KINDS:
            raise ValueError(f"unknown feature kind {self.kind!r} "
                             f"(known: {', '.join(FEATURE_KINDS)})")
        if self.source not in ("auto", "operator"):
            raise ValueError(f"feature source must be 'auto' or 'operator', "
                             f"got {self.source!r}")
        if not np.isfinite([self.azimuth_deg, self.radius_mm, self.z_mm]).all():
            raise ValueError("feature azimuth/radius/z must be finite numbers")
        self.azimuth_deg = wrap_deg(float(self.azimuth_deg))
        self.radius_mm = float(self.radius_mm)
        self.z_mm = float(self.z_mm)

    @property
    def defines_rotation(self) -> bool:
        """Can this feature anchor a rotation? Only with a real lever arm — a concentric
        bore names the axis, not a clock angle."""
        return self.radius_mm >= MIN_LEVER_ARM_MM

    def to_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind,
                "azimuth_deg": round(self.azimuth_deg, 2),
                "radius_mm": round(self.radius_mm, 3),
                "z_mm": round(self.z_mm, 3),
                "source": self.source,
                "defines_rotation": self.defines_rotation}

    @classmethod
    def from_dict(cls, raw: dict) -> "PartFeature":
        try:
            return cls(id=str(raw["id"]), kind=str(raw["kind"]),
                       azimuth_deg=float(raw["azimuth_deg"]),
                       radius_mm=float(raw["radius_mm"]), z_mm=float(raw["z_mm"]),
                       source=str(raw.get("source", "operator")))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"malformed part feature record: {exc}") from exc


@dataclass
class PartAnnotation:
    """A library part's marked features — persisted ONCE per variant and reused by every
    case that ships that part (the productization point: the doctor marks the catalog,
    not each scan). ``revised_at`` is None for an auto seed that was never edited."""

    model: str
    variant: str
    features: List[PartFeature] = field(default_factory=list)
    revised_at: Optional[str] = None

    def __post_init__(self) -> None:
        ids = [f.id for f in self.features]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"duplicate feature id(s) {dupes} — every mark on a part "
                             f"needs its own identity")

    def by_id(self, feature_id: str) -> Optional[PartFeature]:
        return next((f for f in self.features if f.id == feature_id), None)

    def to_dict(self) -> dict:
        return {"model": self.model, "variant": self.variant,
                "revised_at": self.revised_at,
                "features": [f.to_dict() for f in self.features]}

    @classmethod
    def from_dict(cls, raw: dict) -> "PartAnnotation":
        try:
            features = [PartFeature.from_dict(f) for f in raw["features"]]
        except (KeyError, TypeError) as exc:
            raise ValueError(f"malformed part annotation: {exc}") from exc
        return cls(model=str(raw["model"]), variant=str(raw["variant"]),
                   features=features, revised_at=raw.get("revised_at"))


def template_rim_centre(template: trimesh.Trimesh) -> np.ndarray:
    """The part's rim centre (xy, canonical frame) — the origin every azimuth here is
    measured about.

    This MIRRORS ``template_signature``'s own centre construction exactly (p97 top-band
    radius, 0.4mm ring, Kasa fit). It is recomputed rather than read off the signature
    because ``TemplateSignature`` does not carry the centre it unwrapped about; keeping
    the two in step matters — a different centre would shift every feature azimuth
    relative to the clock instrument the gates and the notch re-read use. Pure algebra
    on the vertices: deterministic, no sampling, no RNG."""
    v = np.asarray(template.vertices, float)
    ztop = float(v[:, 2].max())
    top = v[v[:, 2] > ztop - 1.0]
    rmax = float(np.percentile(np.linalg.norm(top[:, :2], axis=1), 97))
    ring = v[np.linalg.norm(v[:, :2], axis=1) > rmax - 0.4]
    return _kasa(ring[:, :2]) if len(ring) >= 20 else np.zeros(2)


def _runs_of(idx: np.ndarray, n: int) -> List[List[int]]:
    """Contiguous circular runs of the sorted bin indices ``idx`` over ``n`` bins — a
    feature straddling theta=0 is ONE run, not two."""
    runs: List[List[int]] = []
    cur = [int(idx[0])]
    for i in idx[1:]:
        i = int(i)
        if i == cur[-1] + 1:
            cur.append(i)
        else:
            runs.append(cur)
            cur = [i]
    runs.append(cur)
    if len(runs) > 1 and runs[0][0] == 0 and runs[-1][-1] == n - 1:
        runs[0] = runs.pop() + runs[0]
    return runs


def coded_feature_azimuths(sig: TemplateSignature) -> List[float]:
    """The template's CODE-FEATURE azimuths (deg, canonical frame), derived
    deterministically from the clock signature: per-theta mean relief over the
    informative rows (row-zero-meaned, so the coded dips are the positive peaks),
    thresholded at half the peak, contiguous circular runs collapsed to their
    depth-weighted circular centroids. This is the same (theta, r) image the e8
    correlation reads — no new instrument, just its peaks named as azimuths.

    (Lifted verbatim out of server.py's ``_template_feature_azimuths`` when the
    correspondence flow needed the same reading: one source of truth, so a marked
    feature and the align-to-mark match can never drift apart.)"""
    return [az for az, _r in _coded_feature_reads(sig)]


def _coded_feature_reads(sig: TemplateSignature) -> List["tuple"]:
    """(azimuth_deg, radius_mm) per coded feature. The radius is the RELIEF-WEIGHTED
    radial centroid of the feature's own cells — where the cutout actually sits on the
    top face — which is what gives a mark its lever arm."""
    if not sig.has_coded_relief:
        return []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # all-NaN theta columns are legitimately empty
        prof = np.nanmean(sig.image, axis=1)
    prof = np.nan_to_num(prof, nan=0.0)
    peak = float(prof.max())
    if peak <= 0.0:
        return []
    idx = np.where(prof >= 0.5 * peak)[0]
    n = int(sig.image.shape[0])
    runs = _runs_of(idx, n)
    step = 360.0 / n
    # radial centre of each informative row, in mm from the rim centre
    row_r = (R_LO + (np.asarray(sig.rows, float) + 0.5) / N_R * (R_HI - R_LO)) * sig.rmax
    cells = np.nan_to_num(sig.image, nan=0.0).clip(min=0.0)
    reads: List[tuple] = []
    for run in runs:
        ang = np.radians((np.asarray(run, float) + 0.5) * step)
        w = prof[run]
        az = np.degrees(np.arctan2(float((w * np.sin(ang)).sum()),
                                   float((w * np.cos(ang)).sum())))
        block = cells[run, :]
        wsum = float(block.sum())
        r = (float((block * row_r).sum() / wsum) if wsum > 0.0
             else float(row_r.mean()))
        reads.append((wrap_deg(az), r))
    return sorted(reads)


def auto_features(template: trimesh.Trimesh) -> List[PartFeature]:
    """The machine's own reading of a library part, as marks: every coded trench plus
    the screw channel. Deterministic (the RNG state ``template_signature`` touches is
    saved and restored inside it) and stable across calls — ids are positional over the
    azimuth-sorted trenches, so ``trench-01`` names the same cutout every time.

    ``z_mm`` for a trench is the part's TOP-FACE plane: the coded features are read (and
    clicked) there, the azimuth is the only rotational content, and the signature's
    image is row-zero-meaned so an absolute cutout floor is not recoverable from it —
    reporting the plane the feature is read in is the honest number. The channel's z is
    its mouth circle's own height, straight off the CAD's boundary loop."""
    sig = template_signature(template)
    features = [
        PartFeature(id=f"trench-{i + 1:02d}", kind="trench", azimuth_deg=az,
                    radius_mm=r, z_mm=sig.ztop, source="auto")
        for i, (az, r) in enumerate(_coded_feature_reads(sig))
    ]
    channel = channel_from_boundary_loops(template)
    if channel is not None:
        centre = template_rim_centre(template)
        off = np.asarray(channel.mouth_centre, float)[:2] - centre
        features.append(PartFeature(
            id="channel", kind="channel",
            azimuth_deg=float(np.degrees(np.arctan2(off[1], off[0]))),
            radius_mm=float(np.linalg.norm(off)),
            z_mm=float(channel.mouth_centre[2]), source="auto"))
    return features


def _snap_to_auto(features: Sequence[PartFeature], azimuth_deg: float,
                  radius_mm: Optional[float] = None) -> Optional[PartFeature]:
    """The auto feature an operator mark RECONCILES with, or None — nearest in azimuth
    inside ``SNAP_AZIMUTH_DEG`` (and, when the mark carries one, inside
    ``SNAP_RADIUS_MM`` radially). A mark placed by azimuth alone has no radius to
    compare, so it reconciles on the azimuth window only; that window is inside the
    catalog's smallest inter-feature half-gap, so it still cannot bind a neighbour."""
    best: Optional[float] = None
    hit: Optional[PartFeature] = None
    for f in features:
        d_az = abs(wrap_deg(azimuth_deg - f.azimuth_deg))
        if d_az > SNAP_AZIMUTH_DEG:
            continue
        if radius_mm is not None and abs(radius_mm - f.radius_mm) > SNAP_RADIUS_MM:
            continue
        if best is None or d_az < best:
            best, hit = d_az, f
    return hit


def _as_operator_mark(f: PartFeature) -> PartFeature:
    """The machine's feature, re-stamped as the operator's mark: same id, same geometry,
    ``source="operator"``. The id says WHICH machine feature the human agrees with."""
    return PartFeature(id=f.id, kind=f.kind, azimuth_deg=f.azimuth_deg,
                       radius_mm=f.radius_mm, z_mm=f.z_mm, source="operator")


def coded_band_radius_mm(template: trimesh.Trimesh) -> float:
    """Mid-radius of the band the codes actually occupy — where a mark that reconciles
    with NO machine feature is placed, since a correspondence needs a lever arm."""
    sig = template_signature(template)
    return 0.5 * (R_LO + R_HI) * sig.rmax


def feature_from_azimuth(template: trimesh.Trimesh, azimuth_deg: float,
                         kind: str = "trench") -> PartFeature:
    """A mark given as a bare AZIMUTH — typed, or an untouched mark re-sent on save.

    It reconciles with the machine's own reading by the SAME rule a click does
    (``_snap_to_auto``), and that is load-bearing, not tidiness: an unreconciled mark is
    placed on the coded band's mid-radius, and that FABRICATED lever arm would hand the
    concentric screw bore (0.02-0.11mm off axis across the catalog) a 2mm arm on a plain
    re-save — turning the one landmark ``MIN_LEVER_ARM_MM`` exists to refuse into a
    nameable rotation anchor. Reconciling also keeps a mark's identity: an untouched
    ``trench-02`` re-sent by azimuth comes back as ``trench-02``, not as a fresh
    free-hand id."""
    az = wrap_deg(float(azimuth_deg))
    snapped = _snap_to_auto(auto_features(template), az)
    if snapped is not None:
        return _as_operator_mark(snapped)
    return PartFeature(id=operator_feature_id(az), kind=kind, azimuth_deg=az,
                       radius_mm=coded_band_radius_mm(template),
                       z_mm=template_signature(template).ztop, source="operator")


def feature_from_point(template: trimesh.Trimesh,
                       point_canonical: Sequence[float],
                       kind: str = "trench") -> PartFeature:
    """The operator clicked the PART in 3D — turn that click into a mark.

    SNAPPING: when the click lands within ``SNAP_AZIMUTH_DEG`` and ``SNAP_RADIUS_MM`` of
    an auto feature, the auto feature's GEOMETRY AND ID are adopted (the mark agrees
    with the machine's own reading, and the two can never drift by a hand-tremor);
    outside either window the operator's exact azimuth is kept — the machine does not
    overrule the eye. Either way the result carries ``source="operator"``: the field
    records who placed the mark, and the id tells you which machine feature it agrees
    with.

    Raises ValueError when the click cannot be a feature of this part: off the part's
    measured extent, or inside the lever-arm radius where there is no azimuth to speak
    of. (Domain invariant — the server turns it into a 422.)"""
    p = np.asarray(point_canonical, float)
    if p.shape != (3,) or not np.isfinite(p).all():
        raise ValueError("a part click must be a finite [x, y, z] triple in the "
                         "part's canonical frame")
    centre = template_rim_centre(template)
    v = np.asarray(template.vertices, float)
    extent = float(np.linalg.norm(v[:, :2] - centre, axis=1).max())
    off = p[:2] - centre
    radius = float(np.linalg.norm(off))
    if radius > extent + CLICK_SLACK_MM:
        raise ValueError(f"the click is {radius:.2f}mm from the part's rim centre but "
                         f"the part only reaches {extent:.2f}mm — that point is not on "
                         f"this part")
    if radius < MIN_LEVER_ARM_MM:
        raise ValueError(f"the click is {radius:.2f}mm from the part's rim centre — "
                         f"inside {MIN_LEVER_ARM_MM}mm there is no azimuth to mark (a "
                         f"concentric landmark names the axis, not a clock angle)")
    azimuth = float(np.degrees(np.arctan2(off[1], off[0])))

    snapped = _snap_to_auto(auto_features(template), azimuth, radius)
    if snapped is not None:
        return _as_operator_mark(snapped)
    return PartFeature(id=operator_feature_id(azimuth), kind=kind,
                       azimuth_deg=azimuth, radius_mm=radius, z_mm=float(p[2]),
                       source="operator")


def operator_feature_id(azimuth_deg: float) -> str:
    """A free-hand mark's identity IS its azimuth (rounded to the degree): two marks
    that collide are the same mark placed twice, and the annotation's duplicate-id
    invariant then rejects the contradiction instead of silently keeping both."""
    return "operator-{:03d}".format(int(round(wrap_deg(azimuth_deg))) % 360)
