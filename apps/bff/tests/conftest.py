"""Shared fixtures: a synthetic data tree + an app wired to tmp paths.

The tree mirrors the real one's SHAPE (scans/, library/caps/, library/construction/) with
EMPTY stl files — discovery and catalog listing read names and directory shape only, so
these tests stay milliseconds. Anything that must parse a real mesh (the relief ceiling)
is exercised against the real tree by test_freeze_guard, not faked here.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bff.config import Settings
from bff.main import create_app


def make_data_tree(root: Path, declared=(None, None)) -> Path:
    """A one-case tree: doctor-neodent-gm, two suggested sites (teeth 4 and 13) whose
    ``declared_variant`` suggestions are the two values given."""
    (root / "library/caps/neodent-gm").mkdir(parents=True)
    (root / "library/caps/neodent-gm/neodent-gm-5020.stl").touch()
    dess = root / "library/construction/dess"
    dess.mkdir(parents=True)
    (dess / "neodent-gm-scanbody.stl").touch()
    scans = root / "scans/doctor-neodent-gm"
    scans.mkdir(parents=True)
    (scans / "upper_jaw.stl").touch()
    (scans / "sites.json").write_text(json.dumps({"suggested_sites": [
        {"tooth": 4, "center": [1.0, 2.0, 3.0], "declared_variant": declared[0]},
        {"tooth": 13, "center": [4.0, 5.0, 6.0], "declared_variant": declared[1]},
    ]}))
    return root


@pytest.fixture
def product_root(tmp_path: Path) -> Path:
    return tmp_path / "product"


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    return make_data_tree(tmp_path / "data")


@pytest.fixture
def settings(data_root: Path, product_root: Path) -> Settings:
    return Settings(data_root=data_root, product_root=product_root)


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))
