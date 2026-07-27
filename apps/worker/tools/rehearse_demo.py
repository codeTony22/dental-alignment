"""THE DEMO-READINESS GATE — drive every case down the UI's own path and compare against
the known baseline. "Predictable demo" means exactly this: before showing anyone, one command
answers "is the fleet behaving the way it behaved when we last looked?"

    make rehearse            (from apps/worker)

What it exercises, per case, in the order the React demo does:
  library catalog -> constructions -> relief ceiling -> pre-run preview (only where the UI
  could fire one) -> run -> per-site deviation payload (incl. the pose block the verify
  panes frame with).

The verdict distinguishes KNOWN flags from NEW ones. A site the pipeline honestly flags —
an unverified rotation, an attention gate — is part of the demo SCRIPT, not a failure; the
gate only goes red when something appears that was not there at the last baseline, because
that is the thing that embarrasses you live. Baseline measured 2026-07-26 (10 sites: all
rim seats, 7/7 declared==identified, rotation code-verified on 8/10 within 3.1 degrees).

Runs against the CODE via TestClient — it certifies the tree, not the running server.
The runbook (docs/engagement/demo-runbook.md) covers restarting + warming the live one.
"""
from __future__ import annotations

import sys
import time
import warnings

warnings.filterwarnings("ignore", message=".*encountered in matmul.*")
sys.path.insert(0, "src")

from fastapi.testclient import TestClient  # noqa: E402

from case_prep.server import app  # noqa: E402

# The accepted baseline: (case_id, tooth) -> the flags we EXPECT and talk through in the
# demo script. Anything beyond these is NEW and turns the gate red. Update this dict only
# after reading the new finding and deciding it belongs in the script.
KNOWN_FLAGS: dict[tuple[str, int], set[str]] = {
    ("297589851-neodent-gm", 20): {"gate=attention", "undeclared"},
    ("neodent-gm", 4): {"gate=attention", "undeclared", "no-confidence",
                        "shared-construction"},
    ("neodent-gm", 13): {"shared-construction"},
    ("cap7030-zimmer-4.5", 29): {"rotation-unverified", "gate=attention"},
    ("zimmer-4.5", 7): {"rotation-unverified", "gate=attention"},
}

# Clamps are DISCLOSURES, not problems — the wall rule doing its job. Listed so a clamp
# APPEARING OR MOVING is still caught (a changed catalog or rule would change these).
KNOWN_CLAMPS: dict[tuple[str, int], float] = {
    # warm_demo has reported "5 sites clamped" since the ceiling landed (2026-07-25);
    # values re-measured from the run payloads on this gate's first calibration run.
    ("276794487-zimmer-4.5", 3): 0.08,
    ("cap7020-zimmer-4.5", 3): 0.08,
    ("cap7030-zimmer-4.5", 29): 0.08,
    ("zimmer-4.5", 7): 0.08,
    ("neodent-gm", 13): 0.05,
}


