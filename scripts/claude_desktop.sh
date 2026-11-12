#!/usr/bin/env bash
# Registers the encrypted health graph with Claude Desktop as the MCP server
# "klarbefund-health": read-only, through `scripts/health_vault.sh mcp`, which
# unlocks the vault and serves a snapshot of the graph.
#
# Claude Desktop keeps its configuration in memory and writes it back to
# claude_desktop_config.json, so an edit made while it runs can be lost (seen
# Nov 12, 2026: the entry was gone an hour later). This script therefore edits
# the file only while Claude Desktop is closed.
#
#   scripts/claude_desktop.sh --status   # is the server configured?
#   scripts/claude_desktop.sh            # adds it; Claude Desktop must be closed
#   scripts/claude_desktop.sh --wait     # waits until you quit Claude Desktop (⌘Q),
#                                        # adds it, then opens Claude Desktop again
#   scripts/claude_desktop.sh --remove   # removes it (also only while closed)
#
# A backup of the configuration is written next to it before every change.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CFG="${CLAUDE_DESKTOP_CONFIG:-$HOME/Library/Application Support/Claude/claude_desktop_config.json}"
NAME="klarbefund-health"
SERVER="$REPO/scripts/health_vault.sh"

log() { echo "claude-desktop: $*" >&2; }
# The app's main process (not its helpers, not Claude Code's own `claude`).
# ps, not pgrep, which does not list it from every context. No grep -q: it
# stops reading early, ps dies of SIGPIPE, and pipefail turns that into "not running".
# shellcheck disable=SC2009
running() { ps -axo comm= | grep '/Claude\.app/Contents/MacOS/Claude$' >/dev/null; }

edit() {  # $1 = add | remove | status
  python3 - "$CFG" "$NAME" "$SERVER" "$1" <<'PY'
import json, os, shutil, sys, time
path, name, server, action = sys.argv[1:]
config = {}
if os.path.exists(path):
    with open(path) as f:
        config = json.load(f)
servers = config.setdefault("mcpServers", {})
if action == "status":
    entry = servers.get(name)
    print(f"{name}: " + (f"configured ({entry.get('command')} {' '.join(entry.get('args', []))})" if entry else "not configured"))
    print("other servers: " + (", ".join(sorted(k for k in servers if k != name)) or "none"))
    sys.exit(0)
if os.path.exists(path):
    shutil.copy2(path, f"{path}.bak-{time.strftime('%Y%m%d-%H%M%S')}")
if action == "add":
    servers[name] = {"command": server, "args": ["mcp"]}
else:
    servers.pop(name, None)
os.makedirs(os.path.dirname(path), exist_ok=True)
tmp = path + ".tmp"
with open(tmp, "w") as f:
    json.dump(config, f, indent=2)
    f.write("\n")
os.replace(tmp, path)
print(f"{name}: {'added' if action == 'add' else 'removed'}; servers now: {', '.join(sorted(servers)) or 'none'}")
PY
}

case "${1:-}" in
  --status)
    edit status
    if running; then log "Claude Desktop is running"; else log "Claude Desktop is closed"; fi
    ;;
  "" | --remove)
    if running; then
      log "Claude Desktop is running and would overwrite the change. Quit it (⌘Q) first, or use --wait."
      exit 1
    fi
    [ -x "$SERVER" ] || { log "$SERVER is missing"; exit 1; }
    edit "$([ "${1:-}" = --remove ] && echo remove || echo add)"
    log "open Claude Desktop to load it"
    ;;
  --wait)
    [ -x "$SERVER" ] || { log "$SERVER is missing"; exit 1; }
    log "waiting for Claude Desktop to quit (⌘Q)..."
    deadline=$(( $(date +%s) + 12 * 3600 ))
    while running; do
      [ "$(date +%s)" -lt "$deadline" ] || { log "gave up after 12 hours"; exit 1; }
      sleep 2
    done
    sleep 2  # let it finish writing its own files
    edit add
    log "opening Claude Desktop"
    open -a Claude
    ;;
  *) sed -n '2,16p' "$0"; exit 2 ;;
esac
