"""Local receiver: Klarbefund on the iPhone -> your Mac -> health.rl.

    python -m health_graph receive --db health.rl

Shows a QR code. Klarbefund scans it (Menu -> "Export to my Mac (Relate)")
and from then on sends each report as a FHIR Bundle, plus the Apple Health
weekly means, straight to this Mac over your own Wi-Fi. No cloud in between.

Security model
- HTTPS with a self-signed certificate made on first start. The QR code
  carries the certificate's SHA-256 fingerprint and the app pins it, so a
  look-alike server on the same network cannot receive anything.
- A bearer token (256 bit) in the QR code; requests without it get 401.
- Only private-network and loopback clients are served.
- One request at a time, so there is a single writer on the store.
The certificate, key and token live in ~/.config/relate-health-graph (0600).
`--rotate` makes a new token, so a phone paired before must scan again.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import socket
import ssl
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

from . import fhir, store

CONFIG = Path(os.environ.get("RELATE_HEALTH_HOME", Path.home() / ".config" / "relate-health-graph"))
MAX_BODY = 10 * 1024 * 1024
HANDSHAKE_TIMEOUT = 15
WRITE_LOCK = threading.Lock()  # one writer on the store at a time


class TLSServer(ThreadingHTTPServer):
    """TLS per connection, in the connection's own thread with a timeout,
    so one slow or broken client can never block the others."""

    daemon_threads = True

    def __init__(self, address, handler, context: ssl.SSLContext, log=print):
        super().__init__(address, handler)
        self.context = context
        self.log = log

    def finish_request(self, request, client_address):
        request.settimeout(HANDSHAKE_TIMEOUT)
        try:
            tls = self.context.wrap_socket(request, server_side=True)
        except (ssl.SSLError, OSError) as e:
            self.log(f"{client_address[0]} TLS handshake failed: {e}")
            return
        tls.settimeout(60)
        self.RequestHandlerClass(tls, client_address, self)


def lan_address() -> str:
    """The address other devices on the Wi-Fi reach this Mac at."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 9))  # TEST-NET, nothing is sent
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def _cert_ok(cert: Path) -> bool:
    """X.509 v3 with a named-curve key: what Apple's TLS stack accepts."""
    try:
        if ssl._ssl._test_decode_cert(str(cert)).get("version") != 3:
            return False
        text = subprocess.run(["openssl", "x509", "-in", str(cert), "-noout", "-text"],
                              check=True, capture_output=True, text=True).stdout
        return "Field Type: prime-field" not in text
    except Exception:
        return False


def _make_certificate(cert: Path, key: Path) -> None:
    """An X.509 v3 server certificate. Apple's TLS stack (iOS, macOS) refuses
    a v1 certificate during the handshake, before any pinning code runs."""
    host = socket.gethostname().split(".")[0]
    sans = ["IP:127.0.0.1", f"IP:{lan_address()}", "DNS:localhost", f"DNS:{host}.local"]
    conf = CONFIG / "openssl.cnf"
    conf.write_text(
        "[req]\ndistinguished_name=dn\nx509_extensions=v3\nprompt=no\n"
        "[dn]\nCN=Relate Health Graph (local)\n"
        "[v3]\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\n"
        f"extendedKeyUsage=serverAuth\nsubjectAltName={','.join(sans)}\n")
    subprocess.run(
        # named_curve: LibreSSL (macOS's openssl) otherwise writes explicit
        # curve parameters, which Apple's TLS rejects with a decode error.
        ["openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1",
         "-pkeyopt", "ec_param_enc:named_curve", "-sha256", "-nodes", "-days", "825", "-config", str(conf),
         "-keyout", str(key), "-out", str(cert)],
        check=True, capture_output=True)
    key.chmod(0o600)


def ensure_identity(rotate: bool = False) -> tuple[Path, Path, str, str]:
    """Certificate, key, token and the certificate's SHA-256 fingerprint."""
    CONFIG.mkdir(parents=True, exist_ok=True, mode=0o700)
    cert, key, token_file = CONFIG / "cert.pem", CONFIG / "key.pem", CONFIG / "token"
    if not cert.exists() or not key.exists() or not _cert_ok(cert):
        _make_certificate(cert, key)
    if rotate or not token_file.exists():
        token_file.write_text(secrets.token_urlsafe(32))
        token_file.chmod(0o600)
    der = ssl.PEM_cert_to_DER_cert(cert.read_text())
    return cert, key, token_file.read_text().strip(), hashlib.sha256(der).hexdigest()


def pairing_link(url: str, token: str, fingerprint: str, name: str, store_name: str) -> str:
    q = lambda s: quote(s, safe="")
    return (f"klarbefund://relate?url={q(url)}&token={q(token)}&fp={fingerprint}"
            f"&name={q(name)}&store={q(store_name)}")


