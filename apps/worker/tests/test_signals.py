"""The adjust/MCP signal envelope — every taxonomy group, no invented metrics."""
from __future__ import annotations

from case_prep.application.adjust import AdjustOutcome
from case_prep.application.signals import SIGNAL_GROUPS, assemble_site_signals, outcome_to_dict
from case_prep.domain.acceptance import CATALOG


def _row(tooth: int = 4) -> dict:
    return {
        "tooth": tooth, "spec": "neodent-gm 5020", "vendor": "dess",
        "seat_method": "rim-seat", "seed_source": "site-center",
        "auto_delta_mm": 0.18, "coverage": 0.91, "icp_fitness": 0.83,
        "fit": {"avg_mm": 0.21, "max_mm": 0.62, "n": 4200},
        "rim_agreement_mm": 0.07, "rim_arc_bins": 12, "rim_off_centre": 0.11,
        "confidence": {"grade": "high"},
        "top_face_agreement_mm": 0.05,
        "clocking": {
            "evidence": "codes", "rotation_unverified": False,
            "notch_corr": 0.51, "notch_prominence": 0.16,
            "notch_shift_deg": -1.0,
        },
        "guidance": {"level": "attention", "actions": [
            "The cap's ROTATION could not be verified."
        ]},
        "alignment_error_mm": 1.4,
        "variant": {"identified": "5020", "declared": "5020",
                    "measured_rim_diameter_mm": 4.73, "flags": []},
        "advisory": True,
        "deviation_rms_mm": 0.43, "deviation_p90_mm": 0.71,
        "rework": {"stale_metrics": ["rim_agreement_mm", "guidance"]},
        "correspondence": {"pairs": 1, "residual_rms_mm": None,
                           "cross_checked": False},
    }


def test_the_taxonomy_names_every_owner_group():
    assert SIGNAL_GROUPS == (
        "capture", "measurement_honesty", "seat", "fit", "correspondence",
        "certification", "residue", "acceptance", "landmarks", "clocking",
        "stability", "guidance",
    )


def test_assemble_emits_every_group_and_the_full_acceptance_catalog():
    envelope = assemble_site_signals(_row())
    assert envelope["group_names"] == list(SIGNAL_GROUPS)
    for name in SIGNAL_GROUPS:
        assert name in envelope["groups"], name
    acceptance = envelope["groups"]["acceptance"]
    assert acceptance["catalog_keys"] == [spec.key for spec in CATALOG]
    assert {m["key"] for m in acceptance["metrics"]} == set(acceptance["catalog_keys"])
    assert envelope["groups"]["landmarks"]["missing"] is True
    assert envelope["groups"]["seated"]["missing"] is True


def test_landmarks_and_seated_are_passed_through_never_synthesised():
    marks = [{"id": "code-1", "kind": "notch", "point": [1, 2, 3]}]
    seated = {"tooth": 4, "stats": {"rms_mm": 0.4}}
    envelope = assemble_site_signals(_row(), landmarks=marks, seated=seated)
    assert envelope["groups"]["landmarks"]["items"] == marks
    assert envelope["groups"]["landmarks"]["missing"] is False
    assert envelope["groups"]["seated"] == seated


def test_outcome_fields_include_the_seat_aware_receipt():
    outcome = AdjustOutcome(
        tooth=4, operation="fit-by-points", detail="fitted",
        translation_mm=0.12, fit_version=3, seat_branch="rotate",
        seat_band_mm=0.35, cross_checked=True, residual_rms_mm=0.04,
        pairs=[{"observation": "point"}],
    )
    payload = outcome_to_dict(outcome)
    assert payload["translation_mm"] == 0.12
    assert payload["fit_version"] == 3
    assert payload["seat_branch"] == "rotate"
    assert payload["seat_band_mm"] == 0.35
    envelope = assemble_site_signals(_row(), outcome=outcome)
    corr = envelope["groups"]["correspondence"]
    assert corr["fit_version"] == 3
    assert corr["translation_mm"] == 0.12
    assert envelope["groups"]["seat"]["seat_branch"] == "rotate"
    assert envelope["groups"]["measurement_honesty"]["cross_checked"] is True
    assert envelope["groups"]["residue"]["deviation_rms_mm"] == 0.43


def test_guidance_actions_are_the_row_verbatim():
    envelope = assemble_site_signals(_row())
    assert envelope["groups"]["guidance"]["actions"] == [
        "The cap's ROTATION could not be verified."
    ]
    assert envelope["groups"]["certification"]["guidance_level"] == "attention"
    assert envelope["groups"]["capture"]["rim_arc_bins"] == 12
