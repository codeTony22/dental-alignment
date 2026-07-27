# Healing-Cap Template Alignment: Industry & Literature Survey

*Prepared 2026-07-14. Grounded against the current implementation in
`apps/worker/src/case_prep/pipeline/auto_flow.py` (`_rim_seat`, `_fit_circle_3d`,
`_pinned_rim_seat`, `_refine_best_fit`, `_best_clocking`) and
`apps/worker/src/case_prep/domain/icp.py` (in-house trimmed point-to-point ICP).
All claims were adversarially verified where possible; verdicts and corrections are in
the appendix (section 7). Claims that failed or partially failed verification are marked
inline with ⚠.*

---

## 1. Executive summary

Our centre-click + multi-rim-click seeding is already **richer than every shipped commercial
baseline** (exocad: one click + best-fit; Blue Sky Plan: one click + manual widget; Medit:
zero clicks but human-assigned variant), and the rim-circle closed-form + trust-region
best-fit is exactly the industry's registration-points-then-best-fit pattern. No surveyed
vendor infers the library **variant** from scan geometry — variant identity is universally
upstream human metadata, so our calibrated catalog search exceeds shipped state of practice,
and height-twin ambiguity (mode d) is an *observability* limit no optimizer can cross.
The literature's fixes map cleanly onto our failure modes: GNC/robust weighting over the
border clicks (mode a); Fitzpatrick TRE-conditioning of click geometry + constrained
residual-DoF search (mode b); symmetric-objective ICP, normal-space sampling and
localizability gating (mode c); and BOP-style visible-surface equivalence-class scoring
plus metadata tie-breaks (mode d). The single most important metrology warning: our fit
residuals and surface-agreement scores are FRE-like surrogates that are **provably
uncorrelated with true pose error** — the benchmark must score 6-DoF pose deviation
against independent ground truth, never the objective being optimized.

---

## 2. What the dental industry actually does

### exocad (DentalCAD)

