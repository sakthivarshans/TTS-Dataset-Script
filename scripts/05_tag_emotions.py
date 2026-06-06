"""
=============================================================
Script 05 — Emotion & Style Tagging via Sarvam LLM
=============================================================
Uses Sarvam's LLM API to classify each segment with:
  - Primary emotion   (neutral, happy, sad, angry, excited, calm, fearful)
  - Speaking style    (formal, conversational, storytelling, instructional,
                       emphatic, whisper, narrative)
  - Energy level      (low, medium, high)
  - Speech rate hint  (slow, normal, fast)
  - Gender (inferred from speaker metadata)
  - Confidence of classification

Also does a SECOND PASS with a cross-check prompt to avoid
hallucinated labels on ambiguous segments.

INSTALL:
    pip install requests tqdm

HOW TO USE:
    python 05_tag_emotions.py
    python 05_tag_emotions.py --lang english --resume
=============================================================
"""

import argparse, json, logging, os, sys, time
import requests
from tqdm import tqdm

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    SARVAM_API_KEY, SARVAM_CHAT_ENDPOINT,
    TRANSCRIPTS_DIR, LOGS_DIR, EMOTION_LABELS,
    API_MAX_RETRIES, API_RETRY_DELAY, API_TIMEOUT
)

os.makedirs(LOGS_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, "05_tag_emotions.log")),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

SARVAM_MODEL = "sarvam-m"   # Sarvam's LLM model

# ── Prompts ───────────────────────────────────────────────────────────────────

EMOTION_SYSTEM_PROMPT = """You are an expert linguist and speech analyst specializing in Indian languages and Indian English.
Your task is to analyze a speech transcript and classify its emotional tone and speaking style.

You MUST respond with ONLY a valid JSON object — no explanation, no markdown, no preamble.

JSON schema:
{
  "emotion": "<one of: neutral, happy, sad, angry, excited, calm, fearful, surprised>",
  "style": "<one of: formal, conversational, storytelling, instructional, emphatic, whisper, narrative, motivational>",
  "energy": "<one of: low, medium, high>",
  "speech_rate": "<one of: slow, normal, fast>",
  "formality": "<one of: very_formal, formal, semi_formal, informal, very_informal>",
  "confidence": <float 0.0–1.0 how confident you are in this classification>,
  "reasoning": "<one short sentence explaining your choice>"
}"""

EMOTION_USER_TEMPLATE = """Analyze this speech transcript:

Language: {language}
Topic/Context: {topic}
Speaker: {gender}, {speaker_id}

Transcript:
\"\"\"{transcript}\"\"\"

Classify the emotion, style, energy, speech rate, and formality. Respond with JSON only."""

CROSSCHECK_SYSTEM = """You are a second-opinion speech analyst. You will see a transcript and a PROPOSED emotion label.
Verify whether the label is correct. If not, provide the correct one.
Respond ONLY with a JSON object: {"agree": true/false, "corrected_emotion": "...", "corrected_style": "..."}"""


def call_llm(system_prompt: str, user_prompt: str) -> str:
    """Call Sarvam LLM API, return response text."""
    headers = {
        "api-subscription-key": SARVAM_API_KEY,
        "Content-Type"        : "application/json",
    }
    payload = {
        "model": SARVAM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        "temperature": 0.1,   # low temp for consistent classification
        "max_tokens" : 300,
    }

    for attempt in range(1, API_MAX_RETRIES + 1):
        try:
            resp = requests.post(
                SARVAM_CHAT_ENDPOINT,
                headers=headers,
                json=payload,
                timeout=API_TIMEOUT
            )
            if resp.status_code == 200:
                data = resp.json()
                return data["choices"][0]["message"]["content"].strip()
            elif resp.status_code == 429:
                time.sleep(API_RETRY_DELAY * attempt)
            elif resp.status_code == 401:
                log.error("Unauthorized — check SARVAM_API_KEY")
                sys.exit(1)
            else:
                log.warning(f"LLM API error {resp.status_code}: {resp.text[:200]}")
                time.sleep(API_RETRY_DELAY)
        except requests.exceptions.Timeout:
            log.warning(f"Timeout attempt {attempt}")
            time.sleep(API_RETRY_DELAY)
        except Exception as e:
            log.warning(f"Request error: {e}")
            time.sleep(API_RETRY_DELAY)

    return ""


def parse_json_response(text: str) -> dict:
    """Safely parse LLM JSON response, handle markdown fences."""
    text = text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object in text
        import re
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
    return {}


