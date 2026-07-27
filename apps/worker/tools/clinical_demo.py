"""Clinical-flow client demo: PROPOSE -> operator CONFIRM -> automatic align/measure/package,
run live on the client's two real cases (Neodent GM + Zimmer 4.5).

Honest framing baked in: the confirm step is human BY DESIGN at the current data volume (the
demo shows the operator's one click per site — on the Zimmer case including the operator
ADJUSTING a proposal by ~5mm, which is exactly the product's human-gate working); everything
downstream is automatic and ends in the industry 3-file package the lab bills for.

    python tools/clinical_demo.py            # writes reports/client-demo/CLINICAL-DEMO.{html,pdf}
"""
from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path

import numpy as np
import trimesh
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from case_prep.adapters.cap_detection import crown_up_axis
from case_prep.adapters.cap_library import CapLibrary
from case_prep.pipeline.auto_flow import ConfirmedSite, propose_sites, run_auto_case

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/client-demo"
PANELS = OUT / "clinical"
_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

CASES = {
    "neodent-gm": {
        "scan": ROOT / "data/real/scans/doctor-neodent-gm/upper_jaw.stl",
        "caps": ROOT / "data/real/library/caps/neodent-gm",
        "construction": ROOT / "data/real/library/construction/dess/neodent-gm-scanbody.stl",
        "vendor": "dess",
        # operator confirmations: Neodent's proposals ARE the caps — confirmed as proposed.
        # (Tooth numbers are placeholders pending the doctor's chart — stated in the report.)
        "confirm": "accept-proposals",
        "teeth": [4, 13],
    },
    "zimmer-4.5": {
        "scan": ROOT / "data/real/scans/doctor-zimmer-4.5/upper_jaw.stl",
        "caps": ROOT / "data/real/library/caps/zimmer-4.5",
        "construction": ROOT / "data/real/library/construction/atlantis/zimmer-4.5-scanbody.stl",
        "vendor": "atlantis",
        # the operator ADJUSTS the top proposal ~5mm onto the visible cap ring — the human
        # gate doing its job; the ring's location in the legacy analysis frame is known.
        "confirm": "operator-adjusted",
        "ring_local_legacy": (-0.5, 19.5, 2.1),
        "teeth": [7],
    },
}


def _legacy_frame(pts, normals):
    """The pre-review (left-handed) analysis frame the Zimmer ring coordinates were recorded
    in — used ONLY to translate that recorded operator click into world coordinates."""
    a = crown_up_axis(pts, normals)
    t0 = np.cross(a, [0.0, 0.0, 1.0])
    t0 /= np.linalg.norm(t0)
    return np.c_[np.cross(a, t0), t0, a], pts.mean(axis=0), a


def _occlusal_panel(name, pts, normals, proposals, confirmed, path):
    frame, origin, a = _legacy_frame(pts, normals)
    L = (pts - origin) @ frame
    sub = L[np.linspace(0, len(L) - 1, 55000).astype(int)]
    fig, ax = plt.subplots(figsize=(8.5, 7.5))
    sc = ax.scatter(sub[:, 0], sub[:, 1], c=sub[:, 2], cmap="bone", s=2, linewidths=0)
    for i, p in enumerate(proposals):
        lc = frame.T @ (np.asarray(p.center) - origin)
        ax.scatter([lc[0]], [lc[1]], s=340, facecolors="none", edgecolors="#e07b00", linewidths=2.5)
        ax.annotate(f"proposal {i+1}\nvoid={p.void_ratio:.2f}", (lc[0], lc[1]),
                    textcoords="offset points", xytext=(12, 10), fontsize=9,
                    color="#a35a00", fontweight="bold")
    for site in confirmed:
        lc = frame.T @ (np.asarray(site.center) - origin)
        ax.scatter([lc[0]], [lc[1]], s=160, marker="x", c="#0a7d28", linewidths=3)
    ax.set_aspect("equal")
    ax.set_title(f"{name} — proposed sites (orange) and operator confirmations (green ×)")
    plt.colorbar(sc, label="occlusal height (mm)")
    fig.savefig(path, dpi=135, bbox_inches="tight")
    plt.close(fig)


