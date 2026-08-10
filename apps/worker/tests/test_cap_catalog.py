"""Domain: the cap catalog and site resolution — pure logic, no meshes, no IO.

Ubiquitous language: a doctor declares a CapSpec ("Certain 3"). Detection produces one
CandidateMatch per (template, location). resolve_sites merges candidates across ALL templates
into distinct CapSites — answering "how many caps, where, and which type fits best".
"""
from __future__ import annotations

import pytest

from case_prep.domain.cap_catalog import (
    CandidateMatch,
    CapSpec,
    CapType,
    classify_diameter,
    propose_variant,
    resolve_sites,
    variant_flags,
)


def _m(spec: CapSpec, center, fitness: float) -> CandidateMatch:
    return CandidateMatch(spec=spec, center=tuple(float(x) for x in center), fitness=fitness)


CERTAIN_3 = CapSpec("certain", "3")
CERTAIN_41 = CapSpec("certain", "4.1")
TSV_45 = CapSpec("tsv", "4.5")


class TestCapSpec:
    def test_label_is_type_dash_diameter(self):
        assert CERTAIN_41.label == "certain-4.1"
        assert TSV_45.label == "tsv-4.5"

    def test_specs_are_value_objects(self):
        assert CapSpec("certain", "3") == CERTAIN_3
        assert CERTAIN_3 != CERTAIN_41

    def test_open_catalog_accepts_new_models(self):
        assert CapSpec("neodent-gm", "5020").label == "neodent-gm-5020"

    def test_model_and_variant_are_validated(self):
        with pytest.raises(ValueError):
            CapSpec("", "5020")
        with pytest.raises(ValueError):
            CapSpec("certain", "")


class TestResolveSites:
    def test_no_candidates_means_no_sites(self):
        assert resolve_sites([]) == []

    def test_single_candidate_is_a_site(self):
        sites = resolve_sites([_m(CERTAIN_41, (0, 0, 0), 0.6)])
        assert len(sites) == 1
        assert sites[0].spec == CERTAIN_41
        assert sites[0].fitness == 0.6

    def test_two_templates_on_same_spot_merge_to_best_fitting_type(self):
        # Certain and TSV both matched near the same location -> ONE site, best type wins
        sites = resolve_sites([
            _m(CERTAIN_41, (0, 0, 0), 0.62),
            _m(TSV_45, (0.8, 0.2, 0.1), 0.41),
        ])
        assert len(sites) == 1
        assert sites[0].spec == CERTAIN_41  # the better fit identifies the type

    def test_distinct_locations_stay_distinct_sites(self):
        sites = resolve_sites([
            _m(CERTAIN_41, (0, 0, 0), 0.62),
            _m(CERTAIN_41, (12, 0, 0), 0.58),
        ])
        assert len(sites) == 2  # the COUNT: two caps on the arch

    def test_min_separation_is_configurable(self):
        near = [_m(CERTAIN_41, (0, 0, 0), 0.6), _m(TSV_45, (5, 0, 0), 0.5)]
        assert len(resolve_sites(near, min_separation_mm=4.0)) == 2
        assert len(resolve_sites(near, min_separation_mm=6.0)) == 1

    def test_sites_ordered_best_fitness_first(self):
        sites = resolve_sites([
            _m(CERTAIN_41, (0, 0, 0), 0.45),
            _m(TSV_45, (15, 0, 0), 0.71),
        ])
        assert [s.fitness for s in sites] == [0.71, 0.45]


class TestVariantClassification:
    """The client requirement: know WHICH size variant each cap is — measured diameter guides,
    the doctor's declaration is authoritative, and a mismatch must surface (billing + clinical:
    never a smaller part in a bigger space). Margins are honest: measured scan rims sit within
    ~0.4-0.8mm of a class while classes are ~0.8mm apart, so classification carries its margin
    and refuses when ambiguous."""

    TABLE = {  # variant label -> (diameter_mm, height_mm), as measured from the CADs
        "5020": (5.49, 3.69), "5030": (5.45, 5.43),
        "6020": (6.22, 3.81), "6030": (6.17, 5.39),
        "7020": (7.20, 3.75), "7030": (7.26, 5.38),
    }

    def test_clean_measurement_classifies_to_the_diameter_class(self):
        from case_prep.domain.cap_catalog import classify_diameter
        result = classify_diameter(7.1, self.TABLE)
        assert result is not None
        assert set(result.variants) == {"7020", "7030"}  # the Ø class, both heights
        assert result.margin_mm > 0.3                    # distance to the next class

    def test_ambiguous_measurement_refuses(self):
        from case_prep.domain.cap_catalog import classify_diameter
        # dead between the 6.2 and 7.2 classes -> no honest answer
        assert classify_diameter(6.7, self.TABLE, min_margin_mm=0.3) is None

    def test_agreement_declared_matches_identified(self):
        from case_prep.domain.cap_catalog import variant_agreement
        assert variant_agreement(declared="7030", identified="7030") == []

    def test_mismatch_produces_explainable_flag(self):
        from case_prep.domain.cap_catalog import variant_agreement
        reasons = variant_agreement(declared="6030", identified="7030")
        assert len(reasons) == 1
        assert "declared" in reasons[0] and "6030" in reasons[0] and "7030" in reasons[0]

    def test_no_declaration_means_no_flag(self):
        from case_prep.domain.cap_catalog import variant_agreement
        assert variant_agreement(declared=None, identified="7030") == []


