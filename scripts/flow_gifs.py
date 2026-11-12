"""Composes the Klarbefund -> Relate -> Claude Desktop animations in the docs
(docs/img/klarbefund/klarbefund-relate-claude.gif, klarbefund-usb.gif).

Left: frames recorded from Klarbefund in the iOS Simulator with the fictional
development dataset. Right: the Mac side, from the real logs and query results
of a scratch receiver and graph fed by that same Simulator run. Nothing here
is real health data, and neither the vault nor the real pairing is involved.

Recording, into one scratch folder D:

  1. health-graph receive --db D/health.rl --config D/identity --name Demo-Mac \
       --host 127.0.0.1 --port 8799 --print-link     (each line prefixed "<epoch>\t", into D/receiver.log)
  2. Klarbefund in the Simulator with -MBDevData; `xcrun simctl io <sim> recordVideo D/phone.mp4`;
     Menu -> Export to my Mac (Relate); `xcrun simctl openurl <sim> <link>`; Send my reports;
     Send everything now. Final screenshot: D/wifi-done.png.
  3. Same for USB: record D/phone-usb.mp4, tap Send over USB cable, then
     health-graph usb --simulator --config D/identity --db D/usb.rl  (into D/usb.log);
     final screenshot D/usb-done.png.
  4. health-graph query --db D/health.rl stats > D/q-stats.txt; one read_cypher call over
     `relate serve --mcp stdio --read-only` -> D/mcp-query.cypher, D/mcp-result.json.
  5. Changed frames: ffmpeg -i D/phone.mp4 -vf "mpdecimate,scale=330:-1" -fps_mode vfr D/f-phone/%04d.png
     (and D/f-phone-usb). The frame numbers below were picked from those.

usage: uv run --python 3.12 --with pillow python scripts/flow_gifs.py <D> <qr example png> <out dir>
"""
import json
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

D, QR, OUT = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
OUT.mkdir(parents=True, exist_ok=True)

W, H = 960, 600
PHONE_H = 476
BG = (245, 245, 247)
INK = (29, 29, 31)
MUTED = (110, 110, 115)
ACCENT = (0, 113, 227)
TERM_BG = (30, 32, 36)
TERM_FG = (220, 223, 228)
TERM_DIM = (130, 136, 146)
TERM_OK = (120, 200, 140)
TERM_CMD = (240, 200, 110)

SANS = "/System/Library/Fonts/Supplemental/Arial.ttf"
SANS_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
MONO = "/System/Library/Fonts/Menlo.ttc"
f_title = ImageFont.truetype(SANS_BOLD, 22)
f_step = ImageFont.truetype(SANS, 15)
f_foot = ImageFont.truetype(SANS, 12)
f_mono = ImageFont.truetype(MONO, 12)
f_label = ImageFont.truetype(SANS_BOLD, 13)

LINE_H = 16
TERM_BOX = (330, 78, 940, 560)  # x0, y0, x1, y1


def phone(name):
    im = Image.open(name).convert("RGB")
    w = round(im.width * PHONE_H / im.height)
    im = im.resize((w, PHONE_H), Image.LANCZOS)
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, PHONE_H - 1), 28, fill=255)
    framed = Image.new("RGB", (w + 12, PHONE_H + 12), (20, 20, 22))
    fm = Image.new("L", framed.size, 0)
    ImageDraw.Draw(fm).rounded_rectangle((0, 0, framed.width - 1, framed.height - 1), 34, fill=255)
    framed.paste(im, (6, 6), mask)
    return framed, fm


