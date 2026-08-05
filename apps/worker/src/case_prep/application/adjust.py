"""THE FOUR ADJUST TOOLS for the product — the demo's operator-rework endpoints, lifted.

FINAL TRANCHE of the server.py lift (plan §4 Adjust / §7 slice 6; copy-debt ledger
row 5). Supersedes, FOR THE PRODUCT: the rotation nudge and its judging
(server.py:1268-1608), align-to-mark (1611-1742), align-to-correspondence
(1745-1994) and the manual best-fit (1997-2244). The demo keeps its own copies
behind the freeze.

THE DOCTRINE, unchanged and non-negotiable: every operator act is a GATED PROPOSAL.
The same ring-fixed kinematics, the same stability bound and the same certification
gates that judge the pipeline's own clocking judge the human's hand. A proposal that
fails them is REFUSED with the gate's own sentence — never silently ignored, never
quietly corrected into something the gates would accept. Nothing here self-corrects.

REFUSALS COME IN TWO CLASSES, matching the demo's own split so the BFF can serve them
without inventing a taxonomy:

  - ``AdjustInvalid`` — the ASK was malformed (a mark across the arch, nine pairs, a
    lever arm inside the axis, a diameter out of bounds). The demo's 422.
  - ``AdjustRefused`` — a GATE said no (the rim cannot hold the rotation, the top face
    would pull off, the part would ride off). The demo's 409.
  - ``AlreadyOptimal`` (an ``AdjustRefused``) — the one refusal that is really a PASS:
    the certified pose already IS the best fit inside the band the operator asked
    about. It carries the machine-readable fields the demo added for exactly this
    (client ask 2026-07-26), so a surface can render a green confirmation with a
    one-click widen instead of re-shipping a refusal-toned pass.

THE TWO-POINT SPAN (client ask 2026-07-26, plan §5) is the one piece of genuinely new
physics in this module — see ``span_readings`` and ``direction_delta`` for the whole
derivation and the radiality gate that keeps a hole's arbitrary diameter from
poisoning the mean.

DIVERGENCES from the lifted region, recorded here and in ledger row 5 per its rules:

  - THE PACKAGE IS THE CALLER'S RUN DIRECTORY — a parameter (AM-1), exactly as
    ``run.run_case`` takes its ``out_dir``. The demo worked under ``OUT/<case>/
    package``; application code names no reports path.
  - NO ``run-history.jsonl``. The demo's append-only stream is serve-time provenance
    in the demo's data plane; the product's replayable audit is the site record's own
    append-only ``adjustments`` list, which now carries an ``evidence`` block (the
    operator's points and the derived observations) so the geometry replays from the
    shipped record itself. The BFF adds nothing to it.
  - NO ``_update_run_row``. The demo folded the post-adjustment reading into its
    cached ``run.json`` on disk; the product's run summary lives in the case session,
    so the reading RETURNS (``AdjustOutcome.clocking`` / ``.deviation`` / ``.best_fit``,
    plus ``.stale_metrics`` — see ``STALE_AFTER_REWORK``) and the BFF folds it into the
    session row inside its own CAS mutation. The demo's row was a CACHE; the product's
    is sealed by the confirmation, which is why this module now says what it re-derived
    and what it could not.
  - NO persisted part ANNOTATION. The demo let an operator re-mark the library part
    and stored the result; the product has no annotator yet, so the part's features
    are the machine's own reading (``auto_features``) — the demo's own auto-seed, with
    the human-override half arriving when the annotator does.
  - The tools also return the SEATED PANE PAYLOAD (``application.preview.
    deviation_payload`` over the new pose) because the product's Adjust stage re-renders
    the three panes from the pose that just passed the gates. The demo's UI reloaded
    the shipped STL instead. Same instrument, same scale as Declare's preview — one
    payload builder, so a pose read before and after an adjustment is comparable.

DIVERGENCES ADDED BY THE ADVERSARIAL REVIEW OF 2026-07-28 (ledger row 5's addendum),
all of them restrictive or corrective — nothing here loosens a bound:

  - INVERSE-VARIANCE WEIGHTS on the correspondence mean (``observation_weight``), where
    the demo weighted every pair equally. Equal weighting is this formula's own special
    case at one shared lever arm — a coded cap's own geometry — so a feature fit
    reproduces the demo exactly; a SPAN no longer hands its averaged midpoint's gain to
    a reading several times noisier.
  - THE SCAN-SIDE LEVER GUARD (``require_clock_lever``) extends the demo's part-side
    ``MIN_LEVER_ARM_MM`` rule to the half it was never applied to.
  - RESET REFUSES a site already on its certified pose (``reset_target``) and retires
    the record's ``best_fit`` with the pose it described. The demo's reset was free;
    this one costs the case its confirmation and release.
  - EVERY best-fit refusal carries the demo's own dial prefix again
    (``best_fit_refusal``) — the lift had kept it on one branch of four.

Plain functions over ``case_prep.pipeline``/``domain``/``adapters`` — NO server import
(test_application_boundaries' AST guard), no HTTP types.
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import trimesh
from scipy.spatial import cKDTree

from case_prep.adapters.output_package import register_package_files
from case_prep.adapters.qc_render import render_alignment_proof
from case_prep.domain.clock_signature import (canon_point_to_world, notch_reading,
                                              scan_rim_centre, template_signature,
                                              wrap_deg)
from case_prep.domain.part_features import (CLICK_SLACK_MM, MIN_LEVER_ARM_MM,
                                            PartAnnotation, PartFeature,
                                            auto_features,
                                            coded_feature_azimuths,
                                            template_rim_centre)
from case_prep.pipeline.auto_flow import (_BEST_FIT_CORR_DIST_MM, _cap_patch_roi,
                                          _crowns_frame, _posed_rim_centre,
                                          _refine_best_fit, _rim_agreement_mm,
                                          _ring_fixed_candidate)

from .cases import CaseRecord
from .catalog import _library_for
from .detection import _scan_mesh
from .preview import deviation_payload


# --- refusals: the demo's two classes, named ---------------------------------------------

class AdjustInvalid(ValueError):
    """The ASK was malformed — a mark across the arch, too many pairs, a lever arm
    inside the part's own axis, a span shorter than its own click noise. The message
    is the whole payload: one human sentence the BFF serves verbatim (the demo's
    422)."""


class AdjustRefused(RuntimeError):
    """A GATE said no. The message is the gate's own sentence, servable verbatim (the
    demo's 409). Nothing was written: a refusal changes nothing at all."""


class AlreadyOptimal(AdjustRefused):
    """THE REFUSAL THAT IS A PASS (client ask 2026-07-26): the certified pose already
    IS the best fit inside the matching band the operator asked about. Still a
    refusal by outcome — nothing changed, nothing to adopt — but it carries the two
    numbers a surface needs to render it GREEN with a one-click widen, because a
    pass wearing a refusal's clothes taught the operator to distrust the tool."""

    def __init__(self, message: str, matching_diameter_mm: float,
                 suggested_diameter_mm: float):
        super().__init__(message)
        self.matching_diameter_mm = float(matching_diameter_mm)
        self.suggested_diameter_mm = float(suggested_diameter_mm)


# --- the bounds, copied VERBATIM from the frozen region ----------------------------------

_NUDGE_MAX_STEP_DEG = 45.0        # a nudge is a correction, not a re-seat
_NUDGE_STABILITY_BOUND_MM = 0.35  # _ring_fixed_candidate excess bound (winner-pass)
_NUDGE_FACE_MEAN_BOUND_MM = 0.4   # face-mean degradation allowance (_clock_gates_ok)
_NUDGE_P90_BOUND_MM = 1.5         # the certification guards' top-face p90 limit
_NUDGE_BAND_REFUSAL_MM = 1.6      # rim-band >= 1.6-and-worsening refusal

_MARK_MAX_DISTANCE_MM = 15.0      # a trench mark belongs ON the site, not across the arch
_CORRESPONDENCE_MAX_PAIRS = 8
# A span on the LIBRARY part cannot be longer than the part. Healing caps in this
# catalog run 4-8mm across, so 12mm is past every one of them with room for a click's
# slack — a bound that catches a mis-click on the far side of the pane without ever
# limiting a real feature. (The SCAN side derives its own bound from the seated
# template's rmax; the part side is checked before a template is in hand.)
_PART_SPAN_MAX_MM = 12.0

_BEST_FIT_DEFAULT_DIAMETER_MM = 0.3
_BEST_FIT_MIN_DIAMETER_MM = 0.05
# ceiling = 2 * the winner pass's own correspondence cutoff (auto_flow's
# _BEST_FIT_CORR_DIST_MM = 1.0mm)
_BEST_FIT_MAX_DIAMETER_MM = 2.0 * _BEST_FIT_CORR_DIST_MM
_BEST_FIT_SEED = 23               # the OPERATOR path is deterministic; state restored


# --- THE TWO-POINT SPAN: the bounds and the maths (plan §5, client ask 2026-07-26) -------
#
# WHY A SPAN AT ALL. One centre click on a trench carries the operator's whole ±0.3mm
# scatter into the rotation. Two clicks at the ENDS of the same feature give:
#   - a MIDPOINT, which averages that scatter (~0.21mm from two ±0.3mm clicks) and
#     whose ends are visually unambiguous where "the centre" is a judgement call;
#   - a DIRECTION, which is a SECOND observation of the same rotation and — this is
#     the part that makes it worth having — a statistically INDEPENDENT one. The
#     midpoint's angular error is driven by (e1 + e2)/2, the direction's by (e2 - e1);
#     for iid click noise those two combinations are uncorrelated, so the pair really
#     does buy two readings rather than one read twice.
#
# WHAT THE DIRECTION IS COMPARED AGAINST. The part half of a pair names ONE azimuth
# (a feature, or a free click), never a direction — ``PartFeature`` carries azimuth,
# radius and z and nothing else. The part-side direction therefore comes from the
# RADIAL MODEL: the coded cutouts are radial slots in the coded band (clock_signature
# reads them as deep cells over a RANGE of r at one theta), so both ends of a trench
# lie along the radius through its azimuth, and the expected span direction on the
# part IS that azimuth.
#
# WHERE THE MODEL BREAKS, AND HOW IT IS CAUGHT — TWO WAYS, because one is not enough.
#
#  (1) A CHORD ACROSS AN OFF-AXIS FEATURE is a span whose direction is arbitrary while
#      its midpoint is still a perfectly good averaged click. It is testable from the
#      clicks alone, because the disagreement between the two observations,
#      ``direction - midpoint_azimuth``, is INVARIANT under the rotation being solved
#      for (both rotate together). Past ``SPAN_RADIAL_TOLERANCE_DEG`` the span reads as
#      chordal: its MIDPOINT still counts (the averaged centre, which is the whole
#      value of spanning a hole out on the part) and its direction is dropped WITH THE
#      REASON STATED — and the reason rides on the observation row the operator reads,
#      not only into the record on disk (review 2026-07-28).
#
#  (2) A SPAN ACROSS THE SCREW ACCESS is the case (1) cannot see, and it is the one an
#      operator is most likely to click, because the access is the biggest thing on the
#      cap. The access is centred ON the part axis, so a diametral span's midpoint
#      lands on the rim centre itself: ``azimuth_deg`` degenerates to atan2(0, 0) and
#      the radial offset reads a PERFECT 0° — the radiality gate reports the most
#      radial span it will ever see and passes the direction through (measured: 33% of
#      hole spans, with the midpoint azimuth essentially uniform over the full circle).
#      The discriminator is the MIDPOINT'S OWN LEVER ARM, and the rule is the domain's
#      existing one, applied to the half it had never been applied to: inside
#      ``MIN_LEVER_ARM_MM`` of the measured rim centre a mark names the AXIS, not a
#      clock angle. See ``require_clock_lever``.
#
# WHAT EACH OBSERVATION IS WORTH. Two readings of one quantity are combined by INVERSE
# VARIANCE or the better one is thrown away by the worse — see ``observation_weight``.

# A span shorter than the operator's own click scatter has no direction to read — the
# two ends are one point plus noise. The fleet's measured click-scatter p90 is 0.61mm,
# so 1.0mm is the shortest span whose direction is signal rather than scatter.
MIN_SPAN_MM = 1.0

# Beyond 30° the span is materially chordal rather than radial — a hole's diameter, a
# rim edge — and the radial model's direction would be a bias, not an average. Below
# it the departure is what two ±0.3mm clicks on a short trench produce on their own.
SPAN_RADIAL_TOLERANCE_DEG = 30.0


