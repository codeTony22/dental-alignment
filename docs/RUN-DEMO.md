# Running the Live Client Demo

> **Scope: this is the FROZEN client demo** — `apps/web` (:5173) with
> `case_prep.server` (:8000), frozen at `8125cbf` and never edited. It is kept working
> for presentations.
>
> It is **not** the product app. The operator product is `apps/product` (:5174) +
> `apps/bff` (:8001), it has five stages, and its own script is
> [`product-runbook.md`](engagement/product-runbook.md). Nothing below applies to it —
> different ports, different vocabulary, different stages.
>
> One number differs on purpose and will look like a bug if you compare screens: the
> verify panes' display band is **9 mm** here and **11 mm** in the product. Both are
> correct; reconciling them would break the freeze.

The interactive demo: pick a real doctor's scan, watch the end-to-end automation run, and
show the manufactured final product — all live pipeline output.

## One-time setup

```bash
# frontend deps (first time only)
cd apps/web && pnpm install

# pre-warm the automation caches so every demo click is instant (~10 min, once)
cd ../worker && .venv/bin/python tools/warm_demo.py
```

## Start the demo

```bash
./scripts/run-demo.sh     # ONE command from the repo root — API :8000 + UI :5173 (or: pnpm demo)
```

Two-terminal equivalent (useful when you want the API log in its own window):

```bash
# terminal 1 — the pipeline API (port 8000)
cd apps/worker && make serve

# terminal 2 — the React app (port 5173)
cd apps/web && pnpm dev
```

Open **http://localhost:5173**.

## The demo script (what to click, what to say)

1. **Select the case** — click *Doctor Neodent GM* (or *Doctor Zimmer 4.5*). The case
   cards are discovered live from `apps/worker/data/real/scans/` — nine today, including
   the numbered doctor exports and the single-cap bench scans; each card shows the jaw and
   the construction vendor (atlantis / dess).
   The doctor's actual upper-jaw STL loads into the 3D viewer — **facing the front**, with
   **Front / Left / Right / Top** preset buttons overlaid (one click = one anatomical view,
   no orbiting hunt). *"The scan greets you the way the doctor sees the patient."* Rotate
   it: real patient anatomy, healing caps in place. *"This is the input — exactly what the
   doctor sends."*
2. **Run detection** — the automation scans the arch and drops markers on the proposed
   healing-cap sites, each with its evidence. *"No clicks, no labels — it found the caps."*
   (Pre-warmed = instant; hit the **⟳ rerun live** button if you want to prove it's live —
   recorded fresh detections take ~10–20 s per case.)
3. **Confirm** — the operator's one-click confirmations. **The variant picker** (RealGUIDE
   library-selection parity): each site offers the model's full catalog — six variants with
   Ø × height — and the declaration is **required**: the unselected option reads *"— declare
   cap variant —"* and the Run button stays disabled until every site has one (there is no
   *auto* in the demo path — declared identification measured 4/4 correct vs 1/4 without).
   The doctor's pick DRIVES the alignment with exactly that part; the measured rim Ø
   independently cross-checks it and flags disagreement. "view part" shows the library part
   in 3D next to the scan. *"A human confirms each site — that's the clinical safety gate,
   and every case confirmed grows the dataset that automates it."*
   - **Presenter note:** redoing marks mid-demo is safe — re-entering step 3 always restores
     a clean input scan, no stale artifacts from the previous run.
   - **The brush (RealGUIDE-style, optional but the wow moment)** — click **🖌 Mark cap**
     on a site, then *paint directly on the 3D scan* over the healing cap (drag; green
     glow). Click **Done** — the chip shows *patch · N pts*. *"The operator marks exactly
     where the cap is — that painted patch drives the alignment. The human loop,
     guaranteed."* A brush run computes live (~15–40 s — narrate; it's the real pipeline).
4. **Run the automation** — alignment, variant identification (measured rim Ø vs the
   declaration — mismatches flag in amber: *the billing/fit guard*), site measurement,
   screw-channel construction, package export. Then:
   - the **results table** — identified variant, measured Ø, agreement, mesio-distal
     space, the **Seed** column (🖌 brush vs click), **Δ auto (mm)** (human-marked site vs
     the automation's own proposal), and **Fit avg/max (mm)** — the registration-error
     numbers, directly comparable to RealGUIDE's Registration Error dialog (theirs: 0.28
     avg / 2.40 max; ours across the warmed demo cases: ~0.4–0.8 avg / ~1.2–2.9 max — the
     max lands on screw-recess points the template's bore can never cover). *"When the
     human and the machine independently land within a millimetre or two of each other,
     that's the confidence number — measured, not claimed."* The gate cell also carries a
     **confidence chip** (high / medium / low): the pose is re-seated 8 times under
     measured click-noise and graded on how much it wobbles. *"The pipeline grades its own
     certainty; low means look."*
   - the **Rotation column** — the automation reads the cap's CODED CUTOUTS (the
     features a lab tech judges rotation by) and clocks the part until they align;
     the residual ships in degrees ("−1.9° — aligned"). *"The coded pattern on the
     cap's face lines up with the scan — measured, in degrees, the way the industry
     specs it (the commercial gold standard itself is 2–3°)."* On weak-evidence sites
     the row auto-expands an operator **nudge control** (−15/−3/+3/+15/Reset): every
     nudge is re-judged by the same safety gates server-side and audit-logged —
     *"the human can correct it, but nobody can silently break it."*
   - the **screw channel** — where the coded features and the scanned screw-recess
     disagree about rotation, the disagreement itself is flagged for attention
     (*"on a rigid part they can't both be right — the software tells you instead of
     guessing"*); the printed phantom validates which instrument is right physically.
   - the **three staged deliverable views**, color-coded live in the viewer (legend
     bottom-left — ivory = doctor's scan, green = aligned healing cap, steel blue =
     construction):
     1. *Healing-cap alignment* — the doctor's whole arch with the aligned cap in green
     2. *Construction in arch* — the arch with the scanned cap region removed and the
        construction seated in its place
     3. *Construction alone* — the final part with the screw channel
   - the **billable package** file list with downloads — now including the two
     per-site **QC acceptance artifacts**: the *clock view* (top-down: scan depth
     field, coded-cutout overlay, bore/void markers, rotation residual) and the
     *signed deviation map* (±0.5 mm colormap + RMS/p90 — the industry lab-tech
     acceptance convention). *"You don't take our word for the alignment — the
     package contains the picture a QC tech signs off on."*
5. Close on the footer (it reads *780+ automated tests*; the frozen demo's own suite
   is 789 today, and the system total is larger — re-measure before quoting a number):
   *788 automated tests, everything advisory-gated, live output.*

## If something misbehaves

- API not responding → check terminal 1; restart `make serve`.
- 3D viewer blank → the scan is ~15 MB; give it a few seconds, check the browser console.
- Want a truly fresh run mid-demo → steps 2 and 4 each have a **⟳ rerun live** option
  (recorded fresh durations across the nine cases: propose 6–21 s, full run 3–13 s; a
  cold server adds mesh-load time — narrate while it works; it's the real pipeline).
- Re-warming after a pipeline change → delete `apps/worker/reports/live-demo` but
  **preserve `run-history.jsonl` inside it** (it is the FLE calibration data), then re-run
  `tools/warm_demo.py`.
