# Implant CAD — Portal (Phase 1) & Automation (Phase 2)

Monorepo for a dental-implant CAD lab: a doctor-facing **portal** (Phase 1) and a
geometry **automation** pipeline (Phase 2) that reduces manual per-case time.

Design docs live in [`docs/`](docs/). The engagement is phased and gated — each phase
is independently billable (see [`docs/technical-design-build-guide.md`](docs/technical-design-build-guide.md) Part 5).

## 🎬 Live demo — quick how-to

The interactive client demo: pick a real doctor's scan, watch the end-to-end automation
run (detect → confirm/brush → align → identify variant → measure → construct → export),
and view the color-coded deliverables in 3D.

```bash
# one-time setup
cd apps/web && pnpm install
cd ../worker && python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python tools/warm_demo.py     # pre-warm caches so demo clicks are instant (~10 min, once)

# run — ONE command from the repo root (starts API :8000 + UI :5173 together)
./scripts/run-demo.sh                   # or: pnpm demo

# (equivalent, two terminals)
cd apps/worker && make serve            # terminal 1 — pipeline API  → http://localhost:8000
cd apps/web    && pnpm dev              # terminal 2 — demo UI       → http://localhost:5173
```

> Note: the demo's pipeline API lives in **`apps/worker`** (Python FastAPI,
> [`src/case_prep/server.py`](apps/worker/src/case_prep/server.py)). `apps/api` is the
> *future* Phase-1 portal backend and is intentionally an empty placeholder.

Open **http://localhost:5173** — that's the demo. (Port 8000 is the API; visiting it
bare just returns a pointer back here. Interactive API docs live at
`http://localhost:8000/docs`.)

### The demo, click by click

1. **Select case** — the flagship demo cases are *Doctor Neodent GM* and *Doctor
   Zimmer 4.5*; every doctor folder in `apps/worker/data/real/scans/` appears as a
   card, so the fleet's single-cap validation scans are listed too. The doctor's real
   jaw scan loads into the 3D viewer facing the front; rotate it freely or jump
   with the **Front / Left / Right / Top** view buttons.
2. **Run detection** — the automation proposes healing-cap sites with evidence
   (pre-warmed = instant; ⟳ reruns it live).
3. **Confirm** — one click per site, plus the **declared cap variant** (required — the
   picker enforces it per site; the machine identifies independently and cross-checks
   against the declaration). Optional but the
   wow moment: **🖌 Mark cap** and *paint the healing cap directly on the 3D scan*
   (green glow → Done). The painted patch drives the alignment — the human loop,
   guaranteed.
4. **Run automation** — the results table shows identified vs declared variant
   (mismatches flag amber — the billing/fit guard), the **Seed** column (🖌 brush vs
   click), **Δ auto (mm)** — how close the human's marking and the machine's own
   proposal landed — and a **confidence chip** (high / medium / low: how stable the
   pose stays when the marks are re-clicked within click-noise) next to the gate.
   Then step through the three color-coded deliverable views
   (legend on the viewer: ivory = doctor's scan, green = aligned healing cap,
   steel blue = construction) and download the billable package.

Full presenter script with talking points: [`docs/RUN-DEMO.md`](docs/RUN-DEMO.md).
Operational handbook (running cases, scoreboard, phantom, FLE study): [`docs/HOWTO.md`](docs/HOWTO.md).

## Status

| Phase | What | State |
|---|---|---|
| **2A spike** | Count → localize → rim-first seat → calibrated variant ID → 6-DoF pose + confidence grade → gate; validation tooling (fleet scoreboard, printable phantom, FLE study) | ✅ **built** — [`apps/worker`](apps/worker), 788 tests green |
| **Live demo** | React + FastAPI interactive demo on the client's real scans | ✅ **built** — [`apps/web`](apps/web) + [`apps/worker/src/case_prep/server.py`](apps/worker/src/case_prep/server.py) |
| 1 — Portal | Multi-tenant intake / fulfillment / billing (React + Supabase + NestJS + S3 + Stripe) | scaffolded placeholders ([`apps/api`](apps/api), [`packages/shared`](packages/shared)) |
| 2B / 2C | Augment pipeline; replace/ML | not started |

**Phase 2A ships first** to confirm automation is viable before the portal build is funded.
Findings & go/no-go evidence: [`docs/engagement/phase2a-spike-findings.md`](docs/engagement/phase2a-spike-findings.md).

## Layout

```
apps/worker     Phase 2 automation, pipeline API (Python) — built; see apps/worker/README.md
apps/web        Live demo UI (React + Vite + three.js) — built
apps/api        Phase 1 backend (NestJS) — placeholder
packages/shared Shared TS types / case contract — placeholder
docs            Design documents, specs, engagement records
```

## Quick start (worker only, no UI)

```bash
cd apps/worker
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
make test                              # 788 tests (~17 min)
make demo-fast                         # every pipeline scenario → reports/demo/dashboard.html
                                       # (make demo = same + reruns the full test battery)
```

The worker pins **Python 3.9** for the spike (the Open3D-0.18-compatible interpreter on the
build host); production CI/container targets 3.11. Node 22 + pnpm 10 drive the monorepo tooling.
