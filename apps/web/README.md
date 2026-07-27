# apps/web — Demo UI (Phase 2A console)

React + Vite + three.js single-page app that drives the Phase 2A automation pipeline in
[`apps/worker`](../worker) (FastAPI server on port 8000). Originally staged as the Phase 1
portal placeholder; it has since grown into the live demo console used with the client.
The funded doctor-portal/operator-console build is still pending — see
[`docs/software-design-document.md`](../../docs/software-design-document.md) §3.

## Running

```sh
pnpm dev          # vite on port 5173 (expects the worker API on :8000)
pnpm test         # vitest
pnpm typecheck    # tsc -b --noEmit
```

Port gotcha: `pnpm dev -- --port X` does **not** change the port — pnpm forwards the
literal `--` to vite, and vite treats everything after `--` as positional, so it stays on
5173. Drop the separator: `pnpm dev --port X` works. `.claude/launch.json` does exactly
that: `demo-web` runs plain `pnpm dev` (vite's default 5173); `demo-web-alt` passes
`--port 5273 --strictPort` via `runtimeArgs`.

## What the demo does

Step rail: pick a case → propose sites → **Step 3 · Confirm** (mark each site, declare
its cap variant) → run the pipeline → review results and the packaged output.

Feature notes (all verified against `src/`):

- **Anatomical camera** — the scan loads facing the front of the mouth.
  `computeAnatomyFrame` ([`src/viewer/anatomyOrientation.ts`](src/viewer/anatomyOrientation.ts))
  derives the frame from the scan itself (PCA occlusal axis + U-apex anterior); it returns
  null for clouds that don't read as an arch sheet, and callers fall back to default
  framing. View presets **Front / Left / Right / Top**
  ([`ViewOrientationBar`](src/components/ViewOrientationBar.tsx)) call
  `sceneController.setAnatomyView` (`AnatomyViewId`: `front | left | right | occlusal`).
- **Marking** — per site, either centre + rim-border clicks (one measurement pair —
  pair integrity is a hard product rule) or the 3D brush (**Mark cap** in the Confirm
  panel) to paint a patch directly on the mesh.
- **Declared variant is required** — the per-site picker must be filled before
  Confirm-all enables (`undeclaredSiteNumbers` in [`src/domain/types.ts`](src/domain/types.ts)).
  The picker's "auto" entry is only the unselected prompt (after a run it shows the
  automation's identification as a hint to confirm against) — a site left on it blocks
  Confirm-all, so nothing runs undeclared.
- **Clean-scan redo** — re-marking in step 3 always restores the clean input scan first
  (`ensureCleanScanView` in [`src/App.tsx`](src/App.tsx)); marks must never be aimed over
  a post-run composite (that's how the one bad redo border click happened). After a run,
  the step-3 buttons fully reset — no stale artifacts.
- **Results table** ([`ResultsTable`](src/components/ResultsTable.tsx)) — scrolls
  horizontally in its own container (`.results-table-scroll`) instead of pushing into the
  3D viewer. The gate cell shows a pose-stability **confidence chip** (high / medium /
  low) when the server returns it (bootstrap re-seating under measured click noise).

The footer's "390+ automated tests" refers to the worker's pytest battery (788 tests).

## Layout

- `src/App.tsx` — state machine for the whole demo flow.
- `src/viewer/` — three.js scene (`sceneController.ts`, `Viewer3D.tsx`,
  `anatomyOrientation.ts`).
- `src/components/` — step rail, confirm panel, results table, guidance, etc.
- `src/api/` — wire types + mappers for the worker API.
- `src/domain/` — UI-side domain types and invariants (tested).
- `src/hooks/` — small shared hooks (`useElapsedSeconds`).
- `viewer-standalone/` — standalone viewer build (`pnpm build:standalone`).
