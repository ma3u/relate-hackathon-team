#!/usr/bin/env python3
"""Builds docs/3d/index.html, the live 3D demo on klarbefund.mabu.red.

It is the same page Klarbefund for Mac opens with *Open 3D view*, built by
scripts/graph3d.py, but from the synthetic sample graph
(examples/health-graph/health.rl) with the knowledge layer of this checkout
seeded on a copy. No real person's data can reach it.

Two changes to the page: the 3D library is served from the site itself
(docs/3d/3d-force-graph.min.js, MIT, the same 1.80.1 the page names), so
the site loads nothing from another host; and a line at the bottom says the
graph is synthetic and links back.

    .venv/bin/python scripts/build_site_demo.py
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "examples" / "health-graph" / "health.rl"
OUT = ROOT / "docs" / "3d" / "index.html"
CDN = '<script src="https://cdn.jsdelivr.net/npm/3d-force-graph@1.80.1/dist/3d-force-graph.min.js"></script>'
LOCAL = '<script src="/3d/3d-force-graph.min.js"></script>'

HEAD = """<meta name="description" content="The 3D view of Klarbefund for Mac, on a synthetic sample graph: health risks, the studies behind them with their quality gate, anamnesis, measures and documents.">
<link rel="canonical" href="https://klarbefund.mabu.red/3d/">
<link rel="icon" type="image/png" href="/site/favicon.png">
"""

BANNER = """<div style="position:fixed;left:50%;bottom:30px;transform:translateX(-50%);z-index:50;
  background:rgba(13,17,23,.92);border:1px solid #2c3644;border-radius:999px;padding:6px 14px;
  font:13px -apple-system,BlinkMacSystemFont,sans-serif;color:#c6cfd9;white-space:nowrap">
  Synthetic sample graph, no real person ·
  <a href="/" style="color:#3d9bff;text-decoration:none">Klarbefund: back to the website</a>
</div>
"""


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "sample.rl"
        shutil.copy(SAMPLE, db)
        subprocess.run([sys.executable, "-m", "health_graph", "knowledge", "--db", str(db)],
                       cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
        page = Path(tmp) / "index.html"
        subprocess.run([sys.executable, str(ROOT / "scripts" / "graph3d.py"), "--db", str(db), "--out", str(page)],
                       cwd=ROOT, check=True)
        html = page.read_text(encoding="utf-8")
    if html.count(CDN) != 1:
        sys.exit("graph3d page does not load the expected 3d-force-graph 1.80.1 from jsDelivr")
    html = html.replace(CDN, LOCAL)
    html = html.replace("<title>Health Graph 3D</title>", "<title>Klarbefund · 3D demo</title>\n" + HEAD, 1)
    html = html.replace("<body>", "<body>\n" + BANNER, 1)
    if "https://cdn." in html:
        sys.exit("the demo page still loads something from a CDN")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(html) // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
