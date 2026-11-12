"""Makes a narration clip deeper and warmer, keeping its timing.

Pitch down (Rubber Band, through pedalboard), a little low end, a little less
high end, and gentle compression. demo_video.py calls it for every segment when
the storyboard has "voice_fx": {"semitones": -2.5}; the result is cached next to
the ElevenLabs audio, so a rebuild costs no characters.

usage: uv run --python 3.12 --with pedalboard python scripts/voice_fx.py <in> <out.wav> <semitones>
"""
import sys

from pedalboard import Compressor, Gain, HighShelfFilter, LowShelfFilter, Pedalboard, PitchShift
from pedalboard.io import AudioFile


def main() -> None:
    src, out, semitones = sys.argv[1], sys.argv[2], float(sys.argv[3])
    with AudioFile(src) as f:
        audio, rate = f.read(f.frames), f.samplerate
    board = Pedalboard([
        PitchShift(semitones=semitones),
        LowShelfFilter(cutoff_frequency_hz=160, gain_db=2.5),
        HighShelfFilter(cutoff_frequency_hz=7000, gain_db=-2.0),
        Compressor(threshold_db=-18, ratio=2.0, attack_ms=10, release_ms=120),
        Gain(gain_db=1.0),
    ])
    deeper = board(audio, rate)
    with AudioFile(out, "w", rate, deeper.shape[0]) as f:
        f.write(deeper)


if __name__ == "__main__":
    main()
