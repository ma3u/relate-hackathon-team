"""Compares the 3D view's data built in Swift (Klarbefund for Mac) with scripts/graph3d.py on one store.

    python tests/graph3d_parity.py STORE.rl     # builds both, prints the differences

Run on a copy: scripts/graph3d.py reads through the relate CLI, Swift through the library."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import graph3d  # noqa: E402


def main(db: str) -> int:
    relate = os.environ.get("RELATE_BIN") or "relate"
    nodes = graph3d.query(relate, db, "MATCH (n) RETURN id(n) AS id, labels(n)[0] AS label, properties(n) AS p")
    links = graph3d.query(relate, db, "MATCH (a)-[r]->(b) RETURN id(a) AS s, id(b) AS t, type(r) AS type, "
                                      "CASE WHEN type(r) = 'RAISES_RISK_OF' THEN properties(r) END AS p")
    py = graph3d.build(nodes, links)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "swift.json"
        env = dict(os.environ, GRAPH3D_PARITY_DB=db, GRAPH3D_PARITY_OUT=str(out))
        subprocess.run(["swift", "test", "--filter", "writeThreeDDataForParity"], cwd=ROOT / "swift", env=env,
                       check=True, capture_output=True)
        sw = json.loads(out.read_text())
    keys = ["g", "n", "d", "dt", "val", "v", "u", "lab", "rl", "rh", "mk", "cur", "dup", "out", "rid", "sid", "r"]
    a = {n["id"]: n for n in py["nodes"]}
    b = {n["id"]: n for n in sw["nodes"]}
    def same(x, y):  # 43.0 and 43 are one number to the page
        if isinstance(x, (int, float)) and isinstance(y, (int, float)) and not isinstance(x, bool):
            return float(x) == float(y)
        return json.dumps(x, sort_keys=True) == json.dumps(y, sort_keys=True)
    diffs = [(i, k, a[i].get(k), b.get(i, {}).get(k)) for i in a for k in keys if not same(a[i].get(k), b.get(i, {}).get(k))]
    la = sorted((l["source"], l["target"], l["t"]) for l in py["links"])
    lb = sorted((l["source"], l["target"], l["t"]) for l in sw["links"])
    print(f"nodes: python {len(a)}, swift {len(b)}; links: python {len(la)}, swift {len(lb)}, same {la == lb}; "
          f"sex: {py['sex']} / {sw['sex']}")
    print(f"field differences: {len(diffs)}")
    for d in diffs[:15]:
        print("  ", d[0], d[1], "| python:", str(d[2])[:70], "| swift:", str(d[3])[:70])
    return 1 if diffs or la != lb or len(a) != len(b) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
