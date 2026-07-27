# Phase 2A — Automated Case Prep: Detect, Count, Localize & Align

**An implementation plan for the smallest slice of Phase 2 that breaks the manual bottleneck.**

This automates the repetitive *case-setup* work — counting the implants in a scan, locating each one, and aligning each scan body to recover the implant's position and axis — and hands the operator a prepared case. It deliberately stops before the clinical design work. It is the front half of the §6 pipeline, scoped to deliver value fast and de-risk the rest.

> **Revision — July 2026.** This plan has been tested against the client's real data (DG Code /
> Certain 3i scans + the clean library CAD). Corrections are applied inline below and the
> full evidence review is in `engagement/phase2-plan-review-2026-07.md`. Headlines: the
> library-CAD dependency (§6) is confirmed decisively (2.6 mm → ~20 µm); the geometric detection
> heuristic in §5 Track A is **disproven** on real scans and replaced by library template
> matching (implemented); **body isolation** — absent from the original pipeline — is the
> binding real-data constraint and is now a first-class stage; measured accuracy meets the §8
> target (0.13 mm on a real toothed arch). Two grilling gates remain open: the RealGUIDE import
> seam (unvalidated, top risk) and shadow/advisory mode (required — the synthetic-calibrated
> gate passed a 1.75 mm-wrong pose on real data).

---

## 1. Why this is the right wedge

The portal's purpose is to take in volume. But volume on top of fully-manual fulfilment just creates a labour bottleneck — more cases, the same hours per case, no margin gain. The throughput and margin upside in the forecast comes from automation, so the portal and *some* automation must ship together. The good news is that you do not need all of Phase 2 to break the bottleneck: the **case-prep steps (count, locate, align) are the most repetitive per-case work and the most tractable to automate**, so automating just these removes the largest, dullest chunk of operator time per case while leaving every clinical decision with a human.

## 2. Scope — what it does and does not do

**Does:**
1. **Counts** the scan bodies (= implants) present in the uploaded scan, and reconciles the count against what the shop declared in the portal.
2. **Localizes** each implant — where it sits on the arch, its emergence point, and its axis (i.e. *where the healing cap / restoration goes*).
3. **Aligns** each scan body to its known manufacturer library mesh to recover the implant's full 6-DoF pose (position, axis, and a rotational/clocking estimate).
4. **Measures each site** *(added 7/26, built)*: healing-cap centre + interproximal
   (mesio-distal) gap to the adjacent teeth with clinical classification (≥7 mm ample /
   6–7 mm narrow-implant / <6 mm insufficient) — feeding implant/diameter selection.
5. Hands the operator a **prepared case**: count verified, each implant's pose recovered and seeded, site measured, ready to import — with low-confidence implants flagged for manual seeding.

**Does not** (these stay in the augment path / later phases): generate crown morphology, build the abutment or screw channel, run manufacturability checks, or replace the human QC sign-off. It is *case preparation*, not design.

## 3. Research grounding — this is a validated technique, not new R&D

The core operation is what Exocad, Medit, and 3Shape already do interactively, which de-risks it substantially:

- **The established workflow:** select the implant system → the CAD software loads the matching scan-body library mesh → the operator seeds one point (Exocad: single-point best-fit) or three points (Medit: three-point) → a **best-fit algorithm superimposes the library scan body onto the scanned one**, converting scan-body position into implant position → the operator verifies and adjusts. We replicate this **headless and automatic**, with a confidence gate deciding when a human must seed.
- **Accuracy is clinically tight when done well:** best-fit alignment achieves ~0.04–0.07 mm linear and ~0.23–0.63° angular deviation. This sets our accuracy target.
- **Two findings that justify the human gate:** (a) automatic best-fit is *less* accurate than careful manual overlay, and (b) an insufficiently accurate alignment produces clinically unacceptable implant positions. So the safe design is auto-align-where-confident, human-verify-the-rest — the same division of labour the operator already performs.
- **It is an active commercial frontier:** some scanners now recognise scan bodies and swap in library components at capture time. That proves feasibility and defines the niche — shops sending STLs *after* capture still need this done server-side.
- **Counting is a solved class of problem:** intraoral-scan segmentation (MeshSegNet / iMeshSegNet / TSegFormer families) is mature, and recent work annotates and counts implants on partial-arch scans.

**The decisive simplification — the portal feeds the automation.** Because the new-case wizard captures the implant system and scan-body type *per site*, the pipeline already knows **which library mesh to load and how many scan bodies to find**. Detection therefore collapses from the hard problem ("identify an unknown object and its type") to the easy one ("locate N *known* objects"). The structured intake is what makes the geometry tractable, and it is already in the design.

