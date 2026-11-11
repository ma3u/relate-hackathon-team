"""Smallest useful relate-db program: open the CLI-built store and query it.

Run from the repo root:
    .venv/bin/python examples/python/hello_relate.py
"""
from pathlib import Path

import relate

STORE = Path(__file__).resolve().parents[1] / "first-graph" / "team.rl"

TEAM_OF = """
MATCH (p:Person)-[w:WORKS_ON]->(:Project {name: $project})
RETURN p.name AS name, w.since AS since
ORDER BY since
"""

print("relate-db", relate.__version__)

# In-memory store: forgets everything on close.
mem = relate.connect(":memory:")
print(mem.execute("RETURN 'hello graph' AS greeting").single()["greeting"])
mem.close()

# File store created by the CLI tutorial (examples/first-graph/team.rl).
conn = relate.connect(str(STORE))
for project in ["relate", "opencypher-tck"]:
    print(project)
    for row in conn.execute(TEAM_OF, {"project": project}):
        print("  ", row["name"], "since", row["since"])
conn.close()
