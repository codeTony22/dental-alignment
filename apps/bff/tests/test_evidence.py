"""THE EVIDENCE BUNDLE BUILDER (plan §6, grill AM-10): the canonical, content-addressed
record a confirmation seals — "canonical JSON, sorted keys, stated rounding, plus SHA-256
of each QC image's bytes", written transactionally under the immutable run directory.

These tests pin the two properties a dispute would lean on:

1. CANONICALIZATION IS STABLE: the same facts produce the same bytes — and so the same
   hash — regardless of dict insertion order or how a float's repr happened to fall out
   of the physics (0.1 + 0.2 vs 0.3). Without this, an honest re-derivation at release
   time could hash differently and 409 a legitimate release.
2. THE HASH IS SENSITIVE: any change to the evidence — a number, a word, one bit of a
   QC image — changes the sha256. Without this, the seal would not mean "you signed
   THIS".
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from bff.evidence import (EvidenceBundle, canonical_bundle, qc_image_hashes,
                          write_bundle)


ASSURANCE = {
    "case_id": "neodent-gm",
    "run_id": "20260727-120000-abc123",
    "sites": [{"tooth": 4, "rim_agreement_mm": 0.07, "gate": {"level": "ready"}}],
}
QC_HASHES = {"neodent-gm-4-clockview.png": "a" * 64,
             "neodent-gm-4-deviation.png": "b" * 64}


class TestCanonicalization:
    def test_dict_order_does_not_change_the_bytes_or_the_hash(self):
        shuffled = {"run_id": ASSURANCE["run_id"], "sites": ASSURANCE["sites"],
                    "case_id": ASSURANCE["case_id"]}
        a = canonical_bundle(ASSURANCE, QC_HASHES)
        b = canonical_bundle(shuffled, dict(reversed(list(QC_HASHES.items()))))
        assert a.canonical == b.canonical
        assert a.sha256 == b.sha256

    def test_float_repr_noise_does_not_change_the_hash(self):
        # 0.1 + 0.2 reprs as 0.30000000000000004 — the STATED ROUNDING RULE (6
        # decimal places, documented on the module) folds physics-path noise into
        # one canonical number, so an honest re-derivation can never hash differently
        # over the same measurement
        noisy = {**ASSURANCE, "relief": {"applied_mm": 0.1 + 0.2}}
        clean = {**ASSURANCE, "relief": {"applied_mm": 0.3}}
        assert canonical_bundle(noisy, QC_HASHES).sha256 == \
            canonical_bundle(clean, QC_HASHES).sha256

    def test_a_changed_number_changes_the_hash(self):
        changed = json.loads(json.dumps(ASSURANCE))
        changed["sites"][0]["rim_agreement_mm"] = 0.08
        assert canonical_bundle(changed, QC_HASHES).sha256 != \
            canonical_bundle(ASSURANCE, QC_HASHES).sha256

    def test_a_changed_qc_hash_changes_the_bundle_hash(self):
        flipped = {**QC_HASHES, "neodent-gm-4-deviation.png": "c" * 64}
        assert canonical_bundle(ASSURANCE, flipped).sha256 != \
            canonical_bundle(ASSURANCE, QC_HASHES).sha256

    def test_the_hash_is_the_sha256_of_the_canonical_bytes(self):
        bundle = canonical_bundle(ASSURANCE, QC_HASHES)
        assert bundle.sha256 == hashlib.sha256(bundle.canonical).hexdigest()
        # and the bytes parse back to the payload — the bundle is READABLE evidence,
        # never an opaque blob (a dispute reads the record, not a hex string)
        assert json.loads(bundle.canonical) == bundle.payload
        assert bundle.payload["qc_sha256"] == QC_HASHES

    def test_a_non_finite_number_refuses_loudly(self):
        # NaN has no canonical JSON encoding — a bundle carrying one could never be
        # re-verified byte-for-byte, so building it refuses instead of guessing
        with pytest.raises(ValueError):
            canonical_bundle({**ASSURANCE, "bad": float("nan")}, QC_HASHES)


class TestQcImageHashes:
    def test_hashes_are_of_the_image_bytes(self, tmp_path: Path):
        (tmp_path / "a.png").write_bytes(b"\x89PNG-first")
        (tmp_path / "b.png").write_bytes(b"\x89PNG-second")
        hashes = qc_image_hashes(tmp_path, ["a.png", "b.png"])
        assert hashes == {
            "a.png": hashlib.sha256(b"\x89PNG-first").hexdigest(),
            "b.png": hashlib.sha256(b"\x89PNG-second").hexdigest(),
        }

    def test_a_one_bit_image_change_changes_the_hash(self, tmp_path: Path):
        (tmp_path / "a.png").write_bytes(bytes([0b1000_0000]))
        before = qc_image_hashes(tmp_path, ["a.png"])["a.png"]
        (tmp_path / "a.png").write_bytes(bytes([0b1000_0001]))
        after = qc_image_hashes(tmp_path, ["a.png"])["a.png"]
        assert before != after

    def test_a_missing_image_refuses(self, tmp_path: Path):
        # the confirm route turns this refusal into a refused confirmation (AM-10:
        # a bundle that cannot cover its images must never be sealed)
        with pytest.raises(FileNotFoundError):
            qc_image_hashes(tmp_path, ["gone.png"])


class TestWriteBundle:
    def test_writes_content_addressed_under_evidence(self, tmp_path: Path):
        bundle = canonical_bundle(ASSURANCE, QC_HASHES)
        returned = write_bundle(tmp_path, bundle)
        assert returned == bundle.sha256
        path = tmp_path / "evidence" / f"{bundle.sha256}.json"
        assert path.read_bytes() == bundle.canonical
        # atomic tmp+replace leaves nothing beside the content-addressed record
        assert [p.name for p in (tmp_path / "evidence").iterdir()] == [path.name]

    def test_rewriting_the_same_bundle_is_idempotent(self, tmp_path: Path):
        bundle = canonical_bundle(ASSURANCE, QC_HASHES)
        write_bundle(tmp_path, bundle)
        write_bundle(tmp_path, bundle)
        path = tmp_path / "evidence" / f"{bundle.sha256}.json"
        assert path.read_bytes() == bundle.canonical

    def test_two_bundles_coexist_content_addressed(self, tmp_path: Path):
        first = canonical_bundle(ASSURANCE, QC_HASHES)
        second = canonical_bundle({**ASSURANCE, "run_id": "later"}, QC_HASHES)
        write_bundle(tmp_path, first)
        write_bundle(tmp_path, second)
        names = sorted(p.name for p in (tmp_path / "evidence").iterdir())
        assert names == sorted([f"{first.sha256}.json", f"{second.sha256}.json"])
