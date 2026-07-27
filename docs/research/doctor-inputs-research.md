# Doctor-Side Inputs for Healing-Cap CAD Alignment — Industry Research

*Research date 2026-07-23. Question: "Do we need better inputs from the doctor — beyond the scan file, the centre mark, and the border circle? What has the industry done here?"*

> **Third-party marks (client directive 2026-07-25).** Competitor product names are out of our
> product and out of this prose; each vendor requirement below is cited by its own document
> number instead (e.g. ZVINST0213, ZVINST0206). The publisher URLs are reproduced **verbatim**
> because they address the vendors' own published PDFs — editing a URL would break the citation
> and misattribute the source. That is the only place a vendor's product name still appears.

Grounding for "expected value" claims: the product's measured limiters — variant ambiguity
(1/4 without declaration → 4/4 with), ROI contamination (median 54% tooth/gingiva in the
patch), submerged caps (collar under tissue, physically invisible; height-twin gap
0.01–0.06 mm), partial rim/top-face scan coverage, one mis-seated site from poor marks,
click noise xy p50/p68/p90 = 0.32/0.46/0.61 mm, rotation now read automatically from coded
cutouts (`docs/research/alignment-confidence-roadmap.md`,
`docs/engagement/phase2a-completion-report.md` §6–7, `docs/architecture-current.md`).

Evidence labels: **[measured]** = peer-reviewed number or vendor-manual requirement with a
number; **[vendor-required]** = stated intake requirement in official workflow docs;
**[marketing]** = vendor claim without published substantiation; **[ours]** = this
project's own measured result.

---

## (a) Industry intake-requirements table (per vendor, cited)

