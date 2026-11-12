"""Renders an animated HTML scene to an MP4, frame by frame, in one Chrome.

The page defines `window.render(t)`, which draws the scene at t seconds. Each frame
calls it and takes a screenshot, so the animation is exact and never depends on
how fast the machine is. Used for the presentation's scenes (phone flows, the
risk views, the metadata model) that demo_video.py then plays as `video` segments.

usage: uv run --python 3.12 --with playwright python scripts/render_scene.py \
         <scene.html> <seconds> <out.mp4> [--fps 30]
"""
import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

W, H = 1920, 1080


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("html")
    ap.add_argument("seconds", type=float)
    ap.add_argument("out")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--still", type=float, action="append", default=[],
                    help="only write a PNG at this time (repeatable), for a look")
    args = ap.parse_args()
    src, out = Path(args.html).resolve(), Path(args.out).resolve()

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        page = browser.new_page(viewport={"width": W, "height": H})
        page.goto(src.as_uri(), wait_until="load")
        page.evaluate("document.fonts.ready")
        page.wait_for_function("[...document.images].every(i => i.complete)")
        if args.still:
            for t in args.still:
                page.evaluate(f"render({t})")
                page.screenshot(path=str(out.with_name(f"{out.stem}-{t:g}.png")))
            browser.close()
            return
        frames = Path(tempfile.mkdtemp(prefix="scene-"))
        n = round(args.seconds * args.fps)
        for f in range(n):
            page.evaluate(f"render({f / args.fps})")
            page.screenshot(path=str(frames / f"{f:05d}.jpg"), type="jpeg", quality=94)
        browser.close()

    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(args.fps), "-i", str(frames / "%05d.jpg"),
                    "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", str(out)], check=True)
    shutil.rmtree(frames)
    print(f"wrote {out} ({n} frames)")


if __name__ == "__main__":
    main()