def azimuth_deg(point_xy: Sequence[float], centre_xy: Sequence[float]) -> float:
    """The azimuth of a canonical-frame point about the measured rim centre, degrees
    CCW — the ONE angular convention this module measures in (the same centre the
    template's feature azimuths are named about and the e8 correlation compares its
    two images under)."""
    p = np.asarray(point_xy, float)
    c = np.asarray(centre_xy, float)
    return float(np.degrees(np.arctan2(p[1] - c[1], p[0] - c[0])))


@dataclass(frozen=True)
class SpanReadings:
    """What two canonical-frame clicks on ONE part feature read out.

    ``midpoint_azimuth_deg`` is the averaged click — it feeds the circular mean
    exactly as a single centre click does (the equality is pinned by test).
    ``direction_deg`` is the span's own bearing in the canonical xy plane, folded to
    a half-turn because a span is UNDIRECTED: clicking A→B and B→A must read the same.
    ``radial_offset_deg`` is the rotation-invariant departure from the radial model —
    the number the radiality gate judges. ``midpoint_lever_mm`` is how far that
    averaged click sits from the measured rim centre: the arm that turns click noise
    into an angle, and the ONE reading that tells an axis-centred span apart from a
    radial one (the radial offset cannot — see the module's note (2)).

    ``baseline_mm`` is the span's length IN THIS PLANE, which is shorter than the two
    clicks' 3-D separation whenever the span runs down the cap's wall. It is the
    baseline ``direction_deg`` was actually read over, so it — not the 3-D distance —
    is what the direction's weight divides by. A span with almost no baseline in plane
    carries almost no clock direction, and the weight says so on its own."""

    midpoint_azimuth_deg: float
    direction_deg: float
    radial_offset_deg: float
    midpoint_lever_mm: float
    baseline_mm: float


def _fold_half_turn(deg: float) -> float:
    """Wrap into (-90, 90]: a span has no head or tail, so ``d`` and ``d + 180``
    are the same bearing and must produce the same reading."""
    folded = wrap_deg(deg)
    if folded > 90.0:
        folded -= 180.0
    elif folded <= -90.0:
        folded += 180.0
    return float(folded)


def span_readings(a_xy: Sequence[float], b_xy: Sequence[float],
                  centre_xy: Sequence[float]) -> SpanReadings:
    """The span's two observations plus its own radiality read, all in the canonical
    xy plane about the measured rim centre. Pure — hand-computable, and unit-pinned."""
    a = np.asarray(a_xy, float)
    b = np.asarray(b_xy, float)
    mid = (a + b) / 2.0
    midpoint_az = azimuth_deg(mid, centre_xy)
    delta = b - a
    direction = _fold_half_turn(float(np.degrees(np.arctan2(delta[1], delta[0]))))
    return SpanReadings(
        midpoint_azimuth_deg=midpoint_az,
        direction_deg=direction,
        radial_offset_deg=_fold_half_turn(direction - midpoint_az),
        midpoint_lever_mm=float(np.linalg.norm(mid - np.asarray(centre_xy, float))),
        baseline_mm=float(np.linalg.norm(delta)),
    )


def require_clock_lever(radius_mm: float, label: str, *, span: bool) -> float:
    """THE SCAN-SIDE LEVER-ARM RULE (review 2026-07-28, finding A) — the domain's own
    ``MIN_LEVER_ARM_MM`` statement applied to the half it had never been applied to.

    A mark inside ``MIN_LEVER_ARM_MM`` of the measured rim centre names the part's
    AXIS, and an axis carries no clock angle: its azimuth is whatever the click noise
    made it. The part half has refused such a landmark since the annotator landed
    (``PartFeature.defines_rotation``, ``_part_half`` below); the scan half did not,
    and the screw access — the biggest, most clickable feature on a healing cap — sits
    exactly there.

    Guarding BOTH halves is deliberate, not symmetry for its own sake: a guard on the
    span alone would be theatre, because the same operator could send the same useless
    spot as a single centre click and get the same garbage rotation through.

    Returns the arm (mm) so callers can go straight on to weighting by it."""
    radius = float(radius_mm)
    if radius >= MIN_LEVER_ARM_MM:
        return radius
    if span:
        raise AdjustInvalid(
            f"the span for {label!r} has its midpoint {radius:.2f}mm from the cap's "
            f"measured rim centre — a span across the SCREW ACCESS is a diameter "
            f"through the part axis, so its midpoint names the axis, not a clock "
            f"angle, and its direction is the arbitrary bearing of a diameter; "
            f"inside {MIN_LEVER_ARM_MM}mm neither end of it can anchor a rotation. "
            f"Span a coded trench along its own radius instead")
    raise AdjustInvalid(
        f"the scan mark for {label!r} sits {radius:.2f}mm from the cap's measured rim "
        f"centre — inside {MIN_LEVER_ARM_MM}mm it names the axis, not a clock angle, "
        f"and cannot anchor a rotation; click the coded trench out on the cap's face")


# --- THE LANDMARKS THE SOFTWARE PROPOSES (client 2026-07-29, item 3) -----------------
#
# "We also need another tool where we automatically mark the points in the library and
# the client has to match the same points on the scan."
#
# The part half of a correspondence pair has always been the easy half — the machine
# already knows every coded feature on the library part and which of them can anchor a
# rotation. Making the operator FIND those by eye, on both halves, is what produced the
# screw-access span the guard above has to refuse: the most clickable feature on a
# healing cap is the one that carries no clock at all.
#
# Proposing the part half removes that failure by CONSTRUCTION rather than by warning:
# every landmark offered here has already passed ``defines_rotation``, so a pair built
# on one cannot fail the part-side lever rule, and the operator's whole job becomes the
# half only a human can do — recognising the same feature in a noisy scan.


def landmark_point(feature: PartFeature,
                   centre_xy: Sequence[float]) -> Tuple[float, float, float]:
    """A feature's CARTESIAN point in the part's canonical frame.

    ``PartFeature`` stores cylindrical coordinates about the part's rim centre, which
    is what makes a feature azimuth directly comparable with a clock reading; the
    viewer needs a point. This is the inverse of the (azimuth, radius) the annotator
    measured, about the SAME centre convention (``template_rim_centre``) — get the
    centre wrong and every landmark lands on a ghost ring offset from the part.

    Pure — hand-computable, and unit-pinned."""
    theta = math.radians(feature.azimuth_deg)
    return (float(centre_xy[0]) + feature.radius_mm * math.cos(theta),
            float(centre_xy[1]) + feature.radius_mm * math.sin(theta),
            float(feature.z_mm))


def clock_landmarks(template: trimesh.Trimesh) -> List[dict]:
    """The part's rotation-defining landmarks, best clock evidence FIRST.

    Filtered by ``PartFeature.defines_rotation`` — a concentric bore names the axis,
    not a clock angle, so offering one would invite exactly the pairing the scan-side
    guard refuses. Sorted by lever arm descending because rotation error scales as
    1/lever: the first landmark offered is the one whose match buys the most.

    Returns plain dicts (the wire's shape), so the BFF adds no vocabulary of its own."""
    centre_xy = template_rim_centre(template)
    out: List[dict] = []
    for feature in auto_features(template):
        if not feature.defines_rotation:
            continue
        x, y, z = landmark_point(feature, centre_xy)
        out.append({
            "id": feature.id,
            "kind": feature.kind,
            "point": [round(x, 4), round(y, 4), round(z, 4)],
            "lever_arm_mm": round(feature.radius_mm, 3),
            "azimuth_deg": round(feature.azimuth_deg, 2),
        })
    out.sort(key=lambda row: -row["lever_arm_mm"])
    return out


# --- WHAT EACH OBSERVATION IS WORTH (review 2026-07-28, finding B) ------------------------

# Every observation estimates the SAME rotation, so the least-squares combination is
# their weighted circular mean with w = 1/variance. The variances follow from ONE
# assumption — iid click noise with per-axis sigma s — and s CANCELS out of the ratio,
# so these weights need no calibration and no fleet constant:
#
#   a single click at lever arm R : angular sigma  s / R            -> w = R^2
#   a span MIDPOINT at lever arm R: averaging two clicks halves the
#                                   positional variance             -> w = 2 R^2
#   a span DIRECTION over baseline L: differencing two clicks doubles
#                                   it, spread over the baseline L  -> w = L^2 / 2
#
# L is the span's IN-PLANE baseline (``SpanReadings.baseline_mm``), not the two clicks'
# 3-D separation: the direction is read in the canonical xy plane, so a span running
# down the cap's wall has a shorter baseline than its click distance suggests and must
# not be weighted as though it were long.
#
# The direction earns the midpoint's weight exactly at L = 2R and not before. Weighting
# the two EQUALLY (as the lift first shipped) hands the noisier reading the same say as
# the averaged one. Measured, 20,000 trials at sigma = 0.3mm, rotation RMS in degrees:
#
#   trench          one click   midpoint alone   direction alone   EQUAL   INVERSE-VAR
#   1.5 -> 2.5mm      8.68          6.14              26.55        13.66      5.99
#   1.8 -> 2.9mm      7.40          5.17              24.20        12.38      5.06
#   1.0 -> 3.0mm      8.79          6.09              12.47         6.95      5.48
#
# Equal weighting was WORSE than one plain centre click on two of the three; inverse
# variance beats the midpoint alone on all three. That ordering is not luck — it is the
# defining property of the weights (see ``test_a_second_reading_can_never_make_the_
# answer_worse``): the combined variance 1/(w1+w2) is never worse than either reading's
# own, so a second click is a gain at best and free at worst, never a regression.
#
# DIVERGENCE FROM THE LIFTED REGION, recorded (ledger row 5): the demo weighted every
# correspondence equally. That is this formula's own special case whenever the pairs
# share one lever arm — which is what a coded cap gives, since its trenches sit in one
# band — so a fit over named features reproduces the demo's rotation exactly. A fit
# mixing FREE points at different radii now weights the longer arm more, because it is
# the more precise reading and always was.
#
# The lever the weight uses is the PART half's: it is exact (the template's own
# geometry) where the scan-side radius is itself a noisy click, and the two agree by
# construction whenever the fit is anywhere near right.

# how much MORE precise than a single click each lever-arm reading is (1 / its variance
# ratio): a midpoint averages two clicks, so its weight is twice a lone click's.
_OBSERVATION_WEIGHT_GAIN = {"point": 1.0, "midpoint": 2.0}


def observation_weight(kind: str, lever_mm: float,
                       span_length_mm: Optional[float] = None) -> float:
    """One observation's inverse-variance weight (see the derivation above).

    The lever-arm readings are strictly positive by construction —
    ``require_clock_lever`` floors the arm at ``MIN_LEVER_ARM_MM``. A DIRECTION's weight
    is floored by nothing and is not meant to be: a span running down the cap's wall has
    almost no in-plane baseline, so its bearing names almost no clock angle, and a weight
    that falls toward zero is the estimator saying exactly that. It cannot reach zero
    while the midpoint carries the pair (``circular_mean_deg`` still has a positive sum).

    An unknown ``kind`` raises rather than defaulting: a new observation type without a
    variance is a programming error, and silently giving it weight 1 would be exactly
    the equal-weighting bug this function exists to end."""
    if kind == "direction":
        if span_length_mm is None:
            raise ValueError("a direction observation is weighted by its span length")
        return float(span_length_mm) ** 2 / 2.0
    return _OBSERVATION_WEIGHT_GAIN[kind] * float(lever_mm) ** 2


def direction_delta(direction_deg: float, part_azimuth_deg: float,
                    midpoint_delta_deg: float) -> float:
    """The rotation the span's DIRECTION asks for, disambiguated by its midpoint.

    Under the radial model the part's expected span bearing is its own azimuth, so
    the direction asks for ``direction - part_azimuth`` — but only modulo 180°, since
    the span is undirected. The MIDPOINT observation resolves the half-turn: the
    representative nearer to it is the one that describes the same physical rotation.
    (That is the division of labour between the two: the direction is precise, the
    midpoint is unambiguous.)"""
    base = _fold_half_turn(direction_deg - part_azimuth_deg)
    alternative = wrap_deg(base + 180.0)
    if abs(wrap_deg(alternative - midpoint_delta_deg)) < \
            abs(wrap_deg(base - midpoint_delta_deg)):
        return float(alternative)
    return float(wrap_deg(base))


