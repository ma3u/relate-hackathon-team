"""Builds the demo video (max 3 minutes) from a storyboard: narrated segments,
each with one visual: a card, a phone screenshot, a GIF, a scroll through the
dashboard, or a screen recording.

    .venv/bin/python scripts/demo_video.py ~/RelateHealth/demo/video.json [--voice] [--only ID]

The storyboard and everything it produces live in the encrypted vault: the
dashboard and the Claude Desktop recording show real health data. Narration
comes from ElevenLabs (ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID in .env), one
file per segment, cached by its text, so a changed line costs only that line.
Without --voice, silent placeholders as long as the text would take are used.

Storyboard (JSON): {"title": ..., "segments": [{"id", "text", "visual": {...},
"min": seconds}]}; visual types:
  card   {"type": "card", "kicker", "title", "body"}           rendered HTML
  phone  {"type": "phone", "images": [...], "caption"}         screenshots side by side
  gif    {"type": "gif", "src", "caption"}                     an animation, looped to fit
  image  {"type": "image", "src"}                              a still, slowly pushed in
  scroll {"type": "scroll", "src", "caption"}                  a tall PNG, panned top to bottom
  video  {"type": "video", "src", "start", "caption"}          a recording, cut to fit
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
W, H, FPS = 1920, 1080, 30
WPM = 150  # placeholder pace without a voice

CSS = """
*{box-sizing:border-box}html,body{margin:0;width:1920px;height:1080px;overflow:hidden}
body{background:#0e1116;color:#f2f3f5;font-family:-apple-system,"SF Pro Display","Helvetica Neue",Arial,sans-serif;
display:flex;flex-direction:column;justify-content:center;padding:0 140px}
.kicker{color:#5aa2ff;font-size:30px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;margin:0 0 18px}
h1{font-size:92px;line-height:1.05;margin:0 0 30px;font-weight:750;max-width:1500px}
.body{font-size:38px;line-height:1.4;color:#c7cbd3;max-width:1450px;white-space:pre-line}
.stage{align-items:center;padding:60px 80px 120px}
.row{display:flex;gap:56px;align-items:center;justify-content:center;height:820px}
.row img{height:820px;border-radius:44px;box-shadow:0 30px 80px rgba(0,0,0,.55);border:8px solid #1d2128}
.cap{position:absolute;left:0;right:0;bottom:46px;text-align:center;font-size:36px;color:#dfe3ea;font-weight:500}
.brand{position:absolute;right:56px;top:40px;font-size:24px;color:#7d8590}
"""


def esc(s) -> str:
    return html.escape(str(s or ""))


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def render_html(page: str, png: Path, work: Path) -> None:
    src = work / (png.stem + ".html")
    src.write_text(f"<!doctype html><meta charset=utf-8><style>{CSS}</style>{page}", encoding="utf-8")
    run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--window-size={W},{H}",
         "--force-device-scale-factor=1", f"--screenshot={png}", f"file://{src}"])


def caption(text: str) -> str:
    return f'<div class="cap">{esc(text)}</div>' if text else ""


def brand(title: str) -> str:
    return f'<div class="brand">{esc(title)}</div>'


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


# ── narration ────────────────────────────────────────────────────────────────
def env() -> dict[str, str]:
    values = {}
    for line in (ROOT / ".env").read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            values[k.strip()] = v.strip().strip('"')
    return values


def narrate(text: str, out_dir: Path, voice: bool) -> Path:
    key = hashlib.sha256(text.encode()).hexdigest()[:16]
    mp3 = out_dir / f"{key}.mp3"
    if mp3.exists():
        return mp3
    if not voice:
        silent = out_dir / f"{key}-silent.m4a"
        if not silent.exists():
            seconds = max(2.0, len(text.split()) / WPM * 60)
            run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", f"{seconds:.2f}", str(silent)])
        return silent
    e = env()
    body = json.dumps({"text": text, "model_id": "eleven_multilingual_v2",
                       "voice_settings": {"stability": 0.5, "similarity_boost": 0.8, "style": 0.2}})
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{e['ELEVENLABS_VOICE_ID']}?output_format=mp3_44100_128"
    # The key goes to curl on stdin (a config file), never on the command line.
    cfg = f'header = "xi-api-key: {e["ELEVENLABS_API_KEY"]}"\nheader = "Content-Type: application/json"\n'
    res = subprocess.run(["curl", "-s", "-f", "-o", str(mp3), "-X", "POST", url, "-K", "-", "--data-binary", body],
                         input=cfg, text=True, capture_output=True)
    if res.returncode != 0:
        mp3.unlink(missing_ok=True)
        sys.exit(f"ElevenLabs refused the segment (curl {res.returncode}); nothing else was sent")
    return mp3


# ── visuals ──────────────────────────────────────────────────────────────────
def clip(seg: dict, seconds: float, work: Path, title: str, base: Path) -> Path:
    v = seg["visual"]
    out = work / f"{seg['id']}.mp4"
    enc = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS), "-t", f"{seconds:.3f}", "-an"]
    fit = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
           f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=0x0e1116,setsar=1")
    if v["type"] == "card":
        png = work / f"{seg['id']}.png"
        render_html(f'<p class="kicker">{esc(v.get("kicker"))}</p><h1>{esc(v["title"])}</h1>'
                    f'<div class="body">{esc(v.get("body"))}</div>{brand(title)}', png, work)
        run(["ffmpeg", "-y", "-loop", "1", "-i", str(png), "-vf", f"{fit},fade=in:0:12", *enc, str(out)])
    elif v["type"] == "phone":
        png = work / f"{seg['id']}.png"
        imgs = "".join(f'<img src="file://{(base / p).resolve()}">' for p in v["images"])
        render_html(f'<body class="stage"><div class="row">{imgs}</div>{caption(v.get("caption"))}{brand(title)}',
                    png, work)
        run(["ffmpeg", "-y", "-loop", "1", "-i", str(png), "-vf", fit, *enc, str(out)])
    elif v["type"] == "image":
        src = (base / v["src"]).resolve()
        # A still, with a slow push-in so it does not sit dead on screen.
        zoom = (f"{fit},scale=2*{W}:2*{H},zoompan=z='min(1+0.0006*on,1.06)':d={int(seconds * FPS)}:"
                f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS}")
        run(["ffmpeg", "-y", "-loop", "1", "-i", str(src), "-vf", zoom, *enc, str(out)])
    elif v["type"] == "gif":
        src = (base / v["src"]).resolve()
        run(["ffmpeg", "-y", "-stream_loop", "-1", "-i", str(src), "-vf", fit, *enc, str(out)])
    elif v["type"] == "scroll":
        src = (base / v["src"]).resolve()
        # Scale to the frame's width, then pan from the top to the bottom over the segment.
        pan = (f"scale={W}:-2,crop={W}:{H}:0:'min(ih-{H},max(0,(ih-{H})*(t-1)/{max(seconds - 2, 1):.2f}))',"
               f"setsar=1")
        run(["ffmpeg", "-y", "-loop", "1", "-i", str(src), "-vf", pan, *enc, str(out)])
    elif v["type"] == "video":
        src = (base / v["src"]).resolve()
        run(["ffmpeg", "-y", "-ss", str(v.get("start", 0)), "-i", str(src), "-vf", fit, *enc, str(out)])
    else:
        sys.exit(f"unknown visual type {v['type']}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("storyboard")
    ap.add_argument("--voice", action="store_true", help="narrate with ElevenLabs (costs characters)")
    ap.add_argument("--only", help="build one segment, for a look")
    args = ap.parse_args()

    board_path = Path(args.storyboard).expanduser()
    if str(ROOT) in str(board_path.resolve()):
        sys.exit("the storyboard and the video belong in the vault, not in the repository")
    board = json.loads(board_path.read_text())
    base = board_path.parent
    work = base / "build"
    audio = base / "audio"
    work.mkdir(exist_ok=True)
    audio.mkdir(exist_ok=True)

    segments = [s for s in board["segments"] if not args.only or s["id"] == args.only]
    chars = sum(len(s["text"]) for s in segments)
    print(f"{len(segments)} segments, {chars} characters of narration" + (" (ElevenLabs)" if args.voice else " (silent)"))

    clips, voices, srt, t = [], [], [], 0.0
    for i, seg in enumerate(segments, 1):
        mp3 = narrate(seg["text"], audio, args.voice)
        spoken = duration(mp3)
        seconds = max(spoken + 0.7, seg.get("min", 0))
        clips.append(clip(seg, seconds, work, board.get("title", ""), base))
        padded = work / f"{seg['id']}-voice.m4a"
        run(["ffmpeg", "-y", "-i", str(mp3), "-af", f"apad,atrim=0:{seconds:.3f}", "-ar", "44100", "-ac", "2",
             str(padded)])
        voices.append(padded)
        stamp = lambda x: f"{int(x // 3600):02}:{int(x % 3600 // 60):02}:{int(x % 60):02},{int(x % 1 * 1000):03}"
        srt.append(f"{i}\n{stamp(t)} --> {stamp(t + spoken)}\n{seg['text']}\n")
        t += seconds
        print(f"  {seg['id']:<10} {seconds:5.1f}s  (spoken {spoken:4.1f}s)")

    name = args.only or "demo"
    video_list = work / "clips.txt"
    video_list.write_text("".join(f"file '{c}'\n" for c in clips))
    audio_list = work / "voices.txt"
    audio_list.write_text("".join(f"file '{a}'\n" for a in voices))
    out = base / f"{name}.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(video_list), "-f", "concat", "-safe", "0",
         "-i", str(audio_list), "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest",
         "-movflags", "+faststart", str(out)])
    (base / f"{name}.srt").write_text("\n".join(srt), encoding="utf-8")
    print(f"wrote {out} ({t:.0f} s){'  -- over 3 minutes!' if t > 180 else ''}")


if __name__ == "__main__":
    main()
