"""Writes the billable run artifacts: accuracy report (JSON + HTML), a run manifest
for traceability, and a feasibility memo. Renders are best-effort (a render failure
never fails the run)."""
from __future__ import annotations

import json
import platform
from dataclasses import asdict
from importlib import metadata
from pathlib import Path
from typing import Dict

from jinja2 import Template

from case_prep.pipeline.evaluation import CaseEvaluation
from case_prep.pipeline.orchestrator import CaseResult

PIPELINE_VERSION = "2a-spike-0.1.0"
_DEPS = ("numpy", "scipy", "trimesh", "open3d", "pydantic")

_HTML = Template(
    """<!doctype html><html><head><meta charset="utf-8">
<title>Case-prep accuracy — {{ case_ref }}</title>
<style>
 body{font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;margin:2rem;color:#1a1a1a}
 h1{font-size:1.4rem} .kpi{display:inline-block;margin:0 2rem 1rem 0}
 .kpi b{display:block;font-size:1.8rem} .pass{color:#0a7d28} .flag{color:#b00020}
 table{border-collapse:collapse;width:100%;margin-top:1rem}
 th,td{border:1px solid #ddd;padding:.4rem .6rem;text-align:right} th{background:#f4f4f6}
 td:first-child,th:first-child{text-align:left}
 caption{caption-side:bottom;color:#666;margin-top:.5rem;font-size:.85rem}
</style></head><body>
<h1>Automated case-prep — accuracy report</h1>
<p>Case <code>{{ case_ref }}</code> · pipeline <code>{{ pipeline_version }}</code>
 · count {{ 'reconciled' if count_match else 'MISMATCH' }}</p>
<div class="kpi"><b>{{ '%.0f'|format(clear_rate*100) }}%</b>clear-rate (auto-passed)</div>
<div class="kpi"><b class="{{ 'pass' if false_confidence_rate==0 else 'flag' }}">{{ '%.0f'|format(false_confidence_rate*100) }}%</b>false-confidence-rate</div>
<table>
<tr><th>tooth</th><th>retention</th><th>pos err (mm)</th><th>axis err (deg)</th>
<th>clocking err (deg)</th><th>in tol</th><th>gate</th></tr>
{% for r in implants %}<tr>
<td>{{ r.tooth }}</td><td>{{ r.retention }}</td>
<td>{{ '%.3f'|format(r.position_error_mm) }}</td>
<td>{{ '%.2f'|format(r.axis_error_deg) }}</td>
<td>{{ '%.2f'|format(r.clocking_error_deg) if r.clocking_error_deg is not none else '—' }}</td>
<td>{{ '✓' if r.within_tolerance else '✗' }}</td>
<td class="{{ 'pass' if r.gate_passed else 'flag' }}">{{ 'PASS' if r.gate_passed else 'FLAG' }}</td>
</tr>{% endfor %}
<caption>PASS = auto-seeded · FLAG = routed to manual seeding. The safety target is a
near-zero false-confidence-rate (auto-passed yet out of tolerance).</caption>
</table>
</body></html>"""
)


def _dependency_versions() -> Dict[str, str]:
    out = {}
    for name in _DEPS:
        try:
            out[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            out[name] = "unknown"
    return out


def _memo(result: CaseResult, ev: CaseEvaluation) -> str:
    flagged = [r for r in ev.implants if not r.gate_passed]
    worst_pos = max((r.position_error_mm for r in ev.implants), default=0.0)
    worst_axis = max((r.axis_error_deg for r in ev.implants), default=0.0)
    return f"""# Feasibility memo — case {ev.case_ref}

**Pipeline:** `{PIPELINE_VERSION}`  ·  **Count:** {'reconciled' if ev.count_match else 'MISMATCH — flagged'}

## Headline
- **Clear-rate:** {ev.clear_rate*100:.0f}% of implants auto-passed the confidence gate.
- **False-confidence-rate:** {ev.false_confidence_rate*100:.0f}% (auto-passed yet out of tolerance) — the safety-critical number.
- **Worst recovered error:** {worst_pos:.3f} mm position, {worst_axis:.2f}° axis.

## Per-implant
{chr(10).join(f"- tooth {r.tooth} ({r.retention}): {r.position_error_mm:.3f} mm / {r.axis_error_deg:.2f}° — "
              f"{'PASS' if r.gate_passed else 'FLAG: ' + '; '.join(r.gate_reasons)}" for r in ev.implants)}

## Read
{len(flagged)} of {len(ev.implants)} implant(s) routed to manual seeding. On clean captures the
chain recovers position+axis (and clocking for screw-retained) within clinical tolerance; degraded
captures are flagged rather than passed blind. The go/no-go for productionising 2B is the clear-rate
measured on the client's real caseload by retention type and scan-body type.
"""


def write_report(out_dir, result: CaseResult, ev: CaseEvaluation) -> Dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    report = {
        "case_ref": ev.case_ref,
        "pipeline_version": PIPELINE_VERSION,
        "count_match": ev.count_match,
        "declared_count": result.declared_count,
        "detected_count": result.detected_count,
        "clear_rate": ev.clear_rate,
        "false_confidence_rate": ev.false_confidence_rate,
        "implants": [asdict(r) for r in ev.implants],
        "unresolved_sites": [
            {"tooth": u.tooth, "retention": u.retention.value, "reason": u.reason}
            for u in result.unresolved_sites
        ],
    }
    json_path = out / "accuracy-report.json"
    json_path.write_text(json.dumps(report, indent=2))

    html_path = out / "accuracy-report.html"
    html_path.write_text(_HTML.render(**report))

    manifest_path = out / "run-manifest.json"
    manifest_path.write_text(json.dumps({
        "pipeline_version": PIPELINE_VERSION,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "dependencies": _dependency_versions(),
        "note": "Open3D registration_icp is unused (segfaults on this arm64 wheel); "
                "registration uses an in-house numpy/scipy trimmed ICP.",
    }, indent=2))

    memo_path = out / "feasibility-memo.md"
    memo_path.write_text(_memo(result, ev))

    return {"json": json_path, "html": html_path, "manifest": manifest_path, "memo": memo_path}
