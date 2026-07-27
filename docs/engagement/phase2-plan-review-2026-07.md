# Phase 2 Plan Review — July 2026

*A re-review of `docs/phase2a-automated-case-prep-plan.md` (and the earlier grilling report)
against what has since been **proven or disproven with real data and working code**. Every verdict
below cites evidence in this repo — tests, measurements on the client's DG scans, or spike
results — not opinion.*

---

## 1. The goal, restated (and sharpened by the client's flow)

The original goal: automate case prep — count, localize, align — and hand the operator a
prepared, confidence-gated case.

The client has since made the *product* flow concrete, which sharpens the goal:

> A doctor uploads an arch scan (upper or lower). The system **counts the healing caps**, finds
> the **center of each**, and **measures each site** (interproximal/mesio-distal gap). The doctor
> supplies the **cap type** (Esthetic / TSV / Certain / ExHex) **+ diameter** (e.g. Certain 3).
> The system selects the matching **implant assembly from the library (6 STL parts)** and routes
> the order to **one of 3 US vendors** for manufacture — with every step confidence-gated and
> human-reviewable.

This adds two elements the original plan never had: **site measurement** (interproximal gap —
now built and validated) and the **catalog/vendor layer** (not yet built). Both fit cleanly
inside the plan's philosophy (automate prep, keep clinical decisions human).

---

## 2. What the plan got RIGHT — now with hard evidence

