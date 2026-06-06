"""
fix_transcripts.py
==================
Rescues all already-transcribed segments that were wrongly
rejected due to confidence=0.0 or low_confidence reason.

NO API CALLS. Works entirely on local files.

Run from D:\TTS folder:
    python fix_transcripts.py
"""

import json, os, sys
from collections import Counter

# Paths
BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
TRANSCRIPTS_DIR = os.path.join(BASE_DIR, "data", "transcripts")
SEGMENTS_DIR    = os.path.join(BASE_DIR, "data", "segments")

MIN_WORDS    = 6     # minimum words to accept a transcript
MAX_WORDS    = 250   # maximum words


def is_valid_transcript(transcript: str) -> tuple:
    """Simple validation with NO confidence check."""
    if not transcript or not transcript.strip():
        return False, "empty_transcript"

    words = transcript.strip().split()

    if len(words) < MIN_WORDS:
        return False, f"too_short_{len(words)}_words"

    if len(words) > MAX_WORDS:
        return False, f"too_long_{len(words)}_words"

    # Check for hallucination (same word repeated)
    if len(words) > 5 and len(set(words)) < len(words) * 0.25:
        return False, "repetition_hallucination"

    return True, "ok"


def rescue_lang(lang: str) -> list:
    lang_dir = os.path.join(TRANSCRIPTS_DIR, lang)

    if not os.path.isdir(lang_dir):
        print(f"  No folder found: {lang_dir}")
        print(f"  Skipping {lang}")
        return []

    json_files = [f for f in os.listdir(lang_dir) if f.endswith(".json")]
    print(f"\n  Found {len(json_files)} JSON files in {lang_dir}")

    accepted  = []
    rejected  = []
    reasons   = Counter()

    for fname in json_files:
        fpath = os.path.join(lang_dir, fname)
        try:
            with open(fpath, encoding="utf-8") as f:
                seg = json.load(f)
        except Exception as e:
            print(f"  Cannot read {fname}: {e}")
            continue

        transcript = seg.get("transcript", "")
        valid, reason = is_valid_transcript(transcript)

        # Update the record
        seg["transcript_valid"] = valid
        seg["reject_reason"]    = None if valid else reason

        # Save updated record back
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(seg, f, ensure_ascii=False, indent=2)

        if valid:
            accepted.append(seg)
        else:
            rejected.append(seg)
            reasons[reason] += 1

    print(f"  Accepted : {len(accepted)} segments")
    print(f"  Rejected : {len(rejected)} segments")
    print(f"  Rejection reasons: {dict(reasons)}")

    total_min = sum(s.get("duration_seconds", 0) for s in accepted) / 60
    print(f"  Total duration: {total_min:.1f} minutes")

    return accepted


def main():
    print("=" * 55)
    print("  TRANSCRIPT RESCUE - No API needed")
    print("  Fixing wrong confidence=0.0 rejections")
    print("=" * 55)

    all_accepted = []

    for lang in ["english", "tamil"]:
        print(f"\n[{lang.upper()}]")
        accepted = rescue_lang(lang)
        all_accepted.extend(accepted)

        # Save per-language manifest
        out_path = os.path.join(TRANSCRIPTS_DIR, f"transcribed_{lang}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(accepted, f, ensure_ascii=False, indent=2)
        print(f"  Saved -> {out_path}")

        # Save empty rejected file
        rej_path = os.path.join(TRANSCRIPTS_DIR, f"rejected_{lang}.json")
        rejected = []
        lang_dir = os.path.join(TRANSCRIPTS_DIR, lang)
        if os.path.isdir(lang_dir):
            for fname in os.listdir(lang_dir):
                fpath = os.path.join(lang_dir, fname)
                try:
                    with open(fpath, encoding="utf-8") as f:
                        seg = json.load(f)
                    if not seg.get("transcript_valid"):
                        rejected.append(seg)
                except Exception:
                    pass
        with open(rej_path, "w", encoding="utf-8") as f:
            json.dump(rejected, f, ensure_ascii=False, indent=2)

    # Save combined manifest
    combined = os.path.join(TRANSCRIPTS_DIR, "transcribed_all.json")
    with open(combined, "w", encoding="utf-8") as f:
        json.dump(all_accepted, f, ensure_ascii=False, indent=2)

    total_min = sum(s.get("duration_seconds", 0) for s in all_accepted) / 60

    print(f"\n{'='*55}")
    print(f"  DONE")
    print(f"  Total accepted : {len(all_accepted)} segments")
    print(f"  Total duration : {total_min:.1f} minutes")
    print(f"  Saved to       : {combined}")
    print(f"\n  Next step: python scripts/05_tag_emotions.py --resume")
    print(f"{'='*55}")


if __name__ == "__main__":
    main()