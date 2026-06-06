"""
=============================================================
Script 04 — Transcription via Sarvam ASR API
=============================================================
Sends each segment to Sarvam's ASR endpoint and saves:
  - Transcript text
  - Word-level timestamps (if available)
  - Confidence score
  - Language detected

INSTALL:
    pip install requests tqdm

HOW TO USE:
    python 04_transcribe.py
    python 04_transcribe.py --lang english
    python 04_transcribe.py --lang tamil
    python 04_transcribe.py --resume        # skip already transcribed
=============================================================
"""

import argparse, base64, json, logging, os, sys, time
import requests
from tqdm import tqdm

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    SARVAM_API_KEY, SARVAM_ASR_ENDPOINT,
    ASR_LANG_ENGLISH, ASR_LANG_TAMIL,
    SEGMENTS_DIR, TRANSCRIPTS_DIR, LOGS_DIR,
    API_MAX_RETRIES, API_RETRY_DELAY, API_TIMEOUT,
    CONFIDENCE_THRESHOLD, MIN_TRANSCRIPT_WORDS, MAX_TRANSCRIPT_WORDS
)

os.makedirs(LOGS_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, "04_transcribe.log")),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

LANG_CODE_MAP = {
    "english": ASR_LANG_ENGLISH,
    "tamil"  : ASR_LANG_TAMIL,
}


def read_audio_b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def call_sarvam_asr(audio_path: str, language_code: str) -> dict:
    """
    Call Sarvam ASR API with retry logic.
    Uses multipart/form-data file upload (current API format).
    Returns dict with keys: transcript, confidence, words (optional)
    """
    headers = {
        "api-subscription-key": SARVAM_API_KEY,
    }

    for attempt in range(1, API_MAX_RETRIES + 1):
        try:
            with open(audio_path, "rb") as audio_file:
                files = {
                    "file": (os.path.basename(audio_path), audio_file, "audio/wav"),
                }
                data = {
                    "model": "saarika:v2.5",
                    "language_code": language_code,
                    "with_timestamps": "true",
                }
                resp = requests.post(
                    SARVAM_ASR_ENDPOINT,
                    headers=headers,
                    files=files,
                    data=data,
                    timeout=API_TIMEOUT,
                )

            if resp.status_code == 200:
                data = resp.json()
                # Extract word-level timestamps if available
                timestamps = data.get("timestamps", {})
                words_list = []
                if timestamps:
                    w = timestamps.get("words", [])
                    starts = timestamps.get("start_time_seconds", [])
                    ends = timestamps.get("end_time_seconds", [])
                    for j in range(len(w)):
                        words_list.append({
                            "word": w[j] if j < len(w) else "",
                            "start": starts[j] if j < len(starts) else 0,
                            "end": ends[j] if j < len(ends) else 0,
                        })
                return {
                    "transcript" : data.get("transcript", "").strip(),
                    "confidence" : data.get("language_probability", 0.0) or 0.0,
                    "words"      : words_list,
                    "language"   : data.get("language_code", language_code),
                    "raw_response": data,
                }

            elif resp.status_code == 429:
                wait = API_RETRY_DELAY * attempt
                log.warning(f"  Rate limited. Waiting {wait}s... (attempt {attempt})")
                time.sleep(wait)

            elif resp.status_code == 401:
                log.error("  Unauthorized -- check SARVAM_API_KEY in config.py")
                sys.exit(1)

            else:
                log.warning(f"  API error {resp.status_code}: {resp.text[:200]}")
                time.sleep(API_RETRY_DELAY)

        except requests.exceptions.Timeout:
            log.warning(f"  Timeout on attempt {attempt}/{API_MAX_RETRIES}")
            time.sleep(API_RETRY_DELAY)
        except requests.exceptions.ConnectionError as e:
            log.warning(f"  Connection error: {e}. Retrying...")
            time.sleep(API_RETRY_DELAY * attempt)

    return {"transcript": "", "confidence": 0.0, "words": [], "language": language_code}


def validate_transcript(transcript: str, confidence: float) -> tuple:
    """
    Returns (is_valid: bool, reject_reason: str)
    """
    if not transcript or len(transcript.strip()) == 0:
        return False, "empty_transcript"

    words = transcript.split()
    if len(words) < MIN_TRANSCRIPT_WORDS:
        return False, f"too_short_{len(words)}_words"

    if len(words) > MAX_TRANSCRIPT_WORDS:
        return False, f"too_long_{len(words)}_words"

    if confidence < CONFIDENCE_THRESHOLD:
        return False, f"low_confidence_{confidence:.2f}"

    # Check for ASR hallucinations (repeated words)
    if len(set(words)) < len(words) * 0.4:
        return False, "repetition_detected"

    # Check for excessive special characters (garbled ASR)
    special_chars = sum(1 for c in transcript if not c.isalnum() and c not in " .,?!-'\"")
    if special_chars > len(transcript) * 0.1:
        return False, "excessive_special_chars"

    return True, "ok"


