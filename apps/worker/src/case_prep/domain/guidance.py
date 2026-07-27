"""The advisory gate as GUIDANCE: what should the operator DO at this site?

The gate never auto-passes (real-data policy) — but a bare ADVISORY label leaves the
human guessing. Every signal the pipeline already computes maps to a concrete action:
paint the cap, re-pick the variant, confirm with the doctor, or accept after a visual
check. Pure domain logic — explainable, unit-tested, no IO.
"""
from __future__ import annotations

from typing import Dict, List, Optional

# fit_avg beyond this on the alignment surface means the seat deserves a second look
# (the real seated caps read 0.25-0.80mm; RealGUIDE's own accepted example reads 0.28)
_FIT_AVG_ATTENTION_MM = 1.0

# border clicks disagreeing (max leave-one-out plane distance) beyond this are a suspect
# gesture, not click noise: good real gestures measure ~0.3, the client's tilted-seat
# redo measured 0.89 (a click past the rim edge on the slope). The seat still honors the
# doctor's circle — this only asks the human to re-check their own clicks.
_BORDER_CLICK_DISAGREE_MM = 0.6

# the part's top face floating beyond this off the scan means the DEPTH is visually
# wrong whatever the band says (the top face is the cap's always-visible surface —
# healthy fleet reads 0.16-0.59 mean; the two measured ride-high failures 1.96/2.45).
# Border clicks pin depth authoritatively, so that is the routed action.
_TOP_FACE_OFF_MM = 1.5
# rotation instruments (coded cutouts vs recess azimuth) must agree on a rigid part;
# beyond this the disagreement itself is the finding (2026-07-20 validation: the
# recess azimuth is the biased instrument when its dip is partially visible)
_CLOCK_CONSISTENCY_DEG = 20.0


def advisory_guidance(seat_method: str, fit_avg_mm: Optional[float],
                      fit_max_mm: Optional[float], declared: Optional[str],
                      dia_class_confident: bool, measurement_disputes_declared: bool,
                      variant_ambiguous: bool, axis_violation: bool,
                      seed_source: str, candidates_too_close: bool = False,
                      border_points_given: bool = False,
                      border_clicks_disagree_mm: Optional[float] = None,
                      top_face_off_mm: Optional[float] = None,
                      rotation_unverified: bool = False,
                      clock_consistency_deg: Optional[float] = None) -> Dict:
    """One verdict + concrete actions per site.

    Levels: ``ready`` (all checks agree — accept after the visual check),
    ``attention`` (a specific check wants a human decision),
    ``action-needed`` (the pipeline could not produce a trustworthy seat).
    """
    actions: List[str] = []
    level = "ready"

    if axis_violation:
        level = "action-needed"
        actions.append("The part could not seat within the plausible axis cone — "
                       "paint the cap area with the brush (🖌 Mark cap) and re-run.")
        actions.append("If there is no healing cap at this site, reject the proposal.")

    if measurement_disputes_declared:
        level = "attention" if level == "ready" else level
        actions.append("The measured rim diameter disagrees with the declared variant — "
                       "confirm the declaration with the doctor or re-pick it in the "
                       "library picker (compare with 'view part').")

    if declared is None and variant_ambiguous:
        level = "attention" if level == "ready" else level
        actions.append("The rim measurement sits between size classes, so the variant "
                       "was identified by fit alone — choose the variant in the library "
                       "picker or obtain the doctor's declaration.")

    if top_face_off_mm is not None and top_face_off_mm > _TOP_FACE_OFF_MM:
        level = "attention" if level == "ready" else level
        actions.append(f"The part's top face sits {top_face_off_mm:.1f}mm off the "
                       "scan — the seating depth is suspect at this site. Click "
                       "several points around the cap's visible border (◐) to pin "
                       "centre, width and depth, then recompute.")

    if (border_clicks_disagree_mm is not None
            and border_clicks_disagree_mm > _BORDER_CLICK_DISAGREE_MM):
        level = "attention" if level == "ready" else level
        actions.append(f"One border click sits {border_clicks_disagree_mm:.2f}mm off "
                       "the plane of the other clicks — a click past the rim edge on "
                       "the slope tilts the whole seat. Re-click the odd point (◐) or "
                       "add 1-2 more border points, then recompute.")

    if candidates_too_close:
        level = "attention" if level == "ready" else level
        actions.append("Two size variants seat almost equally well — the scan cannot "
                       "separate them; the doctor's declaration is required before "
                       "construction (billing + fit).")

    if rotation_unverified:
        level = "attention" if level == "ready" else level
        actions.append("The cap's ROTATION could not be verified — neither the coded "
                       "cutouts nor the screw recess gave usable evidence at this "
                       "site. Visually check the coded features in view 1 (top-down) "
                       "before accepting; a brush over the cap's top face can add "
                       "signal.")

    if clock_consistency_deg is not None and clock_consistency_deg > _CLOCK_CONSISTENCY_DEG:
        level = "attention" if level == "ready" else level
        actions.append(f"The two rotation instruments disagree by "
                       f"{clock_consistency_deg:.0f}° (coded cutouts vs screw-recess "
                       "direction) — on a rigid part both cannot be right. The pose "
                       "follows the coded cutouts (the more reliable signal); "
                       "visually confirm the notches line up in the top-down view.")

    if fit_avg_mm is not None and fit_avg_mm > _FIT_AVG_ATTENTION_MM:
        level = "attention" if level == "ready" else level
        actions.append(f"Registration error is high (avg {fit_avg_mm:.2f}mm) — paint the "
                       "cap area with the brush to give the seat a cleaner surface.")

    if seat_method == "icp" and seed_source == "click" and not axis_violation:
        level = "attention" if level == "ready" else level
        actions.append("The cap rim was only partially visible, so the seat used ICP "
                       "instead of rim geometry — brush the cap to guide the seat, then "
                       "check view 1.")

    if level != "ready" and seed_source == "marks" and not border_points_given:
        # the centre mark is an INDICATOR, not the exact centre (hollow caps swallow
        # the click; overhanging neighbours shadow it) — the border clicks are the
        # measurement that pins width and depth
        actions.append("For the most precise seat, click several points around the "
                       "cap's visible border (◐) — the border fit pins the centre, "
                       "width and depth; the centre mark only locates the cap.")

    if not actions:
        actions.append("All checks agree (variant, measurement, seat). Advisory by "
                       "policy: visually confirm the green cap covers the scanned cap "
                       "in view 1, then accept.")

    return {"level": level, "actions": actions}
