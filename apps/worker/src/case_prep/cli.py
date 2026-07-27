"""Command-line entrypoint for the Phase 2A case-prep spike.

    case-prep run --synthetic --seed 7 --implants 3 --retention screw
    case-prep run --case path/to/case_dir

Generates (or loads) a case, runs the count->localize->align->pose->gate pipeline,
evaluates against ground truth when present, and writes the billable report artifacts.
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from datetime import datetime
from pathlib import Path

# numpy 2.0 + macOS Accelerate BLAS sets spurious FP-status flags on valid matmul;
# results are unaffected. Suppress at the app entrypoint for clean operator output.
warnings.filterwarnings("ignore", message=".*encountered in matmul.*")

from case_prep.adapters import client_data
from case_prep.adapters.report_writer import write_report
from case_prep.adapters.synthetic import SyntheticParams, generate_case
from case_prep.domain.metrics import ClinicalTolerance
from case_prep.domain.poses import Retention
from case_prep.pipeline.evaluation import evaluate_case, load_ground_truth
from case_prep.pipeline.final_product import DEFAULT_GINGIVAL_OFFSET_MM
from case_prep.pipeline.orchestrator import run_case

_DEFAULT_OUT = Path(__file__).resolve().parents[2] / "reports"


_WORKER_ROOT = Path(__file__).resolve().parents[2]


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="case-prep")
    sub = p.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("demo", help="run all demo scenarios + tests and build an HTML dashboard")
    demo.add_argument("--out", type=Path, default=_DEFAULT_OUT / "demo")
    demo.add_argument("--no-tests", action="store_true", help="skip running the test suite")

    bool_demo = sub.add_parser("booleans-demo", help="bore a screw channel via SDF-CSG; export STLs + a render")
    bool_demo.add_argument("--out", type=Path, default=_DEFAULT_OUT / "booleans")

    wf = sub.add_parser("workflow", help="run the staged workflow (stage1 -> seed -> stage2) and emit per-stage artifacts")
    wf.add_argument("--out", type=Path, default=_DEFAULT_OUT / "workflow")
    src = wf.add_mutually_exclusive_group(required=True)
    src.add_argument("--case", type=Path, help="an existing case directory")
    src.add_argument("--synthetic", action="store_true", help="generate a synthetic case")
    src.add_argument("--real-arch", type=Path, help="path to a real intraoral arch (OBJ/STL); builds a semi-real case on it")
    wf.add_argument("--implants", type=int, default=3)
    wf.add_argument("--retention", choices=[r.value for r in Retention], default="cement")
    wf.add_argument("--seed", type=int, default=1)

    rd = sub.add_parser("real-demo", help="real-file demo: our generated placement vs the reference scan body")
    # Default to the client's own drop. Their file names live in ONE module
    # (adapters/client_data) so nothing else in the project — or on a command line — has to
    # spell them; pass --scan/--scanbody to run the demo on a different case.
    rd.add_argument("--scan", type=Path, default=client_data.DG_ARCH,
                    help="the doctor's input scan (STL/OBJ); defaults to the client drop")
    rd.add_argument("--scanbody", type=Path, default=client_data.DG_SCANBODY,
                    help="the scan body (segmented) STL; defaults to the client drop")
    rd.add_argument("--out", type=Path, default=_DEFAULT_OUT / "real-demo")

    auto = sub.add_parser("auto", help="the clinical case flow: propose healing-cap sites, then "
                                       "(with --site confirmations) align, measure and emit the "
                                       "industry output package")
    auto.add_argument("--scan", type=Path, required=True, help="the doctor's arch scan (STL)")
    auto.add_argument("--caps", type=Path, help="cap library dir (<model>-<code>.stl; confirmed mode)")
    auto.add_argument("--out", type=Path, default=_DEFAULT_OUT / "auto")
    auto.add_argument("--case-id", default=None, help="package id (default: scan filename stem)")
    auto.add_argument("--jaw", choices=["upper", "lower"], default="upper")
    auto.add_argument("--construction", type=Path, help="vendor construction scan-body STL")
    auto.add_argument("--vendor", default=None, help="parts vendor (e.g. dess, atlantis)")
    auto.add_argument("--site", action="append", default=[], metavar="TOOTH:X,Y,Z[:VARIANT]",
                      help="operator-confirmed site (repeatable); optional trailing :VARIANT "
                           "is the doctor-declared size (e.g. :6030) — mismatches are flagged; "
                           "omit --site entirely to run PROPOSE mode")
    # The tissue clearance the emitted construction part carries. Exposed here (2026-07-25)
    # because it is now a JUDGED proposal: the export gate fails CLOSED when the relief
    # eats or undercuts the as-built screw channel, and MEASURED, the 0.20 default does
    # that on the whole atlantis/zimmer-4.5 fleet and on dess/neodent-gm 5020. Without a
    # flag the CLI could only ask for the one value the gate refuses on those parts.
    auto.add_argument("--gingival-offset", type=float, default=None, metavar="MM",
                      help=f"gingival profile offset in mm (default "
                           f"{DEFAULT_GINGIVAL_OFFSET_MM}; 0 disables the relief) — the "
                           f"export gate refuses a relief that destroys the screw channel")

    cmp_demo = sub.add_parser("comparison", help="emit the 5 comparison STLs (input/generated/AND/difference/modifications)")
    cmp_demo.add_argument("--out", type=Path, default=_DEFAULT_OUT / "comparison")
    cmp_demo.add_argument("--case", type=Path, help="an existing case dir; omit to generate a synthetic one")
    cmp_demo.add_argument("--seed", type=int, default=4)
    cmp_demo.add_argument("--implants", type=int, default=2)
    cmp_demo.add_argument("--retention", choices=[r.value for r in Retention], default="cement")

    run = sub.add_parser("run", help="run the case-prep pipeline and write a report")
    src = run.add_mutually_exclusive_group(required=True)
    src.add_argument("--synthetic", action="store_true", help="generate an adversarial synthetic case")
    src.add_argument("--case", type=Path, help="path to an existing case directory")
    run.add_argument("--seed", type=int, default=7)
    run.add_argument("--implants", type=int, default=3)
    run.add_argument("--retention", choices=[r.value for r in Retention], default="cement")
    run.add_argument("--noise", type=float, default=0.0, help="gaussian vertex noise stddev (mm)")
    run.add_argument("--partial", type=float, default=0.0, help="fraction of faces dropped (occlusion)")
    run.add_argument("--out", type=Path, default=_DEFAULT_OUT)
    run.add_argument("--tol-pos", type=float, default=0.2)
    run.add_argument("--tol-axis", type=float, default=2.0)
    run.add_argument("--tol-clock", type=float, default=5.0)
    return p


def _prepare_case_dir(args, stamp: str) -> Path:
    if args.case:
        return args.case
    case_dir = Path(args.out) / "cases" / f"{stamp}-synthetic-{args.seed}"
    generate_case(case_dir, SyntheticParams(
        seed=args.seed, n_implants=args.implants, retention=Retention(args.retention),
        noise_mm=args.noise, partial_fraction=args.partial,
    ))
    return case_dir


def _run_demo(args) -> int:
    from case_prep.demo.dashboard import build_dashboard
    from case_prep.demo.runner import run_demo

    out = Path(args.out)
    report = run_demo(work_dir=out / "work", worker_root=_WORKER_ROOT, run_tests=not args.no_tests)
    dashboard = build_dashboard(report, out / "dashboard.html")

    print("demo scenarios:")
    for s in report.scenarios:
        mark = "ok " if s.meets_expectation else "!! "
        print(f"  {mark}{s.name}: clear {s.clear_rate*100:.0f}% / "
              f"false-confidence {s.false_confidence_rate*100:.0f}%")
    if report.test_summary.ran:
        print(f"tests: {report.test_summary.passed}/{report.test_summary.total} passed "
              f"in {report.test_summary.duration_s:.0f}s")
    print(f"dashboard -> {dashboard}")
    return 0 if report.all_expectations_met else 1


def _run_booleans_demo(args) -> int:
    from case_prep.demo.booleans_demo import run_booleans_demo

    cases, render = run_booleans_demo(args.out)
    print("SDF-CSG screw-channel demo:")
    for c in cases:
        print(f"  {c.name}: input watertight={c.input_watertight} -> "
              f"output watertight={c.output_watertight}  "
              f"(vol {c.input_volume:.1f} -> {c.output_volume:.1f} mm³)")
        print(f"    STL: {c.output_stl}")
    if render:
        print(f"  field-slice render -> {render}")
    # the headline: a NON-watertight input still yields a watertight bored solid
    return 0 if all(c.output_watertight for c in cases) else 1


def _run_workflow(args) -> int:
    from case_prep.adapters.synthetic import SyntheticParams, generate_case
    from case_prep.pipeline.stages import run_workflow

    out = Path(args.out)
    operator = False
    if args.real_arch:
        from case_prep.adapters.real_case import build_semireal_case
        case_dir = out / "case"
        build_semireal_case(args.real_arch, case_dir, n_implants=args.implants,
                            retention=Retention(args.retention), seed=args.seed)
        operator = True  # auto-detection is brittle on dense real arches -> operator seeds
        print(f"built semi-real case on REAL arch {args.real_arch.name}")
    elif args.synthetic:
        case_dir = out / "case"
        generate_case(case_dir, SyntheticParams(seed=args.seed, n_implants=args.implants,
                                                retention=Retention(args.retention)))
    else:
        case_dir = args.case

    work = out / "work"
    s1, s2 = run_workflow(case_dir, work, operator_seeds=operator)
    print(f"stage 1  [{s1.status.value}]  detected {s1.detected_count}/{s1.declared_count} bodies")
    print(f"         artifacts: {work}/stage1/  (normalized_scan.stl, localization.json)")
    if s2 is None:
        print("  rejected at ingest — no stage 2")
        return 1
    print(f"stage 2  [{s2.status.value}]  clear-rate {s2.clear_rate*100:.0f}%")
    for r in s2.implants:
        print(f"         tooth {r['tooth']} ({r['retention']}): {r['gate']}")
    print(f"         artifacts: {work}/stage2/  (01_input … 04_difference.stl, result.json)")
    return 0


def _run_comparison(args) -> int:
    import tempfile
    from case_prep.adapters.synthetic import SyntheticParams, generate_case
    from case_prep.demo.comparison import emit_comparison_artifacts

    if args.case:
        case_dir = args.case
    else:
        case_dir = Path(tempfile.mkdtemp()) / "case"
        generate_case(case_dir, SyntheticParams(seed=args.seed, n_implants=args.implants,
                                                retention=Retention(args.retention)))
    paths = emit_comparison_artifacts(case_dir, args.out)
    print("comparison artifacts (open each in a 3D viewer):")
    for key, p in paths.items():
        print(f"  {key:13s} -> {p}")
    return 0


def _run_auto(args) -> int:
    import json as _json

    import trimesh as _trimesh

    from case_prep.adapters.cap_library import CapLibrary
    from case_prep.pipeline.auto_flow import ConfirmedSite, propose_sites, run_auto_case

    scan = _trimesh.load(args.scan, force="mesh")
    case_id = args.case_id or Path(args.scan).stem.replace(" ", "_")

    if not args.site:  # PROPOSE mode: rank candidates for the operator, then stop
        proposals = propose_sites(scan.vertices, normals=scan.vertex_normals)
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / f"{case_id}-proposals.json").write_text(_json.dumps(
            [{"center": list(p.center), "void_ratio": p.void_ratio,
              "rim_below_cusps_mm": p.rim_below_cusps_mm} for p in proposals], indent=2))
        print(f"{len(proposals)} proposed healing-cap site(s) — confirm each with --site:")
        for p in proposals:
            c = ",".join(f"{x:.1f}" for x in p.center)
            print(f"  --site TOOTH:{c}   (void={p.void_ratio:.2f}, "
                  f"below-cusps={p.rim_below_cusps_mm:.1f}mm)")
        print(f"proposals -> {args.out / f'{case_id}-proposals.json'}")
        return 0

    if not (args.caps and args.construction and args.vendor):
        print("confirmed run needs --caps <dir>, --construction <stl> and --vendor <name>")
        return 2
    confirmed = []
    for raw in args.site:
        try:
            parts = raw.split(":")
            if len(parts) not in (2, 3):
                raise ValueError
            tooth = int(parts[0])
            coords = tuple(float(v) for v in parts[1].split(","))
            declared = parts[2] if len(parts) == 3 and parts[2] else None
            if not (1 <= tooth <= 32) or len(coords) != 3:
                raise ValueError
        except ValueError:
            print(f"bad --site {raw!r}: expected TOOTH:X,Y,Z[:VARIANT] with 1<=TOOTH<=32 "
                  f"and 3 coordinates")
            return 2
        confirmed.append(ConfirmedSite(tooth=tooth, center=coords, declared_variant=declared))
    offset = (DEFAULT_GINGIVAL_OFFSET_MM if args.gingival_offset is None
              else float(args.gingival_offset))
    # loaded OUTSIDE the try so the catch below stays narrow to the PIPELINE's refusals —
    # a malformed library is a different failure and must not read as a gate answer
    library = CapLibrary.load(args.caps)
    construction = _trimesh.load(args.construction, force="mesh")
    try:
        summary = run_auto_case(
            case_id=case_id, scan=scan, library=library,
            construction_mesh=construction,
            vendor=args.vendor, confirmed=confirmed, jaw_label=args.jaw, out_dir=args.out,
            gingival_offset_mm=offset)
    except ValueError as exc:
        # The pipeline's REFUSALS travel as ValueError with a human message — the export
        # gates ("package NOT emitted": a catastrophic design-rule violation, or a
        # gingival relief that ate the screw channel) and "no confirmed site could be
        # aligned". Same contract the server turns into a 409 (server.py's /run): they
        # are answers to the operator, so the CLI PRINTS the gate's own words and exits
        # non-zero instead of dumping a traceback the sentence is buried in.
        print(f"refused: {exc}")
        return 2
    for site in summary["sites"]:
        m = site.get("site_measurement", {})
        print(f"  tooth {site['tooth']}: {site['spec']} coverage={site['coverage']:.2f} "
              f"ADVISORY  md_span={m.get('md_span_mm')} [{m.get('classification')}]")
    # THE CLAMP IS NOT A FOOTNOTE (2026-07-25). The run completes when the requested relief
    # exceeds a part's safe ceiling, so the terminal must say the operator got a different
    # number than they asked for — a clamp discovered later in a JSON file is a silent
    # substitution in everything but name.
    relief = summary.get("gingival_relief") or {}
    if relief.get("clamped"):
        print(f"CLAMPED: {relief['clamp_reason']}")
    print(f"package ({len(summary['package_files'])} files) -> {args.out}")
    return 0


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "demo":
        return _run_demo(args)
    if args.command == "auto":
        return _run_auto(args)
    if args.command == "booleans-demo":
        return _run_booleans_demo(args)
    if args.command == "workflow":
        return _run_workflow(args)
    if args.command == "real-demo":
        from case_prep.demo.real_demo import run_real_demo
        r = run_real_demo(args.scan, args.scanbody, args.out)
        print("real-file demo — our output vs the reference scan body:")
        print(f"  position error: {r['position_error_mm']:.2f} mm")
        print(f"  axis error:     {r['axis_error_deg']:.1f} deg")
        print(f"  ICP fitness {r['icp_fitness']:.2f}  surface RMSE {r['rmse_mm']:.3f} mm")
        print(f"  artifacts: {args.out}/  (01_input … 05_error.stl)")
        if r["render"]:
            print(f"  render: {r['render']}")
        return 0
    if args.command == "comparison":
        return _run_comparison(args)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    case_dir = _prepare_case_dir(args, stamp)
    result = run_case(case_dir)
    report_dir = Path(args.out) / f"{stamp}-{result.case_ref}"

    gt_path = Path(case_dir) / "ground_truth.json"
    if gt_path.exists():
        tol = ClinicalTolerance(args.tol_pos, args.tol_axis, args.tol_clock)
        ev = evaluate_case(result, load_ground_truth(case_dir), tol)
        paths = write_report(report_dir, result, ev)
        print(f"case {result.case_ref}: count "
              f"{'reconciled' if result.count_match else 'MISMATCH'} "
              f"({result.detected_count}/{result.declared_count})")
        if ev.shadow_false_confidence_rate is not None:
            # advisory case: nothing auto-passes, so the classic rate reads 0% by construction —
            # the SHADOW rate (what the gate WOULD have passed) is the number that matters here
            print(f"  ADVISORY (routed to human)  "
                  f"shadow-false-confidence {ev.shadow_false_confidence_rate*100:.0f}%")
        else:
            print(f"  clear-rate {ev.clear_rate*100:.0f}%  "
                  f"false-confidence {ev.false_confidence_rate*100:.0f}%")
        for r in ev.implants:
            print(f"  tooth {r.tooth} ({r.retention}): {r.position_error_mm:.3f}mm / "
                  f"{r.axis_error_deg:.2f}deg  {'PASS' if r.gate_passed else 'FLAG'}")
        for u in result.unresolved_sites:
            print(f"  tooth {u.tooth} ({u.retention.value}): UNRESOLVED — {u.reason}")
        print(f"  artifacts -> {paths['json'].parent}")
    else:
        # real case without ground truth: emit the prepared poses + gate, no accuracy
        report_dir.mkdir(parents=True, exist_ok=True)
        prepared = {
            "case_ref": result.case_ref,
            "count_match": result.count_match,
            "implants": [
                {"tooth": reg.tooth, "retention": reg.retention.value,
                 "position": reg.pose.position,
                 "axis": [float(x) for x in reg.pose.axis.direction],
                 "clocking_degrees": reg.pose.clocking_degrees,
                 "gate_passed": decision.passed, "gate_reasons": decision.reasons}
                for reg, decision in result.gated
            ],
        }
        (report_dir / "prepared-case.json").write_text(json.dumps(prepared, indent=2))
        print(f"case {result.case_ref}: prepared {len(result.implants)} implant(s) "
              f"(no ground truth — accuracy not evaluated) -> {report_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
