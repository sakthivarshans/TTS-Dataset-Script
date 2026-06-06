"""
=============================================================
TTS Dataset Pipeline - Master Configuration
=============================================================
Edit this file before running any scripts.
"""

import os

# ─────────────────────────────────────────────
# API KEYS  (set via env or paste here)
# ─────────────────────────────────────────────
SARVAM_API_KEY   = os.getenv("SARVAM_API_KEY", "xxxxxxxxxxxxxxxxx")
HF_TOKEN         = os.getenv("HF_TOKEN",        "xxxxxxxxxxxxxxxxxxxx")

# ─────────────────────────────────────────────
# HUGGINGFACE SETTINGS
# ─────────────────────────────────────────────
HF_REPO_ID       = "CHANGE-TO-UR-USERNAME/indian-tts-dataset"   # e.g. john/indian-tts-dataset
HF_PRIVATE       = False   # set True during dev, False for final submission

# ─────────────────────────────────────────────
# SARVAM API ENDPOINTS
# ─────────────────────────────────────────────
SARVAM_BASE_URL       = "https://api.sarvam.ai"
SARVAM_ASR_ENDPOINT   = f"{SARVAM_BASE_URL}/speech-to-text"
SARVAM_DIARIZE_ENDPOINT = f"{SARVAM_BASE_URL}/speech-to-text-translate"   # used for diarization
SARVAM_CHAT_ENDPOINT  = f"{SARVAM_BASE_URL}/v1/chat/completions"
SARVAM_ASR_TRANSLATE  = f"{SARVAM_BASE_URL}/speech-to-text-translate"

# ASR language codes
ASR_LANG_ENGLISH = "en-IN"
ASR_LANG_TAMIL   = "ta-IN"

# ─────────────────────────────────────────────
# AUDIO SETTINGS
# ─────────────────────────────────────────────
SAMPLE_RATE          = 16000   # Hz — standard for TTS training
CHANNELS             = 1       # mono
AUDIO_FORMAT         = "wav"
MIN_SEGMENT_DURATION = 8       # seconds  — discard anything shorter
MAX_SEGMENT_DURATION = 28      # seconds  — Sarvam REST API limit is 30s
TARGET_LUFS          = -23.0   # loudness normalisation target (EBU R128)
SNR_THRESHOLD_DB     = 20.0    # minimum signal-to-noise ratio to keep a segment

# ─────────────────────────────────────────────
# DATASET TARGETS
# ─────────────────────────────────────────────
TARGET_ENGLISH_MINUTES = 30
TARGET_TAMIL_MINUTES   = 30
TOTAL_TARGET_MINUTES   = 60

# ─────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────
BASE_DIR         = os.path.dirname(os.path.abspath(__file__))
DATA_DIR         = os.path.join(BASE_DIR, "data")
RAW_AUDIO_DIR    = os.path.join(DATA_DIR, "raw_audio")
SEGMENTS_DIR     = os.path.join(DATA_DIR, "segments")
TRANSCRIPTS_DIR  = os.path.join(DATA_DIR, "transcripts")
FINAL_DIR        = os.path.join(DATA_DIR, "final")
LOGS_DIR         = os.path.join(BASE_DIR, "logs")
QUALITY_DIR      = os.path.join(BASE_DIR, "quality_reports")

# ─────────────────────────────────────────────
# EMOTION / STYLE LABELS  (used in tagging)
# ─────────────────────────────────────────────
EMOTION_LABELS = [
    "neutral", "formal", "excited", "happy", "sad",
    "angry", "calm", "conversational", "storytelling",
    "instructional", "whisper", "emphatic"
]

# ─────────────────────────────────────────────
# QUALITY THRESHOLDS
# ─────────────────────────────────────────────
MIN_TRANSCRIPT_WORDS   = 10     # reject segments with fewer words
MAX_TRANSCRIPT_WORDS   = 200    # reject abnormally long (likely ASR hallucination)
CONFIDENCE_THRESHOLD   = 0.70   # Sarvam ASR confidence score minimum
MAX_SPEAKER_OVERLAP    = 0.05   # max fraction of segment that can have >1 speaker



# ─────────────────────────────────────────────
# RETRY / RATE-LIMIT SETTINGS
# ─────────────────────────────────────────────
API_MAX_RETRIES  = 3
API_RETRY_DELAY  = 5   # seconds between retries
API_TIMEOUT      = 60  # seconds per request
