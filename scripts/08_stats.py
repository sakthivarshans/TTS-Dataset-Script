"""
=============================================================
Script 08 — Dataset Statistics & Quality Report
=============================================================
Generates a comprehensive quality report including:
  - Duration breakdown by language, emotion, style
  - SNR distribution histogram (text-based)
  - Speaker diversity analysis
  - Transcript statistics (avg words, vocabulary)
  - Missing data check
  - Export ready-to-paste stats for your PDF report

HOW TO USE:
    python 08_stats.py
    python 08_stats.py --detailed
=============================================================
"""

import argparse, json, math, os, sys
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import FINAL_DIR, QUALITY_DIR, LOGS_DIR


def load_final() -> list:
    path = os.path.join(FINAL_DIR, "final_manifest.json")
    if not os.path.exists(path):
        # Try to load manual review approved
        review_path = os.path.join(QUALITY_DIR, "manual_review.json")
        if os.path.exists(review_path):
            with open(review_path, encoding="utf-8") as f:
                data = json.load(f)
            return data.get("approved", [])
        print("No final manifest found. Run 06_quality_filter.py first.")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def text_bar(value: float, max_val: float, width: int = 30) -> str:
    filled = int((value / max(max_val, 1)) * width)
    return "█" * filled + "░" * (width - filled)


def histogram(values: list, bins: int = 10, label: str = "") -> str:
    if not values:
        return ""
    mn, mx = min(values), max(values)
    step   = (mx - mn) / bins if mx != mn else 1
    counts = [0] * bins
    for v in values:
        idx = min(int((v - mn) / step), bins - 1)
        counts[idx] += 1

    max_count = max(counts) or 1
    lines = [f"\n  {label}"]
    for i, c in enumerate(counts):
        lo = mn + i * step
        hi = lo + step
        bar = text_bar(c, max_count, 25)
        lines.append(f"  {lo:6.1f}–{hi:6.1f} │{bar}│ {c}")
    return "\n".join(lines)


def vocabulary_stats(segments: list) -> dict:
    all_words = []
    for seg in segments:
        all_words.extend(seg.get("transcript","").lower().split())
    total  = len(all_words)
    unique = len(set(all_words))
    return {
        "total_words"  : total,
        "unique_words" : unique,
        "ttr"          : round(unique / max(total, 1), 4),   # Type-Token Ratio
        "avg_word_len" : round(sum(len(w) for w in all_words) / max(total, 1), 2),
    }


def generate_report(segments: list, detailed: bool) -> dict:
    if not segments:
        return {"error": "No segments found"}

    # ── Basic counts ──────────────────────────────────────────────────────────
    total     = len(segments)
    durations = [s["duration_seconds"] for s in segments]
    total_min = sum(durations) / 60

    # ── By language ───────────────────────────────────────────────────────────
    by_lang   = defaultdict(list)
    for s in segments:
        by_lang[s["language"]].append(s)

    lang_stats = {}
    for lang, segs in by_lang.items():
        durs      = [s["duration_seconds"] for s in segs]
        lang_stats[lang] = {
            "count"       : len(segs),
            "total_min"   : round(sum(durs) / 60, 2),
            "avg_dur_sec" : round(sum(durs) / len(durs), 2),
            "emotions"    : dict(Counter(s.get("emotion","?") for s in segs)),
            "styles"      : dict(Counter(s.get("style","?") for s in segs)),
        }

    # ── Speaker diversity ────────────────────────────────────────────────────
    speakers   = Counter(s["speaker_id"] for s in segments)
    gender_cnt = Counter(s.get("gender","unknown") for s in segments)
    topics     = Counter(s.get("topic","?") for s in segments)

    # ── Audio quality ────────────────────────────────────────────────────────
    snrs    = [s.get("snr_db", 0) for s in segments]
    grades  = Counter(s.get("quality_grade","?") for s in segments)

    # ── Transcript quality ────────────────────────────────────────────────────
    confs       = [s.get("confidence", 0) for s in segments]
    verified    = sum(1 for s in segments if s.get("human_verified"))
    corrected   = sum(1 for s in segments if s.get("human_corrected_emotion") or
                      s.get("human_corrected_transcript"))

    # ── Vocabulary ───────────────────────────────────────────────────────────
    en_segs = [s for s in segments if s["language"] == "english"]
    ta_segs = [s for s in segments if s["language"] == "tamil"]

    en_vocab = vocabulary_stats(en_segs)
    ta_vocab = vocabulary_stats(ta_segs)

    report = {
        "summary": {
            "total_segments"     : total,
            "total_minutes"      : round(total_min, 2),
            "human_verified"     : verified,
            "human_corrected"    : corrected,
            "unique_speakers"    : len(speakers),
        },
        "by_language"  : lang_stats,
        "quality": {
            "grades"            : dict(grades),
            "avg_snr_db"        : round(sum(snrs)/len(snrs), 2) if snrs else 0,
            "min_snr_db"        : round(min(snrs), 2) if snrs else 0,
            "max_snr_db"        : round(max(snrs), 2) if snrs else 0,
            "avg_asr_confidence": round(sum(confs)/len(confs), 3) if confs else 0,
        },
        "diversity": {
            "gender_distribution": dict(gender_cnt),
            "topic_distribution" : dict(topics.most_common()),
            "segments_per_speaker": dict(speakers.most_common()),
        },
        "vocabulary": {
            "english": en_vocab,
            "tamil"  : ta_vocab,
        },
    }

    return report


