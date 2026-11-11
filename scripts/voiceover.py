"""Generate a voice-over MP3 for the demo video with ElevenLabs.

Setup: cp .env.example .env and paste your ELEVENLABS_API_KEY into .env.

Usage (from the repo root):
    .venv/bin/python scripts/voiceover.py --list-voices
    .venv/bin/python scripts/voiceover.py docs/demo/voiceover-sample.txt
    .venv/bin/python scripts/voiceover.py docs/demo/voiceover-sample.txt --voice <voice_id> -o media/intro.mp3
"""
import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VOICE = "JBFqnCBsd6RMkjVDRZzb"  # "George", a stock ElevenLabs voice
MODEL = "eleven_multilingual_v2"  # handles English and German


def main() -> int:
    load_dotenv(ROOT / ".env")
    key = os.getenv("ELEVENLABS_API_KEY")
    if not key:
        print("ELEVENLABS_API_KEY is not set. Copy .env.example to .env and add your key.", file=sys.stderr)
        return 2

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("text_file", nargs="?", type=Path, help="plain-text narration script")
    ap.add_argument("--voice", default=os.getenv("ELEVENLABS_VOICE_ID") or DEFAULT_VOICE)
    ap.add_argument("-o", "--out", type=Path, help="output .mp3 (default: media/<text_file stem>.mp3)")
    ap.add_argument("--list-voices", action="store_true", help="print available voices and exit")
    args = ap.parse_args()

    client = ElevenLabs(api_key=key)

    if args.list_voices:
        for v in client.voices.get_all().voices:
            print(f"{v.voice_id}  {v.name}  ({v.category})")
        return 0

    if not args.text_file:
        ap.error("text_file is required unless --list-voices is given")

    text = args.text_file.read_text(encoding="utf-8").strip()
    out = args.out or ROOT / "media" / f"{args.text_file.stem}.mp3"
    out.parent.mkdir(parents=True, exist_ok=True)

    audio = client.text_to_speech.convert(
        voice_id=args.voice,
        text=text,
        model_id=MODEL,
        output_format="mp3_44100_128",
    )
    with out.open("wb") as f:
        for chunk in audio:
            f.write(chunk)
    print(f"wrote {out} ({out.stat().st_size // 1024} KB, {len(text)} chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