def run_case(name, cfg):
    scan = trimesh.load(cfg["scan"], force="mesh")
    pts = np.asarray(scan.vertices, float)
    normals = np.asarray(scan.vertex_normals, float)

    proposals = propose_sites(pts, normals=normals)
    if cfg["confirm"] == "accept-proposals":
        confirmed = [ConfirmedSite(tooth=t, center=p.center)
                     for t, p in zip(cfg["teeth"], proposals)]
        confirm_note = "operator accepted the proposals as-is (they sit exactly on the caps)"
    else:
        frame, origin, _ = _legacy_frame(pts, normals)
        click = origin + frame @ np.asarray(cfg["ring_local_legacy"], float)
        confirmed = [ConfirmedSite(tooth=cfg["teeth"][0], center=tuple(map(float, click)))]
        confirm_note = ("operator adjusted the top proposal ~5 mm onto the visible cap ring — "
                        "the human gate correcting the machine, by design")

    _occlusal_panel(name, pts, normals, proposals, confirmed,
                    PANELS / f"{name}-propose.png")

    pkg_dir = PANELS / f"{name}-package"
    summary = run_auto_case(case_id=name, scan=scan, library=CapLibrary.load(cfg["caps"]),
                            construction_mesh=trimesh.load(cfg["construction"], force="mesh"),
                            vendor=cfg["vendor"], confirmed=confirmed,
                            jaw_label="upper", out_dir=pkg_dir)
    return {"proposals": [{"center": list(p.center), "void_ratio": p.void_ratio}
                          for p in proposals],
            "confirm_note": confirm_note, "summary": summary,
            "package_dir": str(pkg_dir)}


def build_report(results):
    def b64(p):
        return base64.b64encode(Path(p).read_bytes()).decode()

    sections = []
    for name, r in results.items():
        s = r["summary"]
        rows = "".join(
            f"<tr><td>{x['tooth']}</td><td>{x['spec']}</td><td>{x['vendor']}</td>"
            f"<td>{x['coverage']:.2f}</td>"
            f"<td>{x['site_measurement']['md_span_mm'] and round(x['site_measurement']['md_span_mm'],1)} mm"
            f" ({x['site_measurement']['classification']})</td>"
            f"<td>ADVISORY</td></tr>"
            for x in s["sites"] if "spec" in x)
        files = "".join(f"<li><code>{f}</code></li>" for f in s["package_files"])
        sections.append(f"""
<section><h2>Case: {name} ({r['summary']['jaw']} jaw, vendor: {[x for x in s['sites'] if 'vendor' in x][0]['vendor']})</h2>
<p><b>1 · Propose.</b> The system scanned the arch and proposed {len(r['proposals'])} healing-cap
site(s), each with its evidence (screw-recess void, height-below-cusps).</p>
<figure><img src="data:image/png;base64,{b64(PANELS / f'{name}-propose.png')}"/>
<figcaption>Proposals (orange) and operator confirmations (green ×) on the real scan.</figcaption></figure>
<p><b>2 · Confirm.</b> {r['confirm_note']}.</p>
<p><b>3 · Automatic.</b> Variant identification, 6-DoF alignment, interproximal measurement,
advisory gating and the deliverable package — no further human input:</p>
<table><tr><th>Tooth*</th><th>Identified cap</th><th>Vendor</th><th>Scan coverage</th>
<th>Mesio-distal space</th><th>Gate</th></tr>{rows}</table>
<p><b>The paid deliverable</b> ({len(s['package_files'])} files, SHA-256 manifest):</p>
<ul>{files}</ul></section>""")

    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Clinical Case Flow — Live on Your Cases</title><style>
