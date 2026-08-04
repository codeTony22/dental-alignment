# Client asks — everything the codebase still waits on

Two dated sections. The 2026-08-04 section is current: with the §10-AB decision batch and
its whole engineering queue landed, exactly three items remain open, every one blocked on
words or a measurement only the client can supply — nothing is code-blocked. The
2026-07-26 section below it is the demo-phase ask list, kept because none of its items
was ever formally answered in this record.

---

# The three product asks (2026-08-04)

**Part one is written to be sent to the client as-is.** Part two is the engineering
landing for each answer — where it goes, what bumps, which pins amend — so the day an
answer arrives it lands in one sitting, without re-deriving any of this.

## Part one — sendable

Three things are waiting on you, and each is small. Everything else from the August 2
decision batch is built and running.

### 1. The final Terms & Conditions wording — two short texts

At Delivery, the operator signs one agreement before payment and release. Today it shows
placeholder wording inside a loud "PLACEHOLDER" banner, because legal language is yours
to supply, not ours to invent. We need two texts:

1. **Terms and Conditions** — what the signer accepts when authorizing release.
2. **Clinical Responsibility Statement** — the clinical half. One signature covers both:
   the terms incorporate the statement by name, and it is linked from the agreement so a
   signer can read it before ticking the box.

The current placeholders describe exactly what the signature technically covers, and
your wording should preserve these two facts (or tell us to change the mechanics):

- Sites released as **acknowledged exceptions** — flagged rows the operator ticked one
  by one — are INCLUDED in the release the signature authorizes.
- **Withheld** sites are EXCLUDED: a withheld site ships nothing and stays open.

One constraint: the texts must be case-independent — no counts, case names or dates in
the wording. The system renders each case's own numbers beside the checkbox, from the
same source the invoice prices from.

When the wording arrives it lands the same day. Every confirmation already sealed keeps
resolving to the placeholder text its signer actually saw — versions are additive, never
rewritten — so there is no migration and no hurry-induced risk.

### 2. One physical measurement: where does the screw access really sit on the Zimmer 4.5 case?

On three of the nine scans, scanning material sealed over the screw access left a closed
pocket inside the scan. We measure that pocket as an independent witness of where the
screw access sits — and on the Zimmer 4.5 case (`cap7030`) it disagrees with the fitted
pose by **2.1 mm**, on precisely the case you called badly aligned, while our other
software instrument reads the same disagreement as **0.95 mm**. The two instruments
cannot both be right, and no software measurement can break the tie — the model on your
bench can.

What we need, once, on the physical model for `cap7030` — any ONE of these answers it,
listed best first:

1. **A re-scan of that model with the screw access left OPEN** (unsealed). We measure
   everything else from the scan.
