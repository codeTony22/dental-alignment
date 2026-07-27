# Phase 2A worker — convenience targets.
# PYTHONWARNINGS suppresses a harmless macOS LibreSSL/urllib3 import notice
# that fires before pytest's own filters can apply.
export PYTHONWARNINGS := ignore:::urllib3

PY := .venv/bin/python
PYTEST := .venv/bin/pytest

.PHONY: test test-fast test-slow rehearse demo demo-fast booleans-demo workflow-real real-demo automation-demo auto serve run install

install:
	python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"

# THE CERTIFICATION GATE — everything, both lanes. Unchanged: adding markers did not
# narrow what this runs, and nothing may ship on `test-fast` alone.
test:
	$(PYTEST) -q

# The inner-loop lane: every test NOT measured as slow. Runs in ~2 minutes instead of
# ~24, so it is cheap enough to run between edits. It is a FILTER, not a subset anyone
# curated — a new test is in this lane by default and leaves it only by measuring slow.
test-fast:
	$(PYTEST) -q -m "not slow"

# The other half, on its own — useful when a change is confined to the real-data path.
test-slow:
	$(PYTEST) -q -m slow

# THE DEMO-READINESS GATE: every case down the UI's own path, compared against the known
# baseline. Green = "the fleet behaves the way it behaved when we last looked"; red lists
# exactly what is NEW. Run before every client demo (see docs/engagement/demo-runbook.md).
rehearse:
	$(PY) tools/rehearse_demo.py

# Full demo: runs every scenario + the test suite and builds reports/demo/dashboard.html
demo:
	$(PY) -m case_prep.cli demo
	@echo "→ open reports/demo/dashboard.html"

# Fast demo: scenarios + dashboard only, skips the 788-test battery (~10s instead of ~17min)
demo-fast:
	$(PY) -m case_prep.cli demo --no-tests
	@echo "→ open reports/demo/dashboard.html"

# Boolean-operations demo: bore a screw channel via SDF-CSG, export STLs + a field-slice render
booleans-demo:
	$(PY) -m case_prep.cli booleans-demo
	@echo "→ open reports/booleans/csg-slice.png ; STLs in reports/booleans/stl/"

# Staged workflow on a REAL arch (provide an OBJ/STL). Emits per-stage input/output artifacts.
# usage: make workflow-real ARCH=data/real/your_arch.obj
ARCH ?= data/real/QSS7S0G2_lower.obj
workflow-real:
	$(PY) -m case_prep.cli workflow --real-arch $(ARCH) --implants 3 --retention screw
	@echo "→ artifacts in reports/workflow/work/stage1/ and stage2/"

# Real-file demo on the DG Code / Certain 3i case: our output vs the reference scan body.
# The client's own file names are spelled in exactly one place — src/case_prep/adapters/
# client_data.py, which is where the CLI's defaults come from. Set DGSCAN/DGBODY (absolute or
# relative paths) to run the demo on a different drop.
DGSCAN ?=
DGBODY ?=
real-demo:
	$(PY) -m case_prep.cli real-demo $(if $(DGSCAN),--scan "$(DGSCAN)") $(if $(DGBODY),--scanbody "$(DGBODY)")
	@echo "→ open reports/real-demo/real_demo.png ; STLs in reports/real-demo/"

# Step-by-step automation client demo on the client's real arch (auto-localize -> isolate ->
# clean-CAD align), rendering shaded step panels + a self-contained HTML/PDF report. Deterministic.
# Defaults come from adapters/client_data; set AUTO_ARCH/AUTO_LIB for a different scan/library.
AUTO_ARCH ?=
AUTO_LIB ?=
automation-demo:
	$(PY) tools/automation_demo.py $(if $(AUTO_ARCH),--arch "$(AUTO_ARCH)") $(if $(AUTO_LIB),--library "$(AUTO_LIB)")
	@echo "→ open reports/client-demo/CLIENT-REPORT-AUTOMATION.pdf"

# The clinical case flow (propose -> confirm -> package). PROPOSE mode by default; pass
# SITES="--site 8:x,y,z ..." plus CONSTRUCTION/VENDOR for the confirmed run.
AUTO_SCAN ?= data/real/scans/doctor-neodent-gm/upper_jaw.stl
AUTO_CAPS ?= data/real/library/caps/neodent-gm
auto:
	$(PY) -m case_prep.cli auto --scan "$(AUTO_SCAN)" --caps "$(AUTO_CAPS)" $(SITES)

# The live-demo API for the React app (apps/web): http://localhost:8000
serve:
	.venv/bin/uvicorn case_prep.server:app --port 8000 --app-dir src

# Quick single-case run
run:
	$(PY) -m case_prep.cli run --synthetic --seed 7 --implants 3 --retention screw
