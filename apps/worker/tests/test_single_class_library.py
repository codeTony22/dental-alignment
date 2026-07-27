"""THE ONE-SIZE LAB: a cap library holding a SINGLE diameter class must run end to end.

The defect this suite pins (found 2026-07-25, latent on every 2-class catalog we ship
against): ``classify_diameter`` reports the distance to the nearest RIVAL class. With one
class there is no rival, and the old code answered ``float("inf")``. That infinity is a
perfectly good Python float, so nothing failed in the domain, in the row assembly, or on
the disk write (``json.dumps`` emits a bare ``Infinity`` by default). It failed at the very
last step: FastAPI serializes responses with ``allow_nan=False``, so the run returned a
**500 after the whole pipeline had already run** — minutes of alignment work discarded, and
an error message that named nothing an operator or a developer could act on.

The fix is at the domain source: a margin to the nearest rival is UNDEFINED when there is
no rival, so ``margin_mm`` is ``None``. Infinity was never the honest answer either — it
claims unbounded separation confidence from a library that simply cannot be confused.

Two guards live here:
  * the end-to-end run against a GENUINE one-class library must return 200 with a null
    margin (and must NOT get there by refusing to classify — that would be a different,
    silently-similar payload);
  * a serializability guard over the real run payload: no non-finite float may reach any
    response, from this or any other source.

The tree is synthetic and self-contained, mirroring test_server_selection's fixture.
"""
from __future__ import annotations

import json
import math

import numpy as np
import pytest
import trimesh
from fastapi.encoders import jsonable_encoder
from fastapi.testclient import TestClient

import case_prep.server as srv

client = TestClient(srv.app)

MODEL = "onesize"
# ONE diameter class, two collar heights — a real lab that stocks a single cap size still
# stocks both heights. classify_diameter groups by rounded diameter, so this is genuinely
# one class with no rival, not a degenerate single-file library.
CAP_RADIUS = 4.0
SHORT_H, TALL_H = 3.4, 5.4
DOME_MM = 1.2
CONSTRUCTION_ID = "vend-a/generic-abutment.stl"
TOOTH = 8


def _squat(height: float, radius: float = CAP_RADIUS) -> trimesh.Trimesh:
    """A healing-cap-shaped revolute part: open collar, domed top."""
    cyl = trimesh.creation.cylinder(radius=radius, height=height, sections=48)
    keep = cyl.triangles_center[:, 2] > -height * 0.49
    m = trimesh.Trimesh(cyl.vertices.copy(), cyl.faces[keep], process=False)
    m.remove_unreferenced_vertices()
    v = np.asarray(m.vertices, float).copy()
    top = v[:, 2] > height * 0.49
    v[top, 2] += DOME_MM * (1.0 - (np.linalg.norm(v[top, :2], axis=1) / radius) ** 2)
    return trimesh.Trimesh(v, m.faces.copy(), process=False)


def _vendor_body() -> trimesh.Trimesh:
    """An open-shell vendor construction part with wall margin to survive the relief."""
    shell = trimesh.creation.cylinder(radius=2.5, height=8.0, sections=48)
    keep = shell.face_normals[:, 2] < 0.9
    return trimesh.Trimesh(shell.vertices, shell.faces[keep], process=False)


@pytest.fixture(scope="module")
def one_class_case(tmp_path_factory):
    from case_prep.adapters.ingest import canonicalize_revolute
    from case_prep.adapters.real_case import build_embedded_case
    from case_prep.adapters.synthetic import make_gingiva_arch

    root = tmp_path_factory.mktemp("data")
    out = tmp_path_factory.mktemp("out")

    caps = root / "library/caps" / MODEL
    caps.mkdir(parents=True)
    _squat(SHORT_H).export(caps / f"{MODEL}-5020.stl")
    _squat(TALL_H).export(caps / f"{MODEL}-5030.stl")

    cons = root / "library/construction/vend-a"
    cons.mkdir(parents=True)
    _vendor_body().export(cons / "generic-abutment.stl")

    arch_path = root / "arch.stl"
    make_gingiva_arch(np.random.default_rng(0)).export(arch_path)
    cad_path = root / "cap.stl"
    _squat(TALL_H).export(cad_path)
    gt = build_embedded_case(arch_path, cad_path, root / "_case", n_implants=1, seed=1,
                             canonicalize=canonicalize_revolute)

    scans = root / "scans/one-size-lab"
    scans.mkdir(parents=True)
    (scans / "upper_jaw.stl").write_bytes((root / "_case/scan.stl").read_bytes())

    mp = pytest.MonkeyPatch()
    mp.setattr(srv, "DATA", root)
    mp.setattr(srv, "OUT", out)
    mp.setattr(srv, "CASES", srv._discover_cases(root))
    mp.setattr(srv, "_cache", {})
    yield {"root": root, "out": out,
           "centre": [float(c) for c in gt.poses[0].position]}
    mp.undo()


