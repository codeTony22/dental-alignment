# DG Code Real Data — First Run on a Real Certain 3i Case

**Files (client-provided, gitignored at `apps/worker/data/real/dg-code-test/`):** four STLs from a real **Certain 3i (4.1 mm platform)** abutment-alignment scan of an upper jaw —
three full-arch scans (`orig`, `final`, a copy; ~106–119k verts each, non-watertight) and the
**scan body segmented out** (3,968 verts, 8.1×7.6×5.1 mm) sitting in the same coordinate frame
at (26.9, −1.9, 0.1) — i.e. its real location is known.

This is the first time the pipeline touched **real manufacturer implant-scan data.** It both
worked and exposed exactly where the synthetic-tuned pipeline needs real-data re-work — the
point of the "run real cases" gate.

## What the data is (and isn't)

- ✅ A real arch with a real scan body in place, plus the scan body isolated → **ground-truth location**.
- ❌ No **clean library CAD** mesh (the 216 KB file is the *segmented* body — 100% coincident with the arch, ~0.01 mm — not a reference).
- ❌ No **scan-body → implant-platform transform** (the manufacturer spec needed to derive the actual implant pose from the scan-body pose).

## What ran, and what it revealed

1. **A real bug, found and fixed.** `register()` assumed the library mesh is in a canonical
   local frame (centred, axis +z — as the synthetic body is). The real segmented scan body is in
   **world coordinates** at x≈27, so registration sent it ~28 mm off-target (fitness 0). Added
   `canonicalize_library()` (centre + principal-axis align, returning the local→world placement) —
   now a required real-data ingest step, tested.

2. **After canonicalization, registration converges on real geometry:** fitness ~0.40,
   surface RMSE ~0.25 mm — but the recovered centroid lands **~2.4–4.3 mm off** the true location.
   Not clinical (target <0.1 mm). The chain *runs and locks to the surface*; it does not yet recover
   the pose accurately.

3. **Why the ~3 mm error (honest root causes):**
   - The Certain scan body is **chunky** (8×7.6×5 mm, PCA spread [1, 0.65, 0.33]), so the pipeline's
     "implant axis = tallest PCA direction" assumption — valid for a tall cylindrical synthetic body —
     **does not match the real implant axis.**
   - Registering the *segmented* body to its own arch region is a weak, near-self alignment (no clean
     CAD reference to lock against), and the ROI pulls in surrounding gingiva/teeth.

4. **Localization is brittle on a real upper-jaw arch** — the palate and teeth are themselves
   protrusions, so height/cluster detection can't isolate the scan body. Operator-seeding is required
   (the design's default), confirmed again.

## Verdict (truthful)

The foundation is sound — the chain ingests real STLs, canonicalizes, and **converges** on a real
Certain scan body. But **clinical accuracy on real data is not yet there**, and the gap is
specific and addressable, not mysterious. This concretely validates the plan-grilling finding #3:
*synthetic-calibrated geometry/axis assumptions do not transfer to real manufacturer scans.*

## Concrete next steps (what real accuracy requires)

1. **Obtain the clean Certain 3i scan-body library CAD** (canonical frame) — the named hard
   dependency. Register that to the scanned body, not the segmented self.
2. **Use the library's axis convention** (the implant/screw axis from the CAD), not PCA-of-blob.
3. **Obtain the scan-body → platform transform** to derive the real implant pose.
4. **Tighten the ROI** to the body (exclude gingiva/teeth) and **re-calibrate the gate thresholds**
   against real ground truth.
5. Until then: operator-seed + **shadow/advisory mode** (compute, always route to human, log what it
   *would* have passed) — never auto-seed real cases on synthetic-tuned thresholds.

These four data/spec items (clean CAD + axis + platform transform + a labelled real set) are the
gate to real clinical accuracy — and they are sourcing/spec tasks, not open research.
