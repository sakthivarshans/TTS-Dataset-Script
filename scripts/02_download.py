"""
=============================================================
Script 02 — Download & Convert Audio
=============================================================
Downloads audio from YouTube URLs using yt-dlp,
converts to 16kHz mono WAV (TTS standard).

INSTALL:
    pip install yt-dlp ffmpeg-python

HOW TO USE:
    python 02_download.py                         # download all sources
    python 02_download.py --lang english          # only English
    python 02_download.py --lang tamil            # only Tamil
    python 02_download.py --retry-failed          # retry failed downloads
=============================================================
"""

import argparse, io, json, logging, os, shutil, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (DATA_DIR, RAW_AUDIO_DIR, LOGS_DIR,
                    SAMPLE_RATE, CHANNELS)
os.makedirs(LOGS_DIR, exist_ok=True)

# Force UTF-8 output on Windows so Unicode characters don't cause cp1252 errors
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Stream handler with explicit UTF-8 encoding
_stream_handler = logging.StreamHandler(stream=io.TextIOWrapper(
    sys.stdout.buffer if hasattr(sys.stdout, 'buffer') else open(os.devnull, 'wb'),
    encoding='utf-8', errors='replace'
))
_stream_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, "02_download.log"), encoding='utf-8'),
        _stream_handler,
    ]
)
log = logging.getLogger(__name__)


def ensure_dirs():
    for d in [RAW_AUDIO_DIR, LOGS_DIR,
              os.path.join(RAW_AUDIO_DIR, "english"),
              os.path.join(RAW_AUDIO_DIR, "tamil")]:
        os.makedirs(d, exist_ok=True)


# Maximum allowed video duration — skip anything longer than this
MAX_VIDEO_MINUTES = 90