@pytest.fixture(scope="module")
def one_class_run(one_class_case):
    """ONE real run through the HTTP boundary — this is the call that used to 500."""
    res = client.post("/api/cases/one-size-lab/run", json={
        "sites": [{"tooth": TOOTH, "center": one_class_case["centre"],
                   "declared_variant": "5030"}],
        "model": MODEL, "construction_path": CONSTRUCTION_ID, "jaw": "upper"})
    assert res.status_code == 200, f"the one-size library run failed: {res.text}"
    return res.json()


class TestUndefinedMarginAtTheDomainSource:
    """The rule, stated where it lives: no rival class, no margin."""

    def test_a_one_class_table_classifies_with_an_undefined_margin(self):
        from case_prep.domain.cap_catalog import classify_diameter

        table = {"5020": (5.49, 3.69), "5030": (5.45, 5.43)}   # one rounded class: 5
        result = classify_diameter(5.4, table)
        assert result is not None, "a library that cannot be confused must still classify"
        assert set(result.variants) == {"5020", "5030"}
        assert result.margin_mm is None, \
            "the distance to a class that does not exist is undefined, not infinite"

    def test_a_literally_single_variant_table_also_has_no_margin(self):
        from case_prep.domain.cap_catalog import classify_diameter

        result = classify_diameter(5.4, {"5020": (5.49, 3.69)})
        assert result is not None and result.margin_mm is None

    def test_a_multi_class_table_still_reports_its_margin(self):
        from case_prep.domain.cap_catalog import classify_diameter

        table = {"5020": (5.49, 3.69), "6020": (6.22, 3.81)}
        result = classify_diameter(5.4, table)
        assert result is not None
        assert result.margin_mm == pytest.approx(0.73, abs=0.02)

    def test_an_undefined_margin_never_refuses(self):
        """The refusal band compares against min_margin_mm — an undefined margin must
        not fall through it as if it were zero (that would silently kill every
        one-size lab's identification instead of 500-ing it)."""
        from case_prep.domain.cap_catalog import classify_diameter

        assert classify_diameter(5.4, {"5020": (5.49, 3.69)},
                                 min_margin_mm=99.0) is not None


class TestTheRunSurvivesAOneClassLibrary:
    # DELIBERATELY NOT `slow`, though it measures ~1.7s (the module fixture builds an
    # arch + embeds a cap). It is the regression for a bug that reached production as a
    # 500 with the work already done; 1.7s of a ~2-minute lane is the right price for
    # catching that between edits rather than 24 minutes later.
    def test_the_run_returns_200_with_a_null_margin(self, one_class_run):
        row = one_class_run["summary"]["sites"][0]
        assert "error" not in row, row
        assert row["variant"]["diameter_class_margin_mm"] is None

    def test_the_null_margin_is_an_undefined_margin_not_a_refusal(self, one_class_run):
        """Both a refused classification and an undefined margin serialize as null, so
        the 200 alone does not prove the fix. A refusal would have raised the ambiguity
        flag; its absence next to a real measurement means the class WAS identified and
        the null is the honest 'no rival to measure against'."""
        row = one_class_run["summary"]["sites"][0]
        assert row["variant"]["measured_rim_diameter_mm"] is not None
        assert not [f for f in row["variant"]["flags"] if "ambiguous" in f], \
            row["variant"]["flags"]

    def test_the_library_this_ran_against_really_has_one_class(self, one_class_case):
        from case_prep.domain.cap_catalog import classify_diameter

        cfg = srv.CASES["one-size-lab"]
        table = srv._library_for(cfg, MODEL).variant_dimensions()
        assert len(table) == 2, "the fixture must hold both collar heights"
        assert len({round(d, 0) for d, _h in table.values()}) == 1, \
            "the fixture stopped being a one-diameter-class library"
        assert classify_diameter(sum(d for d, _h in table.values()) / len(table),
                                 table).margin_mm is None


def _non_finite_paths(node, path="$"):
    """Every JSON path in ``node`` holding a float that JSON cannot represent."""
    bad = []
    if isinstance(node, dict):
        for k, v in node.items():
            bad += _non_finite_paths(v, f"{path}.{k}")
    elif isinstance(node, (list, tuple)):
        for i, v in enumerate(node):
            bad += _non_finite_paths(v, f"{path}[{i}]")
    elif isinstance(node, float) and not math.isfinite(node):
        bad.append((path, node))
    return bad


class TestRunPayloadIsSerializable:
    """The general guard behind the specific bug: FastAPI encodes responses with
    ``allow_nan=False``, so ONE inf or NaN anywhere in the tree turns a completed run
    into an opaque 500. This walks a real payload rather than trusting review."""

    def test_no_non_finite_number_reaches_the_response(self, one_class_run):
        assert _non_finite_paths(one_class_run) == []

    def test_the_payload_encodes_under_the_response_encoder(self, one_class_run,
                                                            one_class_case):
        # the production path, exactly: jsonable_encoder -> json.dumps(allow_nan=False)
        cached = json.loads((one_class_case["out"] / "one-size-lab/run.json").read_text())
        json.dumps(jsonable_encoder(srv._with_verification(cached)), allow_nan=False)