## 4. The pipeline

```
STL in
  │
  ▼
(1) Ingest & normalize  ── scale-gate (arch 45–70 mm), units, downsample to ~10–16k for processing
  │
  ▼
(2) Detect & count scan bodies ── template-match the declared library part along the occlusal
  │      ridge (a body fits ~0.65, a tooth ~0.2); compare found vs declared N → flag mismatch
  │      (also a billing check). [Rev 7/26: geometric signatures disproven — see §5]
  ▼
(2b) Isolate each body from the surrounding teeth ── vertical-cylinder crop about the occlusal
  │      normal + surface-normal filter + near-axis cap. [Rev 7/26: the binding real-data
  │      constraint — naïve ROI = 1.53 mm error, isolated = 0.13 mm]
  ▼
(3) Localize ── the seed pose IS "where the implant/cap is": position + axis per implant
  │
  ▼
(4) Align (per implant) ── load the declared library scan-body mesh
  │      coarse: cheap trimmed ICP ranked over clocking × a small AXIS-CONE of seeds
  │      fine:   trimmed point-to-point ICP on the best few basins
  │      [Rev 7/26: as implemented — Open3D registration segfaults on this host; the axis-cone
  │      multi-start is required to escape wrong basins ~40° off, even on clean scans]
  │      → 6-DoF scan-body pose
  ▼
(5) Derive implant pose ── apply the library's fixed scan-body→platform transform
  │      → implant platform position + axis (+ clocking estimate) = where the healing cap / restoration seats
  ▼
(6) Confidence gate ── per implant: ICP fitness/RMSE, multi-start clocking best-vs-next gap,
  │      multi-implant consistency → PASS = auto-seed ; LOW = flag to operator to seed manually
  ▼
(7) Output to operator ── prepared case: count verified, per-implant pose + confidence, ready to import
```

Steps 1–5 are the geometry; step 6 is the safety layer; step 7 is the operator hand-off. Each implant is handled independently, so one low-confidence implant flags only itself, not the whole case.

## 5. Two implementation tracks

Build the geometric track first (no dataset needed); add the learned track once data accrues.

**Track A — library-driven template matching (MVP, ships first).** *(Revised 7/26.)*
- *Detection:* **the geometric/heuristic signature originally proposed here is disproven.**
  Three spikes on the client's real scan show no shape signature separates a coded healing cap
  from teeth: a neighbouring tooth is *more* circular (0.04 vs 0.33 wall-circularity residual),
  surface roughness is identical at scanner resolution, and teeth hold their cross-section
  *more* consistently than the coded cap. What works — and is implemented (`auto_localize`) —
  is the plan's own fallback: **best-fit the known library mesh at ridge candidates and keep
  strong matches** (body ≈0.65 fitness vs tooth ≈0.2; 3/3 found on a real arch, 0 false
  positives, no operator click). Because the count is declared, this needs only to find that
  many instances; extended to the full cap catalog it also *identifies the type* per site.
- *Alignment:* custom trimmed point-to-point ICP with an axis-cone multi-start (numpy/scipy —
  Open3D's ICP segfaults on the dev platform and is being removed from the path per the
  grilling). Fully deterministic and explainable — which is what a clinical-safety gate wants.
- *Pros:* no training data, interpretable, proven on the client's data. *Cons:* needs the cap
  CAD per supported type/diameter (the §6 hard dependency — now confirmed decisively); weaker
  on poor scans (which is why those flag to a human).

**Track B — learned detector (later, data-gated).**
- A 3D segmentation/detection model (MeshSegNet/TSegFormer-style, or a small dedicated scan-body detector) trained on labelled scans to segment scan-body instances robustly, including on noisy/partial scans.
- Trained on the **data flywheel** the MVP produces: every operator-verified case is a labelled example (§6.7). Supplements, never replaces, the geometric alignment + gate.
- *Pros:* robust detection on hard scans, less per-geometry tuning. *Cons:* needs hundreds-plus labelled scans; a later investment, not the MVP.

## 6. Dependencies & prerequisites

- **Scan-body CAD libraries (hard dependency).** Best-fit needs the library mesh for every implant system supported (e.g. the Zimmer / Atlantis types seen in the source screenshots). These are per-manufacturer parts. The client already runs these libraries inside RealGUIDE, so they are obtainable — sourcing/managing them is a named prerequisite, not an open research problem.
- **The declared spec** from the portal (implant system + scan-body type per site) — already designed; it is what makes detection tractable.
- **Ground truth for validation** — the known scan-body→implant transform per library part, plus a validation set (see §8).

