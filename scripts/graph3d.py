"""Builds an interactive 3D view of a health graph (3d-force-graph, WebGL).

Reads a Relate store with the `relate` CLI and writes one self-contained HTML
page with every node and relationship embedded: colored by label and grouped
into your data, codes, knowledge and the OMOP copy, with search, label filters
and a focus panel.

    python3 scripts/graph3d.py --db examples/health-graph/health.rl --out /tmp/graph3d/index.html
    scripts/health_vault.sh graph3d     # your real graph: built and served inside the vault

The page holds the values of the store it was built from. For a real graph,
write it only into the encrypted vault; this script refuses to write into the
repository.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = Path(__file__).with_name("graph3d.html")


def query(relate, db, statement):
    out = subprocess.run(
        [relate, "query", "-d", str(db), "--json", "--max-rows", "0", statement],
        check=True, capture_output=True, text=True).stdout
    return json.loads(out)["data"]


def num(v):
    if v is None:
        return ""
    return f"{v:g}" if isinstance(v, float) else str(v)


def describe(label, p):
    """(group, name, detail lines) for one node."""
    if label == "Observation":
        device = p.get("sourceKind") == "device-weekly-mean"
        name = p.get("display") or p.get("loincDisplay") or p.get("code") or "Observation"
        value = f"{p.get('comparator') or ''}{num(p.get('valueQuantity'))} {p.get('unit') or ''}".strip()
        lines = [value, p.get("effectiveDate") or p.get("effectiveStart") or ""]
        if p.get("code"):
            lines.append(f"LOINC {p['code']}")
        if p.get("referenceLow") is not None or p.get("referenceHigh") is not None:
            lines.append(f"Lab range {num(p.get('referenceLow'))} – {num(p.get('referenceHigh'))}")
        elif p.get("referenceText"):
            lines.append(f"Lab range {p['referenceText']}")
        if p.get("taxonDisplay"):
            lines.append(p["taxonDisplay"])
        if p.get("sourceLine"):
            lines.append(f"Source {p['sourceLine']}")
        if p.get("duplicateOf"):
            lines.append("Also in another report")
        return ("Apple Watch week" if device else "Lab value"), name, lines
    if label == "DiagnosticReport":
        return label, p.get("title") or "Report", [p.get("effectiveDate") or "", p.get("performer") or ""]
    if label == "DocumentReference":
        return label, p.get("title") or "Document", [p.get("created") or ""]
    if label == "Provenance":
        return label, f"Provenance: {p.get('activity') or 'scan'}", [p.get("recorded") or ""]
    if label == "Organization":
        return label, p.get("name") or "Lab", []
    if label == "Patient":
        return label, "You", []
    if label == "LoincCode":
        return label, p.get("display") or p.get("code"), [f"LOINC {p.get('code')}"]
    if label == "NcbiTaxon":
        return label, p.get("display") or p.get("code"), [f"NCBI {p.get('code')}"]
    if label == "ReferenceRange":
        g = f"{num(p.get('guidelineLow'))} – {num(p.get('guidelineHigh'))} {p.get('ucum') or ''}"
        o = f"{num(p.get('optimalLow'))} – {num(p.get('optimalHigh'))}"
        lines = [f"Guideline {g}".strip(), f"Optimal {o}", p.get("sex") or "", p.get("sourceLabel") or ""]
        return label, f"Range: {p.get('analyteKey') or p.get('loinc')}", lines
    if label == "HealthRisk":
        return label, p.get("name"), [p.get("description") or ""]
    if label == "RiskScore":
        return label, p.get("name"), [p.get("source") or ""]
    if label == "Knowledge":
        return label, "Knowledge layer", [p.get("rangesSource") or ""]
    if label == "OMOPPerson":
        return label, "OMOP person", []
    if label == "OMOPMeasurement":
        value = f"{num(p.get('valueAsNumber'))} {p.get('unitSourceValue') or ''}".strip()
        return label, p.get("measurementSourceValue") or "OMOP measurement", [value, p.get("measurementDate") or ""]
    return label, label, []


def build(nodes_in, links_in):
    by_id = {r["id"]: r for r in nodes_in}
    # LoincCode nodes often carry only the code: borrow the most common name of
    # the observations coded by it.
    names = {}
    for r in links_in:
        if r["type"] == "CODED_BY" and by_id[r["s"]]["label"] == "Observation":
            p = by_id[r["s"]]["p"]
            if n := p.get("loincDisplay") or p.get("display"):
                names.setdefault(r["t"], Counter())[n] += 1
    for r in nodes_in:
        if r["label"] == "LoincCode" and not r["p"].get("display") and r["id"] in names:
            r["p"]["display"] = names[r["id"]].most_common(1)[0][0]
    # ... and an observation without a name takes its code's.
    for r in links_in:
        o, c = by_id[r["s"]], by_id[r["t"]]
        if r["type"] == "CODED_BY" and o["label"] == "Observation" and c["label"] == "LoincCode":
            if not (o["p"].get("display") or o["p"].get("loincDisplay")) and c["p"].get("display"):
                o["p"]["loincDisplay"] = c["p"]["display"]

    # The first view shows the current risks: the risks and scores, their marker
    # codes, and the latest lab value on each marker.
    markers = {r["t"] for r in links_in if r["type"] in ("MARKER_OF", "USES")}
    latest = {}  # LoincCode id -> newest lab Observation (duplicates count once)
    for r in links_in:
        if r["type"] != "CODED_BY" or r["t"] not in markers:
            continue
        o = by_id[r["s"]]
        p = o["p"]
        if o["label"] != "Observation" or p.get("sourceKind") == "device-weekly-mean" or p.get("duplicateOf"):
            continue
        best = latest.get(r["t"])
        if best is None or (p.get("effectiveDate") or "") > (best["p"].get("effectiveDate") or ""):
            latest[r["t"]] = o
    current = {o["id"] for o in latest.values()}

    nodes = []
    for r in nodes_in:
        group, name, lines = describe(r["label"], r["p"])
        node = {"id": r["id"], "g": group, "n": str(name), "d": [str(x) for x in lines if x]}
        if r["id"] in markers:
            node["mk"] = 1
        if r["id"] in current:
            node["cur"] = 1
        if r["label"] == "Observation":
            p = r["p"]
            node["dt"] = p.get("effectiveDate") or p.get("effectiveStart") or ""
            node["val"] = lines[0]
            if p.get("duplicateOf"):
                node["dup"] = 1
            v, lo, hi = p.get("valueQuantity"), p.get("referenceLow"), p.get("referenceHigh")
            if group == "Lab value" and isinstance(v, (int, float)) and (
                    (lo is not None and v < lo) or (hi is not None and v > hi)):
                node["out"] = 1
                node["d"].insert(1, "Outside the lab's range")
        nodes.append(node)
    links = [{"source": r["s"], "target": r["t"], "t": r["type"]} for r in links_in]
    return {"nodes": nodes, "links": links}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", required=True, help="Relate store (.rl)")
    ap.add_argument("--out", required=True, help="HTML page to write (outside this repository)")
    ap.add_argument("--relate", default=os.environ.get("RELATE_BIN") or shutil.which("relate") or "relate")
    a = ap.parse_args()

    out = Path(a.out).expanduser().resolve()
    if out.is_relative_to(ROOT):
        sys.exit(f"graph3d: refusing to write {out}: the page embeds health data, keep it out of the repository")

    # Read a copy next to the output: an open reader, even a read-only one,
    # would keep a running receiver or app from writing to the store.
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out.parent, prefix=".graph3d-") as tmp:
        db = Path(tmp) / "store.rl"
        src = Path(a.db).expanduser()
        (shutil.copytree if src.is_dir() else shutil.copy2)(src, db)
        nodes = query(a.relate, db, "MATCH (n) RETURN id(n) AS id, labels(n)[0] AS label, properties(n) AS p")
        links = query(a.relate, db, "MATCH (a)-[r]->(b) RETURN id(a) AS s, id(b) AS t, type(r) AS type")

    data = build(nodes, links)
    page = TEMPLATE.read_text().replace(
        "/*DATA*/null", json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"))
    out.write_text(page)
    out.chmod(0o600)
    print(f"graph3d: {len(data['nodes'])} nodes, {len(data['links'])} relationships -> {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
