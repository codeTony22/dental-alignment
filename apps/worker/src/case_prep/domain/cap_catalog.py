"""The healing-cap catalog — the domain of "which cap is this, and how many are there?".

Ubiquitous language:
  * ``CapType`` — the families a doctor names: Esthetic, TSV, Certain, ExHex.
  * ``CapSpec`` — a doctor's declaration: type + diameter ("Certain 3").
  * ``CandidateMatch`` — one library template's fit at one scan location.
  * ``CapSite`` — a resolved detection: where a cap is, which spec fits it best, at what fitness.
  * ``resolve_sites`` — merges candidate matches across ALL templates into distinct sites,
    answering "how many caps, where, and what type" in one pass.

Detection is *library-driven* by design: spikes on real client scans proved no pure geometric
signature separates a coded cap from teeth (a neighbouring tooth is MORE circular than the cap);
what discriminates is fit against a known template (~0.65 body vs ~0.2 tooth). The doctor never
has to pre-declare the type — the system tries the whole catalog and the best fit identifies it.

Pure domain: no meshes, no IO, no framework imports.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import sqrt
from typing import Dict, List, Optional, Sequence, Tuple

# a resolved cap must be at least this far from the next one (two implants are never closer —
# the >=3 mm implant-to-implant clinical rule plus cap radii puts real sites >8 mm apart)
DEFAULT_MIN_SEPARATION_MM = 8.0


class CapType(str, Enum):
    ESTHETIC = "esthetic"
    TSV = "tsv"
    CERTAIN = "certain"
    EX_HEX = "exhex"


@dataclass(frozen=True)
class CapSpec:
    """A healing-cap declaration: model + size-variant code, e.g. ('neodent-gm', '5020') or
    ('certain', '4.1'). The catalog is an OPEN set — real client data arrived with models
    (Neodent GM, Zimmer 4.5) outside the initially-assumed family enum, so the model is a
    validated string; ``CapType`` remains as the known family constants."""

    model: str
    variant: str

    def __post_init__(self) -> None:
        if not self.model or self.model != self.model.lower():
            raise ValueError(f"model must be a non-empty lowercase string, got {self.model!r}")
        if not self.variant:
            raise ValueError("variant must be non-empty")

    @property
    def label(self) -> str:
        return f"{self.model}-{self.variant}"


@dataclass(frozen=True)
class CandidateMatch:
    """One template's fit at one scan location (raw detector output, pre-merge)."""

    spec: CapSpec
    center: Tuple[float, float, float]
    fitness: float  # confirmation score: SCAN-COVERAGE in the clinical path (fraction of the
    #                 isolated ROI the fitted template explains); ICP inlier fraction in the
    #                 tall-scan-body path — see the producing function


@dataclass(frozen=True)
class CapSite:
    """A resolved healing-cap site: the answer to 'where, which type, how confident'."""

    spec: CapSpec
    center: Tuple[float, float, float]
    fitness: float


def _dist(a: Sequence[float], b: Sequence[float]) -> float:
    return sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def resolve_sites(
    candidates: Sequence[CandidateMatch],
    min_separation_mm: float = DEFAULT_MIN_SEPARATION_MM,
) -> List[CapSite]:
    """Merge per-template candidate matches into distinct cap sites.

    Greedy non-max suppression by fitness: the best match anywhere claims its site; any other
    candidate within ``min_separation_mm`` of a claimed site is the SAME cap seen by another
    template (or a duplicate hit) and is absorbed. The winning candidate's spec identifies the
    cap type. Returned best-fitness-first; ``len(result)`` is the cap count.
    """
    kept: List[CapSite] = []
    # stable sort: on an exact fitness tie the earlier candidate wins (i.e. library order) —
    # deterministic, and a tie between templates means the data genuinely cannot separate them
    for cand in sorted(candidates, key=lambda c: -c.fitness):
        if all(_dist(cand.center, site.center) >= min_separation_mm for site in kept):
            kept.append(CapSite(spec=cand.spec, center=cand.center, fitness=cand.fitness))
    return kept


@dataclass(frozen=True)
class DiameterClass:
    """The result of classifying a measured rim diameter: the variants sharing that diameter
    (both collar heights) and the margin to the nearest OTHER class — the honesty number.

    ``margin_mm`` is ``None`` when the library holds a SINGLE diameter class: "how far is
    the runner-up" has no answer when there is no runner-up. It is not infinity — infinity
    would claim unbounded confidence, and (a real consequence, not a purism) it is not a
    JSON number, so it detonated the run response on the way out."""

    diameter_mm: float
    variants: Tuple[str, ...]
    margin_mm: Optional[float]


