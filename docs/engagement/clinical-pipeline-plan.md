# The clinical pipeline plan: find → isolate → align → recompose → deliver

2026-08-13 · engineering plan connecting the boolean engine
(`boolean-engine-plan.md`) to the product's clinical flow, end to end. For each
stage: what is implemented today (with the measured constants), what the dental
industry does, and the improvement slices. Written to be read alongside §10-AT
in `product-app-plan.md`; where this document names a workstream (W1…W6,
Stage 0…3) it means the boolean plan's.

Doctrine binding all of it (§10-AS.14/16/19 + §10-AT 4-r): scan bytes are never
rotated — parts move to the scan; the cut is the exact cap + the site's
gingival offset, nothing inferred; artifacts 1–5 are the open arch, artifact 6
is the one closed exception; statuses and verdicts are server-derived; every
degradation is honest — a fallback always carries a note.

---

## Stage 1 — find the healing cap on the scan

### What we run today (`adapters/cap_detection.py`)

**Yes — the detector is a density instrument.** The question "do we measure
density to find the cap" has a precise answer: the discriminating test is a
**core/ring point-density ratio**, validated on real arches. The full
discriminator stack, in order:

1. **The occlusal axis** (`crown_up_axis`): the arch's thinnest principal
   direction; its SIGN is disambiguated by bump topology — the crowns side
   carries many separate bumps (cusps, cap rims) spread along the arch, the
   palate side one compact dome.
2. **The height window**: a cap's rim sits below the cusp line — measured
   5.9–6.6 mm on real caps vs ≤ 1.9 mm for every tooth site. The proposal gate
   is 2.75 mm (recalibrated on five labeled arches: recall first — 6/6 real
   caps proposed at the cost of ~3 extra candidates, which registration then
   rejects).
3. **The RIM-SLAB density test** — the heart of it. A healing cap presents a
   full-360° ring of surface at ONE height (its rim, level within ±1 mm) with
   an **empty core** above the slab bottom, because the screw recess is deep or
   unscannable. Measured densities: real caps 0.0–0.66 core/ring; flat gingiva
   ~1.9; the worst tissue artifacts 0.79–1.9. The gate is 0.9, with the ring
   itself required to be real surface (≥ 10 pts/mm²) and LEVEL (z-std ≤ 0.6 mm
   — a flank sloping through the slab is not a rim).
4. **Context gates**: the site must be surrounded by scanned tissue on ≥ 10/12
   bearings (scan-edge corners fail this), sit within 7 mm of the cusp-level
   arch trace (palate rugae rings otherwise false-positive), and stand ≥ 8 mm
   from any sibling (implants are never closer).

**The centre**: each candidate's centre is the rim-height point over the void.
It is then REFINED by the template machinery — `register` (multi-start ICP
against the library cap CAD) and `resolve_sites` — so the shipped centre is the
6-DoF template pose's, not the density blob's. `measure_rim_diameter` reads the
visible rim width at the candidate; it is served as
`site_measured_diameter_mm` on the detection record and feeds the pane-2 width
cut (Stage 2).

The design principle: **the generator proposes, template registration
disposes.** Density gets recall; the CAD gets precision. This is why the
detector survives low-profile caps that defeat template-fitness ranking alone
(tooth domes out-rank real caps on fitness — the measured failure that created
this module).

### What the industry does

- **Tall scan bodies**: the mainstream flow (3Shape, exocad implant modules)
  expects a distinctive machined scan body and finds it by template fitness —
  works because the part is DESIGNED to be findable. Healing caps are not; they
  are low, round, and tissue-coloured. Our density stack exists precisely
  because the industry's default assumption fails here.
- **AI segmentation** (Medit, newer 3Shape): learned tooth/tissue labeling.
  Powerful, but a black box — no per-site evidence to show a lab, and training
  data for healing-cap arches is scarce. Our discriminators produce named,
  numeric evidence per candidate (`rim_below_cusps_mm`, `void_ratio`), which
  the product can (and should) surface.

