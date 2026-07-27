"""Offline research/benchmark code — NEVER imported by the production pipeline.

Everything here compares alternative cap-seating algorithms against the shipped,
calibrated baseline (``case_prep.pipeline.auto_flow``) for the report at
``docs/research/alignment-benchmark-results.md``. Nothing in this package may be
imported from ``case_prep.pipeline`` or ``case_prep.domain`` — it is a one-way
dependency (research -> pipeline/domain, read-only) so the benchmark can freely
mirror or call production internals without production ever depending back on
research code.
"""
