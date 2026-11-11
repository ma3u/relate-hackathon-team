#!/usr/bin/env bash
# Regenerate the terminal screenshots in docs/img/ from real command runs.
# Needs: relate on PATH, .venv with relate-db, freeze (brew install charmbracelet/tap/freeze).
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=docs/img
mkdir -p "$OUT"

# shot <file> <shell commands...>: prints each command with a "$" prompt, runs it, renders a PNG.
shot() {
  local file=$1; shift
  # Keep existing shots unless FORCE=1 (the install shot re-downloads the binary).
  if [[ -f "$OUT/$file" && -z "${FORCE:-}" ]]; then echo "kept $OUT/$file"; return; fi
  local script
  script=$(mktemp -t shot).sh
  for cmd in "$@"; do
    printf "printf '\\\\033[1;32m\$\\\\033[0m %%s\\\\n' %q\n%s\n" "$cmd" "$cmd" >> "$script"
  done
  freeze --execute "bash $script" \
    --window --theme dracula --font.family Menlo --font.size 14 --line-height 1.3 \
    --padding 20,24 --margin 0 --border.radius 8 --wrap 120 --execute.timeout 2m \
    -o "$OUT/$file" | grep -v WROTE || true
  echo "wrote $OUT/$file"
}

shot 01-install.png \
  'curl -sSfL https://relatedb.ai/install.sh | bash'

shot 02-verify.png \
  'relate --version' \
  'relate --mode table "RETURN 1 AS ok"'

shot 03-skill.png \
  'relate skill install --agent claude-code' \
  'relate skill check | head -1'

shot 04-python.png \
  'uv venv --allow-existing --python 3.12 .venv && uv pip install --python .venv/bin/python relate-db' \
  '.venv/bin/python -c "import relate; print(relate.__version__)"'

[[ -f "$OUT/05-first-graph.png" && -z "${FORCE:-}" ]] || rm -f examples/first-graph/team.rl
shot 05-first-graph.png \
  'relate query --database examples/first-graph/team.rl --mode table < examples/first-graph/seed.cypher' \
  'relate --database examples/first-graph/team.rl --read-only --mode table "MATCH (p:Person)-[w:WORKS_ON]->(proj:Project) RETURN p.name AS person, proj.name AS project, w.since AS since ORDER BY since"'

shot 06-envelope.png \
  "relate --database examples/first-graph/team.rl --read-only --mode envelope --param name=Grace 'MATCH (:Person {name: \$name})-[:WORKS_ON]->(p:Project) RETURN p.name AS project' | python3 -m json.tool"

shot 07-python-query.png \
  '.venv/bin/python examples/python/hello_relate.py'

shot 08-mcp.png \
  'cat .mcp.json' \
  'claude mcp list 2>/dev/null | grep relate'
