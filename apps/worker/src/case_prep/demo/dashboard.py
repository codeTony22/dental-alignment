"""Builds a single self-contained HTML dashboard from a DemoReport: scenario story +
renders + accuracy tables + the test-suite report, grouped by test file. Images are
embedded as base64 so the file is portable — just open it in a browser.
"""
from __future__ import annotations

import base64
import re
from collections import defaultdict
from pathlib import Path

from jinja2 import Template

from case_prep.demo.runner import DemoReport

_TEMPLATE = Template(r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Case-prep demo dashboard</title>
<style>
 :root{--pass:#0a7d28;--flag:#b00020;--ink:#1a1a1a;--mut:#666;--line:#e3e3e8;--bg:#fafafb}
 *{box-sizing:border-box} body{font:14px/1.55 -apple-system,Segoe UI,Roboto,sans-serif;color:var(--ink);margin:0;background:var(--bg)}
 .wrap{max-width:1060px;margin:0 auto;padding:2rem 1.5rem 4rem}
 h1{font-size:1.6rem;margin:0 0 .25rem} .sub{color:var(--mut);margin:0 0 1.5rem}
 .banner{padding:1rem 1.25rem;border-radius:10px;color:#fff;font-weight:600;margin-bottom:1.5rem}
 .banner.ok{background:var(--pass)} .banner.bad{background:var(--flag)}
 .kpis{display:flex;gap:1rem;flex-wrap:wrap;margin-bottom:2rem}
 .kpi{flex:1;min-width:150px;background:#fff;border:1px solid var(--line);border-radius:10px;padding:.9rem 1.1rem}
 .kpi b{display:block;font-size:1.7rem;line-height:1.1} .kpi span{color:var(--mut);font-size:.85rem}
 .card{background:#fff;border:1px solid var(--line);border-radius:12px;padding:1.25rem 1.4rem;margin-bottom:1.25rem}
 .card h3{margin:.1rem 0 .2rem;font-size:1.15rem} .desc{color:var(--mut);margin:.2rem 0 .9rem}
 .badge{display:inline-block;padding:.12rem .55rem;border-radius:999px;font-size:.78rem;font-weight:700;color:#fff;vertical-align:middle}
 .badge.ok{background:var(--pass)} .badge.bad{background:var(--flag)} .badge.warn{background:#9a6b00}
 .meta{color:var(--mut);font-size:.85rem;margin:.2rem 0 .8rem}
 img.render{width:100%;border:1px solid var(--line);border-radius:8px;background:#fff;margin:.4rem 0 .9rem}
 table{border-collapse:collapse;width:100%;font-size:.9rem} th,td{border:1px solid var(--line);padding:.35rem .55rem;text-align:right}
 td:first-child,th:first-child{text-align:left} th{background:#f4f4f6}
 td.pass{color:var(--pass);font-weight:600} td.flag{color:var(--flag);font-weight:600}
 .reasons{color:var(--flag);font-size:.82rem;margin-top:.4rem}
 details{margin-top:.5rem} summary{cursor:pointer;font-weight:600;color:var(--mut)}
 .tfile{margin:.5rem 0 .2rem;font-weight:600} .tlist{columns:2;font-size:.82rem;color:var(--mut)}
 .tlist .p::before{content:"✓ ";color:var(--pass)} .tlist .f::before{content:"✗ ";color:var(--flag)}
 footer{color:var(--mut);font-size:.8rem;margin-top:2rem;border-top:1px solid var(--line);padding-top:1rem}
</style></head><body><div class="wrap">
<h1>Automated case-prep — demo dashboard</h1>
<p class="sub">Pipeline: count → localize → align → 6-DoF pose → retention-aware gate → report. Each scenario is checked against a stated expectation.</p>

<div class="banner {{ 'ok' if all_ok else 'bad' }}">
 {{ '✓ All scenario expectations met' if all_ok else '✗ Some scenario expectations not met' }}
 {%- if tests.ran %} · tests {{ tests.passed }}/{{ tests.total }} passed{% if tests.failed %} ({{ tests.failed }} failed){% endif %}{% endif %}
</div>

<div class="kpis">
 <div class="kpi"><b>{{ scenarios|length }}</b><span>scenarios</span></div>
 <div class="kpi"><b>{{ scenarios|selectattr('meets_expectation')|list|length }}/{{ scenarios|length }}</b><span>expectations met</span></div>
 <div class="kpi"><b>{{ '%.0f'|format(worst_false_conf*100) }}%</b><span>worst false-confidence</span></div>
 {% if tests.ran %}<div class="kpi"><b>{{ tests.passed }}/{{ tests.total }}</b><span>tests passed · {{ '%.0f'|format(tests.duration_s) }}s</span></div>{% endif %}
</div>

{% for s in scenarios %}
<div class="card">
 <h3>{{ s.name }} <span class="badge {{ 'ok' if s.meets_expectation else 'bad' }}">{{ 'EXPECTED' if s.meets_expectation else 'UNEXPECTED' }}</span></h3>
 <p class="desc">{{ s.description }}</p>
 <p class="meta">clear-rate <b>{{ '%.0f'|format(s.clear_rate*100) }}%</b> ·
  false-confidence <b>{{ '%.0f'|format(s.false_confidence_rate*100) }}%</b> ·
  count {{ 'reconciled' if s.count_match else 'MISMATCH' }} ({{ s.detected_count }}/{{ s.declared_count }})
  · <span style="color:var(--mut)">expect: {{ s.expectation }}</span></p>
 {% if s.render_b64 %}<img class="render" alt="render" src="data:image/png;base64,{{ s.render_b64 }}">{% endif %}
 <table><tr><th>tooth</th><th>retention</th><th>pos err (mm)</th><th>axis err (°)</th><th>clock err (°)</th><th>in tol</th><th>gate</th></tr>
 {% for r in s.implants %}<tr>
  <td>{{ r.tooth }}</td><td>{{ r.retention }}</td>
  <td>{{ '%.3f'|format(r.position_error_mm) }}</td><td>{{ '%.2f'|format(r.axis_error_deg) }}</td>
  <td>{{ '%.2f'|format(r.clocking_error_deg) if r.clocking_error_deg is not none else '—' }}</td>
  <td>{{ '✓' if r.within_tolerance else '✗' }}</td>
  <td class="{{ 'pass' if r.gate_passed else 'flag' }}">{{ 'PASS' if r.gate_passed else 'FLAG' }}</td>
 </tr>{% endfor %}</table>
 {% for r in s.implants if r.gate_reasons %}<div class="reasons">#{{ r.tooth }}: {{ r.gate_reasons|join('; ') }}</div>{% endfor %}
 {% for u in s.unresolved %}<div class="reasons">tooth {{ u.tooth }} ({{ u.retention }}): UNRESOLVED — {{ u.reason }}</div>{% endfor %}
</div>
{% endfor %}

{% if tests.ran %}
<div class="card">
 <h3>Test suite <span class="badge {{ 'ok' if tests.failed == 0 else 'bad' }}">{{ tests.passed }}/{{ tests.total }}</span></h3>
 <p class="meta">{{ tests.passed }} passed, {{ tests.failed }} failed in {{ '%.1f'|format(tests.duration_s) }}s across {{ test_files|length }} files.</p>
 <details><summary>Per-file breakdown ({{ test_files|length }} files — click to expand)</summary>
 {% for f, items in test_files.items() %}
  <div class="tfile">{{ f }} <span style="color:var(--mut);font-weight:400">({{ items|selectattr('1','equalto','passed')|list|length }}/{{ items|length }})</span></div>
  <div class="tlist">{% for name, outcome in items %}<div class="{{ 'p' if outcome == 'passed' else 'f' }}">{{ name }}</div>{% endfor %}</div>
 {% endfor %}
 </details>
</div>
{% endif %}

<footer>Generated by <code>case-prep demo</code> · pipeline <code>2a-spike</code>. Renders are best-effort matplotlib (Open3D offscreen unavailable on this host). Ground truth is held out from the pipeline and used only for these accuracy numbers.</footer>
</div></body></html>""")


def _b64(path) -> str:
    if not path:
        return ""
    p = Path(path)
    if not p.exists():
        return ""
    return base64.b64encode(p.read_bytes()).decode("ascii")


def _group_tests(tests):
    grouped = defaultdict(list)
    for t in tests:
        nodeid = t["name"]
        file = nodeid.split("::", 1)[0]
        name = nodeid.split("::", 1)[1] if "::" in nodeid else nodeid
        grouped[file].append((name, t["outcome"]))
    return dict(sorted(grouped.items()))


def build_dashboard(report: DemoReport, out_path) -> Path:
    scenarios = []
    for s in report.scenarios:
        scenarios.append({**s.__dict__, "render_b64": _b64(s.render_path)})

    worst_false_conf = max((s.false_confidence_rate for s in report.scenarios), default=0.0)
    html = _TEMPLATE.render(
        scenarios=scenarios,
        tests=report.test_summary,
        test_files=_group_tests(report.test_summary.tests),
        all_ok=report.all_expectations_met,
        worst_false_conf=worst_false_conf,
    )
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)
    return out