def frame(phone_path, title, step, lines, panel="Mac · Terminal", extra=None):
    """lines: list of (text, color). extra: (image, (x, y)) pasted into the panel."""
    c = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(c)
    d.text((24, 18), title, font=f_title, fill=INK)
    d.text((24, 48), step, font=f_step, fill=ACCENT)
    ph, pm = phone(phone_path)
    c.paste(ph, (24 + (280 - ph.width) // 2, 74), pm)
    x0, y0, x1, y1 = TERM_BOX
    d.rounded_rectangle((x0, y0, x1, y1), 12, fill=TERM_BG)
    for i, col in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse((x0 + 14 + i * 18, y0 + 12, x0 + 26 + i * 18, y0 + 24), fill=col)
    d.text((x0 + 80, y0 + 10), panel, font=f_label, fill=TERM_DIM)
    max_lines = (y1 - y0 - 48) // LINE_H
    shown = lines[-max_lines:]
    for i, (text, color) in enumerate(shown):
        d.text((x0 + 16, y0 + 40 + i * LINE_H), text, font=f_mono, fill=color)
    if extra:
        img, (ex, ey) = extra
        c.paste(img, (x0 + ex, y0 + ey))
    d.text((24, H - 22), "Fictional development data · Klarbefund (iOS Simulator) → Relate graph on the Mac → Claude Desktop over MCP",
           font=f_foot, fill=MUTED)
    return c


def gif(name, frames):
    """frames: list of (Image, ms). Writes PNGs, then ffmpeg with one palette."""
    tmp = OUT / f".{name}"
    tmp.mkdir(exist_ok=True)
    for p in tmp.glob("*.png"):
        p.unlink()
    concat = []
    for i, (im, ms) in enumerate(frames):
        p = tmp / f"{i:04d}.png"
        im.save(p)
        concat.append(f"file '{p}'\nduration {ms / 1000:.3f}")
    concat.append(f"file '{tmp / f'{len(frames) - 1:04d}.png'}'")
    (tmp / "list.txt").write_text("\n".join(concat) + "\n")
    out = OUT / f"{name}.gif"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(tmp / "list.txt"),
         "-vf", "split[a][b];[a]palettegen=max_colors=128:stats_mode=full[p];[b][p]paletteuse=dither=bayer:bayer_scale=4",
         "-loop", "0", str(out)], check=True)
    print(out, round(out.stat().st_size / 1024), "KB")


def term_table(text):
    return [(l, TERM_FG) for l in text.strip("\n").splitlines()]


fp = lambda n: str(D / "f-phone" / f"{n:04d}.png")
fu = lambda n: str(D / "f-phone-usb" / f"{n:04d}.png")
log = [l.split("\t", 1)[1] for l in (D / "receiver.log").read_text().splitlines() if "\t" in l]
posts = [l for l in log if l.startswith("127.0.0.1 POST") or l.startswith("report ")]
qr = Image.open(QR).convert("RGB").resize((150, 150), Image.NEAREST)

# Shown as the documented command prints it; the run behind it used a
# scratch store and its own identity, never the vault or the real pairing.
LAN = "192.168.1.20"
PHONE_IP = "192.168.1.31"
recv_head = [
    ("$ scripts/health_vault.sh receive", TERM_CMD),
    ("", TERM_FG),
    ("Scan this in Klarbefund: Menu -> Export to my Mac (Relate)", TERM_FG),
] + [("", TERM_FG)] * 10 + [
    (f"Receiving at https://{LAN}:8787 into ~/RelateHealth/health.rl", TERM_FG),
    ("Ctrl+C stops the receiver.", TERM_DIM),
    ("", TERM_FG),
]
qr_at = (16, 40 + 3 * LINE_H)

T1 = "Klarbefund → your own Mac (Wi-Fi)"
frames = []
frames.append((frame(fp(1), T1, "1  On the Mac: unlock the vault and start the receiver", recv_head[:1]), 1200))
frames.append((frame(fp(1), T1, "1  On the Mac: unlock the vault and start the receiver", recv_head, extra=(qr, qr_at)), 1800))
for n, ms in [(8, 1400), (20, 1600)]:
    frames.append((frame(fp(n), T1, "2  In Klarbefund: Menu → Export to my Mac (Relate)", recv_head, extra=(qr, qr_at)), ms))
