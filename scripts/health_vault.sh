#!/usr/bin/env bash
# Keep the health graph in an AES-256 encrypted disk image, unlocked only while used.
#
# Relate stores its graph unencrypted, so the store lives inside an encrypted
# APFS sparse bundle that is mounted at ~/RelateHealth (the same path the
# receiver and the Claude configs use) only while something needs it. The
# image's password is a random 256-bit secret in the macOS login Keychain; it
# is never printed or written to a file.
#
#   scripts/health_vault.sh create    # new empty vault (once)
#   scripts/health_vault.sh migrate   # move an existing ~/RelateHealth/health.rl into a new vault
#   scripts/health_vault.sh mount     # unlock and mount at ~/RelateHealth
#   scripts/health_vault.sh unmount   # lock it again
#   scripts/health_vault.sh status
#   scripts/health_vault.sh receive   # mount, then run the Klarbefund receiver (refuses if not mounted)
#                                     # (Swift: swift/mac; HEALTH_GRAPH_RECEIVER=python for the Python one)
#   scripts/health_vault.sh usb       # mount, then fetch from Klarbefund over the USB cable (no Wi-Fi)
#   scripts/health_vault.sh mcp       # mount, then serve the graph read-only over MCP (for Claude)
#   scripts/health_vault.sh graph3d   # mount, build the 3D view into the vault, serve it on 127.0.0.1
set -euo pipefail

VAULT="${RELATE_HEALTH_VAULT:-$HOME/RelateHealthVault.sparsebundle}"
MOUNT="${RELATE_HEALTH_MOUNT:-$HOME/RelateHealth}"
SERVICE="relate-health-vault"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RELATE="${RELATE_BIN:-$HOME/.local/bin/relate}"

log() { echo "health-vault: $*" >&2; }
mounted() { mount | grep -q " on $MOUNT (" ; }
secret() { security find-generic-password -a "$USER" -s "$SERVICE" -w; }

create() {
  [ -e "$VAULT" ] && { log "$VAULT exists already"; exit 1; }
  security find-generic-password -a "$USER" -s "$SERVICE" >/dev/null 2>&1 ||
    security add-generic-password -a "$USER" -s "$SERVICE" -l "Relate health vault" \
      -j "Password of $VAULT (AES-256 disk image with the local health graph)" \
      -w "$(openssl rand -base64 32)"
  secret | hdiutil create -quiet -size 4g -type SPARSEBUNDLE -fs APFS -encryption AES-256 \
    -stdinpass -volname RelateHealth "$VAULT"
  log "created $VAULT (AES-256), password in the login Keychain as '$SERVICE'"
}

do_mount() {
  mounted && return 0
  [ -e "$VAULT" ] || { log "no vault at $VAULT; run: $0 create"; exit 1; }
  mkdir -p "$MOUNT" && chmod 700 "$MOUNT"
  if [ -n "$(ls -A "$MOUNT" 2>/dev/null)" ]; then
    log "$MOUNT is not empty; refusing to mount over it (run: $0 migrate)"; exit 1
  fi
  secret | hdiutil attach -quiet -stdinpass -nobrowse -owners on -mountpoint "$MOUNT" "$VAULT"
  chmod 700 "$MOUNT"
  log "unlocked: $MOUNT"
}

do_unmount() {
  mounted || { log "already locked"; return 0; }
  hdiutil detach -quiet "$MOUNT" || hdiutil detach -quiet -force "$MOUNT"
  log "locked"
}

count() {  # observations in a store, read-only
  "$REPO/.venv/bin/python" -c "
import sys; sys.path.insert(0, '$REPO')
from health_graph import store
c = store.connect(sys.argv[1], read_only=True)
print(c.execute('MATCH (n) RETURN count(n) AS n').single()['n'], c.execute('MATCH ()-[r]->() RETURN count(r) AS n').single()['n'])
c.close()" "$1"
}

migrate() {
  mounted && { log "already mounted, nothing to migrate"; exit 1; }
  [ -f "$MOUNT/health.rl" ] || { log "no plaintext $MOUNT/health.rl to migrate"; exit 1; }
  local plain
  plain="$MOUNT.plaintext-$(date +%Y%m%d%H%M%S)"
  [ -e "$VAULT" ] || create
  mv "$MOUNT" "$plain"
  do_mount
  cp -Rp "$plain"/. "$MOUNT"/
  local before after
  before="$(count "$plain/health.rl")"
  after="$(count "$MOUNT/health.rl")"
  if [ "$before" != "$after" ] || ! cmp -s "$plain/health.rl" "$MOUNT/health.rl"; then
    log "copy does not match (nodes/rels before: $before, after: $after); plaintext kept at $plain"
    exit 1
  fi
  log "verified: $after (nodes rels), byte-identical"
  rm -rf "$plain"
  log "removed the plaintext copy $plain"
}

