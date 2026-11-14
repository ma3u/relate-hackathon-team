"""Serves the 3D view on 127.0.0.1 and stores the anamnesis protocol answers given in it.

    scripts/graph3d_serve.py --dir ~/RelateHealth/graph3d --port 8799 --db ~/RelateHealth/health.rl
    scripts/graph3d_serve.py --dir ~/RelateHealth/graph3d --port 8799 --inbox "<app group>/Inbox"

GET serves the files in --dir; the page itself gets this run's token, so it can save.
POST /answers {"protocol": "findrisc", "answers": {linkId: {"codes", "text", "prefilled", "observation"}}}
is checked against the protocol (health_graph.protocols.normalise), then

  --db STORE    stored in that Relate store (the vault's own, which the Python receiver writes), or
  --inbox DIR   handed to Klarbefund for Mac as one request file in its app-group Inbox: the app owns
                its graph and stores the request while it is open (as it does for Claude's answers).

Only this Mac reaches the server (127.0.0.1). A write needs this run's token, this origin and this host,
so no other web page, and no DNS-rebound name, can store answers. Nothing about an answer is logged.
health_vault.sh graph3d starts it; it is not meant for anything but the vault's own view.
"""
import argparse
import datetime as dt
import functools
import hmac
import json
import os
import secrets
import sys
import uuid
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from health_graph import protocols, store  # noqa: E402

MAX_BODY = 64 * 1024
SUFFIX = ".protocol.json"   # Klarbefund for Mac's inbox reads these (AnamnesisInbox.protocolSuffix)
INJECT_BEFORE = '<script src="https://cdn.jsdelivr.net/npm/3d-force-graph'


def save_db(db: str, protocol: str, answers: dict) -> str:
    conn = store.connect(db)
    try:
        store.init_schema(conn)
        found = list(conn.execute("MATCH (p:Patient) RETURN p.id AS id"))
        if len(found) != 1:
            raise ValueError("the store holds no single person to answer for")
        counts = protocols.store_response(conn, found[0]["id"], protocol, answers, source="graph3d")
    finally:
        conn.close()
    score = f", score {counts['score']:g} ({counts['band']})" if counts["score"] is not None else \
        f" ({counts['band']})" if counts["band"] else ""
    return (f"Stored in your vault: {counts['answers']} answers{score}, coded with SNOMED CT. "
            "Build the view again to see them in the graph.")


def save_inbox(inbox: str, protocol: str, answers: dict, now: dt.datetime | None = None) -> str:
    rows = protocols.normalise(protocol, answers)   # refuse before anything leaves this process
    if not rows:
        raise ValueError("no answers to store")
    now = now or dt.datetime.now(dt.timezone.utc)
    folder = Path(inbox)
    folder.mkdir(parents=True, exist_ok=True)
    request = {"protocol": protocol, "answers": answers, "source": "graph3d",
               "authored": now.isoformat(timespec="seconds")}
    name = f"{int(now.timestamp() * 1000)}-{uuid.uuid4().hex[:8]}{SUFFIX}"
    tmp = folder / f".{name}.tmp"
    tmp.write_text(json.dumps(request, sort_keys=True))
    os.chmod(tmp, 0o600)
    tmp.rename(folder / name)   # the app never sees half a file
    return (f"Handed to Klarbefund for Mac: {len(rows)} answers. The app stores them while it is open "
            "(build 6 or later), coded with SNOMED CT.")


class Handler(SimpleHTTPRequestHandler):
    token = ""
    port = 0
    db: str | None = None
    inbox: str | None = None

    def log_message(self, fmt, *args):  # the path only, never a body
        sys.stderr.write(f"graph3d: {self.command} {self.path.split('?')[0]}\n")

    def _same_origin(self) -> bool:
        hosts = {f"127.0.0.1:{self.port}", f"localhost:{self.port}"}
        origin = self.headers.get("Origin")
        return self.headers.get("Host") in hosts and origin in {f"http://{h}" for h in hosts}

    def _reply(self, status: int, body: dict):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.split("?")[0] not in ("/", "/index.html"):
            return super().do_GET()
        if self.headers.get("Host") not in {f"127.0.0.1:{self.port}", f"localhost:{self.port}"}:
            return self._reply(403, {"error": "this view answers on 127.0.0.1 only"})
        page = (Path(self.directory) / "index.html").read_text()
        save = json.dumps({"url": "/answers", "token": self.token})
        page = page.replace(INJECT_BEFORE, f"<script>window.GRAPH3D_SAVE = {save};</script>\n{INJECT_BEFORE}", 1)
        data = page.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path != "/answers":
            return self._reply(404, {"error": "not found"})
        if not self._same_origin() or not hmac.compare_digest(self.headers.get("X-Graph3d-Token", ""), self.token):
            return self._reply(403, {"error": "refused: not this page"})
        length = int(self.headers.get("Content-Length") or 0)
        if not 0 < length <= MAX_BODY or "application/json" not in (self.headers.get("Content-Type") or ""):
            return self._reply(400, {"error": "expected a small JSON body"})
        try:
            body = json.loads(self.rfile.read(length))
            protocol, answers = body["protocol"], body["answers"]
            if not isinstance(answers, dict):
                raise ValueError("answers must be an object")
            message = save_db(self.db, protocol, answers) if self.db else save_inbox(self.inbox, protocol, answers)
        except (KeyError, ValueError, json.JSONDecodeError) as e:
            return self._reply(400, {"error": str(e)})
        except Exception as e:  # the store is busy (the receiver writes), the inbox unwritable, ...
            return self._reply(500, {"error": f"{type(e).__name__}: {e}"})
        self._reply(200, {"message": message})


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dir", required=True, help="the folder graph3d.py wrote index.html into")
    ap.add_argument("--port", type=int, default=8799)
    where = ap.add_mutually_exclusive_group(required=True)
    where.add_argument("--db", help="Relate store to write the answers into")
    where.add_argument("--inbox", help="Klarbefund for Mac's app-group Inbox folder")
    a = ap.parse_args()
    Handler.token = secrets.token_urlsafe(24)
    Handler.port, Handler.db, Handler.inbox = a.port, a.db, a.inbox
    server = ThreadingHTTPServer(("127.0.0.1", a.port), functools.partial(Handler, directory=a.dir))
    print(f"graph3d: serving http://127.0.0.1:{a.port}/ (this Mac only); answers go to "
          f"{'the store' if a.db else 'Klarbefund for Mac'}; Ctrl-C stops it", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