def circular_mean_deg(deltas: Sequence[float],
                      weights: Optional[Sequence[float]] = None) -> float:
    """The least-squares rotation over angular observations — atan2 of the summed
    unit vectors (server.py:1944-1946), now with a WEIGHT per observation.

    A plain arithmetic mean would get this wrong across the ±180 seam, which is the
    whole reason the demo used the circular form. ``weights=None`` is the demo's
    equal-weight sum, byte-for-byte; a weight vector is the inverse-variance
    combination ``observation_weight`` derives. Equal weights and None agree exactly
    (pinned by test), so the lifted behaviour is a special case rather than a rewrite.
    """
    rad = np.radians(np.asarray(list(deltas), float))
    if weights is None:
        w = np.ones(rad.shape)
    else:
        w = np.asarray(list(weights), float)
        if w.shape != rad.shape:
            raise ValueError(f"every observation needs its own weight — got "
                             f"{w.size} for {rad.size} observation(s)")
    return float(np.degrees(np.arctan2(float((w * np.sin(rad)).sum()),
                                       float((w * np.cos(rad)).sum()))))


def validate_span(a: Sequence[float], b: Sequence[float], label: str,
                  max_span_mm: float) -> float:
    """The span's own validation, in words — every refusal names what to do instead.
    Returns the span's length in mm (the direction observation's lever arm)."""
    a_arr = np.asarray(a, float)
    b_arr = np.asarray(b, float)
    if a_arr.shape != (3,) or b_arr.shape != (3,):
        raise AdjustInvalid(f"the span for {label!r} needs two [x, y, z] points — "
                            f"both ends of the feature")
    if not (np.isfinite(a_arr).all() and np.isfinite(b_arr).all()):
        raise AdjustInvalid(f"the span for {label!r} has a non-finite end — both "
                            f"clicks must land on the scan")
    length = float(np.linalg.norm(b_arr - a_arr))
    if length < MIN_SPAN_MM:
        raise AdjustInvalid(
            f"the two ends of {label!r} are {length:.2f}mm apart — a span shorter "
            f"than {MIN_SPAN_MM:.1f}mm has no direction to read (coincident clicks "
            f"are one point, not a span); click the feature's two ENDS, or send a "
            f"single centre point instead")
    if length > max_span_mm:
        raise AdjustInvalid(
            f"the two ends of {label!r} are {length:.2f}mm apart — that is longer "
            f"than the cap itself ({max_span_mm:.2f}mm across), so the two clicks "
            f"cannot be spanning one feature of it")
    return length


# --- the site context: the shipped record and the frame it was judged in -----------------

@dataclass(frozen=True)
class SiteContext:
    """Everything an adjust tool acts on, read once (the demo's ``_load_rotation_site``,
    lifted): the shipped record and its library template, plus the site-local (crowns)
    frame and the shipped pose expressed within it — the same frame the winner pass
    judged the pose in (``_crowns_frame`` is deterministic on the scan, so the round
    trip is exact)."""

    case_id: str
    tooth: int
    run_dir: Path
    implant_path: Path
    record: dict
    model: str
    variant: Optional[str]
    template: trimesh.Trimesh
    scan_points: np.ndarray
    frame: np.ndarray
    origin: np.ndarray
    local_points: np.ndarray      # the scan in the site-local frame (the demo's L)
    pose_local: np.ndarray        # the shipped pose in that frame (the demo's t_now)


def implant_record_path(run_dir: Path, case_id: str, tooth: int) -> Path:
    """The site's shipped record inside a run directory — the pipeline's own naming
    (``<case>-<tooth>-implant.json``, adapters/output_package)."""
    return Path(run_dir) / f"{case_id}-{tooth}-implant.json"


def load_site(case: CaseRecord, run_dir: Path, tooth: int) -> SiteContext:
    """Read the run's shipped record for one site and rebuild the frame it was judged
    in. Refuses (never guesses) when the run has no pose for this tooth, when the
    record names no implant system, or when the shipped variant has left the current
    library."""
    run_dir = Path(run_dir)
    implant_path = implant_record_path(run_dir, case.id, tooth)
    if not implant_path.exists():
        raise AdjustInvalid(f"tooth {tooth} has no shipped pose in this run for case "
                            f"{case.id!r} — there is nothing aligned to adjust")
    record = json.loads(implant_path.read_text())
    # the model comes from the SHIPPED RECORD, not from a folder-name match: the run
    # was made under an explicit operator selection and implant.json carries it
    model = record.get("implant_model") or case.suggested_model
    if model is None:
        raise AdjustRefused(f"the shipped record for case {case.id!r} names no "
                            f"implant model — cannot re-pose")
    variant = record.get("variant_code")
    scan = _scan_mesh(case.scan)
    library = _library_for(case.data_root, model, [variant] if variant else None)
    spec = next((sp for sp in library.specs if sp.variant == variant), None)
    if spec is None:
        raise AdjustRefused(f"shipped variant {variant!r} is not in the current "
                            f"{model} library — cannot re-pose")
    template = library.template(spec)
    pts = np.asarray(scan.vertices, float)
    frame, origin, _axis = _crowns_frame(pts, np.asarray(scan.vertex_normals, float))
    local = (pts - origin) @ frame
    world = np.asarray(record["pose_matrix"], float)
    pose_local = np.eye(4)
    pose_local[:3, :3] = frame.T @ world[:3, :3]
    pose_local[:3, 3] = frame.T @ (world[:3, 3] - origin)
    return SiteContext(
        case_id=case.id, tooth=tooth, run_dir=run_dir, implant_path=implant_path,
        record=record, model=model, variant=variant, template=template,
        scan_points=pts, frame=frame, origin=origin, local_points=local,
        pose_local=pose_local)


# --- the gates (server.py:1412-1490, verbatim maths) -------------------------------------

def _certification_gates(template: trimesh.Trimesh, L: np.ndarray, t_now: np.ndarray,
                         cand: np.ndarray) -> None:
    """THE certification bounds every operator pose change is judged by — the exact
    winner-pass math (``_clock_gates_ok`` in auto_flow): face-mean +0.4, top-face p90
    1.5 ride-off, rim-band >= 1.6-and-worsening. Raises ``AdjustRefused`` in the
    gate's own words.

    Shared by the ROTATION paths and the 6-DoF best-fit from ONE implementation (the
    demo's 2026-07-25 factoring, kept): a best-fit has no ring-fixed kinematics to
    form, but it is judged by the same bounds."""
    # The ROI stand-in is the 8mm site crop the clock reading itself uses (the run's
    # localization ROI is not persisted; every gate is relative — before vs after over
    # the SAME point set — so the stand-in judges the same degradation the winner pass
    # would).
    tv = np.asarray(template.vertices, float)
    tpv = tv[tv[:, 2] > tv[:, 2].max() - 1.2]
    if len(tpv) > 400:
        tpv = tpv[np.linspace(0, len(tpv) - 1, 400).astype(int)]
    crop = L[np.linalg.norm(L[:, :2] - t_now[:2, 3], axis=1) < 8.0]
    if len(tpv) < 30 or len(crop) < 40:
        # FAIL CLOSED: with too few points the face/p90/band gates cannot be judged —
        # an unjudgeable proposal is refused, never adopted on the stability bound
        # alone ("the gates are never bypassed")
        raise AdjustRefused(f"too few scan points near the site to judge the "
                            f"certification gates ({len(crop)} in the 8mm crop)")
    crop_tree = cKDTree(crop)

    def _face_mean(m):
        return float(crop_tree.query(tpv @ m[:3, :3].T + m[:3, 3])[0].mean())

    def _top_p90(m):
        return float(np.percentile(
            crop_tree.query(tpv @ m[:3, :3].T + m[:3, 3])[0], 90))

    d0, d1 = _face_mean(t_now), _face_mean(cand)
    if d1 > d0 + _NUDGE_FACE_MEAN_BOUND_MM:
        raise AdjustRefused(f"the top face would pull off the scan "
                            f"({d0:.2f} → {d1:.2f}mm mean, bound "
                            f"+{_NUDGE_FACE_MEAN_BOUND_MM}mm)")
    p0, p1 = _top_p90(t_now), _top_p90(cand)
    if p1 > _NUDGE_P90_BOUND_MM and p1 > p0 + 0.02:
        raise AdjustRefused(f"the part would ride off on one side (top-face p90 "
                            f"{p0:.2f} → {p1:.2f}mm, limit {_NUDGE_P90_BOUND_MM}mm)")
    # rim-band anchor from the CURRENT pose: the ring-fixed kinematics hold the
    # measured rim centre still, so the same anchor is valid at both poses. A 6-DoF
    # best-fit may slide the rim off that anchor, which can only make this comparison
    # HARSHER — a conservative gate, never a permissive one.
    ac = _posed_rim_centre(template, t_now)
    ar = float(np.percentile(np.linalg.norm(tv[:, :2], axis=1), 97))
    if ac is not None:
        bv0 = _rim_agreement_mm(L, ac, ar, template, t_now)
        bv1 = _rim_agreement_mm(L, ac, ar, template, cand)
        if (bv0 is not None and bv1 is not None
                and bv1 >= _NUDGE_BAND_REFUSAL_MM and bv1 > bv0 + 0.02):
            raise AdjustRefused(f"the rim band would leave the scan "
                                f"({bv0:.2f} → {bv1:.2f}mm, refusal at "
                                f"{_NUDGE_BAND_REFUSAL_MM}mm-and-worsening)")


def judge_rotation(template: trimesh.Trimesh, L: np.ndarray, t_now: np.ndarray,
                   applied: float) -> Tuple[np.ndarray, float]:
    """One operator rotation proposal through the FULL judging path every rotation
    tool shares: ring-fixed candidate formation, the stability bound, then
    ``_certification_gates``. Returns (candidate_pose, stability_excess_mm) only when
    every gate passes; raises ``AdjustRefused`` otherwise."""
    rf = _ring_fixed_candidate(template, t_now[:3, :3], t_now[:3, 3],
                               float(np.radians(applied)))
    if rf is None:
        raise AdjustRefused("the part's rim ring is unmeasurable — a ring-fixed "
                            "rotation cannot be formed for this site")
    cand, excess = rf
    if excess > _NUDGE_STABILITY_BOUND_MM:
        raise AdjustRefused(f"ring-fixed stability excess {excess:.2f}mm exceeds the "
                            f"{_NUDGE_STABILITY_BOUND_MM}mm certification bound — the "
                            f"rim cannot hold this rotation still")
    _certification_gates(template, L, t_now, cand)
    return cand, excess


def _read_clock_at(L: np.ndarray, template: trimesh.Trimesh,
                   t_ref: np.ndarray, t_at: np.ndarray):
    """Coded-cutout residual at pose ``t_at`` (site-local frame), with the scan's rim
    centre estimated ONCE at ``t_ref`` and mapped through as a physical point — the
    winner pass's own protocol (re-estimating per pose breaks two-pose consistency,
    measured; see clock_signature's module doc)."""
    sig = template_signature(template)
    crop = L[np.linalg.norm(L[:, :2] - t_ref[:2, 3], axis=1) < 8.0]
    canon0 = (crop - t_ref[:3, 3]) @ t_ref[:3, :3]
    c0 = scan_rim_centre(canon0, sig.ztop, sig.rmax)
    c_phys = t_ref[:3, :3] @ np.array([c0[0], c0[1], sig.ztop]) + t_ref[:3, 3]
    canon1 = (crop - t_at[:3, 3]) @ t_at[:3, :3]
    c1 = ((c_phys - t_at[:3, 3]) @ t_at[:3, :3])[:2]
    return notch_reading(canon1, sig, c1)


def _clocking_fields(notch) -> dict:
    """The instrument reading as the run row carries it (server.py:1348-1353)."""
    return {
        "notch_shift_deg": (round(notch.shift_deg, 1)
                            if notch.shift_deg is not None else None),
        "notch_corr": round(notch.corr, 3),
        "notch_prominence": round(notch.prominence, 3),
    }


# --- the site click mapping (server.py:1835-1851, lifted) --------------------------------

@dataclass(frozen=True)
class SiteClicks:
    """The mapping from an operator's WORLD click on the scan into this site's
    canonical frame, plus the scan's own once-estimated rim centre — factored so one
    pair and many pairs measure identically (the demo's ``_site_click_azimuth``)."""

    context: SiteContext
    rim_centre_xy: np.ndarray

    def to_canon_xy(self, point_world: Sequence[float]) -> np.ndarray:
        ctx = self.context
        t_now = ctx.pose_local
        p_local = ctx.frame.T @ (np.asarray(point_world, float) - ctx.origin)
        return ((p_local - t_now[:3, 3]) @ t_now[:3, :3])[:2]

    def azimuth_of(self, point_world: Sequence[float]) -> float:
        return azimuth_deg(self.to_canon_xy(point_world), self.rim_centre_xy)