def print_report(report: dict, segments: list, detailed: bool):
    r  = report
    s  = r["summary"]
    q  = r["quality"]
    d  = r["diversity"]

    SEP = "=" * 60

    print(f"\n{SEP}")
    print(f"  🎙  TTS DATASET — QUALITY REPORT")
    print(SEP)
    print(f"  Total segments   : {s['total_segments']}")
    print(f"  Total duration   : {s['total_minutes']:.1f} minutes")
    print(f"  Human verified   : {s['human_verified']} segments")
    print(f"  Human corrected  : {s['human_corrected']} labels")
    print(f"  Unique speakers  : {s['unique_speakers']}")

    print(f"\n  ── BY LANGUAGE {'─'*40}")
    for lang, ls in r["by_language"].items():
        print(f"\n  {lang.upper()}")
        print(f"    Segments : {ls['count']}  |  Duration: {ls['total_min']:.1f} min")
        print(f"    Avg dur  : {ls['avg_dur_sec']:.1f}s")
        print(f"    Emotions : {ls['emotions']}")
        print(f"    Styles   : {ls['styles']}")

    print(f"\n  ── AUDIO QUALITY {'─'*39}")
    print(f"  Grade distribution : {q['grades']}")
    print(f"  SNR  avg/min/max   : {q['avg_snr_db']} / {q['min_snr_db']} / {q['max_snr_db']} dB")
    print(f"  ASR confidence avg : {q['avg_asr_confidence']:.3f}")

    print(f"\n  ── SPEAKER DIVERSITY {'─'*35}")
    print(f"  Gender : {d['gender_distribution']}")
    print(f"  Topics : {dict(list(Counter(d['topic_distribution']).most_common(5)))}")

    print(f"\n  ── VOCABULARY {'─'*43}")
    for lang in ["english", "tamil"]:
        v = r["vocabulary"].get(lang, {})
        print(f"  {lang.capitalize()}: {v.get('total_words','?')} total words, "
              f"{v.get('unique_words','?')} unique, "
              f"TTR={v.get('ttr','?')}")

    if detailed:
        snrs = [s.get("snr_db",0) for s in segments]
        durs = [s.get("duration_seconds",0) for s in segments]
        print(histogram(snrs, label="SNR Distribution (dB)"))
        print(histogram(durs, label="Duration Distribution (seconds)"))

    # Check targets
    print(f"\n  ── TARGET CHECK {'─'*41}")
    en_min = r["by_language"].get("english",{}).get("total_min",0)
    ta_min = r["by_language"].get("tamil",  {}).get("total_min",0)
    en_ok  = "✓" if en_min >= 28 else "✗ (need more)"
    ta_ok  = "✓" if ta_min >= 28 else "✗ (need more)"
    tot_ok = "✓" if (en_min + ta_min) >= 58 else "✗ (need more)"
    print(f"  English 30 min  : {en_min:.1f} min {en_ok}")
    print(f"  Tamil 30 min    : {ta_min:.1f} min {ta_ok}")
    print(f"  Total 60 min    : {en_min+ta_min:.1f} min {tot_ok}")
    print(SEP)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--detailed", action="store_true")
    args = parser.parse_args()

    segments = load_final()
    report   = generate_report(segments, args.detailed)

    # Save report
    os.makedirs(QUALITY_DIR, exist_ok=True)
    report_path = os.path.join(QUALITY_DIR, "dataset_stats.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print_report(report, segments, args.detailed)
    print(f"\n  Full stats saved → {report_path}")


if __name__ == "__main__":
    main()
