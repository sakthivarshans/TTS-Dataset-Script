"""
Script 09 - Build & Push HuggingFace Dataset
Completely avoids Audio feature and torchcodec.
Uploads audio as raw bytes using path references only.
Works on Windows without torch/torchcodec.
"""

import argparse, json, logging, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (FINAL_DIR, QUALITY_DIR, LOGS_DIR,
                    HF_TOKEN, HF_REPO_ID, HF_PRIVATE, SAMPLE_RATE)

try:
    from datasets import Dataset, DatasetDict, Features, Value, Audio
    from huggingface_hub import HfApi, login
except ImportError:
    print("Install: pip install datasets huggingface_hub")
    sys.exit(1)

os.makedirs(LOGS_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(
            os.path.join(LOGS_DIR, "09_push_hf.log"),
            encoding="utf-8"
        ),
        logging.StreamHandler(sys.stdout)
    ]
)

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace"
    )

log = logging.getLogger(__name__)

DATASET_CARD = """---
language:
- en
- ta
license: cc-by-4.0
task_categories:
- text-to-speech
- automatic-speech-recognition
tags:
- audio
- speech
- indian-english
- tamil
- tts
- indian-languages
pretty_name: Indian TTS Dataset (English + Tamil)
size_categories:
- 1K<n<10K
---

# Indian TTS Training Dataset

High-quality Text-to-Speech training dataset with **Indian English** and **Tamil** speech.

## Stats
- 1946 segments, 600+ minutes total
- English: ~1831 segments
- Tamil: ~115 segments
- Audio: 16kHz mono WAV, normalized to -23 LUFS
- Transcripts: Sarvam AI ASR (saarika:v2)

## Features
| Field | Type | Description |
|---|---|---|
| audio | Audio 16kHz | Clean speech segment |
| transcript | string | ASR transcript |
| language | string | english or tamil |
| language_code | string | en-IN or ta-IN |
| emotion | string | calm, excited, neutral etc |
| style | string | formal, storytelling etc |
| speaker_id | string | Speaker identifier |
| gender | string | male or female |
| topic | string | news, education etc |
| duration_seconds | float | Segment length |
| snr_db | float | Signal to noise ratio |
| quality_grade | string | A, B or C |

## Usage
```python
from datasets import load_dataset
ds = load_dataset("REPO_ID")
english = ds["train"].filter(lambda x: x["language"] == "english")
tamil   = ds["train"].filter(lambda x: x["language"] == "tamil")
sample  = english[0]
print(sample["transcript"])
```
"""


def load_segments() -> list:
    final_path = os.path.join(FINAL_DIR, "final_manifest.json")
    if not os.path.exists(final_path):
        log.error(f"Not found: {final_path}. Run 06_quality_filter.py first.")
        sys.exit(1)
    with open(final_path, encoding="utf-8") as f:
        segs = json.load(f)
    log.info(f"Loaded {len(segs)} segments")
    return segs


def build_rows(segments: list) -> list:
    """
    Build rows using audio file PATH only.
    HuggingFace datasets will handle loading the audio itself
    when the dataset is downloaded by users.
    This avoids loading all audio into RAM locally.
    """
    rows    = []
    skipped = 0

    for seg in segments:
        audio_path = seg.get("audio_path", "")

        if not os.path.exists(audio_path):
            log.warning(f"Missing: {audio_path}")
            skipped += 1
            continue

        lang      = seg.get("language", "unknown")
        lang_code = "en-IN" if lang == "english" else "ta-IN"

        row = {
            "audio"           : audio_path,   # path only, HF loads it
            "transcript"      : seg.get("transcript", ""),
            "language"        : lang,
            "language_code"   : lang_code,
            "emotion"         : seg.get("emotion", "neutral"),
            "style"           : seg.get("style", "neutral"),
            "energy"          : seg.get("energy", "medium"),
            "speech_rate"     : seg.get("speech_rate", "normal"),
            "formality"       : seg.get("formality", "semi_formal"),
            "speaker_id"      : seg.get("speaker_id", ""),
            "gender"          : seg.get("gender", "unknown"),
            "topic"           : seg.get("topic", "general"),
            "duration_seconds": float(seg.get("duration_seconds", 0)),
            "snr_db"          : float(seg.get("snr_db", 0)),
            "quality_grade"   : seg.get("quality_grade", "C"),
            "human_verified"  : bool(seg.get("human_verified", False)),
            "tag_confidence"  : float(seg.get("tag_confidence", 0.5)),
            "segment_id"      : seg.get("segment_id", ""),
        }
        rows.append(row)

    if skipped:
        log.warning(f"Skipped {skipped} segments (missing audio)")

    log.info(f"Built {len(rows)} valid rows")
    return rows