def site_clicks(ctx: SiteContext, sig=None) -> SiteClicks:
    """ONE PIVOT FOR EVERY ANGULAR READ (the −17.1° ghost probe, 2026-08-05).

    The scan side used to measure click azimuths about the scan's MEASURED rim
    centre while the part side measures feature azimuths about the TEMPLATE's own
    rim centre — and the applied rotation pivots on the template frame. Two pivots
    make the delta between a click and the feature it names carry pure PARALLAX,
    scaled by (centre offset / lever arm): on 276794487 t3, with the measured
    centre ~0.5mm off at a 1.64mm lever, pairing a landmark with its own projected
    position asked for −17.1° when the honest answer is zero — and the operator's
    one-point pair rotated +176° ("wrong alignment, even with the one point").
    A click's azimuth is now measured about the SAME centre the feature azimuths,
    the signature and the rotation are expressed in. The lever guards inherit the
    same pivot, which also makes their own words true — "a mark names the part
    AXIS" is now literally the distance from the part's axis convention. The
    measured scan rim centre remains a MEASUREMENT (qc/clock instruments read it);
    it is no longer an angle pivot."""
    return SiteClicks(context=ctx,
                      rim_centre_xy=template_rim_centre(ctx.template))


# --- adoption: re-emit, re-read, record ---------------------------------------------------

def _reemit_site(ctx: SiteContext, cand: np.ndarray) -> Path:
    """Compose the site-local candidate back to the jaw-world frame and re-emit the
    site's shipped geometry — the aligned-cap STL the viewer loads — updating the
    record's pose fields in place. The construction/scanbody deliverables re-pose on
    the next full run; an operator adjustment corrects the cap-alignment record."""
    w_new = np.eye(4)
    w_new[:3, :3] = ctx.frame @ cand[:3, :3]
    w_new[:3, 3] = ctx.origin + ctx.frame @ cand[:3, 3]
    posed = ctx.template.copy()
    posed.apply_transform(w_new)
    cap_path = ctx.run_dir / f"{ctx.case_id}-{ctx.tooth}-healingcap-aligned.stl"
    cap_path.write_bytes(posed.export(file_type="stl"))
    ctx.record["pose_matrix"] = w_new.tolist()
    ctx.record["position"] = w_new[:3, 3].tolist()
    ctx.record["axis"] = w_new[:3, 2].tolist()
    return cap_path


def _finish_adjustment(ctx: SiteContext, cand: np.ndarray, cap_path: Path,
                       operation: str, detail: str,
                       evidence: Optional[dict] = None) -> List[str]:
    """The common TAIL of every adopted adjustment: append the provenance entry to the
    site's append-only ``adjustments`` record, persist implant.json, render the
    ALIGNMENT PROOF, and re-hash the rewritten files into the package manifest.

    The proof (``<case>-<tooth>-alignment-proof.png``) exists only for sites a human
    actually moved — a clean automatic run never produces one. Manifest registration
    repairs a real gap: an adjustment rewrites the cap STL and implant.json in place,
    so their emission-time hashes went stale. A package with no manifest is left alone
    rather than failing the adjustment.

    ``evidence`` is the product's addition (the demo put this on run-history.jsonl,
    which the product does not keep): the operator's own points and the observations
    derived from them, so the geometry replays from the shipped record itself."""
    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "operation": operation,
        # this layer authenticates nobody. Recording "operator" AND saying that the
        # identity was never captured is the honest record; a name here would be
        # invented (the same posture bff/session.py takes about its signed records).
        "who": "operator (no identity is captured)",
        "detail": detail,
    }
    if evidence:
        entry["evidence"] = evidence
    ctx.record.setdefault("adjustments", []).append(entry)
    ctx.implant_path.write_text(json.dumps(ctx.record, indent=2))
    # the proof is drawn in the SITE-LOCAL frame (points and pose share it) — the same
    # canonical picture the world-frame pair would give, without rebuilding the cloud
    proof = render_alignment_proof(ctx.case_id, ctx.tooth, ctx.local_points, cand,
                                   ctx.template, ctx.record["adjustments"], ctx.run_dir)
    names = [cap_path.name, ctx.implant_path.name, proof.name]
    manifest = ctx.run_dir / f"{ctx.case_id}-manifest.json"
    if manifest.exists():
        register_package_files(manifest, [ctx.run_dir / n for n in names])
    return names


def clock_reference(ctx: SiteContext) -> dict:
    """THE MEASURED RIM CENTRE ``require_clock_lever`` guards against (plan §10-F),
    in WORLD coordinates, beside its own bound — so a client can measure the SAME
    quantity the guard does and refuse locally with no risk of disagreeing.

    ``site_clicks(ctx, sig).rim_centre_xy`` is exactly what every scan-side lever
    check in this module reads (``observations_for``'s single-point and span
    branches, ``align_to_mark``'s click azimuth) — this does not recompute it a
    different way, it only changes the point's COORDINATES, via
    ``canon_point_to_world`` (an exact composition through ``pose_matrix``, proved by
    the round-trip test in test_adjust.py, not merely asserted)."""
    sig = template_signature(ctx.template)
    clicks = site_clicks(ctx, sig)
    pose_world = np.asarray(ctx.record["pose_matrix"], float)
    rim_world = canon_point_to_world(clicks.rim_centre_xy, sig.ztop, pose_world)
    return {"rim_centre": [round(float(v), 6) for v in rim_world],
            "min_lever_mm": MIN_LEVER_ARM_MM}


def _seated_payload(ctx: SiteContext) -> dict:
    """The three panes' union read over the record's CURRENT pose — the same builder
    Declare's preview uses (``application.preview.deviation_payload``), so a pose read
    before and after an adjustment is the same instrument on the same scale.
    ``preview=False``: this colouring describes a SHIPPED pose, not a pre-run seat."""
    payload = deviation_payload(
        ctx.case_id, ctx.tooth, ctx.scan_points,
        np.asarray(ctx.record["pose_matrix"], float), ctx.template,
        implant_model=ctx.model, variant=ctx.variant, preview=False)
    payload["clock_reference"] = clock_reference(ctx)
    return payload


def seated_payload(case: CaseRecord, run_dir: Path, tooth: int) -> dict:
    """The site's shipped pose as the panes render it — Adjust's read surface before
    any tool has been used. Pure: reads the run directory, writes nothing."""
    return _seated_payload(load_site(case, run_dir, tooth))


# --- WHAT AN ADJUSTMENT RE-DERIVES, AND WHAT IT CANNOT (review 2026-07-28, finding E) ----
#
# The run's summary row describes A POSE. When a tool moves that pose, every
# pose-dependent number in the row describes a cap that is no longer on the site — and
# the product's confirmation SEALS that row (bff/resources/deliver.py's assurance
# projection reads its deviation, its rim agreement and its guidance verbatim). Sealing
# stale numbers under a freshly derived hash is worse than not re-hashing: the hash
# proves the bytes changed, never that they are true.
#
# The split below is exactly what CAN be recomputed here and what cannot:
#
#   RE-DERIVED. The deviation scalars are a pure function of (scan, pose, template),
#   and the panes' payload already publishes them from ``site_deviation_stats`` — the
#   very function that wrote the run row. So they are not recomputed by a second
#   transcription; they are READ OFF the same instrument the operator is looking at,
#   which is why the row and the pane cannot drift apart again.
#
#   NOT RE-DERIVED, AND SAID SO. ``rim_agreement_mm`` was anchored on the scan's own
#   fitted rim circle (auto_flow's rim_fit_circle / the doctor's rim marks) — run-time
#   data the shipped record does not carry. Re-deriving it here on the posed rim centre
#   instead would put a DIFFERENT NUMBER under the same name, which is the failure this
#   whole fix is about. ``guidance`` is a pure function too, of a dozen run-time inputs
#   the row does not carry (top-face p90, coverage, the diameter classification, the
#   seed's provenance). Naming them is the honest half: the sealed document then states
#   which of its numbers predate the rework, and the doctor signs knowing that.
#
# Both are re-derived for real by the next full run. This is a rework surface, not a
# re-run.

STALE_AFTER_REWORK = ("rim_agreement_mm", "guidance")


def rederived_reading(pane_payload: dict) -> dict:
    """The run-row numbers an adjustment re-derives, read off the panes' own payload.
    A payload without scalars re-derives NOTHING rather than a comforting zero."""
    stats = pane_payload.get("stats") or {}
    return {"deviation_rms_mm": stats.get("rms_mm"),
            "deviation_p90_mm": stats.get("p90_mm")}


def _post_adjustment_reading(ctx: SiteContext,
                             stale: bool = True) -> Tuple[dict, dict, List[str]]:
    """The panes' read over the pose that just landed, the row numbers it re-derives,
    and the row numbers it leaves behind.

    ``stale=False`` is the RESET's case and it is not a shortcut: a reset puts the site
    back on the pipeline's own certified pose, so the run's rim agreement and guidance
    describe it correctly again. Nothing predates a rework that has been undone."""
    payload = _seated_payload(ctx)
    return (payload, rederived_reading(payload),
            list(STALE_AFTER_REWORK) if stale else [])


# --- the outcomes -------------------------------------------------------------------------

@dataclass(frozen=True)
class AdjustOutcome:
    """What an applied tool produced. ``clocking`` is the post-adjustment instrument
    reading the caller folds into its run row; ``files`` are the run-relative names
    the adjustment rewrote or added; ``pane_payload`` is the new pose's union read
    (None when nothing was applied — a measure-only best-fit)."""

    tooth: int
    operation: str
    detail: str
    files: List[str] = field(default_factory=list)
    clocking: Optional[dict] = None
    # the run-row numbers this act RE-DERIVED over the new pose, and the ones it could
    # not (``STALE_AFTER_REWORK``) — the caller folds the first into its row and states
    # the second on the document the operator signs
    deviation: Optional[dict] = None
    stale_metrics: List[str] = field(default_factory=list)
    nudge: Optional[dict] = None
    applied_delta_deg: Optional[float] = None
    cumulative_deg: Optional[float] = None
    stability_excess_mm: Optional[float] = None
    best_fit: Optional[dict] = None
    pairs: List[dict] = field(default_factory=list)
    residual_rms_mm: Optional[float] = None
    # WHETHER ``residual_rms_mm`` IS EVIDENCE (``cross_checked``, the vacuous-RMS defect
    # 2026-08-01). None on every tool that reports no residual at all; False on the
    # 1-observation fit-by-points, where ``residual_rms_mm`` is None for the same reason.
    # Carried BESIDE the number rather than left to be inferred from an empty field:
    # "there is no figure" and "the figure means nothing" are different facts, and a
    # surface must be able to say the second one out loud.
    cross_checked: Optional[bool] = None
    click_azimuth_deg: Optional[float] = None
    matched_feature_azimuth_deg: Optional[float] = None
    applied: bool = True
    pane_payload: Optional[dict] = None


def fold_outcome_into_row(row: dict, outcome: AdjustOutcome,
                          correspondence_pairs: Optional[int] = None) -> None:
    """Fold an applied tool's outcome into the run-summary row that DESCRIBES THE
    POSE THAT SHIPPED (finding E, 2026-07-28) — the ONE fold, serving both callers:
    the BFF's interactive landing (``bff.resources.adjust._fold_outcome``) and the
    run's evidence re-apply (``application.run._reapply_evidence``, §10-AD). They
    were two hand-written folds once and drifted on four shapes (audit 2026-08-04:
    staleness under a key no projection read, clocking replaced wholesale — erasing
    ``rotation_unverified`` and claiming a verified rotation — nudge and best_fit
    never folded). Sharing one function is what retires that defect class.

    The shapes, and why each is the way it is:

    - ``clocking`` MERGES over the pipeline's block. The tool re-measures only the
      notch keys (``_clocking_fields``); ``evidence``/``consistency_deg``/
      ``rotation_unverified`` are the automation's own facts and survive any rework
      by design — the product's rotation-unverified notice depends on it.
    - ``deviation`` overwrites even with None values: "missing" is the honest
      reading of a pose nobody could measure; keeping pre-rework figures would be
      the stale-row bug again.
    - what could NOT be re-derived lands under ``rework.stale_metrics`` — the ONE
      key the assurance and receipt projections read (bff/resources/deliver.py). An
      act with nothing stale (the reset) CLEARS it: nothing predates a rework that
      has been undone.
    - ``nudge`` only when the tool rotated (the demo's 2026-07-25 rule: a manual
      best-fit is a 6-DoF move, not a clock nudge, and must not overwrite the
      site's cumulative rotation); ``best_fit`` only when one landed, and a
      rotation-reset clears it — the site is back on the pipeline's own pose.
    - the correspondence block BELONGS TO THE ACT THAT PRODUCED IT: rebuilt with
      the caller's pair count on a fit-by-points (span/direction counts off the
      observations' own KINDS — three chord spans are not three clean clicks), and
      popped by every other applied act, because a residual measured against a
      pose that no longer exists must not stand in a sealed document.
      ``cross_checked`` derives HERE from the observation count the same block
      states, so the two numbers in one block can never disagree (the vacuous-RMS
      defect, 2026-08-01).

    Package-file bookkeeping stays with the callers — their containers differ
    (session receipt vs run summary); every ROW shape lives here.
    """
    if outcome.clocking:
        row["clocking"] = {**(row.get("clocking") or {}), **outcome.clocking}
    if outcome.deviation:
        row.update(outcome.deviation)
    if outcome.stale_metrics:
        row["rework"] = {"stale_metrics": list(outcome.stale_metrics)}
    else:
        row.pop("rework", None)
    if outcome.nudge is not None and outcome.operation != "best-fit":
        row["nudge"] = outcome.nudge
    if outcome.best_fit is not None:
        row["best_fit"] = outcome.best_fit
    elif outcome.operation == "rotation-reset":
        row.pop("best_fit", None)
    if correspondence_pairs is not None:
        kinds = [str(p.get("observation") or "") for p in outcome.pairs
                 if isinstance(p, dict)]
        observations = len(outcome.pairs)
        row["correspondence"] = {"pairs": correspondence_pairs,
                                 "observations": observations,
                                 "spans": kinds.count("midpoint"),
                                 "directions_used": kinds.count("direction"),
                                 "max_pairs": _CORRESPONDENCE_MAX_PAIRS,
                                 "residual_rms_mm": outcome.residual_rms_mm,
                                 "cross_checked": cross_checked(observations)}
    else:
        row.pop("correspondence", None)