2. **A straight-down photo of the seated cap with a ruler in frame.**
3. **A caliper distance** from the seated cap's screw-access centre to a clear landmark
   you name (a neighbouring tooth's cusp, or a marked point on the model). We compare
   the same distance in the scan.

What the answer settles: if the true access sits where the fit says (within ~0.5 mm),
the 2.1 mm reading is scanning-material bias and that instrument is retired from
reports. If it really sits ~2 mm off, then the best-fitting seat on the whole fleet
carries a real defect that fit numbers cannot see, and this cross-check earns a
permanent place on the report. Either way, the number we put in front of you stops being
one of two contradicting instruments.

### 3. One sentence on the second adjustment tool: should the second mark change the numbers?

You asked for a "visual matching" tool. The first tool — matching a stretch of the
library part to the scan — is built and shipping. For the second, your description
supports two different products, and we will not guess:

- **A.** The second mark on the library part is a **visual aid only** — it helps the eye
  line things up, the fit's numbers do not move, and the screen says so out loud.
- **B.** Each library mark pairs with its own scan point as an **independent
  measurement** — the second mark genuinely changes the fit (two matched points are
  enough to clear our cross-check floor, so the numbers move honestly).

The question, in operator terms: **when the second library mark lands, should the
numbers change?** "No" means A — a display feature, days of work. "Yes" means B — a
measurement feature, its own slice. One sentence decides it.

## Part two — the engineering landing (not for sending)

### 1. Terms texts → `apps/bff/src/bff/resources/deliver.py`

- Mint new version ids (shape: `client-<date>-terms-v1`, `client-<date>-clinical-v1`),
  point `TERMS_VERSION` / `CLINICAL_VERSION` at them, and ADD entries to
  `TERMS_DOCUMENTS` with `status: "final"`. The placeholder entries STAY — the map is
  additive, never edited in place; a sealed confirmation must keep resolving to the
  words its signer saw (the `placeholder-v1` row is the worked precedent).
- `apps/product/src/domain/deliver.ts::CLINICAL_TERMS_VERSION` mirrors the clinical id —
  bump it in the same commit. (A stale copy 404s loudly by design; it never misstates
  what a signature covered.)
- The DeliverStage placeholder banner (`terms-placeholder-banner`, `DeliverStage.tsx`)
  is DELIBERATELY unconditional — unmissable and independent of any fetch, so a failed
  read can never hide it over placeholder text. It stands down in the same commit the
  real text lands, **not before**; do not pre-wire it to the served status.
- Pins to AMEND, never delete (the rate card's §10-AB.1 confirmation is the pattern):
  `apps/bff/tests/test_deliver.py`'s placeholder-wording and status pins,
  `apps/product/src/pages/TermsPage.test.tsx`, and DeliverStage's banner tests — the
  "placeholder" pins become "final" pins that quote the client's own text.

### 2. Recess measurement → §10-L's record

- Whatever the number says, the recess stays a REPORTED cross-check, never a pose input
  (§10-L, measured three ways; the phantom-clock bias conviction stands).
- **Outcome A (access on the fitted axis):** the second-shell centroid instrument is
  convicted of scanning-material bias — record the conviction in §10-L beside the void
  detector's, and put NEITHER disagreement number in front of the client until an
  instrument survives arbitration.
- **Outcome B (access ~2 mm off):** the centroid cross-check earns the report — wire it
  in §10-L's stated shape ("measured, reported, consumed by nothing", the SHADOW_ISLAND
  doctrine), and `cap7030`'s seat gets a case note: best fleet fit.avg, real off-axis
  channel.
- Either way the measurement, its date and its method go into §10-L so the 2026-08-01
  table stops being the last word.

### 3. Tool-2 ruling → §10-J's record

- **Reading A (visual aid):** a surface-only build — pane arming for the second library
  mark plus the explicit "display only — does not change the fit" wording (the repo's
  say-it-out-loud doctrine). No worker change, no new physics.
- **Reading B (independent pairs):** the physics already exists — two pairs with free
  part points already clear the cross-check floor through `fit-by-points`. The build is
  the matching-first UI over that machinery, sized as its own slice.
- Record the client's sentence verbatim in §10-J before building either.

---

# The demo-phase asks (2026-07-26, kept as recorded)

*Written with the demo baseline (`8125cbf`), companion to CLINICAL-DEMO.pdf. None of
these was formally answered in this record; some may have been resolved on calls without
landing here. On the next call, restate whichever still matters — chiefly #3: the
RealGUIDE round-trip is still the automation plan's last unvalidated assumption.*

## 1. More arch cases (highest value, lowest effort)
Any doctor scans with healing caps in place — upper or lower, any system, with or without the
final restoration. **Why:** the propose step's automation is data-gated. Today it runs on two
labelled arches; every case you add grows the tuning set that converts the one-click confirm
into full auto-detection. Drop STLs in any folder structure; we normalize. *(Since 2026-08-02
they can also be dropped straight onto the product's worklist — the upload is real.)*

## 2. Which caps were actually placed (5 minutes)
For the two demo cases: which size variants were used?
- Neodent GM case — we identified **7030** (site near tooth 4) and **6020** (near tooth 13)
- Zimmer 4.5 case — we identified **5020**
**Why:** verifies (or corrects) the automatic variant identification with ground truth.

## 3. One case exported from RealGUIDE (the big unblock)
A single case exported from your RealGUIDE — the mesh(es) plus the recovered implant pose as
RealGUIDE shows it. **Why:** the entire automation economics rest on our recovered pose
surviving RealGUIDE's import without re-seeding. This one artifact is both the validation spike
(~1 week) and the clinical ground truth for accuracy claims. It is the last unvalidated
assumption in the plan.

## 4. The third vendor (10 minutes)
You mentioned three US vendors; we have DESS and Atlantis wired. The third vendor's name, plus
for all three: what file format / order package do they require from you today? **Why:**
completes the vendor-selection step of the flow with real requirements, not guesses.

## 5. Doctor names for the case folders (optional, 2 minutes)
The scans folder is organized per doctor with placeholder labels. Real names (or your preferred
case IDs) keep the packages traceable to the referring practice.

## 6. Tooth numbers for the demo cases (2 minutes)
The demo packages carry placeholder tooth numbers. The doctor's chart numbers for the three
sites make the packages clinically correct.