| Plan claim | Verdict | Evidence |
|---|---|---|
| §3 "Decisive simplification": knowing the library part makes detection tractable | **Confirmed — stronger than the plan knew** | Template-matching is not just easier, it is the *only* detector that works (see §3 below). `auto_localize`: 3/3 bodies found among real teeth, 0 false positives |
| §6 Scan-body CAD library is the hard dependency | **Confirmed decisively** | The clean Certain CAD took registration from **2.6 mm → ~20 µm** on the client's own part. Single most load-bearing prerequisite, now measured |
| §8 Accuracy target ~0.1 mm / <1° | **Met for position** | 17 µm/0.7° (clean), 24 µm/2° (noisy+occluded), **0.13 mm/4.6°** embedded in a real toothed arch. Auto-path *axis* is the soft spot (1–15° variability) |
| §9 Deterministic confidence gate + human-in-loop | **Right design, wrong thresholds** | Synthetic-calibrated gate passed a 1.75 mm-wrong pose on real data. Shadow/advisory mode (grill must-fix #4) is now **non-negotiable**, confirmed by our own measurement |
| §4 Pipeline shape (ingest→detect→localize→align→pose→gate→handoff) | **Confirmed** | `pipeline/stages.py` implements it staged, with artifacts, 106 tests green |
| Cement-first, screw-later wedge | **Confirmed** | Clocking gate works on synthetic; real-data clocking flagged 2/3 — the gate catching real ambiguity, as designed |

## 3. What the plan got WRONG — proven by spikes on the client's data

1. **Track A detection heuristic is disproven.** The plan proposed detecting scan bodies by
   "height-above-surface + curvature/shape signature (cylinder-like)". Three spikes on the real
   DG scan show **no geometric signature separates a healing cap from teeth**: a neighbouring
   tooth is *more* circular (0.04 vs 0.33 wall-circularity residual), roughness is identical
   (machined cap ≈ enamel at scanner resolution), and teeth hold cross-section *more*
   consistently than the coded cap. The plan's fallback — "best-fitting the known library mesh
   at candidate locations" — is what actually works and is built. **Replace Track A's heuristic
   language with library-driven template matching as the primary detector.**
2. **The registration stack is not what the plan named.** FPFH+RANSAC + point-to-plane ICP was
   the plan; reality is a custom trimmed **point-to-point** ICP with an **axis-cone multi-start**
   (Open3D's ICP segfaults on this host; the axis-cone was required to escape wrong basins ~40°
   off — even on clean scans). The grilling flagged the doc mismatch; the plan should name the
   implemented core and its measured numbers.
3. **The plan skipped the hardest real-data step entirely: body isolation.** Steps (2)→(3)
   "ROI + seed" gloss over separating the body from the teeth it is fused to. This turned out to
   be **the binding constraint** on real arches: naïve ROI = 1.53 mm error; the isolation built
   for it (vertical-cylinder crop + surface-normal filter + near-axis cap) = **0.13 mm**. Any
   revised plan must name isolation as a first-class pipeline stage.
4. **Ingest normalization is not trivial on real/edentulous arches.** `normalize_orientation`
   mis-frames the DG upper jaw; the robust occlusal axis (arch smallest-PCA, crown-oriented) had
   to be built (`site_analysis.occlusal_axis`). The plan's step (1) needs this correction.

## 4. Grilling must-fixes — status today

| # | Must-fix | Status |
|---|---|---|
| 1 | **RealGUIDE import seam spike** | ❌ **Still unvalidated — the top existential risk.** Nothing built since touches it. Needs the client's RealGUIDE build; ~1 week; hard gate before production spend |
| 2 | Worker doesn't exist (mislabeled as hardening) | 🟡 Partially closed: the staged worker (`stages.py`, stage1→awaiting_seed→stage2, artifacts) now exists and is tested. SQS/S3/boto3 adapter still net-new |
| 3 | Synthetic-only validation | 🟡 Substantially closed: real DG scans + embedded-real-arch ground truth now drive validation. Still missing: one patient arch scanned *with* a known library abutment (the true end-to-end case) |
| 4 | Safety metric blind → shadow/advisory mode | ❌ **Not yet built** (task #3 on the board). Confirmed necessary by our own 1.75 mm false-confidence measurement |
| 5 | Tenancy/migration before IAM/KMS | ⏸ Untouched — Phase 1/portal concern, correctly parked |

## 5. Suggested revised Phase 2 plan (dependency-ordered)

**Wedge 1 — finish the detection story (now, no new data needed)**
1. **Library-driven cap detection** (`CapLibrary` + `detect_caps`): match the scan against the
   catalog of known cap types → **count + center + type** in one pass. Type-agnostic *to the
   doctor* (the system tries the library); uses the legacy shelf CAD as the stand-in template until
   per-type CADs arrive. Builds directly on the proven `auto_localize` (~0.65 body vs ~0.2 tooth
   fit discrimination). *This replaces the disproven geometric Track A.*
2. **Shadow/advisory mode + gate recalibration** against embedded-real ground truth (task #3;
   closes grill must-fix #4). Real cases always route to human review; log what *would* have
   passed.
3. **Single `case-prep auto <scan> <library>` command** (task #4) — the seamless surface:
   ingest → detect/count → isolate → register → site-measure → gate → prepared case + report.

**Wedge 2 — the client's product flow (needs client inputs)**
4. **Catalog layer**: `CapType × diameter → 6-STL implant assembly → vendor (1 of 3)`.
   *Client inputs needed:* the per-type cap CADs (Esthetic/TSV/Certain/ExHex × diameters), the
   6-STL default library, the 3 vendor names + any per-vendor output requirements.
5. **Site analysis in the case report** — cap center + interproximal gap (built, validated:
   8.5 mm "ample" on the DG premolar site) becomes a standard per-site output feeding implant
   selection.

**Wedge 3 — the gates that decide production spend (unchanged from the grilling)**
6. **RealGUIDE seam spike** (must-fix #1) — export a known-pose mesh + sidecar into the client's
   actual RealGUIDE; measure whether the pose survives import. **A negative result re-prices the
   whole automation as assisted-manual.** Do this before any worker/infra build-out.
7. **One paired real case** — a patient arch scanned *with* a known library abutment in place +
   the RealGUIDE-recovered pose as ground truth. This single artifact converts every number above
   from "embedded-real" to "clinical".
8. Then (and only then): worker productionization (SQS/S3 adapter on the staged worker), the
   Terraform estate right-sized per the grilling's "must address now" list.

**Accuracy backlog (parallel, as capacity allows)**
- Auto-path **axis hardening** (the 1–15° variability on near-symmetric caps).
- **Multi-implant consistency** check (currently a no-op) + explicit scan-body→platform
  transform (task #5).

## 6. What to ask the client for, in one list

1. Per-type healing-cap CADs: Esthetic, TSV, Certain, ExHex — each diameter you support.
2. The default 6-STL implant assembly library (the six piece files + names).
3. The 3 vendor names + each vendor's required output format.
4. Scan-body→platform transform per system (or confirmation it's in the CAD's frame).
5. One case exported from RealGUIDE with its recovered pose (the seam-spike + ground-truth
   artifact — the highest-value single item on this list).

## 7. Bottom line

The plan's *shape* survived contact with real data; its *detection method* and its *accuracy
assumptions about ingest and ROI* did not. The three highest-leverage moves now are
**(1) library-driven cap counting** (finishes the client's core flow with proven technique),
**(2) advisory mode** (closes the one live safety hole we measured ourselves), and
**(3) the RealGUIDE seam spike** (the unvalidated assumption the entire economic case still
rests on). Everything else — catalog, vendors, infra — hangs off those three.