def _adopt_rotation(ctx: SiteContext, cand: np.ndarray, applied: float,
                    cumulative: float, operation: str, detail: str,
                    evidence: Optional[dict] = None) -> Tuple[dict, dict, List[str]]:
    """ADOPTED ROTATION: anchor the certified pose, re-emit the site's shipped record,
    then re-read the coded-cutout residual at the new pose (the codes are the arbiter
    the operator is steering toward), and write the provenance + alignment proof.
    Returns (clocking, nudge_fields, files)."""
    t_now = ctx.pose_local
    anchored = anchor_certified_pose(ctx.record)   # BEFORE the pose fields are rewritten
    cap_path = _reemit_site(ctx, cand)
    nudge_fields = {"operator_delta_deg": round(applied, 1),
                    "cumulative_deg": round(cumulative, 1)}
    ctx.record["nudge"] = {**nudge_fields, "base_pose_matrix": anchored.tolist()}
    clocking = _clocking_fields(_read_clock_at(ctx.local_points, ctx.template,
                                               t_now, cand))
    files = _finish_adjustment(ctx, cand, cap_path, operation, detail, evidence)
    return clocking, nudge_fields, files


def _rotation_state(ctx: SiteContext) -> Tuple[np.ndarray, float]:
    """The site's rotation bookkeeping as it stands: the pipeline's own certified base
    pose (world frame) and the cumulative operator rotation applied to it.

    A pure READ — its twin ``anchor_certified_pose`` is the CAPTURE, and the two are
    deliberately separate: this one is called before a proposal is even judged (a
    refusal must leave the record untouched), that one only once a pose is being
    adopted."""
    nudge_state = ctx.record.get("nudge") or {}
    base_pose = np.asarray(nudge_state.get("base_pose_matrix")
                           or ctx.record["pose_matrix"], float)
    return base_pose, float(nudge_state.get("cumulative_deg") or 0.0)


def anchor_certified_pose(record: dict) -> np.ndarray:
    """CAPTURE — once — the pipeline's certified pose as this site's reset anchor.

    Every operator act calls this BEFORE it overwrites ``record['pose_matrix']``. After
    that write the certified pose is gone from the record, and an anchor taken then
    would be the operator's OWN output: Reset would faithfully restore the very thing
    it was asked to undo. Making the capture a named act rather than an incidental read
    is what makes that ordering checkable.

    Idempotent, which is the other half of the rule: the second act on a site must not
    re-anchor to the first one's result."""
    nudge = record.setdefault("nudge", {})
    if not nudge.get("base_pose_matrix"):
        nudge["base_pose_matrix"] = [[float(v) for v in row]
                                     for row in record["pose_matrix"]]
    return np.asarray(nudge["base_pose_matrix"], float)


# a pose is "already the certified one" well below any movement an operator can make:
# the measured no-op reset moved 1.8e-15mm, and the tightest real act moves ~1e-4mm.
_RESET_NOOP_TOL_MM = 1e-9


def reset_target(record: dict) -> dict:
    """WHAT A RESET WOULD RESTORE — or a refusal, when the site is already standing on
    it (review 2026-07-28, finding D).

    Reset looked free because geometrically it can be: on an untouched site it moves
    the pose by 1.8e-15mm. It is not free at all. It rewrites the cap STL, drops the
    site to ADJUSTED, and retires the case's confirmation AND its release — so a stray
    click on a delivered case cost the operator their signature to undo nothing.

    The test reads the PHYSICS, not the bookkeeping: the anchor against the pose that
    is actually on the record. That one comparison covers a site nobody has touched
    (no anchor, so the anchor IS the current pose), a site whose acts were already
    reset once, and a nudge block with no anchor to restore from — and it cannot be
    fooled by a cumulative-degrees test, which would wave through the reset of a
    best-fit (a 6-DoF move that books no rotation at all)."""
    nudge = record.get("nudge") if isinstance(record.get("nudge"), dict) else {}
    current = np.asarray(record["pose_matrix"], float)
    base = np.asarray(nudge.get("base_pose_matrix") or record["pose_matrix"], float)
    if np.allclose(base, current, atol=_RESET_NOOP_TOL_MM):
        raise AdjustInvalid(
            "this site already stands on the pipeline's certified pose — there is "
            "nothing to reset. Reset undoes an operator's own rotation or best-fit; "
            "applying it here would rewrite the shipped cap and retire the case's "
            "confirmation to move nothing")
    return nudge


def reset_discards(record: dict, cumulative_deg: float) -> str:
    """The parenthetical on a reset's own sentence: everything the act throws away, in
    the acts' own words. It named the rotation only, while a reset after a best-fit
    silently discarded a 6-DoF move as well (suites 2026-07-28)."""
    parts: List[str] = []
    if abs(float(cumulative_deg)) >= 0.05:
        parts.append(f"{float(cumulative_deg):+.1f}° of operator rotation")
    best = record.get("best_fit")
    if isinstance(best, dict):
        dial = best.get("matching_diameter_mm")
        parts.append(f"a best-fit at Ø{float(dial):.2f}mm" if dial is not None
                     else "a best-fit")
    return " and ".join(parts) if parts else "an operator adjustment"


# --- TOOL 3: the gated rotation step (server.py:1571-1608) -------------------------------

def rotate_site(case: CaseRecord, run_dir: Path, tooth: int, step_deg: float = 0.0,
                reset: bool = False) -> AdjustOutcome:
    """One operator rotation step, degrees CCW about the seated part's own axis —
    the industry-canonical human backstop for weak or unverified clocking.

    ``reset`` restores the pipeline's own certified pose (``step_deg`` is ignored):
    the base pose IS the pipeline's certified output, so restoring it verbatim needs
    no re-judging. Every other step is a proposal through ``judge_rotation``."""
    if not np.isfinite(step_deg) or abs(step_deg) > _NUDGE_MAX_STEP_DEG:
        raise AdjustInvalid(f"step_deg must be a finite step within "
                            f"±{_NUDGE_MAX_STEP_DEG:.0f}°")
    ctx = load_site(case, run_dir, tooth)
    base_pose, prior_cum = _rotation_state(ctx)
    excess: Optional[float] = None
    if reset:
        reset_target(ctx.record)
        applied, cumulative = -prior_cum, 0.0
        cand = np.eye(4)
        cand[:3, :3] = ctx.frame.T @ base_pose[:3, :3]
        cand[:3, 3] = ctx.frame.T @ (base_pose[:3, 3] - ctx.origin)
        detail = (f"restored the pipeline's certified pose (undoing "
                  f"{reset_discards(ctx.record, prior_cum)})")
        operation = "rotation-reset"
        # the best-fit block described a pose this act has just undone; a record that
        # keeps it would claim a fit that is no longer on the site (the same invariant
        # the run row's re-derivation holds — a document describes what shipped)
        ctx.record.pop("best_fit", None)
    else:
        applied = float(step_deg)
        cumulative = prior_cum + applied
        cand, excess = judge_rotation(ctx.template, ctx.local_points, ctx.pose_local,
                                      applied)
        detail = (f"rotated {applied:+.1f}° about the part axis "
                  f"(cumulative {cumulative:+.1f}°)")
        operation = "rotation"
    clocking, nudge_fields, files = _adopt_rotation(
        ctx, cand, applied, cumulative, operation, detail)
    payload, deviation, stale = _post_adjustment_reading(ctx, stale=not reset)
    return AdjustOutcome(
        tooth=tooth, operation=operation, detail=detail, files=files,
        clocking=clocking, deviation=deviation, stale_metrics=stale,
        nudge=nudge_fields,
        applied_delta_deg=round(applied, 1), cumulative_deg=round(cumulative, 1),
        stability_excess_mm=(round(excess, 3) if excess is not None else None),
        pane_payload=payload)


# --- TOOL 4: mark the trench (server.py:1678-1742) ---------------------------------------

def align_to_mark(case: CaseRecord, run_dir: Path, tooth: int,
                  scan_point: Sequence[float]) -> AdjustOutcome:
    """The operator marks the cap's CODED CUTOUT on the scan (the screw hole itself is
    invisible — a smooth dome — but the coded trench IS visible) and the cap rotates so
    its NEAREST code feature lands there. A proposal through the exact rotation
    machinery: same ring-fixed kinematics, same stability bound, same gates."""
    point = np.asarray(scan_point, float)
    if point.shape != (3,) or not np.isfinite(point).all():
        raise AdjustInvalid("the mark must be a finite [x, y, z] point on the scan")
    ctx = load_site(case, run_dir, tooth)
    site_pos = np.asarray(ctx.record["pose_matrix"], float)[:3, 3]
    dist = float(np.linalg.norm(point - site_pos))
    if dist > _MARK_MAX_DISTANCE_MM:
        raise AdjustInvalid(f"the mark is {dist:.1f}mm from tooth {tooth}'s seated "
                            f"cap — click the coded trench on the cap itself "
                            f"(within {_MARK_MAX_DISTANCE_MM:.0f}mm)")
    sig = template_signature(ctx.template)
    features = coded_feature_azimuths(sig)   # domain/part_features: one source of truth
    if not features:
        raise AdjustRefused(f"the {ctx.variant!r} template carries no coded relief — "
                            f"there is no code feature to align to a mark")
    clicks = site_clicks(ctx, sig)
    click_az = clicks.azimuth_of(point)
    # Minimal rotation aligning the NEAREST code feature to the click: rotating the
    # part CCW by delta moves a feature at azimuth f to f+delta in the scan's frame,
    # so delta = click_az - f (wrapped), minimized over the features.
    _absd, applied, matched = min(
        (abs(wrap_deg(click_az - f)), wrap_deg(click_az - f), f) for f in features)
    _base, prior_cum = _rotation_state(ctx)
    cumulative = prior_cum + applied
    cand, excess = judge_rotation(ctx.template, ctx.local_points, ctx.pose_local,
                                  applied)
    detail = (f"marked trench at {click_az:+.1f}°: rotated {applied:+.1f}° to bring "
              f"the code feature at {matched:+.1f}° onto it "
              f"(cumulative {cumulative:+.1f}°)")
    evidence = {"scan_point": [round(float(c), 3) for c in point],
                "click_azimuth_deg": round(click_az, 1),
                "matched_feature_azimuth_deg": round(float(matched), 1)}
    clocking, nudge_fields, files = _adopt_rotation(
        ctx, cand, applied, cumulative, "mark-trench", detail, evidence)
    payload, deviation, stale = _post_adjustment_reading(ctx)
    return AdjustOutcome(
        tooth=tooth, operation="mark-trench", detail=detail, files=files,
        clocking=clocking, deviation=deviation, stale_metrics=stale,
        nudge=nudge_fields,
        applied_delta_deg=round(applied, 1), cumulative_deg=round(cumulative, 1),
        stability_excess_mm=(round(excess, 3) if excess is not None else None),
        click_azimuth_deg=round(click_az, 1),
        matched_feature_azimuth_deg=round(float(matched), 1),
        pane_payload=payload)


# --- TOOL 1: fit by points, with the two-point SPAN (server.py:1854-1994 + plan §5) ------

