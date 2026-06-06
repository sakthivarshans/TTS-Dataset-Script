## TTS Dataset Pipeline

**60-minute TTS training dataset** — Indian English (30 min) + Tamil (30 min)  
Built with Sarvam AI APIs for ASR + LLM tagging.

---

##  Project Structure

```
tts_dataset/
├── 00_run_pipeline.py          ← Master runner (start here)
├── config.py                   ← ALL settings & API keys
├── requirements.txt
├── scripts/
│   ├── 01_sources.py           ← Step 1: Curated YouTube URLs
│   ├── 02_download.py          ← Step 2: Download audio (yt-dlp)
│   ├── 03_segment.py           ← Step 3: VAD segmentation + SNR filter
│   ├── 04_transcribe.py        ← Step 4: Sarvam ASR transcription
│   ├── 05_tag_emotions.py      ← Step 5: 2-pass LLM emotion tagging
│   ├── 06_quality_filter.py    ← Step 6: Deep quality + normalization
│   ├── 07_manual_review.py     ← Step 7: Human review CLI ← CRITICAL
│   ├── 08_stats.py             ← Step 8: Statistics & report
│   └── 09_push_hf.py           ← Step 9: Push to HuggingFace
└── data/
    ├── raw_audio/              ← Downloaded audio
    ├── segments/               ← VAD-segmented clips
    ├── transcripts/            ← ASR + emotion tags
    └── final/                  ← Normalized, filtered final audio
```

---

##  Quick Start (Full Pipeline)

### 1. Install dependencies

```bash
# System: install ffmpeg first
brew install ffmpeg          # macOS
sudo apt install ffmpeg      # Ubuntu/Debian

# Python packages
pip install -r requirements.txt
```

### 2. Set your API keys

Edit `config.py`:
```python
SARVAM_API_KEY = "your_sarvam_key_here"
HF_TOKEN       = "hf_your_huggingface_token"
HF_REPO_ID     = "yourusername/indian-tts-dataset"
```

Or set environment variables:
```bash
export SARVAM_API_KEY="your_key"
export HF_TOKEN="hf_your_token"
```

### 3. Run the full pipeline

```bash
python 00_run_pipeline.py
```

This runs all 9 steps automatically and uploads to HuggingFace.

---

##  Run Individual Steps

```bash
# Step 1: Save source list
python scripts/01_sources.py

# Step 2: Download audio from YouTube
python scripts/02_download.py
python scripts/02_download.py --lang english      # only English
python scripts/02_download.py --lang tamil        # only Tamil
python scripts/02_download.py --retry-failed      # retry failed downloads

# Step 3: Segment with VAD + SNR filter
python scripts/03_segment.py
python scripts/03_segment.py --lang english

# Step 4: Transcribe with Sarvam ASR
python scripts/04_transcribe.py --resume          # skip already done

# Step 5: Tag emotions and speaking style
python scripts/05_tag_emotions.py --resume

# Step 6: Quality filter + normalize audio
python scripts/06_quality_filter.py
python scripts/06_quality_filter.py --strict       # higher SNR threshold

# Step 7: Manual review (IMPORTANT - listen to your data!)
python scripts/07_manual_review.py --sample 30    # review 30 random samples
python scripts/07_manual_review.py --grade A       # review only Grade A
python scripts/07_manual_review.py --resume        # continue previous session

# Step 8: Generate statistics report
python scripts/08_stats.py --detailed

# Step 9: Push to HuggingFace
python scripts/09_push_hf.py --dry-run            # test first!
python scripts/09_push_hf.py                       # actual upload
```

---

##  Manual Review Controls (Step 7)

This is the most important step. **Listen to your data.**

```
[P] Play audio
[A] Approve
[R] Reject  (asks for reason)
[E] Edit    (fix emotion/style/transcript, then approves)
[S] Skip    (undecided)
[Q] Quit    (saves progress)
```

---

##  Dataset Schema

Each row in the final HuggingFace dataset contains:

| Field | Type | Example |
|-------|------|---------|
| `audio` | Audio (16kHz) | WAV samples |
| `transcript` | string | "Today we discuss climate policy..." |
| `language` | string | `english` / `tamil` |
| `language_code` | string | `en-IN` / `ta-IN` |
| `emotion` | string | `excited` |
| `style` | string | `motivational` |
| `energy` | string | `high` |
| `speech_rate` | string | `normal` |
| `formality` | string | `formal` |
| `speaker_id` | string | `en_spk_003` |
| `gender` | string | `male` |
| `topic` | string | `education` |
| `duration_seconds` | float | `42.3` |
| `snr_db` | float | `28.4` |
| `quality_grade` | string | `A` |
| `human_verified` | bool | `true` |
| `tag_confidence` | float | `0.87` |

---

##  Quality Pipeline

```
YouTube video
    ↓
yt-dlp download → 16kHz mono WAV
    ↓
WebRTC VAD → speech segments (8–65s)
    ↓
SNR filter (≥20 dB) → reject noisy segments
    ↓
Sarvam ASR → transcript + confidence score
    ↓
Confidence filter (≥0.70) → reject low-quality transcripts
    ↓
2-pass LLM tagging → emotion + style labels
    ↓
Deep quality filter:
  • Re-check SNR
  • Silence ratio (<55%)
  • Words-per-second sanity check
  • Duplicate detection (MD5 hash)
    ↓
LUFS normalization (-23 LUFS, EBU R128)
+ Silence trim + 5ms fade in/out
    ↓
Manual human review (sample ≥30 segments)
    ↓
HuggingFace dataset push
```

---

##  Getting API Keys

**Sarvam AI:**
1. Go to https://dashboard.sarvam.ai
2. Create account → API Keys → Create new key
3. Copy key into `config.py`

**HuggingFace:**
1. Go to https://huggingface.co/settings/tokens
2. New token → Write access
3. Copy token into `config.py`

---

##  Common Issues

| Problem | Fix |
|---------|-----|
| `yt-dlp: video unavailable` | Replace URL in `01_sources.py` with fresh YouTube link |
| `webrtcvad` install fails | `pip install webrtcvad-wheels` (prebuilt) |
| Sarvam 429 rate limit | Pipeline auto-retries; or reduce batch size |
| Not enough minutes | Add more URLs to `01_sources.py`, or use longer videos |
| Low SNR segments | Choose videos without background music/noise |

---

## Targeting 60 Minutes

Each source video should ideally be **10–30 minutes long**.  
With 15 sources per language × ~4 min usable per source = ~60 min total.

If you're falling short:
```bash
# Check current total
python scripts/08_stats.py

# Add more sources, then re-run from step 2
python 00_run_pipeline.py --start 2
```
