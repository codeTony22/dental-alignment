# Cap-Variant Identification Demo — Design (PARKED, pre-spec draft)

**Status: PARKED 2026-07-11** — design was presented and shaped through four
operator decisions, but the operator redirected focus to another project
before final approval. This file preserves the decisions verbatim so the
brainstorm can resume without re-litigating. NOT yet an approved spec.

## The ask (operator, 2026-07-11, voice)

When a doctor's arch scan comes in, each implant site carries a healing cap —
one of six size variants per implant system (code = Ø×H, e.g.
`zimmer-4.5-5020` = Ø5.0 × 2.0mm). The variant identity per site must be
reliable for (1) **billing** — which part was used, and (2) **clinical
safety** — the emergence profile is cap-shaped; building a prosthesis for the
wrong diameter is a real clinical error. Either the doctor declares the
variant (we verify) or the automation identifies it — the demo must prove the
automation.

## What already exists (worker, post-"task #12")

- `measure_rim_diameter` — Kasa circle fit to the rim in the scan → measured Ø
- `classify_diameter` — diameter class with a 0.3mm refusal margin (refuses →
  routes to declaration/operator, never guesses)
- Scan-coverage fit across candidate templates picks collar height in-class
- CLI declaration `--site TOOTH:X,Y,Z:VARIANT` — authoritative for billing
- `variant_agreement(declared, identified)` — mismatch flags; per-site report
  carries the full `variant` block

## Operator decisions (all four answered)

1. **Truth source**: doctor marks/labels on a website — upload STL, mark
   sites, declare variant per site via dropdowns (or tooth+measurement
   collection). Purpose: demo to prove the automation.
2. **Demo scope**: demo page as the SEED OF PHASE 1 — built in `apps/web`
   (React + Vite, currently placeholder), no auth/S3/billing.
3. **Mismatch policy**: **block until resolved** — a declared-vs-identified
   mismatch hard-stops the output package until a human explicitly resolves
   which is correct; the resolution is an auditable billing record.
4. **Demo loop**: **full loop in browser** — upload → mark + declare → Run →
   per-site verdicts (identified variant, measured Ø, agree/mismatch/blocked)
   + QC overlay. Thin local API (seed of `apps/api`, NestJS) shells out to
   the worker.

## Presented design (awaiting final approval)

- **Data flow**: browser (upload STL, 3D viewer, click-to-mark, variant
  dropdowns from `GET /catalog` reading the real library dir) → `POST /cases`
  (multipart; writes `runs/<case_id>/` + `sites.json`) → spawns
  `case-prep auto --site TOOTH:X,Y,Z[:VARIANT]…` → `GET /cases/:id` (status +
  parsed auto-report + QC overlay) → `POST /cases/:id/resolve` re-runs with
  `--resolve TOOTH:declared|identified`.
- **Case contract**: `sites.json` = `{model, jaw, sites: [{tooth,
  point: [x,y,z], declared_variant | null}]}`.
- **Worker change (only production-logic change)**: new statuses —
  `blocked_mismatch` (variant_agreement flag → package NOT emitted; report
  carries both candidates + evidence) and `needs_declaration` (refused ID +
  no declaration). New `--resolve` input; resolution lands in report +
  manifest.
- **Web UX**: upload → viewer (three.js) → "Propose sites" pre-marks via the
  worker's existing detector → confirm/adjust → variant dropdown or "let
  automation identify" → Run → verdict cards + case status (READY/BLOCKED) +
  resolve buttons.
- **Testing**: worker changes TDD'd in pytest; API e2e against a fixture
  scan; web component tests for marking/verdict logic.
- **Out of scope**: auth/tenancy, S3, Stripe/billing-code mapping, physical/
  coded markers (future identification input), mobile.

## Also pending for this repo (operator-requested, same session)

- Docs refresh: root README says "63 tests" (actual ~177 collected /
  169+2xfail per architecture-current); same staleness in
  phase2a-spike-findings, accomplishments-and-value (106),
  phase2-plan-review (106), the 2026-06-28 spec; `cap_library.py`'s
  "stand-in single-template" note contradicted by the 6 on-disk variant CADs.
- `CLAUDE.md` + Claude skills: none exist anywhere in the repo.
- **`git init`**: the repo has NO version control (a `.gitignore` exists but
  no `.git`).

## Resume point

Present this design for final approval → write the approved spec → run the
docs/skills/git housekeeping → writing-plans → implement.