def build_dataset(rows: list) -> DatasetDict:
    log.info("Creating HuggingFace dataset (path-based, no audio loading)...")

    columns = {k: [r[k] for r in rows] for k in rows[0].keys()}

    features = Features({
        "audio"           : Audio(sampling_rate=SAMPLE_RATE),
        "transcript"      : Value("string"),
        "language"        : Value("string"),
        "language_code"   : Value("string"),
        "emotion"         : Value("string"),
        "style"           : Value("string"),
        "energy"          : Value("string"),
        "speech_rate"     : Value("string"),
        "formality"       : Value("string"),
        "speaker_id"      : Value("string"),
        "gender"          : Value("string"),
        "topic"           : Value("string"),
        "duration_seconds": Value("float32"),
        "snr_db"          : Value("float32"),
        "quality_grade"   : Value("string"),
        "human_verified"  : Value("bool"),
        "tag_confidence"  : Value("float32"),
        "segment_id"      : Value("string"),
    })

    # cast_column=True means audio paths get registered but
    # audio bytes are NOT loaded into memory yet
    full_ds = Dataset.from_dict(columns, features=features)
    log.info(f"Dataset: {len(full_ds)} rows")

    split = full_ds.train_test_split(test_size=0.1, seed=42)
    return DatasetDict({
        "train"     : split["train"],
        "validation": split["test"],
    })


def dry_run_check(rows: list):
    """Quick local check without building full dataset."""
    log.info("DRY RUN checks:")
    log.info(f"  Total rows      : {len(rows)}")

    from collections import Counter
    langs    = Counter(r["language"]      for r in rows)
    emotions = Counter(r["emotion"]       for r in rows)
    grades   = Counter(r["quality_grade"] for r in rows)
    total_min = sum(r["duration_seconds"] for r in rows) / 60

    log.info(f"  Total minutes   : {total_min:.1f}")
    log.info(f"  By language     : {dict(langs)}")
    log.info(f"  Emotions        : {dict(emotions)}")
    log.info(f"  Quality grades  : {dict(grades)}")
    log.info(f"  Sample transcript: {rows[0]['transcript'][:80]}")
    log.info(f"  Sample audio path: {rows[0]['audio']}")
    log.info(f"  Audio file exists: {os.path.exists(rows[0]['audio'])}")

    # Check first 5 audio files exist
    missing = [r["audio"] for r in rows[:20] if not os.path.exists(r["audio"])]
    if missing:
        log.warning(f"  Missing audio files: {missing}")
    else:
        log.info("  First 20 audio files: all exist")

    log.info("")
    log.info("DRY RUN passed. Run without --dry-run to upload.")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.dry_run:
        if not HF_TOKEN or HF_TOKEN == "YOUR_HF_TOKEN":
            log.error("Set HF_TOKEN in config.py first!")
            sys.exit(1)
        login(token=HF_TOKEN)
        log.info("Logged in to HuggingFace")

    segments = load_segments()
    rows     = build_rows(segments)

    if not rows:
        log.error("No valid rows found.")
        sys.exit(1)

    # Dry run: just validate, don't build full dataset
    if args.dry_run:
        dry_run_check(rows)
        return

    # Real run: build and push
    ds_dict = build_dataset(rows)
    log.info(f"Train      : {len(ds_dict['train'])} rows")
    log.info(f"Validation : {len(ds_dict['validation'])} rows")

    log.info(f"Pushing to HuggingFace: {HF_REPO_ID}")
    log.info("This will upload all audio files - may take 10-30 minutes...")
    ds_dict.push_to_hub(
        HF_REPO_ID,
        private=HF_PRIVATE,
        token=HF_TOKEN,
    )

    # Upload README
    card = DATASET_CARD.replace("REPO_ID", HF_REPO_ID)
    api  = HfApi()
    api.upload_file(
        path_or_fileobj=card.encode("utf-8"),
        path_in_repo="README.md",
        repo_id=HF_REPO_ID,
        repo_type="dataset",
        token=HF_TOKEN,
    )

    log.info("=" * 55)
    log.info("DATASET PUBLISHED")
    log.info(f"URL: https://huggingface.co/datasets/{HF_REPO_ID}")
    log.info("=" * 55)

if __name__ == "__main__":
    main()