case "${1:-status}" in
  create) create ;;
  migrate) migrate ;;
  mount) do_mount ;;
  unmount | lock) do_unmount ;;
  status)
    echo "vault: $VAULT ($( [ -e "$VAULT" ] && echo present || echo missing ))"
    echo "mount: $MOUNT ($(mounted && echo "unlocked" || echo "locked"))"
    ;;
  receive | usb)
    [ -e "$VAULT" ] || create
    do_mount
    if [ "$1" = receive ] && [ "${HEALTH_GRAPH_RECEIVER:-swift}" = python ]; then
      cd "$REPO" && exec env PYTHONUNBUFFERED=1 .venv/bin/python -m health_graph receive \
        --db "$MOUNT/health.rl" --require-mount "${@:2}"
    fi
    log "building the Swift receiver (swift/mac)"
    swift build -c release --package-path "$REPO/swift/mac" --product health-graph >&2
    bin="$REPO/swift/mac/.build/release/health-graph"
    # macOS keys Local Network permission to the code signature. swift build signs
    # ad hoc (a new identity per build), so sign with a stable developer identity:
    # "Allow" is asked once and then sticks. RELATE_HEALTH_SIGN overrides it.
    id="${RELATE_HEALTH_SIGN:-$(security find-identity -v -p codesigning | awk '/Apple Development/ {print $2; exit}')}"
    if [ -n "$id" ]; then
      codesign --force --sign "$id" --identifier red.mabu.health-graph "$bin" 2>/dev/null ||
        log "could not sign $bin; macOS may block it from the local network"
    else
      log "no signing identity; macOS may ask for Local Network access after every build"
    fi
    exec "$bin" "$1" \
      --db "$MOUNT/health.rl" --require-mount "${@:2}"
    ;;
  mcp)
    do_mount >/dev/null 2>&1 || do_mount
    # Claude reads a snapshot, never the live store: an open reader, even a
    # read-only one, makes Relate refuse writers in other processes, so the
    # receiver could not store anything while a Claude session was open
    # (Nov 12, 2026). The copy stays inside the encrypted vault; reconnecting
    # the MCP server (or a new session) takes a fresh one.
    snap="$MOUNT/claude-snapshot.rl"
    [ -f "$MOUNT/health.rl" ] && cp -f "$MOUNT/health.rl" "$snap.tmp" && mv -f "$snap.tmp" "$snap" && chmod 600 "$snap"
    exec "$RELATE" serve --mcp stdio --database "$snap" --read-only
    ;;
  graph3d)
    do_mount
    # Newest graph wins: Klarbefund for Mac's snapshot, or the receiver's store.
    src="$MOUNT/health.rl"
    app="$HOME/Library/Group Containers/38R8Z4P7S8.red.mabu.meinbefund/Snapshot/health.rl"
    [ -f "$app" ] && { [ ! -e "$src" ] || [ "$app" -nt "$src" ]; } && src="$app"
    [ -e "$src" ] || { log "no graph yet: open Klarbefund for Mac or run '$0 receive', then send from the iPhone"; exit 1; }
    out="$MOUNT/graph3d/index.html"
    RELATE_BIN="$RELATE" python3 "$REPO/scripts/graph3d.py" --db "$src" --out "$out"
    # 8799, or the next free port when another server (an earlier graph3d) has it.
    port="$(python3 -c '
import socket, sys
p = int(sys.argv[1])
for q in range(p, p + 20):
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", q)); print(q); break
    except OSError:
        pass
    finally:
        s.close()
else:
    sys.exit("no free port")' "${GRAPH3D_PORT:-8799}")"
    log "serving http://127.0.0.1:$port/ from the vault (this Mac only); Ctrl-C stops it"
    ( sleep 1; open "http://127.0.0.1:$port/" ) &
    cd "$MOUNT/graph3d" && exec python3 -m http.server "$port" --bind 127.0.0.1
    ;;
  *) sed -n '2,17p' "$0"; exit 2 ;;
esac