## 7. Tech stack & integration

- **Registration/geometry:** Open3D (open, primary) or MeshLib (licence-gated; consolidates registration + healing + SDF — see the main design doc §6.5/§9). Either supports the global-then-ICP pipeline.
- **Detection:** Track A geometric (trimesh / Open3D / PyMeshLab + NumPy); Track B a PyTorch mesh model later.
- **Runtime:** the sandboxed Fargate worker from the main design (no egress except S3/SQS, resource-limited), invoked on case submission; this is the stage-1 ("localization-prep") stage of the §6.1 split, ending at `awaiting_seed` for any flagged implant.
- **Operator hand-off:** the recovered poses + confidences attach to the case; the operator console shows the prepared result and a one-click manual-seed for flagged implants — then the case proceeds to design (RealGUIDE, augment path) as today.

## 8. Accuracy targets & validation

- **Target:** match the clinical best-fit benchmark — on the order of ~0.1 mm position and well under ~1° axis on cases that clear the gate, with a near-zero rate of confident-but-wrong results.
- **Measured (7/26, clean library CAD + body isolation):** 17 µm / 0.7° on a clean capture,
  24 µm / 2.0° under noise+occlusion, **0.13 mm / 4.6°** embedded in a real toothed arch
  (operator-seeded); fully-automatic path ~0.15 mm position with axis 1–15° (the open accuracy
  item). Without the clean library CAD the same real case measures 2.6 mm — the dependency in
  §6 is the whole ballgame.
- **Ground truth:** primary — derive the true scan-body→implant transform from the library part and a controlled reference; fallback — a machined/measured physical phantom with known implant positions plus an operator-co-validated subset of real cases (the named Plan B from the spike).
- **Metric that decides go/no-go:** the **share of the client's real caseload that clears the confidence gate with near-zero false-confidence**, broken down by case type and scan-body type. That clear-rate is what determines how much manual setup time is actually removed.

## 9. Confidence gating (deterministic, per the safety model)

The automate-or-flag decision is threshold-based, not a model:
- **Position/axis:** ICP fitness and inlier RMSE below threshold → flag.
- **Clocking (screw-retained only):** multi-start ICP about the recovered axis; flag if the best-vs-next-best RMSE gap is small or the anti-rotation-feature residual is high. Cement-retained cases skip this — they only need position + axis, so they clear more often (the easiest wedge).
- **Multi-implant consistency:** inter-implant distances/angles sanity-checked against the declaration.
- **Count mismatch:** detected count ≠ declared count → whole case flags (and surfaces as a billing/verification discrepancy).
Thresholds are calibrated against ground truth in the spike and are explainable for clinical auditability.

## 10. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Scan-body library not available for a system | Source from the client's RealGUIDE libraries; restrict supported systems to those with libraries on hand |
| Poor/partial scans (esp. full-arch) reduce accuracy | Confidence gate routes them to manual seeding — accuracy is never silently sacrificed |
| Clocking ambiguity on screw-retained cases | Hard gate; cement-retained (no clocking) targeted first |
| Detection heuristics brittle across geometries | Declared count narrows the search; Track B learned detector added once data accrues |
| Automatic less accurate than manual (per the literature) | Gate + human verify; the goal is to remove *setup time on easy cases*, not to eliminate the human |

## 11. Effort & sequencing

Delivered in two gated steps, consistent with the main design's §8 cost model:

1. **Spike (de-risk, ~$8–15k):** prove the count→localize→align→pose chain on the client's real cases, establish ground truth, and measure the clear-rate by case/scan-body type. Go/no-go.
2. **Productionize this wedge (~$15–25k):** harden detection + alignment + gating, wire into the worker and operator console, run on live cases. This is a *subset* of full 2B (localization + registration only — not the design pipeline), so it is the cheapest path to a real per-case time saving.

Total ~$25–40k to a working case-prep automation — far less than full 2B, and it is the piece that directly makes portal volume profitable. Cement-retained crowns are the first target (no clocking), widening to screw-retained as the allow-list and gate mature.

## 12. How this makes the portal worthwhile

Each prepared case saves the operator the most repetitive part of setup — finding, counting, and aligning every implant by hand. That is the per-case time reduction that converts incoming volume from "more hours of work" into "more margin," which is precisely the gap the portal-without-automation leaves open. It is the minimum automation that makes the business case for taking in volume hold — and it is built on a clinically-validated technique, fed by the structured intake the portal already captures.
