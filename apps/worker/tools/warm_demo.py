"""Pre-warm the live-demo caches: run propose + the full automation for both demo cases so
the React demo responds instantly in front of the client (results are the same live pipeline
output, computed ahead of time; the UI offers a 'fresh' re-run for proof-it's-live moments).

    .venv/bin/python tools/warm_demo.py
"""
from __future__ import annotations

import warnings

# numpy on macOS Accelerate raises spurious "encountered in matmul" warnings on valid
# data (verified: results correct) — same filter as cli.py / pyproject pytest config
warnings.filterwarnings("ignore", message=".*encountered in matmul.*")


from case_prep.server import CASES, RunIn, SiteIn, propose, run

for case_id, cfg in CASES.items():
    print(f"== warming {case_id} ==")
    p = propose(case_id)
    note = "cached" if p.get("cached") else f"{p['duration_s']}s"
    print(f"   propose: {len(p['proposals'])} proposal(s) ({note})")
    # THE SELECTION IS EXPLICIT (client directive 2026-07-25): the run refuses to guess a
    # library or a construction part. Warming a case therefore means ACCEPTING the case's
    # suggestion on the operator's behalf and saying so; a case the name match cannot
    # suggest for is left to a human — there is nothing to pre-warm without a choice.
    if not (cfg["suggested_model"] and cfg["suggested_construction"]):
        print(f"   run: skipped — no suggested selection (model="
              f"{cfg['suggested_model']!r}, construction="
              f"{cfg['suggested_construction']!r}); the operator must choose")
        continue
    # The relief CLAMP (2026-07-25) makes this total: the run applies min(requested,
    # per-part ceiling) and reports both, so warming at the client's 0.20mm default
    # completes on every case — measured 9/9, 5 sites clamped to their 0.05-0.08mm
    # ceilings. The gate still refuses a part unshippable at ANY offset; nothing in
    # this catalog is.
    r = run(case_id, RunIn(sites=[SiteIn(**s) for s in cfg["suggested_sites"]],
                           model=cfg["suggested_model"],
                           construction_path=cfg["suggested_construction"],
                           jaw=cfg["jaw"],
                           gingival_offset_mm=0.20))
    ok = [x for x in r["summary"]["sites"] if "spec" in x]
    clamped = [x for x in r["summary"]["sites"]
               if (x.get("production") or {}).get("gingival_offset_clamped")]
    relief = ""
    if clamped:
        applied = sorted({(x.get("production") or {}).get("gingival_offset_applied_mm")
                          for x in clamped})
        relief = f", relief 0.20mm CLAMPED to {applied} on {len(clamped)} site(s)"
    print(f"   run: {len(ok)} site(s), {len(r['summary']['package_files'])} files"
          f"{relief} "
          f"({'cached' if r.get('cached') else str(r['duration_s']) + 's'})")
print("warm.")
