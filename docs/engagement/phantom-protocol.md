# The Printed Phantom Protocol

*Companion to `apps/worker/tools/make_phantom.py` and `apps/worker/tools/evaluate_phantom.py`.
Every claim below maps to code in this repository and the generated artifacts under
`apps/worker/reports/phantom/` — nothing here is aspirational.*

## Why

The pipeline aligns healing-cap CAD templates to intraoral scans and reports, per site, a
confidence grade (`high` / `medium` / `low`) derived from how STABLE the seat is to plausible
operator click noise plus fit-quality signals. That grade discriminates the fleet correctly —
tight-clicking, well-fit sites read `high`; sloppy or ambiguous ones read `low` — but until now
it has never been checked against a pose error we *know* is correct, because every real case's
truth is itself the doctor's best guess.

A physical phantom closes that gap. We fuse real library healing caps into a printable plate at
**exactly-designed poses** — position, tilt and clocking are numbers we chose, not measurements.
The lab prints the plate and scans it exactly like a stone model. Because the poses are known
BY CONSTRUCTION, comparing the pipeline's shipped pose against the design file is a true
accuracy measurement, not a comparison against another guess. Resin printing holds roughly
±50 micron dimensional tolerance — an order of magnitude tighter than the 0.3–1.0mm accuracy
claims being validated — so the print itself is not the limiting factor (see "Truth-uncertainty
budget" below for the honest accounting of what is).

The plate also carries **three submergence levels** (exposed / half / deep — how much raised
"gum" material covers each cap's flank) because that is what makes the validation clinically
meaningful: real healing caps are frequently partially covered by soft tissue, and a validation
line built only from fully-exposed caps would not speak to the cases that matter most.

## What is on the plate

- A footprint of ~70×45mm, 12–18mm tall, flat-bottomed for printing, with a shallow curved
  ridge (comparable to a jaw-ridge cross-section) running its length.
- 6 healing-cap sites in two rows: Zimmer 4.5 (6020, 7030, 7020) and Neodent GM (6020, 6030,
  5030), each fused in at a known 4×4 pose — some upright (0° tilt), some tilted ~4–8°, and
  each with a **designed clock angle** (`clock_deg` in the ground truth: the template is
  rotated about its own canonical axis before placement; the six angles are spread across
  0–331° and avoid 90° multiples so a near-symmetric top face cannot alias them) — across
  all three submergence levels. Rotation is therefore ground truth by construction, exactly
  like position and tilt.
- 3 registration-fiducial posts of DIFFERENT height and diameter, plus one chamfered
  (cut-corner) 4th corner, so a scan in an arbitrary orientation can be brought back into the
  design frame unambiguously, with no other information.
- The generated ground truth (`phantom-ground-truth.json`) records every site's model,
  variant, submergence level, and exact pose in the design frame, plus the fiducial geometry.

## Print instructions

- **Process**: resin SLA/DLP, ~50 micron layer height. FDM is not accurate enough to be a
  meaningful truth reference at these tolerances.
- **Orientation**: flat face down (as designed — the plate's own bottom face IS the print
  bed face). No supports on the occlusal (top/ridge) face — that is where every measured
  feature lives; support scarring there would corrupt the truth.
- **Finish**: a glossy resin surface scans poorly (specular dropout). Use a matte gray resin,
  or apply scanning spray/powder to a glossy print before scanning. Do not sand, polish, or
  otherwise alter the occlusal face or the fiducial posts.
- The caps' internal screw-access bores are closed by the plate generator's boolean union —
  expected, and harmless for POSE validation: a surface scan can never see inside a bore
  either. One honest nuance for the ROTATION columns: the printed recess is the residual
  crater above that seal, shallower than a production screw channel, so the recess-void
  instrument reads the crater's centre. Its azimuth — the quantity the instrument actually
  ships — is still well-defined, so the codes-vs-recess comparison stands, with this caveat
  on the recess column's absolute quality.

## Scanning instructions

- Use the **same intraoral or lab scanner used in production cases** — the whole point is to
  validate the pipeline against the equipment it actually runs on.
- Capture the **whole plate in one scan** (or one stitched session) so every fiducial and every
  cap site is present.
- **Do not scan the flat bottom face.** Rest the plate on the scanner stage as you would a
  stone model and scan the top/sides only. This matters for two independent reasons: (1) a real
  intraoral scan is inherently single-sided, so a bottom-inclusive capture is not representative
  of production data; and (2) the pipeline's own crown-up-axis detection
  (`case_prep.adapters.cap_detection.crown_up_axis`) reads the mesh's dominant outward-normal
  direction to decide which way is "up" — on a fully-enclosed print (bottom included) the large,
  flat bottom face can compete with the top for that signal and occasionally flip the recovered
  axis 180 degrees. This was measured directly during protocol validation and is a real,
  documented characteristic of single-sided-capture assumptions baked into the shipped
  pipeline, not a phantom-generator defect — hence the scanning instruction, not a code change
  (`case_prep/` is production code and out of this task's scope).

## Running it

```bash
cd apps/worker

# 1. Generate the plate (once; print this)
.venv/bin/python tools/make_phantom.py \
    --out-dir reports/phantom --voxel-mm 0.15 --n-sites 6
# writes reports/phantom/phantom-plate.stl (watertight, ~45MB, ~450K vertices),
# phantom-ground-truth.json, and phantom-preview.png (a 3-view sanity render)

# 2. Evaluate a scan of the printed-and-scanned plate against that truth
.venv/bin/python tools/evaluate_phantom.py \
    --scan <path-to-scanned-phantom.stl> \
    --truth reports/phantom/phantom-ground-truth.json \
    --out-dir reports/phantom
# writes reports/phantom/phantom-evaluation.md and .json
```

By default the evaluator SYNTHESIZES the operator's marks from the truth file (a centre click
at each cap's designed top + 4 border clicks around its designed visible-rim boundary, jittered
by the measured 0.3mm operator click FLE, snapped to the actual scan surface) — this runs the
exact same code path a human operator's clicks would, so no manual clicking is required to get
a first read. Pass `--marks <marks.json>` (site_id -> `{"tooth", "center", "rim_points"}`, in
the scan's own coordinates) to evaluate real operator clicks instead.

## Reading the validation table

`phantom-evaluation.md` has two parts:

1. **Registration** — the residual (mm) of fitting the scan into the design frame. If this is
   large, treat the whole evaluation with suspicion (or check for a botched scan/print) before
   trusting any row below it.
2. **The confidence-validation table** — one row per site: the pipeline's confidence grade next
   to the TRUE pose error (centre distance in mm, split into in-plane vs along-axis/depth
   components, plus axis error in degrees, plus whether the identified variant matched what was
   declared). Below the table, the verdict lines answer the actual question this whole protocol
   exists to answer: does grade order track true error (Spearman correlation, when there are
   enough graded sites), and what is the worst true error actually seen within each grade
   bucket — e.g. *"on this phantom, 'high' bounded true error at X mm / Y deg."* That sentence,
   not any single row, is the deliverable.
3. **The rotation columns** — the phantom now validates ROTATION as well. Because every site's
   clock angle is designed (`clock_deg`), each row also reports the shipped pose's residual
   clock error as measured by BOTH production rotation instruments, plus which had evidence:
   - `clock_err_codes_deg` — the coded-feature reading (`domain/clock_signature`, the validated
     e8 extractor) at the shipped pose, against the designed angle;
   - `clock_err_recess_deg` — the recess-void bore-azimuth instrument (`auto_flow`'s
     `_screw_void_centre` / off-axis bore arm), same comparison;
   - `evidence` — `codes` / `recess` / `codes+recess` / `none`, using the production evidence
     gates.
   **Goal: ≤ 2° on exposed caps and ≤ 5° on half-submerged caps** (the commercial gold
   standard for rotational registration is 2–3°). Deep-submerged caps gate on evidence, not on
   a number: their collar reaches into the code band, and the extractor's honest refusal
   (`evidence: none` on codes) is the correct behavior there — a confident-but-wrong read is
   the failure mode to look for. This makes the phantom the physical arbiter of the
   codes-vs-recess instrument conflict (2026-07-20: the two disagreed on 5 of 7 fleet sites;
   on a rigid part they cannot both be right). On the simulated print-pitch scan the verdict
   is one-sided — coded reading 1.0–2.2° on every site with a visible code band vs 6.8–176°
   for the recess azimuth — but the PRINTED plate is what settles it.

## Honest caveats

- **Submerged sites are harder to validate tightly than exposed ones**, and the round-trip test
  in `tests/test_phantom.py` deliberately does NOT assert tight bounds on half/deep-submerged
  sites — only sanity bounds (catch a total failure, not measure accuracy precisely). The
  reason is real and worth stating plainly: a real cap CAD's cross-section is not a simple
  monotonic taper (coded anti-rotation features make it asymmetric, and the flare/neck profile
  is not always monotonic with height), and the production seat's pinned-depth resolution
  (`auto_flow._pinned_rim_seat` — "walk down from the top, stop at the first place still that
  wide") is measurably more sensitive to exactly where along that profile the visible tissue
  line sits. This is a genuine, now-documented characteristic of the shipped algorithm that the
  phantom surfaced — exactly the kind of finding this protocol exists to produce, not a phantom
  defect to be engineered away.
- **One shared construction part per evaluation run**: `evaluate_phantom.py` calls the real
  pipeline with `generate_product=False` (the final restoration/screw-channel build is skipped)
  because the phantom validates POSE ACCURACY and CONFIDENCE CALIBRATION, not the downstream
  construction step, which has its own, separate test coverage.
- **Declared-variant shipping path**: each site's TRUE variant is declared to the pipeline (the
  production "doctor's choice drives alignment" flow), matching how real cases ship. This means
  "identified-variant correctness" in the table is a data-plumbing sanity check, not a blind
  variant-identification test — blind identification is calibrated and tested separately
  against real labeled arches (`tests/test_auto_flow.py`).

## Truth-uncertainty budget

The ground truth is not zero-uncertainty; it is *far below* the accuracy being validated, which
is what makes it usable as a reference:

| Source | Typical magnitude | Notes |
|---|---|---|
| Print dimensional tolerance (resin SLA/DLP, ~50µm layer) | ~0.03–0.08mm | Manufacturer-typical for a well-calibrated printer; verify against your specific printer/resin. |
| Scanner trueness (intraoral / desktop lab scanner) | ~0.02–0.05mm (isolated feature), higher (~0.1–0.3mm) over a full-arch-sized stitch | Vendor-published trueness figures for the class of scanner used in production; the SAME scanner should be used here (see "Scanning instructions"). |
| Registration residual (this protocol's own fit) | Reported per run in `phantom-evaluation.md` | Abort threshold enforced by `evaluate_phantom.py`; a large residual invalidates that run's numbers, not the protocol. |

Summed in quadrature, the truth-uncertainty budget is on the order of a few hundredths to low
tenths of a millimeter — comfortably below the 0.3–1.0mm claims the confidence grades are being
validated against. Any true pose error reported by this protocol at the 0.5mm+ scale is real
pipeline behavior, not print/scan noise.