def transcribe_lang(lang: str, resume: bool) -> list:
    manifest_path = os.path.join(SEGMENTS_DIR, f"manifest_{lang}.json")
    if not os.path.exists(manifest_path):
        log.error(f"Manifest not found: {manifest_path}. Run 03_segment.py first.")
        return []

    with open(manifest_path) as f:
        segments = json.load(f)

    lang_code = LANG_CODE_MAP[lang]
    out_dir   = os.path.join(TRANSCRIPTS_DIR, lang)
    os.makedirs(out_dir, exist_ok=True)

    transcribed = []
    rejected    = []

    log.info(f"\n{'='*50}\nTranscribing {lang.upper()} — {len(segments)} segments\n{'='*50}")

    for seg in tqdm(segments, desc=f"ASR {lang}"):
        seg_id     = seg["segment_id"]
        audio_path = seg["audio_path"]
        out_path   = os.path.join(out_dir, f"{seg_id}.json")

        # Resume: skip if already done
        if resume and os.path.exists(out_path):
            try:
                with open(out_path, encoding="utf-8") as f:
                    existing = json.load(f)
                
                # Check validation status from previous run (fallback to checking if transcript is non-empty)
                is_valid = existing.get("transcript_valid", bool(existing.get("transcript")))
                if is_valid:
                    transcribed.append(existing)
                else:
                    rejected.append(existing)
                continue
            except Exception as e:
                log.warning(f"  Error reading existing transcript {out_path}: {e}. Re-transcribing.")

        if not os.path.exists(audio_path):
            log.warning(f"  Audio not found: {audio_path}")
            continue

        # Call ASR
        result = call_sarvam_asr(audio_path, lang_code)

        # Validate
        is_valid, reason = validate_transcript(result["transcript"], result["confidence"])

        record = {
            **seg,
            "transcript"       : result["transcript"],
            "confidence"       : result["confidence"],
            "words"            : result["words"],
            "asr_language"     : result["language"],
            "transcript_valid" : is_valid,
            "reject_reason"    : reason if not is_valid else None,
        }

        # Save individual JSON
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)

        if is_valid:
            transcribed.append(record)
            log.debug(f"  ✓ {seg_id} | conf={result['confidence']:.2f} | "
                      f"'{result['transcript'][:60]}...'")
        else:
            rejected.append({**record, "reject_reason": reason})
            log.debug(f"  ✗ {seg_id} REJECTED — {reason}")

        time.sleep(0.3)   # gentle rate limit

    # Save manifest
    ok_path  = os.path.join(TRANSCRIPTS_DIR, f"transcribed_{lang}.json")
    rej_path = os.path.join(TRANSCRIPTS_DIR, f"rejected_{lang}.json")

    with open(ok_path, "w", encoding="utf-8") as f:
        json.dump(transcribed, f, ensure_ascii=False, indent=2)
    with open(rej_path, "w", encoding="utf-8") as f:
        json.dump(rejected, f, ensure_ascii=False, indent=2)

    total_min = sum(r["duration_seconds"] for r in transcribed) / 60
    log.info(f"\n{lang.upper()} Results:")
    log.info(f"  ✓ Accepted : {len(transcribed)} segments ({total_min:.1f} min)")
    log.info(f"  ✗ Rejected : {len(rejected)} segments")

    return transcribed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lang",   choices=["english", "tamil", "all"], default="all")
    parser.add_argument("--resume", action="store_true", help="Skip already transcribed segments")
    args = parser.parse_args()

    os.makedirs(TRANSCRIPTS_DIR, exist_ok=True)

    if SARVAM_API_KEY == "YOUR_SARVAM_API_KEY":
        log.error("Set your SARVAM_API_KEY in config.py or via environment variable!")
        sys.exit(1)

    langs = ["english", "tamil"] if args.lang == "all" else [args.lang]
    all_transcribed = []

    for lang in langs:
        records = transcribe_lang(lang, args.resume)
        all_transcribed.extend(records)

    # Combined manifest
    combined_path = os.path.join(TRANSCRIPTS_DIR, "transcribed_all.json")
    with open(combined_path, "w", encoding="utf-8") as f:
        json.dump(all_transcribed, f, ensure_ascii=False, indent=2)

    total_min = sum(r["duration_seconds"] for r in all_transcribed) / 60
    log.info(f"\n✅ Total transcribed: {len(all_transcribed)} segments | {total_min:.1f} min")


if __name__ == "__main__":
    main()