@dataclass(frozen=True)
class Correspondence:
    """One operator correspondence. The PART half is EITHER a feature of the library
    part (by id) OR ``part_point`` — an arbitrary canonical-frame click on the part
    itself; exactly one of the two. The SCAN half is where the operator sees that same
    spot: one click, or — the SPAN form — both ENDS of the feature."""

    scan_point: Sequence[float]
    scan_point_end: Optional[Sequence[float]] = None
    feature_id: Optional[str] = None
    part_point: Optional[Sequence[float]] = None
    # THE LIBRARY SPAN (client 2026-08-01, tool 1): both ends of the SAME feature on
    # the part, which turns the part's span bearing from an assumption into a
    # measurement. Only legal beside ``part_point`` — a ``PartFeature`` carries no
    # direction or extent, so a named feature has no second point to give.
    part_point_end: Optional[Sequence[float]] = None

    @property
    def is_span(self) -> bool:
        return self.scan_point_end is not None

    @property
    def is_part_span(self) -> bool:
        return self.part_point_end is not None


@dataclass(frozen=True)
class Observation:
    """ONE angular observation of the rotation. A single-point pair yields exactly one
    (``kind="point"``); a SPAN yields two (``"midpoint"`` and, when the span reads as
    radial, ``"direction"``) — independent readings of the same quantity, which is
    what makes a span worth two clicks.

    ``lever_mm`` is the PART half's arm: the radius at which this observation's angular
    disagreement becomes the millimetres an operator can judge. Every observation of a
    pair reports at the same arm, because they all miss the same marked feature — the
    direction was reported at its own half-length once, which made the noisiest reading
    on the table look like the tidiest (review 2026-07-28, finding C).

    ``weight`` is its inverse-variance share of the rotation (``observation_weight``).
    ``note`` is a sentence the operator is owed about this reading — today, why a span's
    direction did not count. It travels WITH the row: a reason written only to the
    record on disk is a silent no-op as far as the person clicking is concerned."""

    label: str
    kind: str
    part_azimuth_deg: float
    observed_deg: float
    delta_deg: float
    lever_mm: float
    weight: float
    note: Optional[str] = None


def _part_half(pair: Correspondence, ann: PartAnnotation, centre_xy: np.ndarray,
               model: str, variant: Optional[str],
               free_index: int) -> Tuple[str, float, float, dict, Optional[float]]:
    """The pair's PART half → (label, azimuth_deg, lever_arm_mm, audit). The lever-arm
    rule is the demo's, verbatim: a landmark inside ``MIN_LEVER_ARM_MM`` of the part's
    rim centre names the AXIS, not a clock angle."""
    if (pair.feature_id is None) == (pair.part_point is None):
        raise AdjustInvalid("each pair needs exactly one part half — a feature_id or "
                            "a part_point")
    if pair.feature_id is not None:
        feature = ann.by_id(pair.feature_id)
        if feature is None:
            known = ", ".join(f.id for f in ann.features) or "none"
            raise AdjustInvalid(f"{pair.feature_id!r} is not a marked feature of "
                                f"{model}/{variant} (known: {known})")
        if not feature.defines_rotation:
            raise AdjustInvalid(f"{feature.id!r} sits {feature.radius_mm:.2f}mm from "
                                f"the part's rim centre — inside {MIN_LEVER_ARM_MM}mm "
                                f"it names the axis, not a clock angle, and cannot "
                                f"anchor a rotation")
        return (feature.id, feature.azimuth_deg, feature.radius_mm,
                {"feature_id": feature.id}, None)
    # FREE POINT: the positional label ("point-1", "point-2" in click order) is this
    # pair's identity everywhere downstream. Free points are measured about the SAME
    # rim centre a feature azimuth is named about (domain/part_features.
    # template_rim_centre) — that identity is what lets a free pair ride the feature
    # pair's rotation math unchanged.
    label = f"point-{free_index}"
    part_point = np.asarray(pair.part_point, float)
    if part_point.shape != (3,) or not np.isfinite(part_point).all():
        raise AdjustInvalid(f"the part point for {label!r} must be a finite "
                            f"[x, y, z] triple in the part's own frame")
    off = part_point[:2] - centre_xy
    radius = float(np.linalg.norm(off))
    if radius < MIN_LEVER_ARM_MM:
        raise AdjustInvalid(f"{label!r} sits {radius:.2f}mm from the part's rim "
                            f"centre — inside {MIN_LEVER_ARM_MM}mm it names the axis, "
                            f"not a clock angle, and cannot anchor a rotation")
    part_audit = {"label": label,
                  "part_point": [round(float(c), 3) for c in part_point]}
    if pair.part_point_end is None:
        return (label, float(np.degrees(np.arctan2(off[1], off[0]))), radius,
                part_audit, None)
    # THE LIBRARY SPAN. Validated with the SCAN side's own span rule so one operator
    # act cannot be judged two ways, and its MIDPOINT is what the lever-arm guard
    # reads — the same discriminator the scan half uses, for the same reason: a
    # library span across the screw access is a diameter through the part axis.
    end = np.asarray(pair.part_point_end, float)
    validate_span(part_point, end, label, _PART_SPAN_MAX_MM)
    mid = (part_point[:2] + end[:2]) / 2.0
    mid_off = mid - centre_xy
    mid_radius = float(np.linalg.norm(mid_off))
    if mid_radius < MIN_LEVER_ARM_MM:
        raise AdjustInvalid(
            f"the library span for {label!r} has its midpoint {mid_radius:.2f}mm from "
            f"the part's rim centre — a span across the part's own axis names the "
            f"axis, not a clock angle. Span a coded feature out on the part's face")
    delta = end[:2] - part_point[:2]
    direction = _fold_half_turn(float(np.degrees(np.arctan2(delta[1], delta[0]))))
    part_audit["part_point_end"] = [round(float(c), 3) for c in end]
    part_audit["part_direction_deg"] = round(direction, 1)
    # the azimuth and arm are the MIDPOINT's, exactly as the scan half averages its
    # own two clicks — an averaged click is the whole value of spanning
    return (label, float(np.degrees(np.arctan2(mid_off[1], mid_off[0]))), mid_radius,
            part_audit, direction)


def observations_for(pair: Correspondence, label: str, part_azimuth: float,
                     lever_mm: float, clicks: SiteClicks, max_span_mm: float,
                     audit: dict,
                     part_direction: Optional[float] = None) -> List[Observation]:
    """One pair's angular observations, and the audit record that replays them.

    A single point is the demo's math plus the scan-side lever guard:
    ``delta = click - part_azimuth``. A SPAN adds its midpoint (identical math, at the
    averaged click) and — when the span reads as RADIAL — its direction, disambiguated
    by that midpoint. Every observation leaves here already carrying the weight it will
    be combined under and the lever arm its residual will be read at.

    ``part_direction`` is the LIBRARY SPAN's own bearing (client 2026-08-01, tool 1),
    present only when the operator spanned the same feature on the part. With it the
    span's direction is read BEARING TO BEARING and the radiality gate does not apply:
    that gate exists solely to detect the RADIAL MODEL failing, and where the part's
    bearing was measured there is no model to fail. A chord matched by a chord is a
    valid direction reading; a chord matched against an assumed radius is not."""
    if not pair.is_span:
        click_xy = clicks.to_canon_xy(pair.scan_point)
        require_clock_lever(
            float(np.linalg.norm(click_xy - clicks.rim_centre_xy)), label, span=False)
        click = azimuth_deg(click_xy, clicks.rim_centre_xy)
        audit["scan_point"] = [round(float(c), 3) for c in pair.scan_point]
        return [Observation(label=label, kind="point", part_azimuth_deg=part_azimuth,
                            observed_deg=click,
                            delta_deg=wrap_deg(click - part_azimuth),
                            lever_mm=lever_mm,
                            weight=observation_weight("point", lever_mm))]

    length = validate_span(pair.scan_point, pair.scan_point_end, label, max_span_mm)
    a_xy = clicks.to_canon_xy(pair.scan_point)
    b_xy = clicks.to_canon_xy(pair.scan_point_end)
    readings = span_readings(a_xy, b_xy, clicks.rim_centre_xy)
    # BEFORE the radiality read, because the radiality read cannot see this: a span
    # across the axis-centred screw access reports a perfect 0° offset (module note 2).
    require_clock_lever(readings.midpoint_lever_mm, label, span=True)
    midpoint_delta = wrap_deg(readings.midpoint_azimuth_deg - part_azimuth)
    audit["span"] = {
        "scan_point": [round(float(c), 3) for c in pair.scan_point],
        "scan_point_end": [round(float(c), 3) for c in pair.scan_point_end],
        "length_mm": round(length, 3),
        # the in-plane baseline the direction was read over — shorter than length_mm
        # for a span running down the cap's wall, and the one the weight uses
        "baseline_mm": round(readings.baseline_mm, 3),
        "midpoint_azimuth_deg": round(readings.midpoint_azimuth_deg, 1),
        "midpoint_lever_mm": round(readings.midpoint_lever_mm, 3),
        "direction_deg": round(readings.direction_deg, 1),
        "radial_offset_deg": round(readings.radial_offset_deg, 1),
    }
    # WHAT THE SPAN'S DIRECTION IS COMPARED AGAINST decides whether it counts at all.
    # Measured (a library span): always — the two bearings are the same kind of
    # quantity. Assumed (the radial model): only while the assumption holds.
    measured = part_direction is not None
    reference = float(part_direction) if measured else part_azimuth
    radial = measured or abs(readings.radial_offset_deg) <= SPAN_RADIAL_TOLERANCE_DEG
    audit["span"]["direction_used"] = radial
    # NAMED, NOT INFERRED: the same clicks now read differently under the two models,
    # so the record says which one produced this number (the chordal-drop note's own
    # precedent, applied to why a direction COUNTED).
    audit["span"]["direction_reference"] = "library-span" if measured else "radial-model"
    note: Optional[str] = None
    if not radial:
        # NOT SILENT (the doctrine): the operator is told which half of their span
        # counted and why the other did not — and told it HERE, on the observation
        # they get back, not only in the record on disk (review 2026-07-28).
        note = (f"the span runs {abs(readings.radial_offset_deg):.0f}° off its own "
                f"radius — a chord across the feature, not along it, so its direction "
                f"names no clock angle (past {SPAN_RADIAL_TOLERANCE_DEG:.0f}°); the "
                f"averaged midpoint still counts")
        audit["span"]["direction_note"] = note
    observations = [Observation(label=label, kind="midpoint",
                                part_azimuth_deg=part_azimuth,
                                observed_deg=readings.midpoint_azimuth_deg,
                                delta_deg=midpoint_delta, lever_mm=lever_mm,
                                weight=observation_weight("midpoint", lever_mm),
                                note=note)]
    if radial:
        observations.append(Observation(
            label=label, kind="direction", part_azimuth_deg=part_azimuth,
            observed_deg=readings.direction_deg,
            delta_deg=direction_delta(readings.direction_deg, reference,
                                      midpoint_delta),
            # the residual reads at the PART's arm like every other observation of this
            # pair (they all miss the same marked feature); the span's IN-PLANE
            # baseline is what its noise rides on, and that goes into the weight
            lever_mm=lever_mm,
            weight=observation_weight("direction", lever_mm,
                                      span_length_mm=readings.baseline_mm)))
    return observations


def residual_rows(observations: Sequence[Observation],
                  applied: float) -> Tuple[List[dict], float]:
    """Each observation's disagreement with the adopted rotation, as the operator's QC
    table reads it, plus their RMS in millimetres.

    ONE ROW SHAPE for everything — a named feature, a free point, a span's midpoint,
    a span's direction — so the surface renders one list. ``residual_mm`` is the arc the
    MARKED FEATURE misses by at its own lever arm: the millimetres a person can judge,
    and comparable across the rows precisely because every row uses the same arm."""
    rows: List[dict] = []
    for obs in observations:
        res_deg = wrap_deg(obs.delta_deg - applied)
        row = {
            # a free point's and a span's label ride the same identity key as a
            # feature id — one residual shape everywhere
            "feature_id": obs.label,
            "observation": obs.kind,
            "feature_azimuth_deg": round(obs.part_azimuth_deg, 1),
            "click_azimuth_deg": round(obs.observed_deg, 1),
            "delta_deg": round(obs.delta_deg, 1),
            "residual_deg": round(res_deg, 2),
            "residual_mm": round(abs(np.radians(res_deg)) * obs.lever_mm, 3),
            # the say this reading had in the answer (inverse variance) — the number
            # that makes "why did my second click barely move it" answerable
            "weight": round(float(obs.weight), 4),
        }
        if obs.note:
            row["note"] = obs.note
        rows.append(row)
    # COMBINED THE WAY THE ROTATION WAS (review 2026-08-01). The RMS answers "did the
    # observations agree with the answer they produced?", and that answer is the
    # INVERSE-VARIANCE weighted mean above — so the agreement statistic must carry the
    # same weights. A plain root-mean-square hands a reading the estimator almost
    # ignored a full vote in the number that judges the estimate: a span's DIRECTION
    # rides a short in-plane baseline (weight L²/2) while its residual is measured at
    # the PART's arm like every other row, so on a legitimate radial span at R=3.0mm,
    # L=1.5mm, 29° off — inside this module's own SPAN_RADIAL_TOLERANCE_DEG, i.e. what
    # two ±0.3mm clicks produce on their own — the unweighted figure read 1.014mm
    # against a 1.0mm gate while the estimator had already discounted it to +1.65°.
    # That is the equal-weighting bug ``observation_weight`` exists to end, reappearing
    # one function later. The motivating defect is unmoved: three free points at
    # near-equal arms carry near-equal weights (2.355mm plain, 2.360mm weighted).
    weights = np.array([float(o.weight) for o in observations], float)
    squares = np.array([r["residual_mm"] ** 2 for r in rows], float)
    total = float(weights.sum())
    rms = float(np.sqrt(float((weights * squares).sum()) / total)) if total > 0 else 0.0
    return rows, rms


