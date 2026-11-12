"""Renders a real Claude conversation (claude -p --output-format stream-json,
one file per turn) as a video clip: the question, each MCP tool call with its
Cypher, then the answer line by line.

    .venv/bin/python scripts/chat_clip.py OUT.mp4 q1.jsonl q2.jsonl q3.jsonl [--seconds 36]

Nothing is written or edited: every word and every query is taken from the
transcripts. The clip says so in its header. The transcripts and the clip hold
real health data, so both belong in the encrypted vault, never here.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
W, H = 1920, 1080

CSS = """
*{box-sizing:border-box}html,body{margin:0;width:1920px;height:1080px;overflow:hidden;background:#0d0f12;color:#eceef1;
font-family:-apple-system,"SF Pro Text","Helvetica Neue",Arial,sans-serif}
header{height:84px;display:flex;align-items:center;gap:16px;padding:0 64px;border-bottom:1px solid #22262d}
header b{font-size:26px}header span{color:#8c939e;font-size:20px}
.dot{width:14px;height:14px;border-radius:50%;background:#16c60c;box-shadow:0 0 12px #16c60c}
main{position:absolute;top:84px;bottom:58px;left:0;right:0;display:flex;flex-direction:column;justify-content:flex-end;
padding:24px 260px;overflow:hidden;gap:16px}
.q{align-self:flex-end;background:#2a3140;border-radius:22px 22px 6px 22px;padding:18px 24px;font-size:25px;max-width:1100px;line-height:1.35}
.tool{font-family:Menlo,monospace;font-size:17px;color:#9fb6d6;background:#141920;border:1px solid #243041;border-radius:12px;
padding:10px 16px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:1400px}
.tool i{font-style:normal;color:#6fd36a;margin-right:10px}
.a{font-size:22px;line-height:1.45;max-width:1400px}.a p{margin:0 0 10px}.a ul{margin:0 0 8px;padding-left:30px}
.a li{margin:3px 0}.a b{color:#fff}.a h4{margin:6px 0;font-size:22px}
footer{position:absolute;bottom:0;left:0;right:0;height:58px;display:flex;align-items:center;padding:0 64px;color:#7d8590;font-size:17px;
border-top:1px solid #22262d}
"""


def md(text: str) -> list[str]:
    """Markdown lines to HTML blocks (bullets, bold, headings), one block per source line."""
    blocks = []
    for line in text.splitlines():
        if not line.strip():
            continue
        s = html.escape(line.strip())
        s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
        indent = (len(line) - len(line.lstrip())) // 2
        if line.lstrip().startswith(("- ", "* ")):
            pad = 30 * (indent + 1)
            blocks.append(f'<p style="padding-left:{pad}px;text-indent:-18px">• {s[2:]}</p>')
        elif s.startswith("#"):
            blocks.append(f"<h4>{s.lstrip('#').strip()}</h4>")
        else:
            blocks.append(f"<p>{s}</p>")
    return blocks


def turns(path: Path) -> tuple[str, list[str], str]:
    question, tools, answer = "", [], ""
    for line in path.read_text().splitlines():
        m = json.loads(line)
        if m.get("type") == "user" and not question:
            for c in m.get("message", {}).get("content", []) if isinstance(m.get("message", {}).get("content"), list) else []:
                if c.get("type") == "text":
                    question = c["text"]
        if m.get("type") == "assistant":
            for c in m["message"]["content"]:
                if c["type"] == "tool_use" and c["name"].startswith("mcp__"):
                    stmt = " ".join((c["input"].get("statement") or "").split())
                    tools.append(f'<i>{c["name"].split("__")[-1]}</i>{html.escape(stmt) or "(schema)"}')
                if c["type"] == "text":
                    answer = c["text"]  # the final text block is the answer
    return question, tools, answer


def render(page: str, png: Path) -> None:
    src = png.with_suffix(".html")
    src.write_text(f"<!doctype html><meta charset=utf-8><style>{CSS}</style>{page}", encoding="utf-8")
    for attempt in range(3):  # headless Chrome now and then exits early under load
        res = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--window-size={W},{H}",
                              "--force-device-scale-factor=1", f"--screenshot={png}", f"file://{src}"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if res.returncode == 0 and png.exists():
            return
    raise RuntimeError(f"Chrome could not render {src.name}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("transcripts", nargs="+")
    ap.add_argument("--questions", nargs="*", help="the questions as shown (default: from the transcripts)")
    ap.add_argument("--seconds", type=float, default=36)
    args = ap.parse_args()
    out = Path(args.out).expanduser()
    if str(ROOT) in str(out.resolve()):
        sys.exit("the clip holds real health data: write it into the vault, not the repository")
    work = out.parent / "chat-frames"
    work.mkdir(exist_ok=True)

    head = ('<header><div class="dot"></div><b>Claude</b><span>· klarbefund-health (Relate MCP server, read-only, '
            'snapshot of the encrypted vault)</span></header>')
    foot = ('<footer>Real questions and answers: Claude with the klarbefund-health MCP server, every Cypher query as '
            'Claude sent it. Not medical advice.</footer>')
    frames: list[tuple[Path, float]] = []
    shown: list[str] = []

    def frame(weight: float):
        png = work / f"{len(frames):03d}.png"
        render(head + f'<main>{"".join(shown)}</main>' + foot, png)
        frames.append((png, weight))

    for i, t in enumerate(args.transcripts):
        q, tools, answer = turns(Path(t).expanduser())
        if args.questions and i < len(args.questions):
            q = args.questions[i]
        shown = [f'<div class="q">{html.escape(q)}</div>']  # each question starts a fresh screen
        frame(1.6)
        for tool in tools:
            shown.append(f'<div class="tool">{tool}</div>')
            frame(0.6)
        blocks = md(answer)
        step = max(1, len(blocks) // 6)
        body = []
        for j in range(0, len(blocks), step):
            body = blocks[: j + step]
            shown_now = shown + [f'<div class="a">{"".join(body)}</div>']
            png = work / f"{len(frames):03d}.png"
            render(head + f'<main>{"".join(shown_now)}</main>' + foot, png)
            frames.append((png, 1.0))
        frames[-1] = (frames[-1][0], 3.0)  # hold the full answer

    total = sum(w for _, w in frames)
    scale = args.seconds / total
    lst = work / "frames.txt"
    lst.write_text("".join(f"file '{p}'\nduration {w * scale:.3f}\n" for p, w in frames) + f"file '{frames[-1][0]}'\n")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-vf",
                    "fps=30,format=yuv420p", "-c:v", "libx264", str(out)], check=True)
    print(f"wrote {out}: {len(frames)} frames, {args.seconds:.0f} s")


if __name__ == "__main__":
    main()