def _private(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local


def make_handler(db: Path, token: str, name: str, log=print):
    class Handler(BaseHTTPRequestHandler):
        server_version = "RelateHealthGraph/1"

        def log_message(self, fmt, *args):  # quieter, and never log bodies
            log(f"{self.client_address[0]} {fmt % args}")

        def _json(self, status: int, payload: dict):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self) -> bool:
            if not _private(self.client_address[0]):
                self._json(403, {"error": "only devices on your own network"})
                return False
            given = self.headers.get("Authorization", "")
            if not hmac.compare_digest(given.encode(), f"Bearer {token}".encode()):
                self._json(401, {"error": "scan the QR code again"})
                return False
            return True

        def _body(self) -> dict | None:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > MAX_BODY:
                self._json(413 if length else 400, {"error": "a FHIR Bundle up to 10 MB is required"})
                return None
            try:
                return json.loads(self.rfile.read(length))
            except json.JSONDecodeError:
                self._json(400, {"error": "not JSON"})
                return None

        def do_GET(self):
            if self.path != "/v1/status":
                return self._json(404, {"error": "not found"})
            if not self._authorized():
                return
            n = 0
            with WRITE_LOCK:  # never read while this receiver is mid-write
                if db.exists():  # a read-only open never creates a store
                    try:
                        conn = store.connect(db, read_only=True)
                        try:
                            n = conn.execute("MATCH (o:Observation) RETURN count(o) AS n").single()["n"]
                        finally:
                            conn.close()
                    except Exception as e:
                        log(f"status failed: {type(e).__name__}: {e}")
                        return self._json(503, {"error": "the graph is busy, try again"})
            self._json(200, {"name": name, "store": db.name, "observations": n})

        def do_POST(self):
            if self.path not in ("/v1/record", "/v1/wearables"):
                return self._json(404, {"error": "not found"})
            if not self._authorized():
                return
            bundle = self._body()
            if bundle is None:
                return
            if bundle.get("resourceType") != "Bundle":
                return self._json(400, {"error": "not a FHIR Bundle"})
            with WRITE_LOCK:
                for attempt in range(6):  # another process (a CLI query, MCP) may hold the store
                    try:
                        return self._import(bundle)
                    except Exception as e:
                        if "locked" in str(e).lower() and attempt < 5:
                            time.sleep(0.5 * (attempt + 1))
                            continue
                        log(f"import failed: {type(e).__name__}: {e}")
                        return self._json(503 if "locked" in str(e).lower() else 500,
                                          {"error": "the graph could not be written, try again"})

        def _import(self, bundle: dict):
            conn = store.connect(db)
            try:
                store.init_schema(conn)
                if self.path == "/v1/record":
                    report = self.headers.get("X-Klarbefund-Report") or None
                    parsed = fhir.parse_bundle(bundle, report_id=report)
                    stored = store.import_report(conn, parsed)
                    store.omop_transform(conn)
                    skipped = [{"id": o["fhirId"], "reason": o["unmappedReason"] or "no LOINC code"}
                               for o in parsed.observations if not o["code"]]
                    log(f"report {parsed.report_id}: {stored} values")
                    self._json(201, {"stored": stored, "skipped": skipped,
                                     "hubReady": sum(o["hubEligible"] for o in parsed.observations)})
                else:
                    patient = store.single_patient(conn)
                    rows, skipped = fhir.parse_wearables(bundle, patient)
                    stored = store.import_wearables(conn, patient, rows)
                    store.omop_transform(conn)
                    log(f"apple health: {stored} weekly values")
                    self._json(201, {"stored": stored, "skipped": skipped})
            except ValueError as e:
                self._json(400, {"error": str(e)})
            finally:
                conn.close()

    return Handler


def serve(db: str, port: int = 8787, rotate: bool = False, host: str | None = None,
          qr_png: str | None = None, print_link: bool = False) -> None:
    import segno

    db_path = Path(db).resolve()
    conn = store.connect(db_path)  # create the store and schema up front
    store.init_schema(conn)
    conn.close()

    cert, key, token, fp = ensure_identity(rotate)
    address = host or lan_address()
    name = socket.gethostname().split(".")[0]
    url = f"https://{address}:{port}"
    link = pairing_link(url, token, fp, name, db_path.name)

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(cert, key)
    httpd = TLSServer(("0.0.0.0", port), make_handler(db_path, token, name), ctx)

    qr = segno.make(link, error="m")
    print("\nScan this in Klarbefund: Menu -> Export to my Mac (Relate)\n")
    qr.terminal(compact=True, border=2)
    if qr_png:
        qr.save(qr_png, scale=8, border=3)
        os.chmod(qr_png, 0o600)
        print(f"QR code also saved to {qr_png} (it contains the token, keep it private)")
    if print_link:
        print(f"\nPairing link (for the Simulator or a paste; it contains the token):\n{link}")
    print(f"\nReceiving at {url} into {db_path}")
    print(f"Certificate SHA-256: {fp}")
    print("Ctrl+C stops the receiver.\n")
    sys.stdout.flush()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("stopped")
