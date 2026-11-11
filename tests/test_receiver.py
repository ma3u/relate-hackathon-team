"""The QR-paired local receiver: HTTPS with a pinned certificate + bearer token."""
import hashlib
import http.client
import json
import ssl
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from health_graph import receiver, store

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "fixtures" / "fhir" / "2026-09-04-praxis-muster.json"
WEARABLES = ROOT / "fixtures" / "apple-health-weekly.json"


@pytest.fixture()
def server(tmp_path, monkeypatch):
    monkeypatch.setattr(receiver, "CONFIG", tmp_path / "config")
    cert, key, token, fp = receiver.ensure_identity()
    db = tmp_path / "health.rl"
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert, key)
    quiet = lambda *_: None
    httpd = receiver.TLSServer(("127.0.0.1", 0), receiver.make_handler(db, token, "test-mac", log=quiet),
                               ctx, log=quiet)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield {"port": httpd.server_address[1], "token": token, "fp": fp, "db": db}
    httpd.shutdown()


def call(s, method, path, body=None, token=None, headers=None):
    """A client that pins the certificate fingerprint, as Klarbefund does."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE  # trust comes from the pinned fingerprint below
    conn = http.client.HTTPSConnection("127.0.0.1", s["port"], context=ctx, timeout=10)
    conn.connect()
    assert hashlib.sha256(conn.sock.getpeercert(binary_form=True)).hexdigest() == s["fp"]
    h = {"Content-Type": "application/fhir+json", **(headers or {})}
    if token:
        h["Authorization"] = f"Bearer {token}"
    conn.request(method, path, body=json.dumps(body) if body is not None else None, headers=h)
    r = conn.getresponse()
    return r.status, json.loads(r.read() or b"{}")


def test_requires_token(server):
    assert call(server, "GET", "/v1/status")[0] == 401
    assert call(server, "GET", "/v1/status", token="wrong")[0] == 401
    status, body = call(server, "GET", "/v1/status", token=server["token"])
    assert status == 200 and body["name"] == "test-mac"


def test_record_then_wearables(server):
    bundle = json.loads(GOLDEN.read_text())
    status, body = call(server, "POST", "/v1/record", bundle, server["token"],
                        {"X-Klarbefund-Report": "3f2a-report-uuid"})
    assert status == 201 and body["stored"] == 7 and body["hubReady"] == 6
    assert len(body["skipped"]) == 1  # the microbiome value without LOINC

    # sending the same report again replaces it
    assert call(server, "POST", "/v1/record", bundle, server["token"],
                {"X-Klarbefund-Report": "3f2a-report-uuid"})[1]["stored"] == 7

    status, body = call(server, "POST", "/v1/wearables", json.loads(WEARABLES.read_text()), server["token"])
    assert status == 201 and body["stored"] == 16 and body["skipped"] == []

    conn = store.connect(server["db"], read_only=True)
    obs = conn.execute("MATCH (o:Observation) RETURN count(o) AS n").single()["n"]
    weight = [dict(r) for r in conn.execute(
        "MATCH (o:Observation)-[:CODED_BY]->(:LoincCode {code: '29463-7'}) "
        "RETURN o.sourceKind AS kind, count(*) AS n ORDER BY kind")]
    conn.close()
    assert obs == 7 + 16
    # weight from the lab sheet and from Apple Health meet on one LoincCode
    assert weight == [{"kind": "device-weekly-mean", "n": 4}, {"kind": "ocr-transcribed", "n": 1}]


def test_a_stalled_client_does_not_block_others(server):
    import socket
    idle = socket.create_connection(("127.0.0.1", server["port"]))  # never sends a ClientHello
    try:
        assert call(server, "GET", "/v1/status", token=server["token"])[0] == 200
    finally:
        idle.close()


def test_concurrent_sends_and_status(server):
    from concurrent.futures import ThreadPoolExecutor
    bundle = json.loads(GOLDEN.read_text())
    wear = json.loads(WEARABLES.read_text())
    jobs = [("POST", "/v1/record", bundle, {"X-Klarbefund-Report": f"r{i}"}) for i in range(3)]
    jobs += [("POST", "/v1/wearables", wear, None), ("GET", "/v1/status", None, None)] * 2
    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(lambda j: call(server, j[0], j[1], j[2], server["token"], j[3]), jobs))
    assert all(status in (200, 201) for status, _ in results), results
    conn = store.connect(server["db"], read_only=True)
    n = conn.execute("MATCH (o:Observation) RETURN count(o) AS n").single()["n"]
    conn.close()
    assert n == 3 * 7 + 16


def test_rejects_non_bundle(server):
    assert call(server, "POST", "/v1/record", {"resourceType": "Patient"}, server["token"])[0] == 400


def test_pairing_link_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(receiver, "CONFIG", tmp_path / "c")
    _, _, token, fp = receiver.ensure_identity()
    link = receiver.pairing_link("https://192.168.1.20:8787", token, fp, "my-mac", "health.rl")
    u = urlparse(link)
    q = {k: v[0] for k, v in parse_qs(u.query).items()}
    assert (u.scheme, u.netloc) == ("klarbefund", "relate")
    assert q == {"url": "https://192.168.1.20:8787", "token": token, "fp": fp,
                 "name": "my-mac", "store": "health.rl"}
    assert len(fp) == 64 and len(token) >= 43
    assert (tmp_path / "c" / "key.pem").stat().st_mode & 0o077 == 0


def test_certificate_is_x509_v3_for_server_auth(tmp_path, monkeypatch):
    # Apple's TLS refuses a v1 certificate with a decode-error alert.
    monkeypatch.setattr(receiver, "CONFIG", tmp_path / "c")
    cert, *_ = receiver.ensure_identity()
    info = ssl._ssl._test_decode_cert(str(cert))
    assert info["version"] == 3
    assert ("IP Address", "127.0.0.1") in info["subjectAltName"]
    # named curve, not explicit parameters (Apple's TLS: "decode error")
    import subprocess
    text = subprocess.run(["openssl", "x509", "-in", str(cert), "-noout", "-text"],
                          capture_output=True, text=True, check=True).stdout
    assert "Field Type: prime-field" not in text and "prime256v1" in text