The implant-position wizard displays a red reference point on the **library** scan abutment;
the operator clicks the corresponding position on the scan data, then presses *Best fit
matching* ([wiki: Matching the scan abutments](https://wiki.exocad.com/wiki/index.php/Matching_the_scan_abutments)).
The underlying *Align Meshes* best-fit exposes two robustness controls — a **Matching parts
ratio** slider (assumed overlap fraction) and a **Maximum influence distance** slider (capped
correspondence distance) — plus a *Show distance* residual colour scale, and warns "Only use
best-fit matching when you have identically shaped meshes"
([wiki: Align Meshes](https://wiki.exocad.com/wiki/index.php/Align_Meshes)). Those are the
signature knobs of trimmed/robust ICP (the wiki never names the algorithm — that label is
inference, corroborated by peer-reviewed descriptions of exocad best-fit as ICP). A 2024
study of exocad v3.0's one-point + best-fit flow measured 3D implant-position error of
84±132 µm (Medentika) / 94±103 µm (NT-Trading) for the automatic flow vs 21±11 / 35±13 µm
for a **separate fully-manual arm** (⚠ not a "correction pass on top", as sometimes
summarized) — the large SDs mean the automatic flow *occasionally*, not routinely, lands far
off, and the study authors (not the vendor) conclude manual verification is essential
([Kropfeld et al., Dent J 12(4):94, 2024](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11049057/),
[MDPI](https://www.mdpi.com/2304-6767/12/4/94)).

### 3Shape

Dental System ships **both 1-point and 3-point** scan-body alignment. A 2023 in-vitro study
(Dental System 2019) found 3-point significantly better **only** in the submerged regime
(1/3 of scan body exposed) **and** specifically when the scan-body image was also deficient:
linear 0.084±0.068 mm (1-point) vs 0.013±0.005 mm (3-point), angular 0.237±0.059° vs
0.162±0.040°; with an intact scan image at 1/3 exposure the modes were equivalent
(⚠ this conditioning on image deficiency is often dropped when the study is cited)
([Petchmedyai & Thanasrisuebwong, PLoS One 2023](https://pmc.ncbi.nlm.nih.gov/articles/PMC10513296/)).
The authors recommend 3-point alignment for deep implants and warn that modifying scan
bodies breaks software recognition. Implant Studio additionally markets click-free "implant
detection" that matches a (human-pre-assigned) library scan body
([3Shape Implant Studio](https://www.3shape.com/en-us/software/implant-studio)) — existence
proof only; no algorithmic description is public.

### Medit

Once the operator assigns a library part to a tooth number, the scanner "automatically
attempts to align the library … to the acquired scan data" during scanning, with a
post-alignment deviation colour map; the manual fallback is 1-3 clicked points (⚠ the claim
that you can click a point to read a numeric deviation is *not* in Medit's cited doc)
([Medit: Scan Body Library Matching](https://support.medit.com/hc/en-us/articles/360033527711--Scan-Body-Library-Matching)).
A 2025 BMC Oral Health study measured Medit Link's 3-point+AI protocol at 0.0516 mm /
0.3707° vs exocad one-point best-fit at 0.0597 mm / 0.4839°
([BMC Oral Health, 10.1186/s12903-025-07581-z](https://link.springer.com/article/10.1186/s12903-025-07581-z)).
The best published fully-automatic IOS result — Medit i900 "Smart X", mean 13.55±9.70 µm
full-arch — was achieved **only with purpose-built "Scan Ladder" scan bodies** with
irregular, non-repetitive geometries; the paper credits that geometry with enabling AI
recognition, was never ablated against plain scan bodies, and its lead author invents/sells
Scan Ladder (⚠ declared COI; "asymmetric" is a paraphrase — the paper says
irregular/non-repetitive) ([Nulty et al., Dent J 13(11):533, 2025](https://pmc.ncbi.nlm.nih.gov/articles/PMC12650994/)).
**Auto-detection success does not transfer to smooth near-revolute submerged caps.**

### Dental Wings (coDiagnostiX)

The IFU codifies landmark-pairs-then-automatic-surface-registration with explicit
click-geometry rules: landmarks "should not lie on an (approximately) straight line and
must be set at anatomically significant positions and as far away from each other as
possible", then "Perform automatic surface registration", then "Thoroughly check the
congruency of the contours … in all views"; manual 4-view alignment is the fallback
([coDiagnostiX 9 IFU EN v6.0, §4.1](https://ifu.dentalwings.com/ifu/codiagnostix/archive/coDiagnostiX_9_IFU_EN_v6.0.pdf)).
This is vendor-documented **input validation on click geometry** — exactly what our
partial-arc gates do.

### Blue Sky Plan / 3DIEMME RealGUIDE / Straumann

Blue Sky Plan: one click on the scanned abutment head at the red-marker position, catalog
best-fit, then manual 3D-widget cleanup; no numeric registration-error dialog for this step
([BS-LS-0161 Rev 1 manual, §12](https://blueskybio.com/caffeine/uploads/files/documents/BS-LS-0161_Blue-Sky-Plan-User-Manual-Rev1-2019-12.pdf)) —
the industry floor. RealGUIDE's documented registration is fiducial-based (radiopaque
3DMarkers) rather than scan-body best-fit
([RealGUIDE procedure manual](https://www.3diemme.it/gallery/en-realguide-procedure-manual.pdf)):
when geometry is uninformative, industry adds engineered markers. Straumann's patent
[WO2010091868A1](https://patents.google.com/patent/WO2010091868A1/en) derives scan-body pose
by fitting **planes to flat faces** (χ²-fit named as example), intersecting them into
lines/points, and solving pose from over-constrained intersection information — "any point
within a planar area can be used", no corners/edges needed. That is the patent-grade version
of "fit stable primitives from many surface points, not from a handful of clicks".

### Clinical field data

A 2025 retrospective cohort of **243** scan bodies (⚠ not 172 as first circulated) in
clinical TRIOS3 scans found the dominant defect is scan **representation** quality, not
coverage: 44.4% roughened texture, 16% impaired geometry, vs 97.5/92.6/100% coverage of
reference-area/body/base; featureless cylindrical (PEEK) parts, mandibular sites and
single-tooth cases carried the highest risk
([Boz & Akça, Clin Implant Dent Relat Res 2025](https://pmc.ncbi.nlm.nih.gov/articles/PMC11841021/)).
Low-feature cylindrical parts — the closest analog to our caps — are the known worst case
for commercial best-fit.

### Variant identification

No surveyed system infers **which** library variant is present from scan geometry: exocad's
library pick precedes matching (in the CAD wizard), Medit's library is assigned per tooth
number, Blue Sky Plan's part is chosen from the catalog first
([exocad DentalDB](https://wiki.exocad.com/wiki/index.php/First_step_-_choose_implant_type_for_construction_in_DentalDB),
[Medit](https://support.medit.com/hc/en-us/articles/360033527711--Scan-Body-Library-Matching),
[BSP manual](https://blueskybio.com/caffeine/uploads/files/documents/BS-LS-0161_Blue-Sky-Plan-User-Manual-Rev1-2019-12.pdf)).
Our calibrated catalog search is **novel relative to shipped products**, and resolving
height-twins via workflow metadata is industry-standard practice, not a cop-out.

---

## 3. Algorithm landscape mapped to our four failure modes

### (a) One outlier border click tilts the fitted circle

**What addresses it**

- **Robust circle fitting — RANSAC / IRLS / leave-one-out** ([survey](https://arxiv.org/pdf/2508.03720)):
  minimal-subset or reweighted fits over the 3-6 clicks. We already do a scan-arbitrated
  leave-one-out (`_fit_circle_3d` + `_border_click_disagreement`), which is the right family;
  the literature's upgrade is *soft* weighting rather than binary drop-or-keep.
- **Graduated non-convexity (GNC)** ([Yang et al., RA-L 2020](https://arxiv.org/pdf/1909.08605)):
  wrap the circle fit in GNC over per-click weights (Geman-McClure/TLS, annealed µ). One
  outlier click is annealed to zero weight instead of tilting the plane; the clicks are
  never mutated, so it respects the re-click pair-integrity constraint. Tolerated 70-80%
  outliers on registration without an initial guess.
- **Anisotropic per-landmark weighting** ([Danilchenko & Fitzpatrick](https://pmc.ncbi.nlm.nih.gov/articles/PMC4607070/)):
  weight each click by the inverse-sqrt of its FLE covariance. A rim click on a gingival
  slope has large *radial* uncertainty and tight tangential uncertainty — anisotropic
  weighting down-weights exactly the direction the over-shot click is unreliable in.
- **Hybrid point+surface joint objectives** ([Maurer et al. WGF](https://pubmed.ncbi.nlm.nih.gov/9874299/)):
  a strong surface term can pull the pose back against a weak/outlying click.
- **Primitive fits from surface points, not clicks** (Straumann
  [WO2010091868A1](https://patents.google.com/patent/WO2010091868A1/en)): estimate the
  top plane / rim ring from hundreds of RANSAC-able band points; clicks only gate the ROI.
  Our `_rim_seat` band fit already does a version of this; the pinned seat does not.
- **Masuda-style adaptive rejection inside ICP** (2.5×MAD gate + normal compatibility,
  [Rusinkiewicz 2019](https://pixl.cs.princeton.edu/pubs/Rusinkiewicz_2019_ASO/symm_icp.pdf))
  stops a click-induced bad seed being *reinforced* by the refinement.

**What does not**: plain Kasa least-squares (splits one click's error across all points —
the measured 0.89 mm-out click reading 0.206 rms is textbook); whole-fit RMS gates
(same reason); any FRE-style residual threshold (see mode-independent warning in §6).

### (b) Partial rim arcs under-constrain the pose

**What addresses it**

- **Fitzpatrick TRE prediction from landmark configuration**
  ([Fitzpatrick & West, IEEE TMI 1998](https://pubmed.ncbi.nlm.nih.gov/9874293/),
  [distribution paper](https://www.researchgate.net/publication/11764825_The_Distribution_of_Target_Registration_Error_in_Rigid-Body_Point-Based_Registration)):
  expected TRE² is a closed form in click count, spread along principal axes, and target
  distance from the click centroid. A partial arc = clustered fiducials = predictably high
  axis-tilt TRE. Computable *before* fitting → operator advisory ("add a click on the far
  side"), exactly the coDiagnostiX IFU pattern made quantitative.
- **Auto-estimated trimming** (TrICP ψ(f) golden-section, [Chetverikov et al. 2005](https://www.sciencedirect.com/science/article/abs/pii/S0262885604001179);
  FRMSD, Phillips 2007; best-in-class per [Babin et al., ICRA 2019](https://arxiv.org/pdf/1810.01474)):
  unknown per-site overlap (visible fraction varies with submergence) is estimated per
  iteration instead of the fixed `trim_fraction=0.85` we hard-code in `_refine_best_fit`.
- **Normal-space sampling** ([Rusinkiewicz & Levoy 2001](https://www.cs.princeton.edu/~smr/papers/fasticp/fasticp_paper.pdf)):
  the visible cap is an "incised plane" — dominant flat top + thin rim wall. Uniform
  sampling lets the top face dominate and the pose slide; bucketing by normal forces
  rim-wall points into the correspondence set, constraining axis and lateral position.
- **Localizability analysis / X-ICP** ([Tuna et al.](https://arxiv.org/pdf/2211.16335)):
  eigen-analysis of the ICP normal matrix detects which DoF are under-constrained and locks
  them to the click prior instead of letting the optimizer invent values.
- **Constrained residual-DoF search** ([GMOR decomposition](https://arxiv.org/html/2508.17427v1),
  [constrained ICP](https://github.com/mrlooi/constrained_icp)): once the axis is trusted,
  only search the 2-4 residual DoF (tilt cone × height × clocking) densely — an
  under-constrained DoF then shows up as a flat score valley you can *report* rather than
  a silent arbitrary pick.

**What does not**: more ICP iterations (the missing constraint isn't in the data);
1-point seeding (the 3Shape study's deep-implant result); fixed trim ratios (Babin:
environment-dependent optima generalize worst — a fixed ratio breaks across visibility
levels, which *is* mode (b) in disguise).

### (c) Unconstrained ICP wanders into wrong basins

**What addresses it**

- **Trust region + monotonic acceptance** — what we already ship (`_refine_best_fit`,
  ≤1.2 mm/≤8°). Directly analogous to exocad's max-influence-distance + overlap-ratio and
  the ~≤10° practical ICP capture range ([Go-ICP preprint](http://jlyang.org/tpami16_go-icp_preprint.pdf)).
- **Symmetric ICP objective** ([Rusinkiewicz, SIGGRAPH 2019](https://pixl.cs.princeton.edu/pubs/Rusinkiewicz_2019_ASO/symm_icp.pdf)):
  point-to-plane converges faster but has a *narrower* basin than point-to-point (Mitra
  2004); the symmetric objective gets higher convergence order AND a wider basin at
  point-to-plane cost; LM-symmetric had the widest basin of 8 variants **at 20 iterations**
  (⚠ at 500 iterations two-plane is marginally wider — verified nuance). Bonus: the
  symmetric metric is exactly zero for pairs consistent with any constant-curvature
  surface, so the cap's unobservable axis-spin is left unpenalized while rim curvature
  (the diameter signal point-to-plane discards) still constrains the fit.
- **Well-tuned robust kernels** ([Babin et al.](https://arxiv.org/pdf/1810.01474)):
  Cauchy+MAD or adaptive trimming; redescending kernels (Welsch/Tukey/GM) are *worse than
  L2* when scale is under-estimated — never ship a hand-tuned aggressive kernel; anneal
  scale via GNC if using one.
- **Hypothesis generation + calibrated arbitration**: multiple seeds (leave-one-click-out
  circles, coarse residual-DoF grid), each polished by trust-region ICP, arbitrated by the
  calibrated score — the literature-consistent middle ground between one local run and
  full global search. Drost-style final "re-score by visible-surface-explained"
  ([PPF voting](https://arxiv.org/pdf/1808.08319)) is the industrial version of our
  symmetric score arbiter.
- **Go-ICP as offline oracle** ([Yang et al., TPAMI 2016](https://arxiv.org/abs/1605.03344)):
  certified global optimum of the trimmed L2 cost, run on the click-cropped ROI with a
  shrunk search cube. Separates "local method fell in the wrong basin" from "the global
  optimum itself is wrong/ambiguous". Not production: 15-30 s/case, trim fraction must be
  hand-set, and with the wrong trim it certifies a wrong basin — a certificate attaches to
  the objective, not to correctness.

**What does not**: the entire correspondence-robust global family — **TEASER++, RANSAC+FPFH,
Fast Global Registration, 4PCS/Super4PCS, PPF voting as primary solver**. A 6 mm smooth
near-revolute cap showing a top face + partial rim yields essentially zero distinctive
true-inlier feature matches; the failure "is not a correspondence outlier problem but an
absence of true inliers problem", which robust solvers cannot fix
([TEASER++](https://arxiv.org/abs/2001.07715), [degeneracy field study](https://arxiv.org/pdf/2408.11809),
[FGR](http://vladlen.info/papers/fast-global-registration.pdf),
[Super4PCS ≥25% overlap validity](https://geometry.cs.ucl.ac.uk/projects/2014/super4PCS/)).
This rules out a large branch of the design space; their headline robustness numbers do not
transfer.

### (d) Height twins are physically indistinguishable when submerged

**What addresses it**

- **Nothing algorithmic — it is an observability limit.** Continuous rotational symmetry
  and occluded distinguishing geometry make some DoF/hypotheses carry zero geometric
  evidence; symmetry-aware pose literature models the ambiguity explicitly rather than
  letting a scored search silently pick
  ([cylindrical CAD-to-scan](https://arxiv.org/pdf/2405.10557),
  [symmetry-aware survey](https://link.springer.com/article/10.1007/s00138-024-01657-6)).
- **Industry practice**: variant identity is upstream metadata everywhere (§2); RealGUIDE's
  lesson is that when geometry is uninformative you change the part or add a marker.
- **Correct engineering responses**: (i) report the twin *pair* with a confidence tie and
  route to the doctor (our "too-close rule" already does this — keep it); (ii) score twin
  cases as "correct-set" in benchmarks, per BOP's VSD "indistinguishable poses are
  equivalent" doctrine ([BOP metrics](https://arxiv.org/pdf/2009.07378)); (iii) isolate the
  ambiguity to the one DoF it lives in — translation along the axis — via constrained
  search, and let the 2× above-gingiva term extract whatever partial evidence exists;
  (iv) Go-ICP twin-tie certification: if the global optimum scores both twins equally,
  no registration algorithm can separate them — documentable proof for the client.

**What does not**: better optimizers, wider basins, certificates, deep features — all
answer "which pose best explains the data", not "is the data informative".

---

## 4. Where our pipeline already matches industry practice — and where it diverges

### Matches (be honest: this is the standard pattern)

| Ours | Industry equivalent |
|---|---|
| Centre + rim clicks → closed-form seat → `_refine_best_fit` | The universal registration-points-then-best-fit flow (exocad, 3Shape, BSP, coDiagnostiX §2); our multi-click seeding is *richer* than exocad/BSP's single click and matches 3Shape's recommended 3-point mode for deep implants |
| Trust region (≤1.2 mm/≤8°) + `max_corr_dist=1.0` + `trim_fraction=0.85` in trimmed ICP | exocad's Maximum-influence-distance + Matching-parts-ratio sliders — the same two robustness knobs, ours hard-coded, theirs exposed |
| Arc-bin / seating-cone / one-sided-clicks refusal gates | coDiagnostiX IFU click-geometry rules (no near-collinear, spread far apart) — we enforce programmatically what their IFU asks the human to do |
| `_rim_agreement_mm` p90 read-out, reporting-only | exocad/Medit residual colour maps as human verification aids, never auto-gates |
| Human confirm before anything ships | exocad-study conclusion that verification of automatic matching is essential |
| Rim band fit from *surface points* with inlier pruning (`_rim_seat`) | Straumann's fit-primitives-from-many-points doctrine |

### Divergences

- **Ahead of industry**: calibrated variant identification from scan geometry (nobody ships
  it); symmetric two-term score penalizing claimed-but-unseen surface (Drost-style
  visible-surface re-scoring, which vendors only use for pose, not identity); pinned-seat
  contract checks; scan-arbitrated outlier-click hypothesis handling.
- **Behind the literature**: (1) the pinned seat trusts the clicked circle *rigidly* —
  no soft fusion of click and surface evidence (WGF/ECPD joint objectives); (2) point-to-point
  inner ICP objective — symmetric/point-to-plane with normal gating is a known basin/accuracy
  upgrade; (3) fixed trim fraction instead of auto-estimated overlap; (4) no
  quantitative click-conditioning (TRE prediction) — our gates are binary refusals, not
  graded advisories; (5) no independent QA metric — the seat residual and agreement score
  are FRE-like and provably non-predictive of pose error (§6); (6) single-hypothesis
  polish rather than a small multi-seed hypothesis set arbitrated by the calibrated score
  (we have this only for the 2-circle outlier case).
- **Deliberate, defensible divergence**: refusing free 6-DoF ICP as primary solver. The
  literature (basin studies, degeneracy analyses, exocad's "identical shapes only" warning)
  says we are right; the fallback multi-start trimmed ICP should remain a fallback.

---

## 5. Benchmark candidate set

All candidates are numpy/scipy-only (Open3D `registration_icp` segfaults on this host;
in-house implementations only). Baseline = current pipeline (closed-form rim seat / pinned
seat + `_refine_best_fit` trust-region trimmed point-to-point ICP).

| # | Candidate | Targets | Expected win | Expected cost | Implementation notes (numpy/scipy) |
|---|---|---|---|---|---|
| 1 | **GNC-weighted rim-circle fit** (Geman-McClure/TLS weights per click, annealed µ; anisotropic per-click covariance optional) | (a), reports into (b) | Outlier click down-weighted to ~0 instead of tilting the axis; smoother than the current binary drop/keep two-hypothesis machinery; clicks never mutated (pair-integrity safe) | ~1 day; microseconds per fit | Alternate weighted plane+Kasa fit (closed form, reuse `_fit_circle_plane` with weights) with closed-form GM weight update; anneal µ from large→1 over ~10 steps. Keep the scan-hug arbitration as final check |
| 2 | **Joint click+surface objective (WGF-style)**: minimize w_clicks·Σ‖clicks−ring(pose)‖² + w_surf·trimmed surface term over 6-DoF, clicks weighted by Fitzpatrick-style anisotropic covariance | (a), (b) | Surface evidence pulls back against a weak click; graceful degradation on partial arcs instead of hard refusal; the literature's canonical hybrid ([Maurer WGF](https://pubmed.ncbi.nlm.nih.gov/9874299/)) | ~2-3 days | `scipy.optimize.least_squares` (LM/TRF) over 6 params (axis-angle + t); click residuals to the template's silhouette ring at clicked radius; surface residuals via per-variant precomputed KD-tree or SDF grid. Warm-start from current seat |
| 3 | **Constrained residual-DoF dense search over precomputed per-variant SDF** (PLuM/LM-ICP architecture: Gaussian reward or robust distance from a lookup table; enumerate tilt-cone ×2, height ×1, clocking ×1 around the seed; joint over ~6 variants) | (b), (c), isolates (d) to 1 DoF | No local minima at all inside the searched region — replaces trust-region *hoping* with exhaustive *knowing*; pose and variant become one argmax; flat score valleys become reportable ambiguity ([PLuM](https://pmc.ncbi.nlm.nih.gov/articles/PMC10054539/), [LM-ICP](https://www.sciencedirect.com/science/article/abs/pii/S0262885603001835), [GMOR decomposition](https://arxiv.org/html/2508.17427v1)) | ~3-4 days; SDF grids precomputed offline per variant (~0.1 mm voxels over a 12 mm cube ≈ 1.7M floats each); runtime ~10⁴ poses × O(patch) trilinear lookups ≈ interactive | Build SDF per template once with `scipy.ndimage.distance_transform_edt` on a voxelized mesh (or KD-tree distances to dense samples); score = mean robust ρ(SDF(patch under pose⁻¹)) + calibrated above-gingiva term. Grid: tilt ±10° (2 DoF, ~5° steps refined to 1°), height ±3 mm (0.1 mm), clocking 24 steps |
| 4 | **Symmetric-objective ICP with Masuda rejection + normal-space sampling** as the `_refine_best_fit` inner engine (replaces point-to-point Kabsch) | (c), helps (b) | Wider basin at same cost ([Rusinkiewicz 2019](https://pixl.cs.princeton.edu/pubs/Rusinkiewicz_2019_ASO/symm_icp.pdf)); leaves axis-spin unpenalized while using rim curvature; normal-space sampling stops top-face domination ([Rusinkiewicz & Levoy 2001](https://www.cs.princeton.edu/~smr/papers/fasticp/fasticp_paper.pdf)); adaptive 2.5×MAD gate + normal-compatibility rejects buried-gum correspondences | ~2 days | Needs patch normals (we have `Ln`) and template normals (trimesh face normals at samples). Linearized symmetric objective is a 6×6 solve per iteration (`np.linalg.lstsq`); rotate-by-half trick per paper. Bucket template samples by normal into ~26 bins, sample uniformly across buckets. Keep trust region + monotonic accept unchanged |
| 5 | **Localizability gate (X-ICP-style)**: eigen-decompose the 6×6 ICP normal matrix at the seed; lock DoF whose eigenvalue is below threshold to the click prior; solve only well-conditioned DoF | (b), (c) | Turns silent under-constraint into a measured, per-DoF diagnosis; refinement can never move along a direction the data does not constrain ([X-ICP](https://arxiv.org/pdf/2211.16335)) | ~1-2 days; negligible runtime (one 6×6 eigendecomposition per iteration) | Build J from point-to-plane residuals (needs normals); `np.linalg.eigh` on JᵀJ; project the update step off low-eigenvalue subspace. Also emit the eigen-spectrum as a per-site conditioning report (pairs naturally with candidate 6) |
| 6 | **Fitzpatrick TRE predictor as click-quality advisory + benchmark covariate** (not a pose solver) | (a) warning, (b) gating | Principled, closed-form pre-fit prediction of pose error from click geometry; replaces binary arc-bin refusals with a graded mm-scale advisory the operator can act on; per the FRE/TRE theorem it is the *only* valid click-derived confidence ([Fitzpatrick 1998](https://pubmed.ncbi.nlm.nih.gov/9874293/)) | ~0.5-1 day; trivial runtime | Closed form: TRE²(target) ≈ FLE²/N · (1 + ⅓Σ d²ₖ/f²ₖ) over principal axes of the click configuration; target = implant platform centre at depth. Calibrate FLE from operator re-click spread on the 4 labeled arches |
| 7 | **Constrained trimmed BnB oracle (Go-ICP style, offline only)**: branch over tilt-cone (2 DoF) × height (1 DoF) with Lipschitz bounds on the SDF score; certified argmax within the clicked ROI | (c) diagnosis, (d) certification | Per-case certificate "the production seat is/is not the global optimum of its own score in the trusted region"; twin-tie certificates prove observability limits to the client ([Go-ICP](https://arxiv.org/abs/1605.03344), [Hartley & Kahl](https://users.cecs.anu.edu.au/~hartley/Papers/PDF/HartleyKahl:Ematrix.pdf)) | ~3 days; seconds-to-minutes per case, offline benchmark harness only | 2-3 branched dims only (never 6); interval bounds from SDF Lipschitz constant 1; reuse candidate 3's SDF grids. Not a production stage |

Recommended build order: **6 → 1 → 4 → 3 → 5 → 2 → 7** (cheapest diagnostics first; 3 is
the likely architectural end-state; 2 and 7 are comparison arms).

---

## 6. Recommended benchmark protocol

**Vocabulary** (ISO 5725 via [dental accuracy literature](https://pmc.ncbi.nlm.nih.gov/articles/PMC9103333/)):
report **trueness** (vs ground truth) and **precision** (spread under input perturbation,
no truth needed) as separate tracks.

**Ground-truth sources (what we have)**
1. *4 labeled doctor-cap arches with known variant* — trueness track for variant ID and
   pose plausibility; the variant label is authoritative, pose truth is approximate.
2. *Curated sites on 10 real cases* — paired-comparison track: no absolute truth, but every
   algorithm sees the identical scan + identical clicks, and expert-accepted seats define
   a reference pose.
3. *Place-and-recover synthetic protocol* — the only source of exact pose truth: place a
   known variant at a known pose in a real arch (boolean into gingiva at controlled
   submergence), re-sample with scanner-like noise, derive clicks programmatically. Follow
   the field-data corruption profile ([Boz & Akça](https://pmc.ncbi.nlm.nih.gov/articles/PMC11841021/)):
   inject surface roughening at ~44% incidence and local geometry impairment at ~16%, not
   just occlusion; control exposed fraction (1/3, 2/3, full — the
   [3Shape study design](https://pmc.ncbi.nlm.nih.gov/articles/PMC10513296/) is a ready-made
   template) and deficiency location. If physical validation is later demanded, the
   standard rig is reference desktop/industrial scanner or CMM truth
   ([CMM protocol](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7844289/)).

**Perturbation design** (Pomerleau/Babin/Rusinkiewicz protocol,
[Pomerleau 2013](https://link.springer.com/article/10.1007/s10514-013-9327-2),
[Babin 2019](https://arxiv.org/pdf/1810.01474)): for each site, sample many controlled
perturbations of the inputs — click jitter at calibrated FLE, **synthetic single-outlier
clicks** (0.5-2 mm past the rim on the slope: mode a), **truncated rim arcs** (drop clicks
to leave 90°/120°/180° sectors: mode b), and pose-seed perturbations on a
(rotation × translation) grid. Report **success-rate heatmaps** over perturbation magnitude
and **cumulative error distributions / quantiles — never means** (heavy-tailed,
asymmetric distributions).

**Metrics** (per site, per algorithm)
- **Axis angle error (deg)** and **centre error (mm, split in-plane vs along-axis)** —
  6-DoF pose deviation, the readout that cannot be gamed by a good-looking surface RMS
  ([per-element 6-DoF deviation](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8898215/)).
- **ADD-S** (closest-point variant, correct for revolute parts,
  [BOP](https://www.researchgate.net/publication/328113519_BOP_Benchmark_for_6D_Object_Pose_Estimation))
  as the single-number headline; threshold anchored to clinical tolerance (start at the
  scan-body literature's <100 µm/<0.5° as aspiration,
  [CMM studies](https://pubmed.ncbi.nlm.nih.gov/36288490/), recalibrated for the submerged
  regime).
- **Rim-band p90 (mm)** — keep `_rim_agreement_mm` as the doctor-facing readout, but never
  as the benchmark's accuracy metric.
- **Variant identification accuracy**, scored **correct-set** for height twins (BOP VSD
  doctrine: visible-surface-indistinguishable poses are equivalent,
  [BOP metrics](https://arxiv.org/pdf/2009.07378)) — twins count as correct if the true
  variant is in the reported tie-set AND the tie is flagged.
- **Registration recall** at threshold (fraction of runs with rotation AND translation
  under tolerance, [Fontana 2021](https://www.sciencedirect.com/science/article/abs/pii/S0921889021000191)) —
  measures wrong-basin behaviour (mode c) as a rate, which means mask.
- **Refusal accounting**: refusals are neither free nor fatal — report the
  (refused, wrong-and-confident, right) triple; a method that refuses mode-b cases beats
  one that confidently mis-seats them.

**Statistics**: paired per-site comparison (identical scan + clicks + seeds for every
algorithm), Wilcoxon signed-rank, headline **median + p90/p95 + max**
([non-normal dental error distributions](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7921766/)).

**Three hard rules** (each verified in §7):
1. **Never score with the objective being optimized** — surrogate similarity scores are
   provably foolable ([Rohlfing's CURT](https://pmc.ncbi.nlm.nih.gov/articles/PMC3274625/));
   a wrong-basin pose that "explains ridge walls" is exactly a CURT-style false positive.
2. **Never report fit residual as accuracy** — FRE and TRE are uncorrelated to first order
   ([Fitzpatrick](https://pubmed.ncbi.nlm.nih.gov/9874293/)); measure error at independent
   targets (implant platform centre at depth, unclicked top-face points).
3. **Include the oracle arms**: a "human nudge" upper bound (operator correction after
   auto-seat, mirroring the exocad study's manual arm) and the Go-ICP/BnB certified arm
   (candidate 7) to separate optimizer failure from objective/observability failure.

---

## 7. Verified-claims appendix

Verdicts from adversarial verification (primary-source fetch + refutation attempts).
**Confirmed** = all load-bearing facts check out against cited sources. **Plausible** =
core holds but a stated detail was wrong or unverifiable (correction noted). **Refuted
details** are called out explicitly. Claims 11+ were not put through the verification pass
and are marked accordingly.

| # | Claim (short) | Verdict | Corrections / notes |
|---|---|---|---|
| 1 | exocad one-click + best-fit; 84±132/94±103 µm auto vs 21±11/35±13 µm manual | **Confirmed** | Red point is on the *library* part in the wizard, not physically on the scanned part; manual figures are a **separate manual arm**, not a correction pass; "routinely lands off" overstated — *occasionally* (large SDs); verification is study advice, not vendor mandate; the two citations are one paper (Kropfeld 2024) |
| 2 | exocad Align Meshes = trimmed-ICP-style with overlap-ratio + max-distance sliders; "identical shapes only" warning | **Confirmed** | All slider/warning text verbatim on the wiki. ⚠ "trimmed ICP" is *inference* — the wiki never names the algorithm (corroborated by third-party ICP descriptions). Wiki also documents a third control the claim omitted: brush-based exclude-regions masking |
| 3 | 3Shape 1-pt vs 3-pt; 3-pt better when submerged (0.084 vs 0.013 mm etc.) | **Plausible** | ⚠ Key correction: the quoted numbers are for 1/3 exposure **plus simulated scan-image deficiency**; with an intact image at 1/3 exposure the modes were statistically equivalent (0.020 mm both). Advantage is conditional on representation defects, not submergence alone |
| 4 | Medit auto library matching, deviation colour map, 3-pt+AI fallback; 0.0516 mm/0.3707° vs exocad 0.0597/0.4839° | **Confirmed** | ⚠ "Click a point to read its deviation value" is **not** in Medit's cited doc (unsupported). "No human clicks" mildly overstated (assignment + fallback clicks). Study numbers verified |
| 5 | Medit i900 Smart X 13.55±9.70 µm, credited to Scan Ladder geometry | **Plausible** | ⚠ "Asymmetric" refuted — paper says irregular/non-repetitive; "best published fully-automatic result" not claimed by the paper (photogrammetry reaches ~5 µm); "only by pairing" is inference (no ablation arm); lead author has declared financial interest in Scan Ladder |
| 6 | Straumann WO2010091868A1: plane-fit + intersection pose, over-constrained, any planar point usable | **Confirmed** | χ² is the *example* fitting procedure, not mandated; "noise resilience" is paraphrase of "even higher precision"; ICP is simply unmentioned, not rejected |
| 7 | coDiagnostiX IFU landmark rules + automatic surface registration + congruency check + 4-view fallback | **Confirmed** | All quotes verbatim in IFU §4.1; "coarse-to-fine" is an accurate interpretive label, not IFU wording |
| 8 | 2025 cohort: representation defects dominate (44.4% texture, 16% geometry vs ~100% coverage) | **Plausible** | ⚠ Sample size **243, not 172** (the 172 figure appears nowhere in the paper). All percentages, risk factors (cylindrical PEEK, mandibular, single-tooth) verified. Study assessed already-aligned scan bodies, so "matching-problem risk" is a slight reframe of scan-quality risk |
| 9 | No commercial system infers variant from geometry; identity is upstream metadata | **Confirmed** | Minor: exocad's library pick happens in the CAD wizard at the matching step, not the order form (order form fixes type). Third-party lab guidance confirms software will not catch a variant/SKU mismatch |
| 10 | Symmetric ICP: wider basin than point-to-plane; LM-symmetric widest of 8 variants | **Confirmed** | ⚠ Nuance: LM-symmetric is widest **at 20 iterations**; at 500 iterations two-plane is marginally wider. Grid spans (60°, 50%-of-mesh) and >20% IOU pairs verified verbatim |
| 11-15 | Symmetric-objective zero-set property; Masuda rejection recipe; Babin kernel survey (Cauchy+MAD, under-scaled redescenders worse than L2); TrICP ψ(f)/FRMSD auto-overlap; Sparse ICP / FRICP | *Plausible — not independently verified* | Consistent with the verified Rusinkiewicz paper (#10) and primary sources cited; kernel-policy prescriptions load-bearing for candidate 4 — spot-check before implementation |
| 16-22 | GNC (Yang RA-L 2020); FGR; LM-ICP distance-transform architecture; normal-space sampling; Go-ICP guarantees & costs; TEASER++/absence-of-inliers; GMOR decomposition; Hartley-Kahl BnB; PLuM; CMA-ES in 2D/3D registration; BO-for-hyperparameters-only | *Plausible — not independently verified* | Standard, widely-replicated results from primary venues; the TEASER++/FGR *inapplicability* argument (no true inlier features on smooth revolute caps) is our inference from the degeneracy literature, flagged as such in §3(c) |
| 23-27 | Fitzpatrick FRE⊥TRE; TRE configuration formula; WGF hybrid objective; Danilchenko anisotropic weighting; A-ICP; ECPD/BCPD; constrained/X-ICP; NIST datum association | *Plausible — not independently verified* | FRE/TRE theory is textbook (multiple independent sources in findings); it is load-bearing for §6 rules 1-2 and candidate 6 — the closed-form TRE formula should be re-derived/tested against synthetic clicks during implementation |
| 28-34 | ISO 5725 trueness/precision; Rohlfing CURT; ADD/ADD-S; BOP VSD/MSSD; reference-scanner/CMM ground truth; two-stage ROI-restricted superimposition; per-element 6-DoF deviation; non-parametric paired stats; <100 µm/<0.5° acceptance | *Plausible — not independently verified* | Metrology-methodology claims; internally consistent and multiply sourced. The <100 µm/<0.5° thresholds are for supragingival feature-rich scan bodies — must be recalibrated for the submerged-cap regime before use as pass/fail |

**Summary of refuted/corrected details** (do not repeat these in client-facing material):
sample size 172→**243** (#8); 3Shape 3-point advantage is **conditional on scan-image
deficiency**, not submergence alone (#3); Medit numeric click-to-read deviation
**unsupported** (#4); Scan Ladder "asymmetric" wording and "best published" superlative
**not in the paper**, COI present (#5); exocad manual-arm framing and "order form" library
location corrected (#1, #9); LM-symmetric basin superiority qualified to the 20-iteration
budget (#10); "trimmed ICP" label for exocad is inference, not documentation (#2).

---

## Addendum: dental accuracy literature (backfilled)

*Added 2026-07-14 to fill the missing "academic dental literature" research angle
(original sweep agent died on an API error). Scope: published intraoral-scanner
implant-digitization accuracy — scan-body registration trueness/precision, scan-body
design effects, coded/healing-abutment (ZimVie BellaTek) workflows, and the state of
published scan-body **localization** algorithms including deep learning. Sources fetched
and read where possible; figures taken only from a search-engine abstract summary (full
text blocked, e.g. HTTP 403 / auth redirect) are marked **(abstract only)**; claims I
could not confirm from any primary source are marked **(unverified)**. These are the
published numbers our own accuracy figures should be judged against.*

### Findings

1. **Scan-body geometry sets a wide accuracy floor, and low-feature shapes are the worst
   case.** The 2025 systematic review on scan-body geometry (Ahmed et al., *Dentistry
   Journal* 13(6):252) reports linear trueness from a best of **4.0 ± 2.4 µm** (an
   optimally-dimensioned cylinder) to **28.8 ± 8.6 µm** (a cuboid), with a typical
   commercial-body spread of **28.5–119.5 µm** and complete-arch **37–128 µm**; angular
   trueness ran **0.013 ± 0.010°** (cylinder) to **0.178 ± 0.010°** (cuboid), typical
   **0.19–2.56°** across designs. Cylindrical > cuboidal/spherical, and adding a rigid bar
   extension cut mean linear deviation **119.5 → 68.9 µm** (p = 0.008) and angular
   **0.75° → 0.36°** — i.e. distinctive, non-revolute geometry is what buys accuracy
   ([PMC12191632](https://pmc.ncbi.nlm.nih.gov/articles/PMC12191632/),
   [MDPI 2304-6767/13/6/252](https://www.mdpi.com/2304-6767/13/6/252)).

2. **Single-implant supragingival scan bodies are the "easy" regime: sub-100 µm / sub-1°.**
   Across in-vitro single-implant studies, positional deviation clusters in the
   **~38–90 µm** band and angular deviation **~0.2–0.85°** for well-exposed bodies; material
   matters — blasted titanium **89 ± 86 µm** and polished titanium **80 ± 72 µm** beat PEEK
   **149 ± 131 µm** on depth accuracy, because featureless low-contrast plastic parts
   register worse ([Effects of scan-body material/length/top design, PMC12270716](https://pmc.ncbi.nlm.nih.gov/articles/PMC12270716/)).
   Full-arch trueness is far wider — one review spans **7.6–731.7 µm** trueness and
   **15.2–204.2 µm** precision; short-span median trueness **38–47 µm** vs complete-arch
   **147–433 µm** (abstract only)
   ([Int J Implant Dent 40729-024-00543-0](https://link.springer.com/article/10.1186/s40729-024-00543-0)).

3. **Reducing exposed scan-body length degrades pose accuracy roughly monotonically — this
   is the closest published analog to submergence.** A single-implant study varying scan-body
   exposure height reported angular deviation rising from **0.17° at 9 mm exposure to 0.84°
   at 2 mm exposure**, and positional deviation **38.41 µm → 77.17 µm** over the same range
   (abstract only) ([ScienceDirect S0300571223002270](https://www.sciencedirect.com/science/article/abs/pii/S0300571223002270)).
   The "exposed length" in-vitro study reaches the same conclusion: accuracy of implant-position
   reproduction falls as exposed scan-body length decreases across all scanners
   ([Appl. Sci. 11(4):1689](https://www.mdpi.com/2076-3417/11/4/1689)) — full text 403, cited
   from abstract.

4. **Subgingival implant depth degrades trueness/precision, with a threshold around
   3.0–4.5 mm.** A five-scanner in-vitro comparison found precision drops for depths **≥ 3.0 mm**
   and trueness for **≥ 4.5 mm**; global linear distortion was 99 µm (3 mm), 60.6 µm (6 mm),
   107 µm (9 mm), and most IOS beat conventional impressions up to ~6 mm subgingival depth
   ([PubMed 34919607](https://pubmed.ncbi.nlm.nih.gov/34919607/)). The standing clinical
   mitigation is explicit: the deeper the implant, the longer the scan body should be, or
   bring the reference supragingival with a stock/multiunit abutment first.

5. **Coded healing abutments — the direct analog to our submerged caps — are
   measurably less accurate than exposed scan bodies, and the field has not fully endorsed
   them.** The systematic review of digitally-coded healing abutments (CHAs) reports scanned-CHA
   linear deviation **35–425 µm** and angular **0.40–0.70°**, versus conventional open-tray
   **13–24 µm / 0.046–0.12°**; elastomeric-impression CHA was far worse (up to
   **1.38–2.49°**). Angulation and visible height are significant, and an 8 mm CHA performed
   worse than 3 mm posteriorly. Conclusion: intraoral scanning of CHAs "appears more accurate"
   than elastomeric CHA impressions but "more studies are needed before CHA can be recommended"
   broadly ([PMC10724348](https://pmc.ncbi.nlm.nih.gov/articles/PMC10724348/)).

6. **Head-to-head, a scan body beats a coded healing abutment by ~2.4×.** A 2024 in-vitro
   comparison measured mean deviation from reference of **0.089 mm (scan body)** vs
   **0.217 mm (coded healing abutment)**, concluding scan bodies give clinically meaningful
   improvement ([J Korean Acad Implant Dent](https://www.implantology.or.kr/articles/article/5rkP/)).
   This is the quantitative version of "our problem is harder than a normal scan body": the
   occlusal-code-only geometry of a healing abutment carries less registration information than
   a purpose-built scan body.

7. **Best-fit / library superimposition IS the standard registration and evaluation method —
   our approach is mainstream.** Across this literature, precision is measured by best-fit /
   local-best-fit superimposition of repeat scans, and trueness by best-fit superimposition of
   test vs reference; digital workflows superimpose the implant-library analog onto the scanned
   scan body "according to the best-fit principle." Our rim-seat + best-fit refinement is the
   same family the whole field uses to both register and score
   ([Int J Implant Dent 40729-024-00543-0](https://link.springer.com/article/10.1186/s40729-024-00543-0),
   abstract only).

8. **The published ceiling for automatic library matching is ~13.6 µm — but only with
   deliberately irregular scan-body geometry.** The best fully-automatic result, Medit "Smart X"
   real-time AI library matching at **13.55 ± 9.70 µm** full-arch, was obtained only with
   irregular, non-repetitive "Scan Ladder" scan bodies; the geometry is credited with enabling
   the AI recognition, and there was no ablation against plain bodies (COI: lead author
   develops Scan Ladder) ([PMC12650994](https://pmc.ncbi.nlm.nih.gov/articles/PMC12650994/)).
   (This paper is already cited in §2; repeated here because it is the only published
   in-vitro evaluation of automatic scan-body *matching* accuracy.)

9. **Published deep-learning work on intraoral-scan meshes is mature for teeth, thin for scan
   bodies.** Mesh deep learning is well established for tooth segmentation and landmark
   localization on raw IOS meshes (e.g. TS-MDL / iMeshSegNet,
   [PMC10547011](https://pmc.ncbi.nlm.nih.gov/articles/PMC10547011/)), and CNNs classify
   implant *type* from radiographs at ~95% accuracy
   ([ScienceDirect S0022391323008120](https://www.sciencedirect.com/science/article/pii/S0022391323008120)),
   but I found no peer-reviewed deep-learning method that specifically **detects and 6-DoF-poses
   a scan body in an intraoral mesh** — the only shipped "AI real-time library matching" is
   proprietary and evaluated solely in the Scan-Ladder study above **(unverified — proving a
   literature gap; absence of a published scan-body-specific pose-detection benchmark could
   not be confirmed exhaustively)**. General CAD-to-scan 6D pose and part-in-whole registration
   methods exist outside dentistry (e.g. ZeroPose, [arXiv 2305.17934](https://arxiv.org/pdf/2305.17934))
   but are not validated on dental scan bodies.

### How the literature's expectations map to our submerged-healing-cap problem

The published accuracy bands are earned on **exposed, feature-rich, supragingival scan bodies**:
~4–29 µm / ~0.01–0.18° for good single-implant cylinders, degrading to sub-100 µm / sub-1° as
conditions worsen — and the literature is explicit that both **reduced exposure/submergence**
(angular error roughly doubling from 9 mm to 2 mm exposure; precision breaking down past
3–4.5 mm depth) and **low distinguishing geometry** (PEEK worse than titanium, coded healing
abutments ~2.4× worse than scan bodies) each push accuracy down. Our submerged healing caps sit
at the intersection of *both* penalties — a coded-healing-abutment-class low-feature part seen at
sub-scan-body exposure — so the sources genuinely support treating this as a harder regime than a
standard exposed scan body, and expecting accuracy below the tidy ~50 µm / ~0.3° single-implant
band. Concretely, our **10–25 µm on clean isolated parts** lands right in the published best-case
scan-body trueness band (4–29 µm cylinders), which is the sanity check that our pipeline is not
worse than the field on the easy case; our **0.5–1.0 mm p90 rim-seat agreement on submerged caps**
is well above the exposed-scan-body position band, consistent with the literature's submergence +
low-feature degradation — but note this p90 is a rim-band **surface-agreement** readout, not a
6-DoF pose-error metric, so it is not directly comparable to the trueness/precision figures above
(the FRE≠TRE caveat from §6 applies), and a like-for-like comparison requires reporting our
axis-angle and platform-centre errors against the same place-and-recover ground truth those studies
use.