status = [(f"{PHONE_IP} GET /v1/status 200", TERM_OK)]
frames.append((frame(fp(30), T1, "3  Scan the Mac's QR code: paired, certificate pinned", recv_head + status), 2000))
frames.append((frame(fp(31), T1, "4  Send my reports, then Send everything now", recv_head + status), 1200))
shown = recv_head + status
sending = [35, 40, 45, 50, 55, 60, 64]
chunk = max(1, len(posts) // len(sending))
for i, n in enumerate(sending):
    for l in posts[i * chunk:(i + 1) * chunk]:
        shown = shown + [(l.replace("127.0.0.1", PHONE_IP), TERM_OK if "201" in l else TERM_FG)]
    frames.append((frame(fp(n), T1, "4  34 reports go to the Mac over TLS, one FHIR bundle each", shown), 450))
for l in posts[len(sending) * chunk:]:
    shown = shown + [(l.replace("127.0.0.1", PHONE_IP), TERM_OK if "201" in l else TERM_FG)]
DONE = str(D / "wifi-done.png")
frames.append((frame(DONE, T1, "4  Done: 240 values from 34 reports on Demo-Mac", shown), 2600))

stats = (D / "q-stats.txt").read_text()
q = [("$ health-graph query --db ~/RelateHealth/health.rl stats", TERM_CMD)] + term_table(stats)
frames.append((frame(DONE, "The graph on the Mac: Relate, Neo4j's embedded graph database", "5  One node per report, value, LOINC code and source", q), 3800))

res = json.loads((D / "mcp-result.json").read_text())
cy = (D / "mcp-query.cypher").read_text().splitlines()
rows = res["rows"]
table = [f"{'date':<11}{'value':>6} {'unit':<6} {'printed':<8} source"]
table += [f"{r['date']:<11}{r['value']:>6} {r['unit']:<6} {r['printed']:<8} {r['source']}" for r in rows]
mcp = (
    [("MCP server klarbefund-health: relate serve --mcp --read-only", TERM_DIM), ("", TERM_FG),
     ("Asked in Claude Desktop: \"How did my LDL cholesterol develop?\"", TERM_CMD), ("", TERM_FG),
     ("→ tools/call read_cypher   (an example of the Cypher Claude writes)", TERM_OK)]
    + [("  " + l, TERM_FG) for l in cy]
    + [("", TERM_FG), (f"← {len(rows)} rows", TERM_OK)]
    + [("  " + l, TERM_FG) for l in table]
)
T3 = "Claude Desktop reads the graph over MCP"
frames.append((frame(DONE, T3, "6  Claude Desktop calls the local MCP server, read-only", mcp[:5], panel="MCP: what Claude Desktop sends and gets back"), 1800))
frames.append((frame(DONE, T3, "6  It writes Cypher; Relate answers from the graph on the Mac", mcp[:5 + len(cy)], panel="MCP: what Claude Desktop sends and gets back"), 2400))
frames.append((frame(DONE, T3, "6  Only the rows a question returns go to Claude", mcp, panel="MCP: what Claude Desktop sends and gets back"), 5000))
gif("klarbefund-relate-claude", frames)

# --- USB ---
ulog = [l.split("\t", 1)[1] for l in (D / "usb.log").read_text().splitlines() if "\t" in l]
reports = [l for l in ulog if l.startswith("report ")]
done = [l for l in ulog if l.startswith("Done:")][0]
done = re.sub(r"into .*$", "into ~/RelateHealth/health.rl", done)
T2 = "Klarbefund → your own Mac (USB cable, no shared Wi-Fi)"
head = [("$ scripts/health_vault.sh usb", TERM_CMD), ("Waiting for an iPhone on the USB cable...", TERM_FG)]
uf = []
uf.append((frame(DONE, T2, "1  Connect the iPhone with a cable; run the usb command", head), 1800))
found = head + [("iPhone found. In Klarbefund: Menu -> Export to my Mac (Relate)", TERM_FG), ("  -> Send over USB cable", TERM_FG)]
uf.append((frame(fu(2), T2, "2  In Klarbefund: Send over USB cable", found), 2200))
shown = found + [("Connected over USB. Receiving...", TERM_OK)]
steps = [34, 38, 42, 46, 50, 54, 58]
chunk = max(1, len(reports) // len(steps))
for i, n in enumerate(steps):
    shown = shown + [(l, TERM_FG) for l in reports[i * chunk:(i + 1) * chunk]]
    uf.append((frame(fu(n), T2, "3  The Mac proves it is the paired one, then the phone sends", shown), 450))
head_done, tail_done = done.split(" into ")
shown = shown + [(l, TERM_FG) for l in reports[len(steps) * chunk:]] + [(head_done, TERM_OK), ("  into " + tail_done, TERM_OK)]
uf.append((frame(str(D / "usb-done.png"), T2, "4  Done: the same graph, no network involved", shown), 4000))
gif("klarbefund-usb", uf)
