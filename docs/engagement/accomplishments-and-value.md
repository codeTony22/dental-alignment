# Phase 2A De-Risk Spike — Accomplishments & Value Summary

*Prepared for pricing/negotiation. Every claim below maps to committed code, tests, infrastructure,
or a generated artifact in this repository — nothing is aspirational.*

---

## 1. What the engagement set out to do

**Goal:** de-risk **Phase 2** — automating implant case-prep (recovering each implant's 3D position,
axis and clocking from an intraoral scan, then building the restoration geometry) *around*
RealGUIDE, which is closed. Prove it's feasible, quantify the accuracy, and set the stage for
Phase 1 — with real, billable research, experimentation and reusable artifacts.

**Bottom line: feasibility is proven, and the path on real clinical data is defined and
partially demonstrated on the client's own scans.**

---

## 2. Goals accomplished (headline outcomes)

| Outcome | Evidence |
|---|---|
| **Automated implant-pose recovery works** | Synthetic ground truth: **~14–20 µm** accuracy, **0% false-confidence** (never confidently wrong) |
| **The clean library CAD closes the real-data gap** | Registration goes from **2.6 mm → ~15–24 µm** once the clean reference is used (the client's provided file, validated) |
| **Bodies are isolated from real teeth** | On a real toothed arch: **1.53 mm → ~0.13 mm** (≈14× improvement) |
| **Bodies are found automatically** | Template-matching locates every scan body among real teeth, **0 false positives, no operator click** (~15 s) |
| **It runs on the client's OWN data** | Full step-by-step automation demonstrated on the client's real Certain 3i scan |
| **CAD geometry works on messy scans** | Screw-channel boring + restoration via signed-distance CSG, robust to non-watertight real meshes |
| **Cloud infrastructure is designed & coded** | Terraform IaC (6 modules) + AWS architecture plan, matching the client's existing conventions |
| **Rigor** | **106 automated tests, all passing**, test-first (TDD), hexagonal/DDD architecture |

---

## 3. What was built (concrete deliverables)

### A. Phase 2A automation engine (`apps/worker/`, Python)
- End-to-end staged pipeline: **ingest → localize → register → 6-DoF pose (incl. clocking) →
  retention-aware confidence gate → report**, with real per-stage file artifacts.
- **Custom registration core** — an in-house trimmed-ICP with axis-cone multi-start (Open3D's
  registration segfaults on this hardware; the replacement is deterministic and clinical-grade).
- **Body isolation** — separates a scan body from surrounding teeth (the key real-data unlock).
- **Auto-localization** — finds scan bodies with no operator click via CAD template-matching.
- **SDF-CSG boolean engine** — screw-channel bore, abutment union, cement-gap offset; robust to
  the holey, non-watertight meshes real intraoral scanners produce.
- **Clinical-safety gate** — retention-aware, explainable, never confidently passes a wrong result.
- **106 passing tests**, TDD throughout.

### B. Real-data validation (the client's own files)
- Ingested and validated against the client's real **DG Code / Certain 3i** scans
  (three real toothed upper-jaw scans + the segmented scan body).
- Established the **decisive finding**: the clean scan-body library CAD is the single unblock —
  and confirmed it collapses the error from millimetres to microns.
- Independent verification in **CloudCompare** (industry-standard 3D metrology).
- Honest findings documented (`docs/engagement/`): what works, what real data still needs.

### C. Cloud infrastructure (`infrastructure/`)
- **Terraform IaC**, 6 modules (network sandbox / KMS / storage / queue / worker / observability),
  S3-locked state backend, `terraform validate` clean — matching the client's `wl-gateway-service`
  conventions.
- **AWS architecture plan** — Fargate workers + SQS → Step Functions (human-in-the-loop boundary)
  + S3/KMS sandbox for PHI-adjacent data.

### D. Client-facing demos & reports (`apps/worker/reports/client-demo/`)
- **Step-by-step automation report** (PDF) on the client's real scan — reproducible via
  `make automation-demo`.
- Accuracy report, boolean/CAD demos, deviation heat-maps, comparison artifacts, STL viewer.
- Opportunity/ROI forecast, plan-grilling (architect + dental product-owner lenses).

---

## 4. Value delivered (why this is worth paying for)

1. **De-risked a multi-phase engagement.** The client now *knows* Phase 2 is feasible and *where*
   the accuracy sits — before committing to Phase 1 or a full build. That is the entire point of a
   spike, and it's done with hard numbers, not opinions.
2. **Turned an open question into a sourcing task.** The one remaining blocker to clinical accuracy
   on real cases is a defined, sourceable input (the clean library CAD + calibration set), not
   open-ended R&D. That materially lowers the cost and risk of everything downstream.
3. **Reusable IP.** A working automation engine, a robust geometry engine, and production-shaped
   cloud infrastructure — all reusable directly in Phase 2, not throwaway spike code.
4. **Honesty as an asset.** Accuracy is independently verified and the limits are stated plainly.
   The client can trust the numbers, which is what lets them fund the next phase confidently.

---

## 5. Fair-price basis (at the agreed $150/hr)

The scope above is genuinely a multi-week body of **specialized** work (dental-implant CAD
automation, 3D registration, computational geometry, cloud IaC). Estimating by workstream:

| Workstream | Est. specialized hours |
|---|---|
| Phase 2A automation engine (pipeline, custom ICP, gate, tests) | 60–80 |
| SDF-CSG boolean/geometry engine | 15–20 |
| Real-data ingestion + validation + findings (client files) | 20–30 |
| Body isolation + auto-localization (breakthroughs + deep debugging) | 20–30 |
| AWS architecture plan + Terraform IaC (6 modules) | 15–25 |
| Client demos, reports, metrology verification | 15–25 |
| Research, plan-grilling, documentation | 10–15 |
| **Total** | **≈ 155–225 hrs** |

**At $150/hr → roughly $23k–34k for the full scope delivered to date.** (The earlier ~$18k
estimate covered only the initial spike + IaC + plan; the real-data validation, body isolation,
auto-localization and the client-data demo are substantial additions since.)

*Guidance for negotiation:* price on the **value and the deliverables**, not just hours — this
spike replaces a much larger and riskier speculative build, and hands over reusable engine +
infrastructure. A fixed fee in the **$25k–32k** band is defensible for the scope; anchor high,
justify with the artifact list above, and hold the honesty of the findings as the differentiator.
Set the final number to what is fair for your actual time and the value created.