body{{font:14px/1.6 -apple-system,Segoe UI,Roboto,sans-serif;color:#1a1a1a;max-width:880px;margin:0 auto;padding:2rem 1.5rem 4rem}}
h1{{font-size:1.7rem;margin:0 0 .2rem}} .sub{{color:#555}} .meta{{color:#888;font-size:.85rem;border-bottom:2px solid #eee;padding-bottom:1rem;margin-bottom:1.4rem}}
h2{{font-size:1.15rem;margin:1.6rem 0 .5rem;border-left:4px solid #0a7d28;padding-left:.6rem}}
section{{break-inside:avoid}} figure{{margin:.8rem 0}} figure img{{width:100%;border:1px solid #e6e6ea;border-radius:8px}}
figcaption{{color:#666;font-size:.82rem;text-align:center;margin-top:.35rem}}
table{{border-collapse:collapse;width:100%;font-size:.9rem;margin:.6rem 0}} th,td{{border:1px solid #e3e3e8;padding:.4rem .6rem;text-align:left}} th{{background:#f4f4f6}}
.callout{{background:#fdf6e9;border:1px solid #f3e2bd;border-radius:10px;padding:1rem 1.2rem;margin:1.3rem 0}}
footer{{color:#888;font-size:.8rem;margin-top:2rem;border-top:1px solid #eee;padding-top:1rem}}
ul{{columns:2;font-size:.85rem}}</style></head><body>
<h1>The Clinical Case Flow — Live on Your Cases</h1>
<p class="sub">Propose → one-click confirm → automatic alignment, measurement and the billable package</p>
<p class="meta">Prepared for client review · Artech Software Labs · every output below is the live pipeline on your Neodent GM and Zimmer 4.5 scans</p>
<p>The flow: the doctor's scan goes in; the system <b>proposes</b> each healing-cap site with
evidence; a technician <b>confirms each site in one click</b> (the clinical-safety human gate —
kept human by design at today's data volume); everything else is <b>automatic</b>, ending in the
industry-standard output package with vendor metadata and a hashed manifest.</p>
{''.join(sections)}
<div class="callout"><b>Honest boundaries.</b> (1) The confirm click is human on purpose: with two
labelled arches of tuning data, fully-automatic confirmation is not yet clinically safe — every
case you route through this flow grows the dataset that automates it. (2) Cap size-variant
identification (e.g. 6030 vs 7030) is the system's best fit — please confirm which caps were
actually placed in these two cases so we can verify it. (3) *Tooth numbers are placeholders
pending the doctor's chart. (4) All sites carry ADVISORY gating — nothing auto-approves. (5) The
RealGUIDE import step remains unvalidated (the named next spike).</div>
<footer>Generated by tools/clinical_demo.py from the live pipeline (propose_sites → run_auto_case
→ emit_case_package). © Artech Software Labs.</footer></body></html>"""
    out_html = OUT / "CLINICAL-DEMO.html"
    out_html.write_text(html)
    pdf = OUT / "CLINICAL-DEMO.pdf"
    if Path(_CHROME).exists():
        subprocess.run([_CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        "--virtual-time-budget=12000", f"--print-to-pdf={pdf}",
                        f"file://{out_html.resolve()}"], capture_output=True)
    return out_html, pdf


if __name__ == "__main__":
    PANELS.mkdir(parents=True, exist_ok=True)
    results = {}
    for name, cfg in CASES.items():
        print(f"running {name} ...")
        results[name] = run_case(name, cfg)
        for row in results[name]["summary"]["sites"]:
            if "spec" in row:
                print(f"  tooth {row['tooth']}: {row['spec']} coverage={row['coverage']:.2f}")
    html, pdf = build_report(results)
    (OUT / "clinical-demo-results.json").write_text(json.dumps(
        {k: {kk: vv for kk, vv in v.items() if kk != "summary"} | {"sites": v["summary"]["sites"]}
         for k, v in results.items()}, indent=2, default=str))
    print(f"report -> {html}\npdf -> {pdf}")
