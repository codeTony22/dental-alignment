# Demo runbook — the predictable demo

**Purpose:** the same demo, every time. One command answers "is the fleet behaving the way it
behaved when we last looked?", and this page holds the script for everything the fleet is
KNOWN to say. Baseline: 2026-07-26 (10 sites, all rim seats, declared==identified 7/7,
rotation code-verified 8/10 within ±3.1°).

---

## 1. Before every demo (10 minutes, in order)

```bash
# from apps/worker — gate the code against the baseline. Green or don't demo.
make rehearse
```

```bash
# start (or RESTART — required after any code change; the verify panes' framing rides on a
# payload field the server must be serving) the API on :8000
make serve
```

```bash
# pre-warm every case so runs answer instantly in front of the client
.venv/bin/python tools/warm_demo.py
```

```bash
# from apps/web — the demo UI on :5173
npm run dev
```

Browser window **≥1600×1000** (verified layout; 1280×800 also verified but tighter).

## 2. Case order

**Lead with these five** — clean end-to-end, no caveats to manage:

| case | tooth | rim seat | rotation | notes |
|---|---|---|---|---|
| cap6020-neodent-gm | 29 | 0.55 mm | +0.1° code-verified | the walkthrough case |
| cap6030-neodent-gm | 29 | 0.22 mm | −2.2° code-verified | tightest seat |
| 276794487-zimmer-4.5 | 3 | 0.38 mm | +1.1° code-verified | upper jaw + relief clamp story (§3) |
| 295811960-neodent-gm | 29 | 0.35 mm | −1.9° code-verified | |
| cap7020-zimmer-4.5 | 3 | 0.54 mm | +0.8° code-verified | upper jaw |

**Show deliberately or skip** (the honesty story, not the accuracy story):

- **cap7030-zimmer-4.5 t29** — rotation +23.8° with *no code evidence*: the system flags it
  instead of pretending. Script: "this is what refusing to guess looks like" → open the
  verify dialog, correct on the union pane's rotation dial.
- **zimmer-4.5 t7** — the scan has a hole across 46% of the seat band. −150.5° unverified,
  confidence low. Script: this is a **rescan request**, the capture gate's whole point.
- **297589851-neodent-gm t20** — ships undeclared; declare `4020` live (the automation
  independently identifies it — good theatre, low risk).

**Keep out of a first demo:** `neodent-gm` (two sites, two different variants sharing one
construction part — the pipeline itself says "per-variant construction parts needed"; t4 has
no confidence read, so its chip renders blank next to t13's).

## 3. Lines for the flags that WILL appear

- **Relief clamp banner** — appears on FIVE sites at the 0.20 mm default (276794487 t3,
  cap7020 t3, cap7030 t29, zimmer-4.5 t7 → 0.08 mm; neodent-gm t13 → 0.05 mm): *not* an
  error. "The 0.20 mm you asked for would thin the screw-channel wall below the 0.50 mm
  rule — the system built at the maximum safe relief and told you both numbers. Nothing is
  ever silently substituted."
- **medium confidence everywhere**: honest by design — the grade prices in the click noise
  the current marks carry; the roadmap item that removes it (marks-as-locators) is measured
  and parked, not missing.
- **Rotation column** reads e.g. "+1.1° — aligned · read from the coded cutouts": the number
  is *measured* from the cap's coded features, not chosen by anyone. Correction, when needed,
  happens on the 3D (union pane dial), never as blind degrees in a table.

## 4. Recovery moves

- Union pane says "restart make serve" → the API predates a payload field; restart + rewarm.
- A dialog misbehaves → `Esc` closes it; nothing is processed without the acknowledgment.
- "Is this canned?" → the **rerun live** button re-runs the real pipeline on the spot.
- Camera lost → `⊞ Whole arch`, then `◎ This site`; the four view presets orbit whatever is
  framed.

## 5. Keeping the gate honest

`tools/rehearse_demo.py` holds the baseline (`KNOWN_FLAGS` / `KNOWN_CLAMPS`). When the fleet
legitimately changes (a fix lands, a case is rescanned), update the baseline **in the same
change**, with the finding read and understood first — the gate is only worth having while
"green" means "same as the last time a human looked".