def get_video_duration_yt(url: str, cookie_args: list) -> float:
    """Return video duration in seconds via yt-dlp metadata (fast, no download)."""
    cmd = [
        "yt-dlp",
        "--no-playlist",
        "--no-check-certificates",
        "--js-runtimes", "node",
        "--extractor-args", "youtube:player_client=web",
        "--print", "duration",
        *cookie_args,
        url
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding='utf-8', errors='replace', timeout=30
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0  # unknown — let it try anyway


def download_video(url: str, out_path: str) -> bool:
    """Download best audio stream from YouTube URL."""
    # Use cookies file if present (needed to bypass YouTube bot-detection)
    cookies_raw = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cookies.txt")
    if os.path.exists(cookies_raw):
        cookies_clean = clean_cookies_file(cookies_raw)
        cookie_args = ["--cookies", cookies_clean]
    else:
        cookie_args = []

    cmd = [
        "yt-dlp",
        "--no-playlist",
        "--extract-audio",
        "--audio-format", "wav",
        "--audio-quality", "0",          # best quality
        "--postprocessor-args", f"ffmpeg:-ar {SAMPLE_RATE} -ac {CHANNELS}",
        "--output", out_path,
        "--no-cache-dir",
        "--socket-timeout", "30",
        "--retries", "3",
        "--no-check-certificates",
        "--js-runtimes", "node",         # use Node.js to solve YouTube JS challenge
        "--extractor-args", "youtube:player_client=web",
        *cookie_args,                    # inject cookies if file exists
        "--ffmpeg-location", _find_ffmpeg(),
        url
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding='utf-8', errors='replace', timeout=300
        )
        if result.returncode == 0:
            return True
        else:
            log.error(f"yt-dlp error for {url}:\n{result.stderr[:800]}")
            return False
    except subprocess.TimeoutExpired:
        log.error(f"Timeout downloading {url}")
        return False
    except FileNotFoundError:
        log.error("yt-dlp not found. Install: pip install yt-dlp")
        sys.exit(1)


def _find_ffmpeg() -> str:
    """Return directory containing ffmpeg, checking PATH and known install locations."""
    # 1. Check current PATH
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        return os.path.dirname(ffmpeg_path)
    # 2. Check common Windows install locations
    candidates = [
        r"D:\ffmpeg-8.1.1-essentials_build\bin",
        r"D:\ffmpeg-8.1.1-full_build\bin",
        r"C:\ffmpeg\bin",
        r"C:\Program Files\ffmpeg\bin",
        r"C:\ProgramData\chocolatey\bin",
        # winget full_build install path
        os.path.join(os.environ.get("LOCALAPPDATA", ""),
                     r"Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin"),
    ]
    # Also search winget install location under LOCALAPPDATA / ProgramFiles
    for base in [os.environ.get("LOCALAPPDATA", ""), os.environ.get("ProgramFiles", "")]:
        if base:
            candidates.append(os.path.join(base, "Microsoft", "WinGet", "Packages"))
    for d in candidates:
        if d and os.path.isfile(os.path.join(d, "ffmpeg.exe")):
            return d
    # 3. Scan PATH environment for ffmpeg.exe manually (handles session-only PATH changes)
    for p in os.environ.get("PATH", "").split(os.pathsep):
        if os.path.isfile(os.path.join(p, "ffmpeg.exe")):
            return p
    return ""  # let yt-dlp try on its own


def clean_cookies_file(src: str) -> str:
    """Fix malformed Netscape cookie lines and return path to cleaned temp file."""
    import tempfile
    cleaned = []
    with open(src, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            stripped = line.rstrip("\n")
            # Keep header/comment lines unchanged
            if stripped.startswith("#") or stripped == "":
                cleaned.append(stripped)
                continue
            parts = stripped.split("\t")
            if len(parts) == 7:
                domain = parts[0]
                # Netscape rule: domain_specified must be TRUE when domain starts with '.'
                if domain.startswith(".") and parts[1].upper() == "FALSE":
                    parts[1] = "TRUE"
                cleaned.append("\t".join(parts))
            # skip lines that don't fit the 7-field Netscape format
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix="_yt_cookies.txt",
                                      delete=False, encoding="utf-8")
    tmp.write("\n".join(cleaned))
    tmp.close()
    return tmp.name


def convert_to_standard_wav(in_path: str, out_path: str) -> bool:
    """Ensure 16kHz mono PCM WAV regardless of source format."""
    ffmpeg_dir = _find_ffmpeg()
    ffmpeg_exe = os.path.join(ffmpeg_dir, "ffmpeg.exe") if ffmpeg_dir else (shutil.which("ffmpeg") or "ffmpeg")
    cmd = [
        ffmpeg_exe, "-y",
        "-i", in_path,
        "-ar", str(SAMPLE_RATE),
        "-ac", str(CHANNELS),
        "-sample_fmt", "s16",
        "-acodec", "pcm_s16le",
        out_path
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding='utf-8', errors='replace', timeout=120
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        log.error(f"ffmpeg error: {e}")
        return False


def get_audio_duration(path: str) -> float:
    """Return duration in seconds using ffprobe."""
    ffmpeg_dir = _find_ffmpeg()
    ffprobe_exe = os.path.join(ffmpeg_dir, "ffprobe.exe") if ffmpeg_dir else (shutil.which("ffprobe") or "ffprobe")
    cmd = [
        ffprobe_exe, "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding='utf-8', errors='replace', timeout=30
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def process_sources(sources: list, lang: str, failed_log: str) -> dict:
    lang_dir = os.path.join(RAW_AUDIO_DIR, lang)
    stats = {"downloaded": 0, "failed": 0, "total_minutes": 0.0}
    failed = []

    for i, src in enumerate(sources, 1):
        url        = src["url"]
        speaker_id = src["speaker_id"]
        out_file   = os.path.join(lang_dir, f"{speaker_id}.wav")
        tmp_file   = os.path.join(lang_dir, f"{speaker_id}_raw.%(ext)s")

        if os.path.exists(out_file):
            dur = get_audio_duration(out_file)
            log.info(f"[{i}/{len(sources)}] SKIP (exists) {speaker_id} — {dur/60:.1f} min")
            stats["downloaded"] += 1
            stats["total_minutes"] += dur / 60
            continue

        log.info(f"[{i}/{len(sources)}] Downloading {speaker_id} from {url}")
        tmp_pattern = os.path.join(lang_dir, f"{speaker_id}_raw.%(ext)s")

        # Pre-check: skip videos that exceed the max duration limit
        cookies_raw = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cookies.txt")
        _cookie_args = ["--cookies", clean_cookies_file(cookies_raw)] if os.path.exists(cookies_raw) else []
        vid_sec = get_video_duration_yt(url, _cookie_args)
        if vid_sec > 0 and vid_sec > MAX_VIDEO_MINUTES * 60:
            log.warning(f"  [SKIP] {speaker_id} is {vid_sec/60:.0f} min — over {MAX_VIDEO_MINUTES} min limit.")
            stats["failed"] += 1
            continue

        # Step 1: download
        ok = download_video(url, tmp_pattern)
        if not ok:
            log.warning(f"  [FAIL] Download failed: {url}")
            failed.append(src)
            stats["failed"] += 1
            time.sleep(2)
            continue

        # Step 2: find downloaded file (yt-dlp fills %(ext)s)
        raw_file = None
        for ext in ["wav", "webm", "m4a", "mp3", "ogg"]:
            candidate = os.path.join(lang_dir, f"{speaker_id}_raw.{ext}")
            if os.path.exists(candidate):
                raw_file = candidate
                break

        if raw_file is None:
            log.warning(f"  [FAIL] Downloaded file not found for {speaker_id}")
            failed.append(src)
            stats["failed"] += 1
            continue

        # Step 3: convert/normalise
        ok = convert_to_standard_wav(raw_file, out_file)
        if ok:
            # Remove raw intermediate
            os.remove(raw_file)
            dur = get_audio_duration(out_file)
            log.info(f"  [OK] {speaker_id} saved - {dur/60:.1f} min")
            stats["downloaded"] += 1
            stats["total_minutes"] += dur / 60

            # Save metadata alongside audio
            meta_path = out_file.replace(".wav", "_meta.json")
            with open(meta_path, "w") as mf:
                json.dump({**src, "duration_minutes": dur/60,
                           "audio_path": out_file}, mf, indent=2)
        else:
            log.warning(f"  [FAIL] Conversion failed for {speaker_id}")
            failed.append(src)
            stats["failed"] += 1

        time.sleep(1)  # polite delay

    # Save failed list for retry
    with open(failed_log, "w") as f:
        json.dump(failed, f, indent=2)

    return stats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lang", choices=["english", "tamil", "all"], default="all")
    parser.add_argument("--retry-failed", action="store_true")
    args = parser.parse_args()

    ensure_dirs()

    if args.retry_failed:
        for lang in ["english", "tamil"]:
            failed_log = os.path.join(LOGS_DIR, f"failed_{lang}.json")
            if os.path.exists(failed_log):
                with open(failed_log, encoding='utf-8-sig') as f:  # utf-8-sig handles BOM
                    sources = json.load(f)
                if sources:
                    log.info(f"Retrying {len(sources)} failed {lang} downloads...")
                    process_sources(sources, lang, failed_log)
        return

    langs_to_process = []
    if args.lang in ("english", "all"):
        langs_to_process.append(("english", "sources_english.json"))
    if args.lang in ("tamil", "all"):
        langs_to_process.append(("tamil", "sources_tamil.json"))

    total_stats = {"downloaded": 0, "failed": 0, "total_minutes": 0.0}

    for lang, src_file in langs_to_process:
        src_path = os.path.join(DATA_DIR, src_file)
        if not os.path.exists(src_path):
            log.error(f"Source file not found: {src_path}. Run 01_sources.py first.")
            continue

        with open(src_path) as f:
            sources = json.load(f)

        log.info(f"\n{'='*50}")
        log.info(f"Processing {lang.upper()} — {len(sources)} sources")
        log.info(f"{'='*50}")

        failed_log = os.path.join(LOGS_DIR, f"failed_{lang}.json")
        stats = process_sources(sources, lang, failed_log)

        log.info(f"\n{lang.upper()} Summary:")
        log.info(f"  Downloaded : {stats['downloaded']}")
        log.info(f"  Failed     : {stats['failed']}")
        log.info(f"  Total time : {stats['total_minutes']:.1f} min")

        for k in total_stats:
            total_stats[k] += stats[k]

    log.info(f"\n{'='*50}")
    log.info(f"OVERALL: {total_stats['downloaded']} downloaded, "
             f"{total_stats['failed']} failed, "
             f"{total_stats['total_minutes']:.1f} min total")


if __name__ == "__main__":
    main()
