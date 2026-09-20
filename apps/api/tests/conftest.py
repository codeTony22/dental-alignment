"""Synthetic data tree + an app wired to tmp paths (same shape as the BFF suite)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from case_api.config import Settings
from case_api.main import create_app


CASE = "neodent-gm"


def make_data_tree(root: Path) -> Path:
    (root / "library/caps/neodent-gm").mkdir(parents=True)
    (root / "library/caps/neodent-gm/neodent-gm-5020.stl").touch()
    scans = root / "scans/doctor-neodent-gm"
    scans.mkdir(parents=True)
    (scans / "upper_jaw.stl").touch()
    (scans / "sites.json").write_text(json.dumps({"suggested_sites": [
        {"tooth": 4, "center": [1.0, 2.0, 3.0], "declared_variant": "5020"},
        {"tooth": 13, "center": [4.0, 5.0, 6.0], "declared_variant": "5020"},
    ]}))
    return root


def row(tooth: int = 4, level: str = "ready") -> dict:
    return {
        "tooth": tooth, "spec": "neodent-gm 5020",
        "seat_method": "rim-seat", "seed_source": "site-center",
        "fit": {"avg_mm": 0.21, "max_mm": 0.62, "n": 4200},
        "rim_agreement_mm": 0.07, "rim_arc_bins": 12, "rim_off_centre": 0.11,
        "confidence": {"grade": "high"},
        "top_face_agreement_mm": 0.05,
        "clocking": {
            "evidence": "codes", "rotation_unverified": level != "ready",
            "notch_corr": 0.51, "notch_prominence": 0.16,
        },
        "guidance": {"level": level, "actions": [] if level == "ready" else [
            "The cap's ROTATION could not be verified."
        ]},
        "variant": {"identified": "5020", "declared": "5020",
                    "measured_rim_diameter_mm": 4.73, "flags": []},
        "deviation_rms_mm": 0.43, "deviation_p90_mm": 0.71,
        "rework": {"stale_metrics": ["rim_agreement_mm", "guidance"]},
    }


def land_session(product_root: Path, rows=None, run_id: str = "run-1") -> Path:
    rows = rows if rows is not None else [row(4, "attention"), row(13)]
    run_dir = product_root / CASE / "runs" / run_id
    run_dir.mkdir(parents=True)
    (product_root / CASE / "session.json").write_text(json.dumps({
        "run": {
            "state": "done", "run_id": run_id, "job_id": run_id,
            "summary": {"sites": rows, "package_files": []},
        }
    }))
    return run_dir


@pytest.fixture
def product_root(tmp_path: Path) -> Path:
    return tmp_path / "product"


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    return make_data_tree(tmp_path / "data")


@pytest.fixture
def settings(data_root: Path, product_root: Path) -> Settings:
    land_session(product_root)
    return Settings(data_root=data_root, product_root=product_root)


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))