def classify_segment(seg: dict) -> dict:
    """Run 2-pass emotion classification for one segment."""
    transcript = seg.get("transcript", "")
    language   = "Indian English" if seg["language"] == "english" else "Tamil"
    topic      = seg.get("topic", "general")
    gender     = seg.get("gender", "unknown")
    speaker_id = seg.get("speaker_id", "")
    expected   = seg.get("expected_style", "")

    # ── Pass 1: Primary classification ────────────────────────────────────────
    user_prompt = EMOTION_USER_TEMPLATE.format(
        language=language, topic=topic,
        gender=gender, speaker_id=speaker_id,
        transcript=transcript[:800]   # cap to avoid token overflow
    )

    raw = call_llm(EMOTION_SYSTEM_PROMPT, user_prompt)
    result = parse_json_response(raw)

    if not result or "emotion" not in result:
        log.warning(f"  LLM parse failed for {seg['segment_id']}, using defaults")
        result = {
            "emotion"   : "neutral",
            "style"     : expected or "neutral",
            "energy"    : "medium",
            "speech_rate": "normal",
            "formality" : "formal",
            "confidence": 0.4,
            "reasoning" : "LLM parse failed — default assigned",
        }

    time.sleep(0.5)   # rate limit between pass 1 and 2

    # ── Pass 2: Cross-check (only if confidence < 0.75) ───────────────────────
    conf = result.get("confidence", 0.5)
    if conf < 0.75:
        crosscheck_user = (
            f"Transcript: \"{transcript[:400]}\"\n\n"
            f"Proposed emotion: {result.get('emotion')}\n"
            f"Proposed style: {result.get('style')}\n\n"
            f"Do you agree? Respond with JSON only."
        )
        raw2   = call_llm(CROSSCHECK_SYSTEM, crosscheck_user)
        check  = parse_json_response(raw2)

        if check and not check.get("agree", True):
            corrected_emotion = check.get("corrected_emotion")
            corrected_style   = check.get("corrected_style")
            if corrected_emotion and corrected_emotion in [
                "neutral","happy","sad","angry","excited","calm","fearful","surprised"
            ]:
                result["emotion"] = corrected_emotion
                result["crosscheck_corrected"] = True
            if corrected_style:
                result["style"] = corrected_style
        time.sleep(0.5)

    # ── Validate emotion label is in allowed set ───────────────────────────────
    valid_emotions = ["neutral","happy","sad","angry","excited","calm","fearful","surprised"]
    valid_styles   = ["formal","conversational","storytelling","instructional",
                      "emphatic","whisper","narrative","motivational","neutral"]

    if result.get("emotion") not in valid_emotions:
        result["emotion"] = "neutral"
    if result.get("style") not in valid_styles:
        result["style"] = expected or "neutral"

    return result


def tag_lang(lang: str, resume: bool) -> list:
    in_path = os.path.join(TRANSCRIPTS_DIR, f"transcribed_{lang}.json")
    if not os.path.exists(in_path):
        log.error(f"Not found: {in_path}. Run 04_transcribe.py first.")
        return []

    with open(in_path, encoding="utf-8") as f:
        segments = json.load(f)

    out_dir = os.path.join(TRANSCRIPTS_DIR, "tagged", lang)
    os.makedirs(out_dir, exist_ok=True)

    tagged = []
    log.info(f"\n{'='*50}\nTagging {lang.upper()} — {len(segments)} segments\n{'='*50}")

    for seg in tqdm(segments, desc=f"Tagging {lang}"):
        seg_id    = seg["segment_id"]
        tag_path  = os.path.join(out_dir, f"{seg_id}_tagged.json")

        if resume and os.path.exists(tag_path):
            with open(tag_path, encoding="utf-8") as f:
                tagged.append(json.load(f))
            continue

        emotion_data = classify_segment(seg)
        record = {
            **seg,
            "emotion"            : emotion_data.get("emotion", "neutral"),
            "style"              : emotion_data.get("style",   "neutral"),
            "energy"             : emotion_data.get("energy",  "medium"),
            "speech_rate"        : emotion_data.get("speech_rate", "normal"),
            "formality"          : emotion_data.get("formality",   "formal"),
            "tag_confidence"     : emotion_data.get("confidence",  0.5),
            "tag_reasoning"      : emotion_data.get("reasoning",   ""),
            "crosscheck_corrected": emotion_data.get("crosscheck_corrected", False),
        }

        with open(tag_path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)

        tagged.append(record)
        log.debug(f"  {seg_id}: {record['emotion']} / {record['style']} "
                  f"(conf={record['tag_confidence']:.2f})")

        time.sleep(0.5)

    # Save tagged manifest
    out_path = os.path.join(TRANSCRIPTS_DIR, f"tagged_{lang}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(tagged, f, ensure_ascii=False, indent=2)

    # Print distribution
    from collections import Counter
    emotion_dist = Counter(r["emotion"] for r in tagged)
    style_dist   = Counter(r["style"]   for r in tagged)
    log.info(f"\n{lang.upper()} Emotion distribution: {dict(emotion_dist)}")
    log.info(f"{lang.upper()} Style distribution:   {dict(style_dist)}")

    return tagged


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lang",   choices=["english","tamil","all"], default="all")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    if SARVAM_API_KEY == "YOUR_SARVAM_API_KEY":
        log.error("Set SARVAM_API_KEY in config.py!")
        sys.exit(1)

    langs = ["english","tamil"] if args.lang == "all" else [args.lang]
    all_tagged = []

    for lang in langs:
        records = tag_lang(lang, args.resume)
        all_tagged.extend(records)

    combined = os.path.join(TRANSCRIPTS_DIR, "tagged_all.json")
    with open(combined, "w", encoding="utf-8") as f:
        json.dump(all_tagged, f, ensure_ascii=False, indent=2)

    total_min = sum(r["duration_seconds"] for r in all_tagged) / 60
    log.info(f"\n✅ Total tagged: {len(all_tagged)} segments | {total_min:.1f} min")


if __name__ == "__main__":
    main()