### Improvement slices

- **1a · Serve the discriminator evidence.** The detection record already
  carries the measured diameter; add `rim_below_cusps_mm` and `void_ratio` per
  suggested site so the digest and the Intake UI can say WHY a site was
  proposed. (Small: application/detection → BFF view → digest.)
- **1b · The missed-cap path stays manual-first.** The one-click missed-cap
  mark (task #31) is the honest fallback when recall fails; no threshold
  loosening without a labeled-arch recalibration like 2026-07-11's.

---

## Stage 2 — isolate the cap and show it (the two-pane tool)

### What we run today

Pane 2 ("Scanned cap") isolates the cap from the arch **client-side, by an
honest ladder** — each rung a strictly weaker measurement, the caption naming
the rung in use (`scanPaneCapCylinder` in `domain/declare.ts`; crop kernels in
`packages/viewer`):

1. **Template-matched** ("the healing cap only") — when a pose stands (the
   held preview pose or the seated pose), keep crop triangles within
   CAP_MATCH_BAND_MM = 0.6 of the POSED library cap surface
   (`buildSurfaceGrid`/`cropTrianglesNearSurface`), with the **core-keep
   correction** (`cropCapIsolation`): inside a core radius (rim − 1.0 mm,
   floor 1.2 mm) triangles are kept unconditionally, because the scanned
   screw-recess interior has no template counterpart — the band would carve a
   hole in the cap itself (shipped after exactly that defect, client
   2026-08-11).
2. **Width cut** ("the healing cap · by width") — no pose yet: a cylinder at
   exactly min(catalog rim Ø, measured visible Ø)/2 about the frame's axis.
3. **Spherical band** — no variant dimensions at all.

Nothing is moved and nothing is resliced — the crop selects whole triangles
from the doctor's own bytes. The two-pane workspace shows this isolated cap
beside the library cap (pane 1), both framed top-of-cap, so doctor or lab
compares like with like.

### What the industry does

Manual lasso/brush trimming (every lab package), or AI margin detection tuned
for PREP LINES on teeth — a real geometric step. For healing caps the step
vanishes exactly where it matters: tissue heals AGAINST the cap, and we
measured (tooth 20) that the cap–tissue boundary is where the surface blends
smoothly. Curvature/crease segmentation was therefore explicitly rejected
(§10-AT front 1). Our advantage is structural: we HOLD the exact CAD template
and its measured pose, so isolation is shape-matched, not inferred — something
generic dental CAD cannot do for tissue-level parts.

### Improvement slices

- **2a · The isolation becomes an artifact** (boolean plan 4d): emit
  `{case}-{tooth}-scanned-cap.stl` per site — the matched-rung result — so the
  lab can inspect exactly what the scanner saw of the cap, outside our viewer.
  Small and additive; the caption's rung lands in the manifest note.
- **2b · Isolation stats in the digest**: triangle counts per rung
  (41,091 → 31,550 → 16,651 on tooth 20 was the live proof) so "how much
  tissue the cut removed" is a number the client can quote.

---

## Stage 3 — align, then perfect the alignment

### What we run today

Automation: multi-start ICP registration of the library cap at each detected
site (axis-cone seeds, trimmed point-to-plane), then per-site **instruments**
sealed into acceptance rows — position agreement, rotation from the coded band
(readability-gated), the recess-azimuth instrument as fallback, rim-centring
agreement (click-anchored, with a machine-anchored twin dual-reported), the
delivered channel. Statuses derive server-side; verdicts are the run's own.

Operator tooling: marks, point-pairs and best-fits persist as
`alignment_evidence` and re-apply across runs (§10-AD); receipts render on
Adjustment. The two §10-AT slices shipped:

- **A1 — the single-pair caution**: one pair fixes rotation exactly and can
  never disagree with itself; the drawer now says so instead of rendering
  honest silence that read as "fine" (the client's −120°/+8°/+1°/−2° loop on
  tooth 20 was this gap).
- **A2 — buried codes speak**: code band below its gates AND rotation standing
  on no evidence → the rotation row itself names the connection and the two
  honest paths (2+ pairs on visible features, or chairside re-capture).

### What the industry does

The standard flow is "3-point + best fit": the operator clicks three rough
correspondences, ICP refines, and the software reports a single RMS. Two
things it typically does NOT do, which we do: (1) decompose the fit into
per-degree-of-freedom instruments with their own evidence gates (rotation is
usually silently trusted to ICP even when the feature that determines it is
buried), and (2) persist operator evidence across re-runs. Our A1 caution is
the honest version of a cross-check the industry mostly skips.

### The perfection path (workstream B — every lever gated by `make verify-fleet`)

- **B1 · The scan-pivot experiment**: N clicks, one feature, one pose — to
  separate operator scatter from the measured pivot-parallax bias (ring offset
  0.25–0.38 mm ⇒ up to 14° azimuth error). If confirmed, scan azimuths
  re-anchor about the scan's own measured ring centre — a calibrated-fold
  change, done at the fold, never by rewriting old evidence.
- **B2 · Phantom arbitration** of the two rotation instruments (the
  designed-clock-angle rig): calibrate codes-vs-recess bias so two-instrument
  agreement becomes a truth-calibrated judgment.
- **B3 · Promote the machine-anchored rim metric** once phantom-checked; the
  click-anchored value stays dual-reported.
- **B4 · Codes-unreadable fallback**: rotation degrades to the recess
  instrument WITH its arbitrated bias bound, instead of "none".
- **Stage-2 feedback loop**: the isolation (Stage 2) directly improves pairs —
  clicks land on cap surface, not tissue contour (§10-AT A3).

---

## Stage 4 — putting the cap back: booleans, the variant choice, the unlock

### The flow, as the operator experiences it

1. **Alignment** declares each site: the variant chooser binds the site to a
   library cap (vendor/variant), whose dimensions come from CAD truth (bore
   from boundary loops — the G2 finding: vendor lumen destroys the part,
   cap-mouth radius is correct).
2. **Adjustment** runs; instruments seal; sites resolve (ready or flagged).
3. **Construction library UNLOCKS** when the run is DONE **and** every site is
   resolved (`domain/flow.ts` — the single home of stage reachability). The
   gate is real: an unresolved site means the pose is not certified, and a
   construction chosen over an uncertified pose would be a lie downstream.
4. **Delivery unlocks** when a construction part is chosen. A part change over
   a DONE run does NOT re-run — the re-emit lane (`emit_from_poses`) re-emits
   the package from the certified poses in ~1 s into a new immutable run dir.

### Where the booleans do the work

- **"Putting the cap back" is a true union** (§10-AT 3b,
  `arch_with_parts_fused`): solidify the arch (internal), union with each
  part posed as a zero-offset exact punch, strip the closure — an open-arch
  composite whose part-to-gum seams are real manifold seams, not
  interpenetrating shells. Volume-proved (~4.7 mm³ of buried overlap removed
  exactly). Fallback: concatenation with a per-row `composite_note` — which
  fired on a real scan on 2026-08-11 ("the solidified shell is not
  watertight"), making **W5 (open-shell robustness)** the next hardening
  target with a live reproduction case.
- **The recess** (the cap's absence) is the exact-cap difference
  (`cap_imprint_parts` → `_csg_carve`), and the **closed model** (artifact 6)
  is the same difference without the strip.
- **The hardening order** is the boolean plan's: W1 (provenance strip — the
  union composites' strip becomes identity-exact, retiring the 0.35 mm
  distance test), W2 (Minkowski offset — the gingival offset can no longer
  self-intersect), W5 (the watertight-shell failure above), inside Stage 0's
  seam + corpus.

### What the industry does

This is "library replacement + model builder": CAD suites place the library
part and their model creator cuts an implant-analog hole into a printed model.
Our artifact 6 is exactly the analog-model concept (drilled by exact boolean
instead of a parametric hole); our artifacts 1–5 are the part the industry
does NOT ship — the scan-truth open arch wearing the same certified geometry,
which is what makes the alignment inspectable rather than asserted.

---

## Stage 5 — the artifact set, and why each exists

Audience key: **D** = doctor (clinical verification), **L** = lab (fabrication),
**M** = machine (downstream CAD/print). Served sentences are the catalogue's
(`_ARTIFACT_SENTENCES`, §10-AT 4b) — one line each, rendered on the download
rows and in the digest.

| # | artifact | audience | why it is needed |
|---|---|---|---|
| 1 | `arch-with-healingcaps` | D | "the alignment made solid." The doctor's ONE verification: the green library cap must cover the scanned cap. If this composite is wrong, everything downstream is wrong — it is the checkable claim. |
| 2 | `arch-with-constructions` | D, L | the treatment's future state in situ: the chosen construction parts at certified poses, fused into the patient's own anatomy. The lab checks emergence and clearance against neighbours HERE, before fabricating. |
| 3 | per-site part STL (`-scanbody-…`) | L, M | the construction part alone, at its certified pose — importable into any downstream CAD without our viewer. The unit of fabrication. |
| 4 | `arch-capless` (dish) | L | the seat: each cap replaced by its exact recess with the 1.8 mm inspection dish. The lab inspects the seat surface the prosthetic will meet. |
| 5 | `arch-platform` | L | the countersink to the implant platform — the floor that SHOWS the gingival offset. This is the emergence-profile working view the client asked for by screenshot (2026-08-09). |
| 6 | `model-closed` | L | the printable lab model: solidified, based, every cap cut out exactly. The industry's analog model, built by exact boolean. Retired once, restored by client ruling 2026-08-11 — the lab wants the physical form. |
| — | `arch-socketless` / `socket-dish` / `socket-platform` | M (viewer) | preview layers: the tinted split of arch vs recess surfaces that lets the product paint the socket its own colour. Mechanism, honestly named as such. |
| — | `implant.json` | M | the certified pose record — matrix, identity, provenance. THE interoperability artifact: any external CAD can reconstruct everything above from the scan + library + this file. |
| — | QC renders (clock view, deviation map) | D, L | flat evidence for the record: rotation state and signed surface deviation as images that survive email, print and audit — no viewer required. |
| — | `manifest.json` | M | files, hashes, relief record, production notes — what the confirmation SEALS. Attestation lives here (boolean plan W4 makes the hashes deterministic). |
| — | `view.html`, scan echo | D | a standalone browser view of the package, and the doctor's scan exactly as uploaded — the untouched input, provable by bytes. |

The design rule behind the set: **every claim the product makes must have an
artifact the claimant can inspect without trusting us.** The alignment claim →
artifact 1; the fabrication claim → 3/4/5/6; the identity claim →
implant.json + manifest hashes; the evidence claim → QC renders. Nothing in
the list is decorative; each is the checkable form of one promise.

---

## Sequencing

1. **Now**: boolean Stage 0 (kernel seam + conformance corpus + env pin) —
   1–2 weeks, retires the unpinned-env risk, makes every later swap measurable.
2. **Then W1 + W5** (provenance strip; the watertight-shell failure has a live
   repro from 2026-08-11) and **W2** (Minkowski offset) — Stage 1's core.
3. **In parallel, product-side small slices**: 1a (serve discriminator
   evidence), 2a/2b (isolation artifact + stats).
4. **Then workstream B** in its measured order (B1 experiment → B2 phantom →
   B3/B4 promotions), each gated by `make verify-fleet` before/after.
5. **Then boolean Stage 2** (the three-kernel scoreboard) and the Stage 3
   decision.

Every slice: tests first; §10 ledger entry in the same commit; freeze line
checked; full battery + `make rehearse` before anything ships.
