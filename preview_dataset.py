"""
preview_dataset.py
==================
View your dataset before uploading to HuggingFace.
Shows samples, stats, and plays audio.

Place in D:\TTS\ and run:
    python preview_dataset.py
    python preview_dataset.py --lang tamil
    python preview_dataset.py --emotion calm
    python preview_dataset.py --play       # plays audio too
"""

import json, os, sys, argparse, subprocess, platform
from collections import Counter

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
FINAL_DIR  = os.path.join(BASE_DIR, "data", "final")
MANIFEST   = os.path.join(FINAL_DIR, "final_manifest.json")


def play_audio(path):
    try:
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess.run(["afplay", path])
        else:
            subprocess.run(["aplay", path])
    except Exception as e:
        print(f"  Cannot play audio: {e}")


def show_sample(seg: dict, idx: int, play: bool):
    print(f"\n{'─'*60}")
    print(f"  Sample #{idx+1}")
    print(f"{'─'*60}")
    print(f"  ID          : {seg.get('segment_id','?')}")
    print(f"  Language    : {seg.get('language','?').upper()}")
    print(f"  Speaker     : {seg.get('speaker_id','?')}  |  Gender: {seg.get('gender','?')}")
    print(f"  Topic       : {seg.get('topic','?')}")
    print(f"  Emotion     : {seg.get('emotion','?')}")
    print(f"  Style       : {seg.get('style','?')}")
    print(f"  Duration    : {seg.get('duration_seconds',0):.1f} seconds")
    print(f"  SNR         : {seg.get('snr_db',0):.1f} dB")
    print(f"  Grade       : {seg.get('quality_grade','?')}")
    print(f"  Audio       : {seg.get('audio_path','?')}")
    print(f"  Transcript  :")
    print()
    # Word wrap
    words = seg.get("transcript","").split()
    line  = "    "
    for w in words:
        if len(line) + len(w) > 65:
            print(line)
            line = "    " + w + " "
        else:
            line += w + " "
    if line.strip():
        print(line)
    print()

    if play:
        audio_path = seg.get("audio_path","")
        if os.path.exists(audio_path):
            print("  Playing audio...")
            play_audio(audio_path)
        else:
            print("  Audio file not found.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lang",    choices=["english","tamil"], default=None)
    parser.add_argument("--emotion", default=None,
                        help="Filter by emotion e.g. calm, excited, neutral")
    parser.add_argument("--grade",   choices=["A","B","C"], default=None)
    parser.add_argument("--count",   type=int, default=10,
                        help="How many samples to show (default 10)")
    parser.add_argument("--play",    action="store_true",
                        help="Play audio for each sample")
    args = parser.parse_args()

    if not os.path.exists(MANIFEST):
        print(f"Manifest not found: {MANIFEST}")
        print("Run 06_quality_filter.py first.")
        sys.exit(1)

    with open(MANIFEST, encoding="utf-8") as f:
        segments = json.load(f)

    # Apply filters
    if args.lang:
        segments = [s for s in segments if s.get("language") == args.lang]
    if args.emotion:
        segments = [s for s in segments if s.get("emotion") == args.emotion]
    if args.grade:
        segments = [s for s in segments if s.get("quality_grade") == args.grade]

    print(f"\n{'='*60}")
    print(f"  DATASET PREVIEW")
    print(f"{'='*60}")

    # Overall stats
    total_min = sum(s.get("duration_seconds",0) for s in segments) / 60
    langs     = Counter(s.get("language","?")      for s in segments)
    emotions  = Counter(s.get("emotion","?")        for s in segments)
    styles    = Counter(s.get("style","?")          for s in segments)
    grades    = Counter(s.get("quality_grade","?")  for s in segments)
    genders   = Counter(s.get("gender","?")         for s in segments)
    topics    = Counter(s.get("topic","?")          for s in segments)

    print(f"\n  Total segments  : {len(segments)}")
    print(f"  Total duration  : {total_min:.1f} minutes")
    print(f"\n  By language     : {dict(langs)}")
    print(f"  By emotion      : {dict(emotions)}")
    print(f"  By style        : {dict(styles)}")
    print(f"  By grade        : {dict(grades)}")
    print(f"  By gender       : {dict(genders)}")
    print(f"  Top topics      : {dict(topics.most_common(5))}")

    # Target check
    en_min = sum(s.get("duration_seconds",0) for s in segments
                 if s.get("language") == "english") / 60
    ta_min = sum(s.get("duration_seconds",0) for s in segments
                 if s.get("language") == "tamil") / 60

    print(f"\n  TARGET CHECK")
    print(f"  English 30 min  : {en_min:.1f} min  {'OK' if en_min >= 30 else 'NEED MORE'}")
    print(f"  Tamil   30 min  : {ta_min:.1f} min  {'OK' if ta_min >= 30 else 'NEED MORE'}")
    print(f"  Total   60 min  : {en_min+ta_min:.1f} min  {'OK' if en_min+ta_min >= 60 else 'NEED MORE'}")

    print(f"\n{'='*60}")
    print(f"  SHOWING {min(args.count, len(segments))} SAMPLES")
    print(f"{'='*60}")

    # Show samples evenly spread across the dataset
    import random
    random.seed(42)
    sample_size = min(args.count, len(segments))
    samples = random.sample(segments, sample_size)

    for i, seg in enumerate(samples):
        show_sample(seg, i, args.play)
        if args.play and i < len(samples) - 1:
            input("\n  Press Enter for next sample...")

    print(f"\n{'='*60}")
    print(f"  Ready to upload!")
    print(f"  Run: python scripts/09_push_hf.py")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()