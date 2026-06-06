"""
=============================================================
Script 03 — Smart Segmentation + Quality Pre-filter
=============================================================
VAD BACKEND (auto-selected, no C++ compiler needed on Windows):
  Primary     → silero-vad   (torch-based, best accuracy)
  Fallback    → webrtcvad-wheels (pre-built binary, NO compiler)
  Last resort → energy-based VAD (pure numpy, always works)

INSTALL (pick one):
    pip install silero-vad torch torchaudio soundfile scipy tqdm
    pip install webrtcvad-wheels soundfile scipy tqdm        ← Windows easy
    pip install soundfile scipy tqdm                         ← zero-dep fallback

HOW TO USE:
    python 03_segment.py
    python 03_segment.py --lang english
    python 03_segment.py --lang tamil
    python 03_segment.py --vad energy    # force numpy fallback
=============================================================
"""

import argparse, json, logging, math, os, sys, wave
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (RAW_AUDIO_DIR, SEGMENTS_DIR, LOGS_DIR,
                    SAMPLE_RATE, MIN_SEGMENT_DURATION, MAX_SEGMENT_DURATION,
                    SNR_THRESHOLD_DB)

try:
    import soundfile as sf
    from scipy.signal import butter, sosfilt
    from tqdm import tqdm
except ImportError as e:
    print(f"Missing: {e}\nInstall: pip install soundfile scipy tqdm")
    sys.exit(1)

# ── Detect best available VAD backend ────────────────────────────────────────
VAD_BACKEND = "energy"
_silero_model = None

try:
    import torch
    from silero_vad import load_silero_vad, get_speech_timestamps
    VAD_BACKEND = "silero"
    print("✓ VAD backend: Silero (best quality)")
except ImportError:
    try:
        import webrtcvad as _wrtcvad
        VAD_BACKEND = "webrtc"
        print("✓ VAD backend: WebRTC VAD")
    except ImportError:
        print("⚠  VAD backend: Energy (basic numpy — works everywhere)")
        print("   Better option: pip install webrtcvad-wheels")
        print("   Best option  : pip install silero-vad torch torchaudio")

os.makedirs(LOGS_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, "03_segment.log")),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

FRAME_MS       = 30
PADDING_MS     = 400
MIN_SILENCE_MS = 700


# ── Audio I/O ─────────────────────────────────────────────────────────────────

def read_wav_16k_mono(path: str):
    try:
        data, sr = sf.read(path, dtype="int16")
        if data.ndim > 1:
            data = data[:, 0]
        if sr != SAMPLE_RATE:
            log.warning(f"  SR={sr}, expected {SAMPLE_RATE}. Check ffmpeg conversion.")
        return data, sr
    except Exception as e:
        log.error(f"  Cannot read {path}: {e}")
        return None, None


# ── VAD backends ──────────────────────────────────────────────────────────────

def _vad_silero(samples: np.ndarray, sr: int) -> list:
    """Best quality. Requires: pip install silero-vad torch torchaudio"""
    global _silero_model
    if _silero_model is None:
        _silero_model = load_silero_vad()
    audio_f32 = torch.from_numpy(samples.astype(np.float32) / 32768.0)
    ts = get_speech_timestamps(
        audio_f32, _silero_model,
        sampling_rate=sr,
        min_speech_duration_ms=int(MIN_SEGMENT_DURATION * 800),
        min_silence_duration_ms=MIN_SILENCE_MS,
        return_seconds=False,
    )
    return [(t["start"], t["end"]) for t in ts]


def _vad_webrtc(samples: np.ndarray, sr: int) -> list:
    """Good quality. Windows: pip install webrtcvad-wheels (no compiler needed)"""
    vad          = _wrtcvad.Vad(2)
    frame_len    = int(sr * FRAME_MS / 1000)
    pad_fr       = int(PADDING_MS / FRAME_MS)
    triggered    = False
    ring         = []
    voiced       = []
    segs         = []
    seg_start    = 0

    pad      = frame_len - (len(samples) % frame_len)
    buf      = np.concatenate([samples, np.zeros(pad, dtype=np.int16)])

    for start in range(0, len(buf) - frame_len, frame_len):
        frame      = buf[start:start + frame_len]
        try:    is_sp = vad.is_speech(frame.tobytes(), sr)
        except: is_sp = False

        if not triggered:
            ring.append((start, is_sp))
            if len(ring) > pad_fr: ring.pop(0)
            if sum(v for _, v in ring) > 0.9 * pad_fr:
                triggered = True
                seg_start = ring[0][0]
                voiced    = list(ring)
                ring      = []
        else:
            voiced.append((start, is_sp))
            ring.append((start, is_sp))
            if len(ring) > pad_fr: ring.pop(0)
            if sum(not v for _, v in ring) > 0.9 * pad_fr:
                triggered = False
                segs.append((seg_start, voiced[-1][0] + frame_len))
                ring = []; voiced = []

    if triggered and voiced:
        segs.append((seg_start, voiced[-1][0] + frame_len))
    return segs