# --- THE CROSS-CHECK FLOOR (defect, cap6020-neodent-gm 2026-08-01) -----------------------
#
# A fit-by-points built from ONE observation is exactly determined for rotation: that
# single delta IS the answer, its residual is zero BY CONSTRUCTION, and the RMS over one
# zero is 0.000mm. The number is arithmetic, not evidence — there is nothing for it to
# disagree with — and the outcome sentence spent it in the same words a genuinely
# cross-checked fit earns. The real case: 14:32:30 a clean run, 14:32:52 "fit by 1 point
# pair(s) → 1 observation(s): rotated -50.9° (cumulative -50.9°), marks agree to 0.000mm
# RMS", and a site that left at 0.451mm RMS / 0.745mm p90.
#
# THE ACT STAYS POSSIBLE. One correspondence is the documented answer where the automatic
# reader has no evidence at all, and the physics supports it — raising the minimum to two
# would delete a capability instead of disclosing a limit. What changes is that the fit
# says WHICH of the two it is, in every place it speaks.
CROSS_CHECK_MIN_OBSERVATIONS = 2

# --- THE ADVISORY BAND UNDER THE BOUND (review of the gate, 2026-08-01) ------------------
#
# The evidence gate below is a REFUSAL at 1.00mm, and a refusal alone leaves the whole
# band beneath it flat: a 0.99mm fit printed the identical sentence to a 0.02mm one, which
# is a narrower version of the very complaint the gate answers — a fit with a BAD number
# saying nothing about it. The gate stopped the catastrophe and left the near-miss silent.
#
# 0.50mm is chosen from the measured fleet rather than picked: healthy fits scatter
# 0.02–0.331mm, the two refusals were 1.546 and 2.349mm, and nothing was observed between.
# A floor under 0.331 would caution every good fit into noise; one at the bound would never
# fire. This DISCLOSES, it does not gate: the operator who has a reason to accept a 0.7mm
# fit still can, which is the same division of labour the one-observation clause uses.
ADVISORY_DISAGREEMENT_MM = 0.5


def cross_checked(n_observations: int) -> bool:
    """Whether this fit's residual RMS is a MEASUREMENT or a tautology.

    Two is the floor because two is where a residual first has something to disagree
    with. Counted in OBSERVATIONS, never in pairs: one radial span is two observations
    and is genuinely cross-checked, while one chordal span is one and is not — a count
    of pairs would get both backwards."""
    return n_observations >= CROSS_CHECK_MIN_OBSERVATIONS


def agreement_words(n_observations: int, rms_mm: float) -> str:
    """The QC clause of a fit-by-points' outcome sentence.

    THE ONE-OBSERVATION BRANCH PRINTS NO MILLIMETRES, deliberately and not merely as
    phrasing: any figure it could print is the arithmetic of a single zero, and a
    reader who sees millimetres in this clause is entitled to read them as agreement."""
    if not cross_checked(n_observations):
        return ("a single observation fixes the rotation exactly — there is no second "
                "mark for it to disagree with, so this fit has no agreement number")
    if rms_mm >= ADVISORY_DISAGREEMENT_MM:
        return (f"marks agree POORLY — {rms_mm:.3f}mm RMS, inside the "
                f"{MAX_PAIR_DISAGREEMENT_MM:.2f}mm bound but well above the fleet's "
                f"click scatter; re-place the marks if this fit matters")
    return f"marks agree to {rms_mm:.3f}mm RMS"


# --- THE EVIDENCE GATE ON A CROSS-CHECKED FIT (defect, cap7030-zimmer-4.5 2026-08-01) ---
#
# The cross-check floor above answers "is this RMS a measurement?". It does not answer
# "and did the measurement PASS?" — so a fit whose marks disagreed by 2.349mm carried
# ``cross_checked: true`` and rode through every gate onto a sealed confirmation:
# "fit by 3 point pair(s) → 3 observation(s): rotated -85.3° (cumulative -85.3°), marks
# agree to 2.349mm RMS". The three pairs missed the adopted rotation by 15°, 38° and
# 108°; they named three different rotations and their weighted mean was an average of
# answers, not an answer.
#
# WHY NO EXISTING GATE CATCHES IT. ``judge_rotation`` judges the POSE, never the
# evidence: a ring-fixed candidate turns the part about its own axis, which moves the
# rim by almost nothing at any angle, so the 0.35mm stability bound passes -85.3° as
# readily as -0.3°. The certification gates read the same pose. Nothing downstream reads
# the RMS either — the product's caution fires only on ``cross_checked === false``
# (domain/deliver.ts), i.e. on the fit that has NO number, so the fit with a BAD number
# said nothing at all.
#
# THE BOUND, and what it is derived from rather than invented from: this module already
# carries the fleet's measured operator click-scatter — p90 0.61mm, from ±0.3mm clicks
# (see ``MIN_SPAN_MM``). Residuals at that scatter land a few tenths of a millimetre;
# 1.0mm is the same line ``MIN_SPAN_MM`` draws for the same measured reason, the point
# where a reading is signal rather than scatter. It is a wide gate on purpose: the
# healthy fits on this fleet measure 0.02-0.08mm RMS and the defect measured 2.349mm, so
# the bound sits in an empty gap between them and refuses only what is unambiguous.
MAX_PAIR_DISAGREEMENT_MM = 1.0


def require_pair_agreement(rows: Sequence[dict], rms_mm: float) -> None:
    """Refuse a cross-checked fit whose marks do not agree with each other.

    ``rows`` and ``rms_mm`` are ONE measurement — ``residual_rows``' own return — so the
    observation COUNT is derived here rather than passed alongside them: three
    independent arguments describing one reading can disagree, and a count that
    disagreed with the rows would have reached ``max()`` on an empty sequence and
    raised ``ValueError`` where this contract is ``AdjustInvalid``.

    Silent on a fit that is not cross-checked: with one observation the residual is
    zero BY CONSTRUCTION, so there is no disagreement to judge and none to refuse. That
    limit is DISCLOSED (``agreement_words``) rather than gated — one correspondence is
    the documented answer where the automatic reader has no evidence at all, and
    refusing it here would delete a capability instead of reading a measurement.

    Names the WORST-missing pair, because the operator's cheapest repair is one undo:
    the same affordance ``require_clock_lever``'s refusal offers, and the same one the
    product's error footer already promises ("undo just the one the message names")."""
    if not cross_checked(len(rows)):
        return None
    if rms_mm <= MAX_PAIR_DISAGREEMENT_MM:
        return None
    worst = max(rows, key=lambda r: r["residual_mm"])
    raise AdjustInvalid(
        f"the marks disagree with each other by {rms_mm:.3f}mm RMS, past the "
        f"{MAX_PAIR_DISAGREEMENT_MM:.2f}mm bound — the fleet's measured click scatter "
        f"is 0.61mm at p90, so a disagreement this size is not click noise: these "
        f"marks name DIFFERENT rotations, and their weighted mean would be an average "
        f"of answers rather than an answer. {worst['feature_id']!r} misses the fit by "
        f"the most ({worst['residual_mm']:.3f}mm) — undo that pair and re-place it on "
        f"the feature it was meant to match, rather than starting the set again")


def align_to_correspondence(case: CaseRecord, run_dir: Path, tooth: int,
                            pairs: Sequence[Correspondence]) -> AdjustOutcome:
    """FIT BY POINTS: the operator names a feature on the LIBRARY PART and the same
    feature on the SCAN, and the cap rotates so the named pairs meet.

    This is align-to-mark with the ambiguity removed — nearest-match binds a click to
    whichever code feature happens to be closest, wrong by a whole inter-feature gap on
    a 3-trench cap and unusable where the automatic reader has no evidence at all.
    More than one pair adds a QC number the operator can read: the per-observation
    residual in millimetres at its own lever arm.

    AND EXACTLY ONE OBSERVATION HAS NO SUCH NUMBER — the concession this docstring made
    in passing, now stated on the wire (``cross_checked``, the 2026-08-01 defect). One
    observation is exactly determined for rotation, so its residual is zero by
    construction. The fit is still legitimate and still applied — it is the documented
    answer where the automatic reader has no evidence — but it reports NO agreement
    figure rather than a 0.000mm RMS that means nothing.

    Still a PROPOSAL: the same ring-fixed kinematics, the same stability bound, the
    same certification gates, the same re-read and re-emit."""
    pairs = list(pairs)
    if not pairs:
        raise AdjustInvalid("name at least one correspondence — a feature of the part "
                            "and where you see it on the scan")
    if len(pairs) > _CORRESPONDENCE_MAX_PAIRS:
        raise AdjustInvalid(f"a correspondence is capped at "
                            f"{_CORRESPONDENCE_MAX_PAIRS} pairs, got {len(pairs)}")
    # The duplicate check names FEATURES only: one part feature cannot sit at two
    # places on the scan, but several free points are legal by construction — each one
    # IS its own spot on the part.
    named = [p.feature_id for p in pairs if p.feature_id is not None]
    dupes = sorted({i for i in named if named.count(i) > 1})
    if dupes:
        raise AdjustInvalid(f"feature(s) {dupes} are named twice — one part feature "
                            f"cannot sit at two places on the scan")

    # THE LIBRARY SPAN'S TWO IMPOSSIBLE SHAPES, refused here in the cheapest band
    # (this whole prelude runs before a mesh is parsed) because both are decidable
    # from the ask alone.
    for pair in pairs:
        if not pair.is_part_span:
            continue
        if pair.feature_id is not None:
            raise AdjustInvalid(
                f"{pair.feature_id!r} is a marked feature of the part, and a marked "
                f"feature has no second point — it carries an azimuth and a radius, "
                f"not a direction or an extent. Span the library with two free part "
                f"points, or name the feature and click one spot on the scan")
        if not pair.is_span:
            raise AdjustInvalid(
                "a library span was given both ends on the part but only one click "
                "on the scan — a bearing and a point have nothing to subtract. Place "
                "both ends on the scan too, or drop the second part point")

    ctx = load_site(case, run_dir, tooth)
    sig = template_signature(ctx.template)
    ann = PartAnnotation(model=ctx.model, variant=str(ctx.variant),
                         features=auto_features(ctx.template))
    centre_xy = template_rim_centre(ctx.template)
    clicks = site_clicks(ctx, sig)
    site_pos = np.asarray(ctx.record["pose_matrix"], float)[:3, 3]
    # a span must lie ON the cap: the part's own measured extent plus the hand
    # tolerance the part annotator already uses — exact, not a guessed multiple
    max_span_mm = 2.0 * float(sig.rmax) + 2.0 * CLICK_SLACK_MM

    observations: List[Observation] = []
    audit_pairs: List[dict] = []
    free_count = 0
    for pair in pairs:
        if pair.part_point is not None:
            free_count += 1
        label, part_azimuth, lever, audit, part_direction = _part_half(
            pair, ann, centre_xy, ctx.model, ctx.variant, free_count)
        for point in ([pair.scan_point] if not pair.is_span
                      else [pair.scan_point, pair.scan_point_end]):
            p = np.asarray(point, float)
            if p.shape != (3,) or not np.isfinite(p).all():
                raise AdjustInvalid(f"the mark for {label!r} must be a finite "
                                    f"[x, y, z] point on the scan")
            dist = float(np.linalg.norm(p - site_pos))
            if dist > _MARK_MAX_DISTANCE_MM:
                raise AdjustInvalid(f"the mark for {label!r} is {dist:.1f}mm from "
                                    f"tooth {tooth}'s seated cap — click the feature "
                                    f"on the cap itself (within "
                                    f"{_MARK_MAX_DISTANCE_MM:.0f}mm)")
        observations.extend(observations_for(pair, label, part_azimuth, lever,
                                             clicks, max_span_mm, audit,
                                             part_direction=part_direction))
        audit_pairs.append(audit)

    # Rotating the part CCW by delta carries a feature at canonical azimuth f to
    # f+delta in the scan's frame, so each observation asks for its own delta. With
    # one that IS the rotation; with several, the least-squares rotation over the
    # angular residuals is their circular mean, WEIGHTED BY INVERSE VARIANCE — a span
    # that averaged its click noise must not have that gain handed back to a reading
    # several times noisier (``observation_weight``).
    applied = circular_mean_deg([o.delta_deg for o in observations],
                                [o.weight for o in observations])
    residuals, rms = residual_rows(observations, applied)
    # THE MEASUREMENT IS READ, not merely reported (defect cap7030-zimmer-4.5). Before
    # any candidate pose is formed, because no POSE gate can see this: a ring-fixed turn
    # moves the rim by almost nothing at any angle, so ``judge_rotation`` would pass a
    # rotation these marks never agreed on. See ``MAX_PAIR_DISAGREEMENT_MM``.
    require_pair_agreement(residuals, rms)
    checked = cross_checked(len(observations))
    # THE RESIDUAL THAT CANNOT EXIST IS NOT REPORTED AS A NUMBER. ``residual_rms_mm`` is
    # Optional on this outcome, on the BFF's view, in the row's correspondence block and
    # on the wire's TypeScript — None was already legal everywhere, and it is the only
    # honest value here: a 0.000 travelling in a float field is a quality figure to every
    # surface that renders it, however carefully the sentence beside it is worded.
    reported_rms = round(rms, 3) if checked else None

    _base, prior_cum = _rotation_state(ctx)
    cumulative = prior_cum + applied
    cand, excess = judge_rotation(ctx.template, ctx.local_points, ctx.pose_local,
                                  applied)
    detail = (f"fit by {len(pairs)} point pair(s) → {len(observations)} observation(s): "
              f"rotated {applied:+.1f}° (cumulative {cumulative:+.1f}°), "
              f"{agreement_words(len(observations), rms)}")
    clocking, nudge_fields, files = _adopt_rotation(
        ctx, cand, applied, cumulative, "fit-by-points", detail,
        {"pairs": audit_pairs, "residuals": residuals,
         "residual_rms_mm": reported_rms, "cross_checked": checked})
    payload, deviation, stale = _post_adjustment_reading(ctx)
    return AdjustOutcome(
        tooth=tooth, operation="fit-by-points", detail=detail, files=files,
        clocking=clocking, deviation=deviation, stale_metrics=stale,
        nudge=nudge_fields,
        applied_delta_deg=round(applied, 1), cumulative_deg=round(cumulative, 1),
        stability_excess_mm=(round(excess, 3) if excess is not None else None),
        pairs=residuals, residual_rms_mm=reported_rms, cross_checked=checked,
        pane_payload=payload)