def main() -> int:
    c = TestClient(app)
    cases = c.get("/api/cases").json()
    new_problems: list[str] = []
    seen_flags: list[str] = []
    t_start = time.time()
    print(f"rehearsing {len(cases)} cases\n", flush=True)

    for case in cases:
        cid = case["id"]
        model = case.get("suggested_model")
        construction = case.get("suggested_construction")
        sites = case.get("suggested_sites") or []
        if not (model and construction and sites):
            new_problems.append(f"{cid}: no suggested selection")
            continue

        lib = c.get(f"/api/library?model={model}")
        if lib.status_code != 200 or not lib.json():
            new_problems.append(f"{cid}: library {lib.status_code}")
        if c.get("/api/constructions").status_code != 200:
            new_problems.append(f"{cid}: constructions failed")

        # one ceiling per declared cap — the endpoint's contract is (construction, model,
        # variant), singular, exactly as the UI asks it
        for d in {s.get("declared_variant") for s in sites} - {None}:
            rl = c.get(f"/api/relief-limit?model={model}"
                       f"&construction_path={construction}&variant={d}")
            if rl.status_code != 200:
                new_problems.append(f"{cid}: relief-limit({d}) {rl.status_code}")

        # The pre-run preview — only where the UI could fire one (a declared variant).
        s0 = sites[0]
        if s0.get("declared_variant"):
            pv = c.post(
                f"/api/cases/{cid}/sites/{s0['tooth']}/preview-alignment",
                json={"sites": sites, "model": model,
                      "construction_path": construction, "jaw": case["jaw"]})
            if pv.status_code != 200:
                new_problems.append(f"{cid}: preview {pv.status_code}")

        rr = c.post(f"/api/cases/{cid}/run",
                    json={"sites": sites, "model": model,
                          "construction_path": construction, "jaw": case["jaw"],
                          "gingival_offset_mm": 0.20})
        if rr.status_code != 200:
            new_problems.append(f"{cid}: RUN {rr.status_code}: {rr.text[:120]}")
            continue

        for s in rr.json()["summary"]["sites"]:
            tooth = s["tooth"]
            key = (cid, tooth)
            flags: set[str] = set()
            prod = s.get("production") or {}
            clk = s.get("clocking") or {}
            var = s.get("variant") or {}
            gate = (s.get("guidance") or {}).get("level")

            if s.get("seat_method") != "rim":
                flags.add(f"seat={s.get('seat_method')}")
            if var.get("declared") is None:
                flags.add("undeclared")
            elif var.get("identified") and var["declared"] != var["identified"]:
                flags.add(f"declared!=identified({var['declared']}/{var['identified']})")
            if clk.get("rotation_unverified"):
                flags.add("rotation-unverified")
            if gate not in ("ready", None):
                flags.add(f"gate={gate}")
            if s.get("confidence") is None:
                flags.add("no-confidence")
            if "shared across sites" in str(prod.get("note") or ""):
                flags.add("shared-construction")

            if prod.get("clamped"):
                applied = prod.get("gingival_offset_applied_mm")
                expect = KNOWN_CLAMPS.get(key)
                if expect is None or abs(applied - expect) > 1e-6:
                    new_problems.append(
                        f"{cid} t{tooth}: clamp changed — applied {applied} "
                        f"(baseline {expect})")
            elif key in KNOWN_CLAMPS:
                new_problems.append(f"{cid} t{tooth}: expected clamp missing")

            dv = c.get(f"/api/cases/{cid}/sites/{tooth}/deviation")
            if dv.status_code != 200:
                new_problems.append(f"{cid} t{tooth}: deviation {dv.status_code}")
            elif not dv.json().get("pose"):
                # the verify panes frame down this — a payload without it silently
                # degrades all three panes to the 6-42 degree occlusal proxy
                new_problems.append(f"{cid} t{tooth}: deviation has no pose block")

            known = KNOWN_FLAGS.get(key, set())
            fresh = flags - known
            stale = known - flags
            for f in sorted(flags & known):
                seen_flags.append(f"{cid} t{tooth}: {f} (known — in the script)")
            for f in sorted(fresh):
                new_problems.append(f"{cid} t{tooth}: NEW {f}")
            for f in sorted(stale):
                # a flag that VANISHED is information too — the script mentions it
                seen_flags.append(f"{cid} t{tooth}: baseline flag gone: {f}")
        print(f"  {cid:34s} done", flush=True)

    print(f"\n{time.time() - t_start:.0f}s total")
    if seen_flags:
        print("\nknown flags (the demo script covers these):")
        for f in seen_flags:
            print(f"  - {f}")
    if new_problems:
        print("\nNEW since baseline — read before demoing:")
        for p in new_problems:
            print(f"  ! {p}")
        return 1
    print("\nREHEARSAL CLEAN — fleet matches the baseline. Demo away.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