def _vad_energy(samples: np.ndarray, sr: int) -> list:
    """Pure numpy — zero extra dependencies. Works everywhere."""
    frame_len = int(sr * 0.02)   # 20ms
    floats    = samples.astype(np.float64) / 32768.0

    energies = np.array([
        np.sqrt(np.mean(floats[i:i+frame_len]**2))
        for i in range(0, len(floats)-frame_len, frame_len)
    ])
    if len(energies) == 0:
        return []

    noise_floor = np.percentile(energies, 10)
    threshold   = max(noise_floor * 4.0, 0.005)
    mask        = energies > threshold

    # Smooth
    win      = max(1, int(200 / 20))
    smoothed = np.convolve(mask.astype(float),
                           np.ones(win)/win, mode="same") > 0.4

    hop   = frame_len
    pad_f = int(PADDING_MS / 20)
    segs  = []
    in_sp = False
    s_fr  = 0

    for i, sp in enumerate(smoothed):
        if sp and not in_sp:
            s_fr = max(0, i - pad_f)
            in_sp = True
        elif not sp and in_sp:
            e_fr = min(len(smoothed)-1, i + pad_f)
            segs.append((s_fr * hop, e_fr * hop))
            in_sp = False

    if in_sp:
        segs.append((s_fr * hop, len(samples)))

    return segs


def vad_segment(samples: np.ndarray, sr: int,
                force_backend: str = None) -> list:
    """Dispatch to best available VAD backend."""
    b = force_backend or VAD_BACKEND
    if b == "silero":   return _vad_silero(samples, sr)
    if b == "webrtc":   return _vad_webrtc(samples, sr)
    return _vad_energy(samples, sr)


# ── Segment utilities ─────────────────────────────────────────────────────────

def merge_segments(segs: list, min_gap: int) -> list:
    if not segs: return []
    merged = [list(segs[0])]
    for s, e in segs[1:]:
        if s - merged[-1][1] < min_gap: merged[-1][1] = e
        else: merged.append([s, e])
    return [(s, e) for s, e in merged]


def split_long_segment(start, end, samples, sr, max_dur) -> list:
    if (end - start) / sr <= max_dur:
        return [(start, end)]
    seg   = samples[start:end].astype(np.float64)
    third = len(seg) // 3
    mid   = seg[third:2*third]
    frame = sr // 10
    if len(mid) < frame:
        return [(start, end)]
    energies  = [np.sqrt(np.mean(mid[i:i+frame]**2))
                 for i in range(0, len(mid)-frame, frame)]
    split_off = np.argmin(energies) * frame + third
    split_pt  = start + split_off
    return (split_long_segment(start, split_pt, samples, sr, max_dur) +
            split_long_segment(split_pt, end, samples, sr, max_dur))


# ── Quality metrics ───────────────────────────────────────────────────────────

