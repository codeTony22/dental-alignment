"""ZERO-DIFF RECEIPT: the shipped pose matrices of a fixed set of REAL sites.

A refactor of the winner pass (or of how the pipeline draws its random numbers) is only
allowed to change the SHAPE of the code, never the part that gets machined. This tool
records what actually ships — the world-frame 4x4 pose written into each site's paid
record — as exact bytes (``float.hex()``: no decimal rounding, so "identical" means
identical, not "agrees to 6 places").

    PYTHONWARNINGS=ignore .venv/bin/python tools/pose_receipt.py --out after.json
    PYTHONWARNINGS=ignore .venv/bin/python tools/pose_receipt.py \\
        --compare reports/receipts/winner-poses-baseline.json after.json

``reports/receipts/winner-poses-baseline.json`` is the recorded pre-hygiene state
(2026-07-25, before the RNG injection / winner-pass extraction / renames);
``winner-poses-after-hygiene.json`` is the same four sites after, byte-for-byte equal.

The sites are three real client cases across BOTH implant systems and both seat paths,
chosen so a refactor that only works on one library cannot look clean. Runs are
deterministic by the pipeline's own seeding contract; ``compute_confidence`` and
``render_qc`` are off (neither moves a pose, both cost seconds).

Research/verification code — never imported by the pipeline.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import trimesh

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from case_prep.adapters.cap_library import CapLibrary  # noqa: E402
from case_prep.pipeline.auto_flow import ConfirmedSite, run_auto_case  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

# folder -> implant system. Both systems, both jaws, four sites total: one AUTO-mode site
# (no declared variant, so the whole catalog competes) and three declared-variant sites.
CASES = (
    ("doctor-neodent-gm", "neodent-gm"),
    ("doctor-zimmer-4.5", "zimmer-4.5"),
    ("doctor-cap6020-neodent-gm", "neodent-gm"),
)


def _hex_matrix(m) -> list:
    """Exact bytes of a 4x4, row-major. float.hex() round-trips losslessly."""
    return [float(v).hex() for v in np.asarray(m, float).reshape(-1)]


def capture() -> dict:
    receipt = {}
    for folder, model in CASES:
        case_dir = ROOT / "data/real/scans" / folder
        scan = trimesh.load(next(case_dir.glob("*.stl")), force="mesh")
        lib = CapLibrary.load(ROOT / "data/real/library/caps" / model)
        vendor_part = next((ROOT / "data/real/library/construction").glob(
            f"*/{model}-scanbody.stl"))
        sites = json.loads((case_dir / "sites.json").read_text())["suggested_sites"]
        confirmed = [ConfirmedSite(s["tooth"], tuple(s["center"]),
                                   s.get("declared_variant"),
                                   center_mark=s.get("center_mark"),
                                   rim_mark=s.get("rim_mark"),
                                   rim_points=s.get("rim_points")) for s in sites]
        tmp = Path(tempfile.mkdtemp())
        out = run_auto_case(case_id="receipt", scan=scan, library=lib,
                            construction_mesh=trimesh.load(vendor_part, force="mesh"),
                            vendor=vendor_part.parent.name, confirmed=confirmed,
                            jaw_label="x", out_dir=tmp / "out",
                            # 0.00 relief: the shipped 0.20 trips the thin-wall export
                            # gate on one of these real sites and no package is emitted
                            # at all. The relief is applied AFTER every pose is final
                            # (and behind its own seeded shim), so it cannot move the
                            # matrices this receipt records.
                            gingival_offset_mm=0.0,
                            compute_confidence=False, render_qc=False)
        for site in sites:
            key = f"{folder}/t{site['tooth']}"
            rec_path = tmp / "out" / f"receipt-{site['tooth']}-implant.json"
            if not rec_path.exists():
                receipt[key] = {"error": "no paid record emitted"}
                continue
            rec = json.loads(rec_path.read_text())
            row = next(r for r in out["sites"] if r["tooth"] == site["tooth"])
            receipt[key] = {
                "pose_matrix_hex": _hex_matrix(rec["pose_matrix"]),
                "variant": row["variant"]["identified"],
                "seat_method": row["seat_method"],
            }
    return receipt


def compare(before: dict, after: dict) -> int:
    keys = sorted(set(before) | set(after))
    bad = 0
    for k in keys:
        b, a = before.get(k), after.get(k)
        if b == a:
            print(f"  IDENTICAL  {k}  ({(a or {}).get('variant')}, "
                  f"{(a or {}).get('seat_method')})")
        else:
            bad += 1
            print(f"  CHANGED    {k}")
            print(f"    before: {b}")
            print(f"    after:  {a}")
    print(f"\n{len(keys) - bad}/{len(keys)} sites byte-identical")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, help="write a receipt here")
    ap.add_argument("--compare", nargs=2, type=Path, metavar=("BEFORE", "AFTER"))
    args = ap.parse_args()
    if args.compare:
        return 1 if compare(json.loads(args.compare[0].read_text()),
                            json.loads(args.compare[1].read_text())) else 0
    receipt = capture()
    text = json.dumps(receipt, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text)
        print(f"wrote {args.out} ({len(receipt)} sites)")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