class TestDeclaredVsMeasuredGate:
    def test_confident_measurement_outside_declared_class_flags(self):
        """RealGUIDE-parity flow: the doctor CHOOSES the variant and alignment uses it —
        so the billing/fit gate must come from the independent MEASUREMENT: a rim that
        confidently classifies into a class not containing the declaration is said out
        loud (identified == declared is vacuous once the choice drives alignment)."""
        table = {"5020": (4.6, 3.4), "5030": (4.6, 5.4),
                 "7020": (6.9, 3.4), "7030": (6.9, 5.4)}
        cls = classify_diameter(4.7, table)
        assert cls is not None and "5020" in cls.variants
        flags = variant_flags("7030", "7030", 4.7, cls, len(table))
        assert any("declared 7030" in f and "measured" in f for f in flags)

    def test_measurement_inside_declared_class_is_clean(self):
        table = {"5020": (4.6, 3.4), "5030": (4.6, 5.4),
                 "7020": (6.9, 3.4), "7030": (6.9, 5.4)}
        cls = classify_diameter(6.8, table)
        assert variant_flags("7030", "7030", 6.8, cls, len(table)) == []

    def test_submerged_underreading_with_seat_confirmation_is_a_note_not_a_warning(self):
        """Client report (cap7020, 2026-07-14): visible rim 6.03 vs declared 7020 —
        EXPECTED submergence physics (visible rim under-reads native by up to 2.1mm
        on these arches). When the seat independently confirms the declared variant
        and the declaration is the LARGER class, the flag is informational."""
        table = {"5020": (4.6, 3.4), "5030": (4.6, 5.4),
                 "7020": (6.9, 3.4), "7030": (6.9, 5.4)}
        cls = classify_diameter(4.7, table)
        flags = variant_flags("7020", "7020", 4.7, cls, len(table),
                              seat_confirms_declared=True)
        assert len(flags) == 1
        assert "submerged" in flags[0] and "confirms" in flags[0]
        assert "verify before construction" not in flags[0]

    def test_declared_smaller_than_measured_still_warns_even_with_seat(self):
        """The dangerous direction: the space measures BIGGER than the declared part
        — a smaller part into a bigger space must never pass silently, seat or not."""
        table = {"5020": (4.6, 3.4), "5030": (4.6, 5.4),
                 "7020": (6.9, 3.4), "7030": (6.9, 5.4)}
        cls = classify_diameter(6.8, table)
        assert cls is not None and "7020" in cls.variants
        flags = variant_flags("5020", "5020", 6.8, cls, len(table),
                              seat_confirms_declared=True)
        assert any("verify before construction" in f for f in flags)


class TestProposeVariant:
    """The client escalation (2026-08-09, cap 297589851-neodent-gm tooth 20): a
    diameter class groups every collar HEIGHT sharing that Ø (``DiameterClass.
    variants`` — see ``classify_diameter``'s own test above, where the Ø-7 class
    already holds BOTH 7020 and 7030), so nothing picked between them and a TALL
    variant was declared, unmeasured, over a visibly SHORT cap. ``propose_variant``
    is the missing second axis: height breaks the tie ``classify_diameter`` was
    never asked to resolve."""

    TABLE = {  # variant label -> (diameter_mm, height_mm) — the CURRENT-shelf-only
        "5020": (5.49, 3.69), "5030": (5.45, 5.43),  # table propose_variant is given
        "6020": (6.22, 3.81), "6030": (6.17, 5.39),
        "7020": (7.20, 3.75), "7030": (7.26, 5.38),
    }

    def test_a_short_measured_cap_picks_the_20_family(self):
        assert propose_variant(7.22, 3.80, self.TABLE) == "7020"

    def test_a_tall_measured_cap_at_the_same_diameter_picks_the_30_family(self):
        assert propose_variant(7.22, 5.35, self.TABLE) == "7030"

    def test_a_missing_diameter_never_guesses(self):
        assert propose_variant(None, 3.80, self.TABLE) is None

    def test_a_missing_height_never_guesses(self):
        assert propose_variant(7.22, None, self.TABLE) is None

    def test_an_ambiguous_diameter_class_refuses_regardless_of_height(self):
        # dead between the 6.2 and 7.2 classes, per classify_diameter's own test
        assert propose_variant(6.7, 3.80, self.TABLE) is None

    def test_a_coin_flip_height_refuses_rather_than_pick_a_side(self):
        # equidistant between 3.75 (7020) and 5.38 (7030): 4.565 exactly
        assert propose_variant(7.22, 4.565, self.TABLE) is None

    def test_an_empty_table_has_nothing_to_propose_against(self):
        assert propose_variant(7.22, 3.80, {}) is None

    def test_a_single_height_class_needs_no_height_tie_break(self):
        # a shelf carrying only one height family per Ø: height still required
        # (never absent), but there is no family to break a tie between
        one_height = {"5020": (5.49, 3.69), "7020": (7.20, 3.75)}
        assert propose_variant(7.22, 3.80, one_height) == "7020"
        assert propose_variant(7.22, None, one_height) is None