def compute_snr(samples: np.ndarray) -> float:
    fs = SAMPLE_RATE // 10
    energies = sorted([
        np.sqrt(np.mean(samples[i:i+fs].astype(np.float64)**2))
        for i in range(0, len(samples)-fs, fs)
    ])
    if len(energies) < 4: return 0.0
    noise  = np.mean(energies[:max(1, len(energies)//10)]) + 1e-9
    signal = np.mean(energies[len(energies)//2:]) + 1e-9
    return round(20 * math.log10(signal / noise), 2)


def compute_lufs(samples: np.ndarray) -> float:
    f = samples.astype(np.float64) / 32768.0
    sos = butter(2, 100/(SAMPLE_RATE/2), btype='high', output='sos')
    flt = sosfilt(sos, f)
    ms  = np.mean(flt**2) + 1e-12
    return round(-0.691 + 10 * math.log10(ms), 2)


def detect_clipping(samples: np.ndarray) -> float:
    return round(np.sum(np.abs(samples) >= 32000) / len(samples), 6)


# ── Main per-file processing ──────────────────────────────────────────────────

def process_audio_file(wav_path: str, speaker_id: str,
                       lang: str, vad_backend: str) -> list:
    log.info(f"  Segmenting {speaker_id} [{vad_backend}]...")
    samples, sr = read_wav_16k_mono(wav_path)
    if samples is None: return []

    raw_segs = vad_segment(samples, sr, vad_backend)
    log.info(f"    VAD found {len(raw_segs)} speech regions")

    min_gap = int(MIN_SILENCE_MS / 1000 * sr)
    merged  = merge_segments(raw_segs, min_gap)
    log.info(f"    After merge: {len(merged)} regions")

    all_segs = []
    for s, e in merged:
        all_segs.extend(split_long_segment(s, e, samples, sr, MAX_SEGMENT_DURATION))

    valid = [(s, e) for s, e in all_segs
             if (e - s) / sr >= MIN_SEGMENT_DURATION]
    log.info(f"    Valid duration: {len(valid)} segments")

    out_dir = os.path.join(SEGMENTS_DIR, lang, speaker_id)
    os.makedirs(out_dir, exist_ok=True)
    records = []

    for idx, (s, e) in enumerate(valid, 1):
        seg      = samples[s:e]
        duration = (e - s) / sr
        snr      = compute_snr(seg)
        lufs     = compute_lufs(seg)
        clipping = detect_clipping(seg)

        if snr < SNR_THRESHOLD_DB:
            log.debug(f"    Seg {idx:03d} REJECT — SNR {snr:.1f}dB"); continue
        if clipping > 0.001:
            log.debug(f"    Seg {idx:03d} REJECT — clipping {clipping:.4f}"); continue
        if lufs < -50:
            log.debug(f"    Seg {idx:03d} REJECT — too quiet {lufs:.1f} LUFS"); continue

        seg_id   = f"{speaker_id}_seg{idx:04d}"
        out_path = os.path.join(out_dir, f"{seg_id}.wav")

        with wave.open(out_path, "w") as wf:
            wf.setnchannels(1); wf.setsampwidth(2)
            wf.setframerate(sr); wf.writeframes(seg.tobytes())

        records.append({
            "segment_id"       : seg_id,
            "speaker_id"       : speaker_id,
            "language"         : lang,
            "audio_path"       : out_path,
            "start_sample"     : int(s),
            "end_sample"       : int(e),
            "duration_seconds" : round(duration, 3),
            "snr_db"           : snr,
            "lufs"             : lufs,
            "clipping_fraction": clipping,
            "quality_pass"     : True,
        })

    total_min = sum(r["duration_seconds"] for r in records) / 60
    log.info(f"    Exported {len(records)} clean segs ({total_min:.1f} min)")
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lang", choices=["english","tamil","all"], default="all")
    parser.add_argument("--vad",  choices=["silero","webrtc","energy"],
                        default=None, help="Force VAD backend")
    args = parser.parse_args()

    os.makedirs(SEGMENTS_DIR, exist_ok=True)
    for lang in ["english","tamil"]:
        os.makedirs(os.path.join(SEGMENTS_DIR, lang), exist_ok=True)

    langs = ["english","tamil"] if args.lang == "all" else [args.lang]
    all_records = []

    for lang in langs:
        lang_dir  = os.path.join(RAW_AUDIO_DIR, lang)
        if not os.path.isdir(lang_dir):
            log.warning(f"No raw audio for {lang}. Run 02_download.py first.")
            continue

        wav_files = [f for f in os.listdir(lang_dir)
                     if f.endswith(".wav") and "_raw" not in f]
        log.info(f"\n{'='*50}\nSegmenting {lang.upper()} — {len(wav_files)} files\n{'='*50}")

        lang_records = []
        for wf in tqdm(wav_files, desc=lang):
            spk_id  = wf.replace(".wav","")
            records = process_audio_file(
                os.path.join(lang_dir, wf), spk_id, lang,
                args.vad or VAD_BACKEND
            )
            lang_records.extend(records)

        manifest = os.path.join(SEGMENTS_DIR, f"manifest_{lang}.json")
        with open(manifest, "w") as f:
            json.dump(lang_records, f, ensure_ascii=False, indent=2)

        total_min = sum(r["duration_seconds"] for r in lang_records) / 60
        log.info(f"\n{lang.upper()}: {len(lang_records)} segs, {total_min:.1f} min")
        all_records.extend(lang_records)

    combined = os.path.join(SEGMENTS_DIR, "manifest_all.json")
    with open(combined, "w") as f:
        json.dump(all_records, f, ensure_ascii=False, indent=2)

    total_min = sum(r["duration_seconds"] for r in all_records) / 60
    log.info(f"\n✅ Total: {len(all_records)} segments | {total_min:.1f} min")


if __name__ == "__main__":
    main()