| Vendor / workflow | What the doctor (or submitting lab) MUST provide | Rejection / rescan criteria | Sources |
|---|---|---|---|
| **ZimVie (Biomet 3i) BellaTek coded healing abutment** — coded healing abutment; the direct analog of our product | (1) Scan (or impression) in which the **code markings are clearly visible**; (2) **entire circumference of the healing abutment** captured plus **all soft-tissue contours**; (3) collar **1–2 mm above the soft tissue (1 mm minimum)** around the whole circumference; (4) implant **connection type identified before ordering** (TSV = 3 grooves on the screw's occlusal portion — read off the scan/model); (5) **Kit = exact vendor catalog code** selected from the code-scheme matrix (ZBINST0013), with emergence-profile diameter measured from the scan if needed; (6) antagonist/bite "if available"; shade; diagnostic wax-up for 3+ units; (7) lab-side: **three-point alignment clicking 3 dots ON THE CODES** in the scan and the same 3 dots on the virtual template, then **Difference Map / 2D cross-section acceptance check** before design proceeds; (8) 3Shape "gingival scan" option must be **unselected** for IOS cases | Impression/scan rejected if codes not clearly visible, rips/tears/bubbles/distortion, collar circumference not 1–2 mm supragingival, voids; alignment rejected at the difference-map step (manual shows successful vs unsuccessful examples); cast off the mounting plate = "will not be scanned correctly" | [Lab Manual ZVINST0213](https://www.zimvie.com/content/dam/zimvie-corporate/en/dental/literature/zvinst0204/zvinst0204_tsv_bellatek_encode_abutmnts_lab_manual_final_secured.pdf) (text extracted); [TSV restorative tech guide ZVINST0206](https://www.zimvie.com.au/content/dam/zimvie-corporate/en/dental/literature/zvinst0206/zvinst0206_tsv_bellatek_eha_tech_guide_final_secured.pdf) (text extracted): "Verify that a clear scan has captured all the … markings, all the soft-tissue contours and the entire circumference of the healing abutment"; [product page](https://www.zimvie.com/en/dental/digital-solutions/bellatek-encode-impression-system.html) |
| **Dentsply Sirona Atlantis** (scan-body abutment workflow) | (1) One **Atlantis IO FLO scan body scan per implant site** — brand-specific scan body is mandatory; 3Shape scan bodies allowed **only** via the validated 3Shape→WebOrder direct path, not via STL upload; (2) **opposing arch REQUIRED for intraoral scans** (for model scans: opposing or diagnostic wax-up); (3) treatment-arch scan "optional but strongly recommended" for IOS; (4) **scanner model declared** (dropdown at order creation); (5) arch + tooth positions; (6) implant system/platform completed in WebOrder; (7) obligatory lab-side **scan-body detection and review step** with pictorial correct/incorrect acceptance criteria (flat side(s) and sphere of the FLO head fully visible; symmetric visibility of cylinder and plane surfaces) | Explicit **RESCAN REQUESTED order state**: "The scans you provided are not suitable for abutment design **and will be deleted**"; named causes: overlapped scan bodies in one STL, corrupted scan-body surface, artifacts on the surface (powder, **saliva accumulated during digital impression**), big part of the flat surface missing, altered scan-body shape; "Poor scan quality may lead to incorrect scanbody detection which will affect the abutment design" | [Atlantis Scan Upload user guide 32670865](https://workflows.orderdigitalsolutions.com/pdf/Atlantis%20Scan%20Upload_User%20guide.pdf) (text extracted); [iTero-for-Atlantis flyer](https://www.dentsplysirona.com/content/dam/dentsply/web/Implants/Franchise%20Content/32670620-USX-1407-Intraoral-scanning-for-ATLANTIS-Abutment-with-iTero-LR-7t66ea0-en-1409.pdf); [compatibility chart](https://www.dentsplysirona.com/content/dam/master/product-procedure-brand-categories/implant-dentistry/cad-cam-restorations/atlantis-abutments/documents/IMP-Brochure-AtlantisCompatibility-EN.pdf) |
| **3Shape TRIOS implant workflow** (generic scan-body) | (1) Scan body type/library declared in the order; (2) pre-preparation/provisional scan as design reference; (3) **Bite 1 always required; Bite 2 additionally for full arch**; (4) scan bodies scanned **one at a time with the lock-surface tool** so gingiva collapse doesn't corrupt the surface; (5) **disable color capture** while scanning scan bodies; (6) **dry the teeth** before scanning; (7) 3–4 teeth of overlap for bite alignment | Case-side quality control is chairside (review before send); labs bounce cases with unclear scan-body geometry | [Straumann/3Shape implant workflow how-to](https://www.straumann.com/content/dam/media-center/digital/en-us/documents/knowledge-center/trios/DISPLAY-How-to-Perform-a-Workflow-for-an-implant-EN.pdf); [3Shape TRIOS tips](https://www.3shape.com/en/blog/how-to-use-trios/tips-perfect-trios-scan); [Avinent 5-steps](https://avinent.com/en/blog/5-steps-for-perfect-scanning-with-trios-by-3shape/); [ioConnect best practices](https://support.3shape.com/truabutment-ioconnect-kit/truabutment-workflow) |
| **Medit (Scan for Clinics/Labs)** | (1) **Scan-body library assigned per tooth** (Company → Implant → Type → Subtype) — the software auto-aligns library to scan; (2) when auto-alignment fails, **manual 3-corresponding-point alignment** is the designed fallback (same 3-point pattern as ZimVie/Atlantis) | Failed library auto-alignment forces manual 3-point; wrong library = wrong geometry downstream (library-matching failure was a shipped bug fixed in Medit Link v3.4.2) | [Scan Body Library Matching](https://support.medit.com/hc/en-us/articles/360033527711--Scan-Body-Library-Matching); [Library Alignment](https://medit.document360.io/docs/scan-body-library-alignment); [v3.4.2 hotfix](https://www.medit.com/software-hotfix-medit-link-v3-4-2/) |
| **iTero restorative implant workflow** | Arch with provisional, opposing + bite, **soft-tissue emergence profile scan**, then scan body screwed in and scanned individually and in-arch | Chairside eraser/rescan of defective regions; Align patents describe **automated blood/saliva percentage classification with a rescan threshold** — a machine quality gate on moisture contamination | [iTero Lumina implant workflow job aid](https://assets.ctfassets.net/o8m7afojxkhl/2FB9FFN6AKrV1TXO6Imfk1/762bd4919594fa04a444087a19abb4ef/-EN-iTero_Lumina_Implant_workflow_job_aid.pdf); [case report](https://www.ijcridentistry.com/archive/article-full-text/100036Z07JM2021); [US 12521213 (blood/saliva scan-quality logic)](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12521213) |
| **Generic lab submission checklists** (Glidewell, PanAm, NextDental, Associated) | (1) **Implant brand, system, platform/connection declared**; (2) scan body **hand-tightened, seating verified — radiographic confirmation recommended before scanning**; (3) tissue management: retraction cord ~5 min then immediate scan; area **cleaned and dried**; (4) opposing + bite; (5) shade + photographs (shade tab in frame); (6) chairside review for voids/scatter before sending; avoid auto-fill features | Common remake/rejection causes: unseated scan body ("even a slight gap will translate to a misfit"), blood/saliva over the geometry, incomplete scan-body capture, missing bite, missing implant identification | [Glidewell digital implant impression](https://glidewelldental.com/company/blog/how-to-capture-an-accurate-digital-impression-for-implant-cases); [Glidewell 4 steps](https://glidewelldental.com/education/chairside-magazine/volume-16-issue-3/restoring-implants-4-steps-to-an-accurate-digital-impression); [PanAm implant submission tips](https://panamdl.com/blog/best-practices-implant-case-submissions/); [NextDental lab guide](https://www.nextdentallab.com/digital-vs-conventional-implant-impressions); [Associated scan-body checklist](https://associateddl.com/scan-body-torque-handling-checklist-how-to-prevent-indexing-errors-and-protect-implant-accuracy/); [radiographic verification of abutment seating (PubMed 9553883)](https://pubmed.ncbi.nlm.nih.gov/9553883/) |
| **Photogrammetry systems (PIC dental, Imetric iCam4D)** — full-arch implant position capture | Dedicated coded flags/scan bodies per implant + a separate IOS soft-tissue scan; the two datasets are registered in CAD. 2025 JPD work: **coded healing abutments used as the registration fiducial** between soft-tissue scan and implant-position scan, "avoid[ing] the need for posterior alignment … in CAD programs" | n/a (capture-time system) | [ITI blog accuracy review](https://blog.iti.org/clinical-insights/accuracy-photogrammetry-full-arch-implant-position/) (PIC trueness 10–49 µm, iCam4D 24–77 µm **[measured]**; PIC's "4 µm" claim **[marketing]**); [JPD 2025 alignment w/ coded healing abutments (PubMed 40610309)](https://pubmed.ncbi.nlm.nih.gov/40610309/); [JPD 2025 registration accuracy (PubMed 40450447)](https://pubmed.ncbi.nlm.nih.gov/40450447/) |

**Cross-vendor pattern:** every commercial workflow collects (i) a machine-readable
**identity declaration** (kit code / scan-body library / implant system+platform), (ii) a
**coverage/visibility requirement on the coded feature with a hard rescan gate**, (iii)
**seating verification** (radiograph recommended), (iv) opposing/bite (for restoration
design, not for fixture alignment), and (v) uses operator clicks only as a **3-point
coarse locator or fallback**, with a **difference-map visual acceptance step** after
automated alignment. No vendor asks the doctor for precision landmarks.

---

## (b) Scan-protocol factors ranked by evidenced accuracy impact

Primary sources: [Springer/IJID systematic review of implant-scanning accuracy factors
(PMC11063012)](https://pmc.ncbi.nlm.nih.gov/articles/PMC11063012/); [full-arch IOS
meta-analysis (PMC10756734)](https://pmc.ncbi.nlm.nih.gov/articles/PMC10756734/);
[coded-healing-abutment systematic review (PubMed
38107040)](https://pubmed.ncbi.nlm.nih.gov/38107040/); [factors review, J Dent
2025](https://www.sciencedirect.com/science/article/pii/S0300571225004178);
[methodological factors, Comput Biol Med 2025](https://pubmed.ncbi.nlm.nih.gov/39919664/).

| Rank | Factor | Evidence of impact | Lab-enforceable gate |
|---|---|---|---|
| 1 | **Scan extent / span** (full arch vs quadrant) | **[measured]** Full-arch deviations grow with span and implant count (positive correlation between number of implants and 3D deviation); meta-analysis pooled full-arch digital 137.9 µm vs conventional 182.5 µm; 200 µm cited as the misfit acceptability line; single-molar misfit 40.5±18.9 µm vs 3-unit distal 80.3±12.4 µm | Prefer quadrant-scoped capture around the site; treat cross-arch registration numbers with suspicion |
| 2 | **Coverage completeness of the coded feature** (rim circumference, flat faces) | **[vendor-required]** Coded-abutment standard: entire circumference + all markings or reject; Atlantis: missing flat surface / altered shape ⇒ RESCAN REQUESTED; "incomplete scan body data leads to misaligned restorations" | Automated coverage metric on the cap crop with a hard rescan threshold — the industry norm is re-capture, not in-fill |
| 3 | **Visible height / exposure of the coded abutment above tissue** | **[measured]** CHA systematic review: "angulation and **visible height** of CHA play a significant role in impression accuracy"; The coded-abutment standard hard-codes 1–2 mm (min 1 mm) supragingival collar | Numeric exposure check at intake; below threshold = submerged-cap flag (matches our physics ceiling) |
| 4 | **Moisture / blood / saliva on the feature; tissue over it** | **[vendor-required]** Atlantis lists saliva accumulation as a rescan cause; Glidewell: clean + dry, retraction cord ~5 min; Align patent implements a blood/saliva % threshold that triggers rescan; modern scanners tolerate saliva better than early ones but implant features remain sensitive | Color/texture-based contamination estimate on the ROI (see candidate inputs) |
| 5 | **Scan body / cap type, material, geometry** | **[measured]** Titanium ISBs beat PEEK; dome vs cuboid geometry shifts virtual alignment up to ~30 µm/0.09°; bevel orientation significant (F=7.92, p<0.001) | Fixed by the client's cap catalog — but supports declaring exact cap model, not just size |
| 6 | **Scanner model** | **[measured]** Primescan and iTero beat Medit i500 and Vatech EZ (p<0.05) in the systematic review | Collect scanner model (Atlantis already does) as a confidence prior, not a rejection |
| 7 | **Scan path / strategy** | **[measured]** Angular deviation significantly influenced by pattern (F=6.227, p=0.002); minimize vertical rotation of the wand; scan-bodies one-by-one with surface lock (3Shape) | Publish a one-page scan-path protocol; cannot be verified from the STL alone |
| 8 | **Implant/cap angulation & depth** | **[measured, mixed]** ≤15–20° angulation shows minimal impact; deeper/subgingival placement worsens capture in some studies, not significant in others | No gate; angulation is visible in our own rim fit anyway |
| 9 | **Operator experience** | **[measured, mixed]** Significant in some studies, insignificant (p>0.051) in others | Do not gate on it; gate on the artifact (coverage/contamination), which is what experience produces |
| 10 | **Calibration / ambient conditions** | **[weak evidence]** Recommended in methodological reviews; no strong field numbers in the sources fetched | Ask on the intake form ("scanner calibrated per manufacturer schedule Y/N") at most |

---

## (c) Candidate-input table for OUR product

Limiter key: **A** = variant ambiguity/height-twin, **B** = ROI contamination, **C** =
submerged cap, **D** = partial rim/top-face coverage, **E** = mis-seated cap, **F** = click
noise, **G** = rotation evidence.

| Candidate input | Limiter it addresses | Expected value (grounded) | Doctor friction | Industry precedent |
|---|---|---|---|---|
| **1. Declared cap variant (kit code)** — already required | A | **[ours, measured]** 1/4 → 4/4 identification; the height-twin is unresolvable from the scan below ~2.5 mm exposure, so this is the only channel for that DoF | Low (chart data; already enforced) | Universal: coded-abutment kit code from code-scheme matrix; Medit per-tooth library; Atlantis scan-body type. **Strongest possible precedent** |
| **2. Photo of the cap's engraved markings / package label (or catalog-code transcription)** | A (+ ground truth) | Converts the declaration from recall to transcription; also supplies the missing **variant ground truth** the project has never had (memory: "variant ground truth unverified"). Coded-abutment patents show the caps' physical markings carry **height, diameter, seating surface, hex orientation** — identity is physically on the part | Low (one phone/IOS photo at placement, attached to the case) | The coded-abutment premise is machine-readable identity on the cap ([US 6558162 family](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/6558162)); labs already require photos in submissions (shade/records) — [NextDental](https://www.nextdentallab.com/dental-lab-communication-checklist), [PanAm](https://panamdl.com/blog/best-practices-implant-case-submissions/) |
| **3. Implant system + platform diameter declaration** | A (cross-check), plus vendor construction-part routing | Narrows the catalog before scoring; guards a mis-declared kit code (diameter class IS scan-resolvable, so system+platform gives a second opinion the pipeline can check); required anyway for the construction part / screw channel | Low (chart data; every lab Rx already asks) | Universal on lab Rx forms ([Glidewell](https://glidewelldental.com/company/blog/how-to-capture-an-accurate-digital-impression-for-implant-cases), [NextDental](https://www.nextdentallab.com/digital-vs-conventional-implant-impressions)); The coded-abutment standard requires connection-type identification before ordering; Atlantis WebOrder requires system/platform |
| **4. Periapical radiograph of the seated cap** | E | Catches the one measured failure mode (mis-seated site) *before* alignment; a tilted/unseated cap violates the seat model silently — no scan-side signal distinguishes "cap tilted in scan" from "cap tilted on implant" | Low (routine intraoral PA, seconds; already standard of care for scan bodies) | **[vendor-required/standard]** Glidewell: "obtain radiographic confirmation to ensure complete seating before scanning"; [PubMed 9553883](https://pubmed.ncbi.nlm.nih.gov/9553883/); [Avant guide](https://avantdental.com.au/clinical/the-complete-guide-to-implant-scanning/) |
| **5. Hard capture-coverage requirement + dry field on the cap** (protocol + automated intake gate) | D, B, G | Directly attacks partial rim/top-face coverage (the #2–#4 evidenced factors above). ZimVie's own gate — all markings + entire circumference + 1–2 mm supragingival — is exactly the input our rim fit, code clock, and t2p score starve without. Cheap to enforce: compute rim-arc fraction + coded-band coverage at upload, refuse with a concrete "rescan the buccal rim" message while the patient may still be in the chair | Low–medium (30–60 s rescan; industry-normal) | ZimVie circumference rule; Atlantis RESCAN REQUESTED state with pictorial criteria; Align blood/saliva threshold patent ([US 12521213](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12521213)) |
| **6. Color/texture export (PLY/OBJ) instead of bare STL** | B (+ C detection) | ROI contamination is our largest precision lever (median 54% non-cap points; drives 4–5° axis error). Titanium cap vs pink gingiva vs white enamel is a near-trivial color segmentation the STL throws away; also gives a direct submergence estimate (tissue color over collar). No re-scan needed — same capture, richer export | **Near zero** (export setting) | IOS devices capture color natively; Align's quality logic classifies blood/saliva from scan appearance; note 3Shape advises disabling color *during* scan-body capture for geometry stability — precedent is mixed on capture, none against transmitting texture |
| **7. Exposure/tissue-height declaration OR "swap to taller cap" protocol for submerged sites** | C | The physics ceiling: below ~2.5 mm exposure the height-twin and the collar are invisible (95–98% shell coincidence within 0.2 mm). Industry answer is not software: The coded-abutment standard **requires** 1–2 mm supragingival collar or the case is not accepted; CHA literature confirms visible height drives accuracy. A checkbox ("collar fully visible / partially submerged") routes submerged sites to the declared-variant-only path honestly | Medium (declaration cheap; swapping to a taller cap = hardware + visit friction) | The 1–2 mm collar rule **[vendor-required]**; CHA systematic review **[measured]**; roadmap already concluded only an external input collapses this DoF |
| **8. Multi-angle rescan of the cap area on demand** (lab-initiated, targeted) | D | Fills specific coverage holes (missing lingual rim arc etc.); industry practice is targeted re-capture, never synthetic in-fill (Glidewell: avoid auto-fill; Atlantis deletes bad scans) | Medium (only when gated; chairside eraser/rescan is normal IOS practice) | Atlantis rescan loop; iTero region rescan; Glidewell |
| **9. Bite / opposing-arch scan** | none of A–G (occlusal orientation already derived; rotation from codes) | Near-zero for alignment; needed later for restoration design/occlusion — collect for product completeness, not for the aligner | Low (already standard) | Atlantis: opposing REQUIRED for IOS; TRIOS bite scans required — but all for prosthesis design |
| **10. Previous-visit / emergence-profile scan (cap removed, sulcus scanned <30 s)** | C | The only way to *see* the submerged geometry; two-scan technique is established for emergence profiles (tissue collapses within ~30 s–2 min of cap removal). But it defeats the coded-cap value proposition (no removal) and adds real clinical burden — hold as an escalation path for low-confidence/submerged sites only | High (cap removal, timing-critical scan) | [JPD digital custom impression technique](https://www.sciencedirect.com/science/article/abs/pii/S0022391319300952); [Concord Lab sulcus scans, 15–20 s window](https://concorddentallab.com/sulcus-scans/); iTero workflow includes an emergence-profile scan step |
| **11. Scanner model + calibration status field** | confidence priors | Sets a noise prior per case (scanner model measured significant, rank 6); zero-cost dropdown | Near zero | Atlantis Scan Upload requires scanner selection at order creation |
| **12. Intraoral photo of the occlusal cap face** | G, A (QC tie-break) | Human-auditable rotation/code check when the depth-image clock evidence is weak (`rotation_unverified` sites); photos are 2D — no product uses them for geometric CAD alignment (photogrammetry with coded targets is the geometric photo route) — so value is audit/tie-break, not pose | Low | Labs collect photos routinely (shade/esthetics); no alignment-from-photo product found — treat any such pitch as **[marketing]** |

---

## (d) Do-NOT-collect list

1. **Screw-hole / hole marks from the doctor.** **[ours, measured]** The scan contains no
   hole — a smooth dome (scanned centre +0.13 mm above rim vs CAD 5.3 mm below); the rim
   already pins position/axis better than a click; rotation is now read from the coded
   cutouts automatically (e8 extractor, 6/7 sites ≤10°). Industry agrees: the machine reads
   the coded features; ZimVie's 3-dot click is on the *codes*, used as a coarse locator
   with a difference-map check — never a precision landmark
   (`alignment-confidence-roadmap.md` §1c, completion report §7).
2. **A separate surgical/prosthetic platform-depth input.** **[ours]** Redundant with the
   declared variant for this direct-seat catalog — the collar height IS the transform's
   translation; a second noisier intake for the same DoF (roadmap "do NOT build" list).
3. **Extra precision clicks / more landmark points from the doctor.** Click noise is
   measured at 0.32–0.61 mm xy — an order of magnitude above the automated rim fit; every
   vendor treats operator points as 3-point *coarse* alignment or a fallback when
   auto-align fails (ZimVie, Medit, Atlantis). The client's move to "approximate locators
   only" matches the industry exactly. Invest in the difference-map acceptance step
   instead (already shipped as QC renders).
4. **Elastomeric/model-scan route for coded caps.** **[measured]** CHA systematic review:
   elastomeric impressions of coded abutments performed poorly vs conventional for
   multiple implants, while IOS of the same abutments was more accurate; JPD 2021: model
   scanning with scannable healing abutments "may not be clinically acceptable"
   ([PubMed 38107040](https://pubmed.ncbi.nlm.nih.gov/38107040/),
   [JPD S0022-3913(20)30584-9](https://www.thejpd.org/article/S0022-3913(20)30584-9/abstract)).
   Accept IOS only.
5. **Powder/contrast spray.** Atlantis explicitly bans powder artifacts on FLO scan
   bodies; the powder era ended with modern scanners — a powder requirement today would be
   a step backward and a rescan cause
   ([Atlantis guide](https://workflows.orderdigitalsolutions.com/pdf/Atlantis%20Scan%20Upload_User%20guide.pdf)).
6. **Software-filled ("auto-fill") surfaces.** Glidewell: auto-filled data does not
   represent the missing anatomy; Atlantis deletes and demands rescan. Our intake gate
   should likewise refuse synthetic in-fill rather than align to it
   ([Glidewell](https://glidewelldental.com/company/blog/how-to-capture-an-accurate-digital-impression-for-implant-cases)).
7. **Operator-experience certification as an intake gate.** Evidence mixed/insignificant
   (p>0.051 in some studies) — gate on the artifact (coverage, contamination), not the
   person ([PMC11063012](https://pmc.ncbi.nlm.nih.gov/articles/PMC11063012/)).
8. **Bite/opposing as an *alignment* input.** Required by vendors for prosthesis design
   only; adds nothing to cap pose (occlusal orientation derived from the arch; rotation
   from codes). Collect it, but never let it into the aligner.
9. **A "gingival scan" software layer in coded-cap IOS cases.** ZimVie instructs it be
   unselected — the extra tissue layer corrupts the coded-abutment workflow (Lab Manual
   ZVINST0213).

---

## Notes on evidence quality

- ZimVie and Atlantis requirements were read from the primary vendor PDFs (text extracted
  locally from the official documents) — **[vendor-required]**, the strongest tier here.
- Accuracy factor rankings rest on one systematic review + one meta-analysis + one CHA
  systematic review; in-vivo evidence is thinner than in-vitro (the reviews themselves flag
  this).
- The coded-abutment system's own accuracy: measured *less* accurate than conventional copings (centre-point
  deviation ~35–47 µm vs 14–19 µm; hex rotation 2.9° vs 1.8°) yet judged clinically
  acceptable for single crowns/short spans
  ([PubMed 21453396](https://pubmed.ncbi.nlm.nih.gov/21453396/)) — i.e., the commercial
  coded-cap gold standard ships at roughly the accuracy class our pipeline already reports
  (rotation ≤3.1° on 8/10 sites), and it does so on the back of *intake discipline*, not
  extra doctor landmarks.
- PIC "4 µm" and general "most precise" claims are **[marketing]**; peer-reviewed trueness
  ranges are 10–49 µm (PIC) / 24–77 µm (iCam4D)
  ([ITI blog summary](https://blog.iti.org/clinical-insights/accuracy-photogrammetry-full-arch-implant-position/)).
