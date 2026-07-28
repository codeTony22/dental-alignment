"""THE EVIDENCE BUNDLE (plan §6, grill AM-10): what a confirmation actually seals.

The demo derives its acceptance numbers per response and mutates QC PNGs in place — a
bare digest of thin air could never be re-verified in a dispute. The product's
confirmation therefore seals a PERSISTED bundle: the assurance projection (the worker's
words, as served) plus the SHA-256 of each QC image's BYTES, canonically encoded and
written content-addressed under the immutable run directory. Release re-derives the
same bundle and refuses unless it hashes to the confirmed one — so "the case changed
since it was confirmed" is a byte-level fact, not a heuristic.

CANONICAL ENCODING, stated in full (a dispute re-implements this from the text):

  - JSON, keys sorted at every level, separators ``(",", ":")`` (no whitespace),
    ``ensure_ascii=True`` (pure-ASCII bytes: no encoding ambiguity).
  - THE ROUNDING RULE: every float is rounded to ``ROUND_DECIMALS`` (6) decimal
    places before encoding. Six places is 1 nanometre on millimetre-valued metrics —
    far below every stated measurement noise floor (click scatter p90 is 0.61 mm) —
    so the rule folds float-repr noise (0.1 + 0.2 vs 0.3) into one canonical number
    without ever masking a real change. Integer-valued floats stay floats (JSON
    ``x.0``), bools are never rounded (Python's ``bool`` is an ``int``; guarded).
  - Non-finite numbers REFUSE (``allow_nan=False``): NaN has no canonical JSON, and
    a bundle that cannot be re-encoded byte-for-byte is no evidence at all.

The bundle's payload shape is ``{"assurance": <projection>, "qc_sha256":
{filename: hex}, "adjustments": <"skip" | "adjust" | null>}`` — the projection is
the SAME dict the assurance endpoint serves (one derivation, two readers), so what
the operator saw and what the seal covers can never be two different documents.

``adjustments`` JOINED THE SHAPE (client 2026-07-27's Delivery-vs-Skip fork): the
standing directive is that when Adjust is not surfaced the assurance must still show
what was done, so whether the fits were reworked or waved through is part of what a
confirmation covers — confirm, change the decision, and release 409s through the
same re-derivation that catches a moved number. The VALUE alone rides, not the
record: the fork's ``at``/``run_id`` are attribution, and re-deciding the same way
describes the same case (the SeatedSelection precedent — values only, so an
identical re-act flips no equality).

THAT MAKES BUNDLES WRITTEN BEFORE THIS CHANGE STALE — their canonical bytes lack the
key and hash differently. Harmless by construction: a bundle is per-RUN and always
re-derived, so a case confirmed under the old shape simply refuses release with "the
case changed since it was confirmed" until it is re-confirmed over what is there now
— the same honest path any other drift takes.

WHAT THE BUNDLE NEVER CARRIED, and now cannot: an ACTOR. The confirmation record
used to hold an ``X-Operator`` name (the bundle itself never did); that field is
gone entirely (client 2026-07-27 — see bff/session.py's note). The bundle seals the
EVIDENCE, and the act of sealing it is the whole attestation.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional

ROUND_DECIMALS = 6

# the run directory's evidence store: runs/<run_id>/evidence/<sha256>.json
EVIDENCE_DIRNAME = "evidence"


@dataclass(frozen=True)
class EvidenceBundle:
    """One sealed record: the payload (rounded, as encoded), its canonical bytes,
    and the sha256 hex digest of exactly those bytes."""

    payload: Dict[str, Any]
    canonical: bytes
    sha256: str


def _rounded(value: Any) -> Any:
    """The rounding rule, applied recursively. Bools first: ``bool`` is an ``int``
    subclass and ``round`` would quietly turn True into 1."""
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        return round(value, ROUND_DECIMALS)
    if isinstance(value, dict):
        return {k: _rounded(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_rounded(v) for v in value]
    return value


def canonical_bundle(assurance: Mapping[str, Any],
                     qc_hashes: Mapping[str, str],
                     adjustments: Optional[str]) -> EvidenceBundle:
    """Build the bundle: rounded payload → canonical bytes → sha256. Raises
    ``ValueError`` on non-finite numbers (``allow_nan=False`` — see the module doc:
    evidence that cannot be re-encoded identically is not evidence).

    ``adjustments`` is the fork's decision WORD ("skip" | "adjust") or None when the
    fork was never faced. Required positionally, deliberately: a default would let a
    caller omit the case's own answer to "were the fits reworked?" and seal a bundle
    that quietly says nothing."""
    payload = {
        "assurance": _rounded(dict(assurance)),
        "qc_sha256": dict(sorted(qc_hashes.items())),
        "adjustments": adjustments,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=True, allow_nan=False).encode("ascii")
    return EvidenceBundle(payload=payload, canonical=canonical,
                          sha256=hashlib.sha256(canonical).hexdigest())


def qc_image_hashes(run_dir: Path, qc_names: Iterable[str]) -> Dict[str, str]:
    """SHA-256 of each QC image's BYTES (AM-10: the images are part of what the
    operator signs — a one-bit render change must change the seal). A missing file
    raises ``FileNotFoundError``: the caller (the confirm route) turns that into a
    refused confirmation, because a bundle that cannot cover its images must never
    be sealed."""
    return {name: hashlib.sha256((Path(run_dir) / name).read_bytes()).hexdigest()
            for name in qc_names}


def write_bundle(run_dir: Path, bundle: EvidenceBundle) -> str:
    """Persist ``runs/<run_id>/evidence/<sha256>.json`` atomically (unique tmp +
    ``os.replace`` — the session store's own discipline: a crash mid-write leaves
    the previous state, never half a record). Content-addressed, so a re-write of
    the same bundle is idempotent by construction. Returns the sha256; raising is
    the transactional half of AM-10 — a confirmation whose bundle failed to write
    REFUSES rather than sealing a hash nothing on disk backs."""
    evidence_dir = Path(run_dir) / EVIDENCE_DIRNAME
    evidence_dir.mkdir(parents=True, exist_ok=True)
    path = evidence_dir / f"{bundle.sha256}.json"
    tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_bytes(bundle.canonical)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return bundle.sha256