# --- TOOL 2: the bounded best-fit (server.py:2117-2244) -----------------------------------

def _pose_move(t_now: np.ndarray, cand: np.ndarray) -> dict:
    """How far a 6-DoF candidate moved the part: the ORIGIN shift in mm and the
    rotation angle in degrees — the two numbers an operator can judge (the trust
    region inside ``_refine_best_fit`` is stated in the same units)."""
    rel = cand[:3, :3] @ t_now[:3, :3].T
    angle = float(np.degrees(np.arccos(np.clip((np.trace(rel) - 1.0) / 2.0, -1.0, 1.0))))
    return {"translation_mm": round(float(np.linalg.norm(cand[:3, 3] - t_now[:3, 3])), 4),
            "rotation_deg": round(angle, 3)}


def best_fit_refusal(diameter_mm: float, reason: str) -> AdjustRefused:
    """EVERY best-fit refusal names the dial it was refused at (server.py:2084-2090's
    ``_refuse_best_fit``, whose prefix reached every branch). The lift kept the prefix
    on the trust-region exit only, so a gate refusal arrived as a bare sentence with no
    hint that widening or tightening the band was the lever — the operator's one
    control went unnamed in the very message telling them to use it."""
    return AdjustRefused(f"best-fit at a {diameter_mm:.2f}mm matching diameter "
                         f"refused: {reason}")


def _fit_residual(patch: np.ndarray, points: np.ndarray, cutoff: float) -> dict:
    """The fit's own support and residual at a pose: how many ROI scan points fall
    INSIDE the matching band of the posed part, and the RMS/max of those matched
    distances. Points beyond the band are excluded on purpose — they are the surface
    the operator's matching diameter says not to fit to."""
    d = cKDTree(points).query(patch)[0]
    matched = d[d <= cutoff]
    return {"n_matched": int(matched.size),
            "rms_mm": (round(float(np.sqrt(np.mean(matched ** 2))), 4)
                       if matched.size else None),
            "max_mm": round(float(matched.max()), 4) if matched.size else None}


def best_fit_site(case: CaseRecord, run_dir: Path, tooth: int,
                  matching_diameter_mm: float = _BEST_FIT_DEFAULT_DIAMETER_MM,
                  apply: bool = True) -> AdjustOutcome:
    """The industry's post-processing step as an OPERATOR-TRIGGERED pass on the
    shipped pose. It runs the pipeline's OWN refinement (auto_flow's
    ``_refine_best_fit``, not a second transcription), so the trust region (≤1.2mm,
    ≤8°) and the monotonic-improvement rule that keep the historical trimmed-ICP
    failure out of the winner pass keep it out of here too.

    MAPPING, stated out loud: ``domain.icp.trimmed_icp``'s ``max_corr_dist`` is a
    RADIUS, so a search DIAMETER of d maps to a cutoff of d/2.

    ``apply=False`` MEASURES ONLY: the refinement runs and the gates still judge it,
    but nothing on disk is touched — a candidate that cannot be adopted cannot be
    previewed as adoptable either."""
    if not np.isfinite(matching_diameter_mm) or not (
            _BEST_FIT_MIN_DIAMETER_MM <= matching_diameter_mm
            <= _BEST_FIT_MAX_DIAMETER_MM):
        raise AdjustInvalid(f"matching_diameter_mm must be between "
                            f"{_BEST_FIT_MIN_DIAMETER_MM} and "
                            f"{_BEST_FIT_MAX_DIAMETER_MM}mm, got "
                            f"{matching_diameter_mm!r}")
    ctx = load_site(case, run_dir, tooth)
    diameter = float(matching_diameter_mm)
    cutoff = diameter / 2.0
    t_now = ctx.pose_local
    sig = template_signature(ctx.template)
    # the ROI is the pipeline's OWN auto-brush around the shipped pose (auto_flow's
    # _cap_patch_roi — a ball at rim height), not a fresh crop invented here: the
    # refinement must see the surface the winner pass fitted, or "the same refinement"
    # is a claim and not a fact
    patch = _cap_patch_roi(ctx.local_points, t_now[:2, 3],
                           rim_radius_mm=float(sig.rmax))
    if patch is None:
        raise best_fit_refusal(diameter, "too little scan surface around the seated "
                                         "part to fit against")
    tv = np.asarray(ctx.template.vertices, float)
    if len(tv) > 4000:
        tv = tv[np.linspace(0, len(tv) - 1, 4000).astype(int)]

    def _fit_mean_mm(m: np.ndarray) -> float:
        """Mean scan-to-part distance over the ROI, read from the template's own
        VERTICES — a deterministic read-out of the quantity ``_refine_best_fit``
        judges on its seeded surface samples (reported, never the adoption
        criterion)."""
        return float(cKDTree(tv @ m[:3, :3].T + m[:3, 3]).query(patch)[0].mean())

    state = np.random.get_state()
    reject_reasons: list = []
    try:
        np.random.seed(_BEST_FIT_SEED)
        cand = _refine_best_fit(patch, ctx.template, t_now, max_corr_dist=cutoff,
                                on_reject=reject_reasons.append)
    finally:
        np.random.set_state(state)
    if cand is None:
        # A None wears TWO faces and only one is a pass. A TRUST-REGION exit means ICP
        # found only a different basin — nothing proved the certified pose optimal in
        # this band — so it refuses like every real refusal; a green "already optimal"
        # here would invite the wider search that makes the basin escape MORE likely.
        if "trust-region" in reject_reasons:
            raise best_fit_refusal(
                diameter, "the refinement left the trust region (>1.2mm or >8° from "
                          "the certified seat) — a different basin, not a refinement; "
                          "try a TIGHTER matching diameter")
        # A CONFIRMATION, NOT A FAILURE (client ask 2026-07-26): "no strict
        # improvement" at this cutoff means the certified pose already IS the best fit
        # in the band the operator asked about.
        suggested = min(_BEST_FIT_MAX_DIAMETER_MM, 2.0 * diameter)
        if suggested > diameter:
            message = (f"the certified pose is already the best fit within this "
                       f"matching diameter — nothing to correct at Ø{diameter:.2f}mm; "
                       f"widen to search further")
        else:
            # at the operator ceiling the doubled suggestion caps to the dial itself:
            # "widen" would be a lie and a one-click widen re-ran the identical search
            # forever — say the band IS the widest instead
            message = (f"the certified pose is already the best fit within this "
                       f"matching diameter — nothing to correct at Ø{diameter:.2f}mm, "
                       f"and this is the widest matching band the tool searches")
        raise AlreadyOptimal(message, matching_diameter_mm=diameter,
                             suggested_diameter_mm=suggested)

    move = _pose_move(t_now, cand)
    # THE GATES RUN EVEN FOR A PREVIEW: a candidate that cannot be adopted must not be
    # shown to the operator as adoptable either. Their sentences arrive under the
    # best-fit's own prefix (the demo's rule) — the gate said no to THIS dial setting.
    try:
        _certification_gates(ctx.template, ctx.local_points, t_now, cand)
    except AdjustRefused as exc:
        raise best_fit_refusal(diameter, str(exc)) from exc

    before, after = _fit_mean_mm(t_now), _fit_mean_mm(cand)
    fit = {"roi_mean_before_mm": round(before, 4), "roi_mean_after_mm": round(after, 4),
           "matching_diameter_mm": round(diameter, 3),
           "correspondence_cutoff_mm": round(cutoff, 3), **move,
           **_fit_residual(patch, tv @ cand[:3, :3].T + cand[:3, 3], cutoff),
           "rim_agreement_mm": None}
    anchor = _posed_rim_centre(ctx.template, cand)
    if anchor is not None:
        band = _rim_agreement_mm(
            ctx.local_points, anchor,
            float(np.percentile(np.linalg.norm(tv[:, :2], axis=1), 97)),
            ctx.template, cand)
        fit["rim_agreement_mm"] = round(band, 4) if band is not None else None

    detail = (f"best-fit at a {diameter:.2f}mm matching diameter: moved "
              f"{move['translation_mm']:.3f}mm / {move['rotation_deg']:.2f}°, ROI mean "
              f"{before:.3f} → {after:.3f}mm")
    if not apply:
        # MEASURE ONLY: judged, reported, and NOT written.
        return AdjustOutcome(tooth=tooth, operation="best-fit", detail=detail,
                             best_fit=fit, applied=False)

    # THE RESET ANCHOR, captured before ``_reemit_site`` overwrites the pose fields
    # (``anchor_certified_pose`` — same call, same ordering, as every rotation tool). A
    # best-fit is NOT a clock nudge, so it adds no rotation bookkeeping of its own; it
    # must still anchor, or a later reset would "restore" the best-fitted pose it was
    # meant to undo.
    anchor_certified_pose(ctx.record)
    cap_path = _reemit_site(ctx, cand)
    ctx.record["best_fit"] = fit
    clocking = _clocking_fields(_read_clock_at(ctx.local_points, ctx.template,
                                               t_now, cand))
    files = _finish_adjustment(ctx, cand, cap_path, "best-fit", detail,
                               {"best_fit": fit})
    payload, deviation, stale = _post_adjustment_reading(ctx)
    return AdjustOutcome(
        tooth=tooth, operation="best-fit", detail=detail, files=files,
        clocking=clocking, deviation=deviation, stale_metrics=stale,
        # the site's rotation bookkeeping as it stands, unchanged by this pass
        nudge={k: v for k, v in ctx.record["nudge"].items()
               if k != "base_pose_matrix"} or None,
        best_fit=fit, pane_payload=payload)
