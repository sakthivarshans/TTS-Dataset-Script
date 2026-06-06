"""
fix_tags.py
===========
Adds default emotion/style tags from the source metadata
without needing any API call.

Place in D:\TTS\ and run:
    python fix_tags.py
"""

import json, os

BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
TRANSCRIPTS_DIR = os.path.join(BASE_DIR, "data", "transcripts")
DATA_DIR        = os.path.join(BASE_DIR, "data")

# Style -> emotion mapping
STYLE_TO_EMOTION = {
    "formal"        : "neutral",
    "motivational"  : "excited",
    "excited"       : "excited",
    "calm"          : "calm",
    "instructional" : "neutral",
    "conversational": "neutral",
    "storytelling"  : "happy",
    "emphatic"      : "emphatic",
    "narrative"     : "neutral",
    "happy"         : "happy",
    "neutral"       : "neutral",
}

def load_sources():
    """Load speaker metadata from source JSON files."""
    speaker_meta = {}
    for lang in ["english", "tamil"]:
        src_path = os.path.join(DATA_DIR, f"sources_{lang}.json")
        if not os.path.exists(src_path):
            continue
        with open(src_path, encoding="utf-8") as f:
            sources = json.load(f)
        for src in sources:
            spk_id = src.get("speaker_id", "")
            speaker_meta[spk_id] = {
                "gender"        : src.get("gender", "unknown"),
                "topic"         : src.get("topic", "general"),
                "style"         : src.get("expected_style", "neutral"),
                "emotion"       : STYLE_TO_EMOTION.get(
                                    src.get("expected_style","neutral"), "neutral"),
                "energy"        : "medium",
                "speech_rate"   : "normal",
                "formality"     : "formal" if src.get("expected_style") in
                                  ["formal","instructional","emphatic"] else "semi_formal",
                "tag_confidence": 0.6,
                "tag_reasoning" : "assigned from source metadata",
            }
    return speaker_meta


def tag_all():
    speaker_meta = load_sources()
    print(f"Loaded metadata for {len(speaker_meta)} speakers")

    all_tagged = []

    for lang in ["english", "tamil"]:
        in_path = os.path.join(TRANSCRIPTS_DIR, f"transcribed_{lang}.json")
        if not os.path.exists(in_path):
            print(f"Not found: {in_path} -- skipping")
            continue

        with open(in_path, encoding="utf-8") as f:
            segments = json.load(f)

        print(f"\n{lang.upper()}: tagging {len(segments)} segments...")

        tagged = []
        for seg in segments:
            spk_id = seg.get("speaker_id", "")
            meta   = speaker_meta.get(spk_id, {})

            record = {
                **seg,
                "gender"             : meta.get("gender", "unknown"),
                "topic"              : meta.get("topic", "general"),
                "emotion"            : meta.get("emotion", "neutral"),
                "style"              : meta.get("style", "neutral"),
                "energy"             : meta.get("energy", "medium"),
                "speech_rate"        : meta.get("speech_rate", "normal"),
                "formality"          : meta.get("formality", "semi_formal"),
                "tag_confidence"     : meta.get("tag_confidence", 0.6),
                "tag_reasoning"      : meta.get("tag_reasoning", "from metadata"),
                "crosscheck_corrected": False,
            }
            tagged.append(record)

        # Save tagged manifest
        out_path = os.path.join(TRANSCRIPTS_DIR, f"tagged_{lang}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(tagged, f, ensure_ascii=False, indent=2)

        print(f"  Saved {len(tagged)} tagged segments -> {out_path}")
        all_tagged.extend(tagged)

    # Save combined
    combined = os.path.join(TRANSCRIPTS_DIR, "tagged_all.json")
    with open(combined, "w", encoding="utf-8") as f:
        json.dump(all_tagged, f, ensure_ascii=False, indent=2)

    total_min = sum(s.get("duration_seconds", 0) for s in all_tagged) / 60
    print(f"\n{'='*50}")
    print(f"DONE")
    print(f"Total tagged   : {len(all_tagged)} segments")
    print(f"Total duration : {total_min:.1f} minutes")
    print(f"Saved to       : {combined}")
    print(f"\nNext step: python scripts/06_quality_filter.py")
    print(f"{'='*50}")


if __name__ == "__main__":
    tag_all()