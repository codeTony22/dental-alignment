"""case_prep.application — the PRODUCT'S orchestration layer over pipeline/domain/adapters.

The seam the product app plan names (docs/engagement/product-app-plan.md §3, grill AM-2):
the BFF imports ONLY ``case_prep.pipeline``/``domain``/``adapters`` and THIS package —
never ``case_prep.server``, which is the frozen demo's HTTP surface and boots the demo's
module state. New files only; server.py is untouched (that is the freeze).

These modules re-state, in clean framework-free functions, the orchestration the demo's
server built inline — the ~1,200-line Python lift the plan's debt ledger records. Each
module's docstring names the server.py lines it supersedes FOR THE PRODUCT; the demo keeps
its own copy, which is the freeze working as designed, not drift.
"""