def classify_diameter(measured_mm: float, table: Dict[str, Tuple[float, float]],
                      min_margin_mm: float = 0.3) -> Optional[DiameterClass]:
    """Map a measured rim diameter to a variant DIAMETER CLASS, or None when ambiguous.

    ``table`` maps variant label -> (diameter_mm, height_mm), measured from the CADs (classes
    sit ~0.8mm apart; scans read within ~0.4-0.8mm of a class). Grouping is by rounded class
    diameter; the classification carries its margin and REFUSES (None) when the measurement
    falls within ``min_margin_mm`` of two classes — a refused identification routes to the
    doctor's declaration or the operator, never to a guess (billing + clinical safety).

    A ONE-CLASS library (a lab that stocks a single cap size, in one or both collar
    heights) has no rival class to be confused with, so the classification always stands
    and its margin is UNDEFINED — ``margin_mm is None``. Consumers must treat that as
    "not measured", exactly like the ``None`` this function returns when it refuses."""
    classes: dict = {}
    for label, (dia, _h) in table.items():
        key = round(dia, 0)
        classes.setdefault(key, {"dias": [], "variants": []})
        classes[key]["dias"].append(dia)
        classes[key]["variants"].append(label)
    scored = sorted(
        ((abs(measured_mm - sum(c["dias"]) / len(c["dias"])),
          sum(c["dias"]) / len(c["dias"]), tuple(sorted(c["variants"])))
         for c in classes.values()),
        key=lambda t: t[0])
    best = scored[0]
    # no rival class -> the margin is UNDEFINED, not infinite (see DiameterClass)
    margin = (scored[1][0] - best[0]) if len(scored) > 1 else None
    if margin is not None and margin < min_margin_mm:
        return None
    return DiameterClass(diameter_mm=best[1], variants=best[2],
                         margin_mm=None if margin is None else float(margin))


def variant_agreement(declared: Optional[str], identified: str) -> List[str]:
    """The billing/clinical gate signal: an explainable flag when the doctor's DECLARED variant
    disagrees with what the system identified on the scan (a smaller part constructed into a
    bigger space — or vice versa — must never pass silently). No declaration, no flag."""
    if declared is None or declared == identified:
        return []
    return [f"variant mismatch: doctor declared {declared} but the scan identifies "
            f"{identified} — verify before construction (billing + fit)"]


def variant_flags(declared: Optional[str], identified: str,
                  measured_dia_mm: Optional[float],
                  dia_class: Optional[DiameterClass],
                  n_table_variants: int,
                  seat_confirms_declared: bool = False) -> List[str]:
    """All variant-gate signals for one site, in one place: the declared-vs-identified
    billing/fit mismatch, plus the measurement-ambiguity notice when the rim diameter could
    not be classified (only meaningful when the table actually has multiple variants).

    ``seat_confirms_declared``: the geometric seat independently identified the SAME
    variant the doctor declared. A visible rim reading UNDER the declared native size
    is then EXPECTED SUBMERGENCE (measured on the labeled arches: up to -2.1mm), not
    a dispute — an informational note instead of a warning. A rim reading LARGER than
    the declared class still warns (a bigger space than the declared part is the
    dangerous direction)."""
    flags = variant_agreement(declared, identified)
    if measured_dia_mm is not None and dia_class is None and n_table_variants > 1:
        flags = flags + [
            f"measured rim diameter {measured_dia_mm:.2f}mm is ambiguous between size "
            f"classes — variant identified by fit only; verify before construction"]
    # the INDEPENDENT cross-check for the doctor-chooses flow: once the declaration drives
    # alignment, identified == declared is vacuous — the measurement is the second opinion
    if (declared is not None and dia_class is not None
            and measured_dia_mm is not None and declared not in dia_class.variants):
        declared_is_larger = all(declared > v for v in dia_class.variants)
        if seat_confirms_declared and declared_is_larger:
            flags = flags + [
                f"visible rim reads {measured_dia_mm:.2f}mm — under the declared "
                f"{declared}'s native size, as expected for a partially submerged "
                f"cap; the seat independently confirms {declared}"]
        else:
            flags = flags + [
                f"measured rim diameter {measured_dia_mm:.2f}mm suggests "
                f"{'/'.join(dia_class.variants)} but the doctor declared {declared} — "
                f"verify before construction (billing + fit)"]
    return flags
