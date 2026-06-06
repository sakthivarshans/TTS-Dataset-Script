"""
=============================================================
Script 07 — Manual Review Tool (CLI)
=============================================================
THIS IS THE MOST IMPORTANT STEP.
Sarvam AI explicitly said: "Listen to your data."

This tool lets you:
  - Play each audio segment in your terminal
  - See the transcript and emotion tags
  - Approve ✓, Reject ✗, or Edit ✎ each segment
  - Saves your manual review decisions

Segments you manually approve get a "human_verified: true" flag,
which is a HUGE quality signal for anyone using the dataset.

INSTALL:
    pip install playsound   (or use afplay/aplay/mpg123)

HOW TO USE:
    python 07_manual_review.py                      # review all
    python 07_manual_review.py --lang english       # only English
    python 07_manual_review.py --grade A            # only grade A
    python 07_manual_review.py --sample 20          # review 20 random samples
    python 07_manual_review.py --resume             # continue from where left off
=============================================================
"""

import argparse, json, os, platform, random, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import FINAL_DIR, QUALITY_DIR, LOGS_DIR


def play_audio(path: str):
    """Cross-platform audio playback."""
    system = platform.system()
    try:
        if system == "Darwin":          # macOS
            subprocess.run(["afplay", path], timeout=70)
        elif system == "Linux":
            # Try multiple players
            for player in ["aplay", "mpg123", "ffplay -nodisp -autoexit"]:
                try:
                    cmd = player.split() + [path]
                    subprocess.run(cmd, timeout=70,
                                   stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
                    return
                except (FileNotFoundError, subprocess.TimeoutExpired):
                    continue
        elif system == "Windows":
            subprocess.run(["start", "/wait", path], shell=True, timeout=70)
    except Exception as e:
        print(f"  [Audio playback failed: {e}. Skipping playback.]")


def clear():
    os.system("cls" if platform.system() == "Windows" else "clear")


def print_segment_info(seg: dict, idx: int, total: int, reviewed: int):
    clear()
    print("=" * 65)
    print(f"  MANUAL REVIEW — Segment {idx}/{total}  |  Reviewed so far: {reviewed}")
    print("=" * 65)
    print(f"  ID         : {seg['segment_id']}")
    print(f"  Language   : {seg['language'].upper()}")
    print(f"  Speaker    : {seg['speaker_id']}  |  Gender: {seg.get('gender','?')}")
    print(f"  Duration   : {seg['duration_seconds']:.1f}s")
    print(f"  SNR        : {seg.get('snr_db','?')} dB")
    print(f"  Quality    : Grade {seg.get('quality_grade','?')}")
    print(f"  Emotion    : {seg.get('emotion','?')}  |  Style: {seg.get('style','?')}")
    print(f"  Energy     : {seg.get('energy','?')}   |  Speed: {seg.get('speech_rate','?')}")
    print(f"  Tag Conf   : {seg.get('tag_confidence',0):.2f}")
    print("-" * 65)
    print(f"  TRANSCRIPT :")
    print()
    # Word-wrap transcript at 60 chars
    words = seg.get("transcript","").split()
    line = "  "
    for w in words:
        if len(line) + len(w) > 63:
            print(line)
            line = "  " + w + " "
        else:
            line += w + " "
    if line.strip():
        print(line)
    print()
    print("-" * 65)
    print("  [P] Play audio   [A] Approve   [R] Reject   [E] Edit label")
    print("  [S] Skip         [Q] Quit & save")
    print("-" * 65)


def edit_labels(seg: dict) -> dict:
    """Let reviewer correct emotion/style labels."""
    print("\n  Current emotion:", seg.get("emotion"))
    print("  Options: neutral, happy, sad, angry, excited, calm, fearful, surprised")
    new_emotion = input("  New emotion (Enter to keep): ").strip().lower()
    if new_emotion:
        seg["emotion"] = new_emotion
        seg["human_corrected_emotion"] = True

    print("\n  Current style:", seg.get("style"))
    print("  Options: formal, conversational, storytelling, instructional, emphatic, narrative, motivational")
    new_style = input("  New style (Enter to keep): ").strip().lower()
    if new_style:
        seg["style"] = new_style
        seg["human_corrected_style"] = True

    print("\n  Current transcript (first 100 chars):", seg.get("transcript","")[:100])
    fix = input("  Fix transcript? (Enter to keep, or type correction): ").strip()
    if fix:
        seg["transcript"] = fix
        seg["human_corrected_transcript"] = True

    return seg


def run_review(segments: list, output_path: str,
               resume_ids: set, sample_n: int):

    if sample_n:
        segments = random.sample(segments, min(sample_n, len(segments)))

    approved = []
    rejected = []
    skipped  = []
    reviewed = 0

    # Load existing if resuming
    if os.path.exists(output_path):
        with open(output_path, encoding="utf-8") as f:
            existing = json.load(f)
        approved = existing.get("approved", [])
        rejected = existing.get("rejected", [])
        reviewed = len(approved) + len(rejected)

    for idx, seg in enumerate(segments, 1):
        seg_id = seg["segment_id"]

        # Skip already reviewed
        if seg_id in resume_ids:
            continue

        print_segment_info(seg, idx, len(segments), reviewed)

        played = False
        while True:
            choice = input("\n  Your choice: ").strip().upper()

            if choice == "P" or (not played and choice == ""):
                print("  ▶ Playing audio...")
                play_audio(seg["audio_path"])
                played = True
                print_segment_info(seg, idx, len(segments), reviewed)
                continue

            elif choice == "A":
                seg["human_verified"]  = True
                seg["review_decision"] = "approved"
                approved.append(seg)
                reviewed += 1
                print(f"  ✓ APPROVED")
                break

            elif choice == "R":
                reason = input("  Reject reason (optional): ").strip()
                seg["human_verified"]    = False
                seg["review_decision"]   = "rejected"
                seg["human_reject_reason"] = reason or "reviewer_rejected"
                rejected.append(seg)
                reviewed += 1
                print(f"  ✗ REJECTED")
                break

            elif choice == "E":
                seg = edit_labels(seg)
                seg["human_verified"]  = True
                seg["review_decision"] = "approved_with_edits"
                approved.append(seg)
                reviewed += 1
                print(f"  ✎ EDITED & APPROVED")
                break

            elif choice == "S":
                skipped.append(seg_id)
                print(f"  → SKIPPED")
                break

            elif choice == "Q":
                print(f"\n  Quitting. Saving progress...")
                _save(output_path, approved, rejected)
                _print_stats(approved, rejected, skipped)
                return approved

            else:
                print("  Invalid. Press P/A/R/E/S/Q")

        # Auto-save every 10 reviews
        if reviewed % 10 == 0:
            _save(output_path, approved, rejected)
            print(f"  💾 Auto-saved progress ({reviewed} reviewed)")

    _save(output_path, approved, rejected)
    _print_stats(approved, rejected, skipped)
    return approved


def _save(path: str, approved: list, rejected: list):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"approved": approved, "rejected": rejected}, f,
                  ensure_ascii=False, indent=2)


def _print_stats(approved, rejected, skipped):
    total_min = sum(r["duration_seconds"] for r in approved) / 60
    print(f"\n{'='*55}")
    print(f"  Review Complete:")
    print(f"  ✓ Approved : {len(approved)} ({total_min:.1f} min)")
    print(f"  ✗ Rejected : {len(rejected)}")
    print(f"  → Skipped  : {len(skipped)}")
    print(f"{'='*55}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lang",   choices=["english","tamil","all"], default="all")
    parser.add_argument("--grade",  choices=["A","B","C","all"], default="all")
    parser.add_argument("--sample", type=int, default=0,
                        help="Review N random samples (0 = all)")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    final_manifest = os.path.join(FINAL_DIR, "final_manifest.json")
    if not os.path.exists(final_manifest):
        print("ERROR: Run 06_quality_filter.py first.")
        sys.exit(1)

    with open(final_manifest, encoding="utf-8") as f:
        all_segs = json.load(f)

    # Filter by lang
    if args.lang != "all":
        all_segs = [s for s in all_segs if s["language"] == args.lang]

    # Filter by grade
    if args.grade != "all":
        all_segs = [s for s in all_segs if s.get("quality_grade") == args.grade]

    print(f"\n  Segments to review: {len(all_segs)}")
    print(f"  Language filter   : {args.lang}")
    print(f"  Grade filter      : {args.grade}")
    print(f"  Sample size       : {args.sample or 'all'}")
    print(f"\n  Press ENTER to start...")
    input()

    output_path = os.path.join(QUALITY_DIR, "manual_review.json")

    # Load already-reviewed IDs for resume
    resume_ids = set()
    if args.resume and os.path.exists(output_path):
        with open(output_path, encoding="utf-8") as f:
            existing = json.load(f)
        for seg in existing.get("approved", []) + existing.get("rejected", []):
            resume_ids.add(seg["segment_id"])
        print(f"  Resuming — {len(resume_ids)} already reviewed, skipping those.")

    approved = run_review(all_segs, output_path, resume_ids, args.sample)

    # Merge back into final manifest
    if approved:
        reviewed_ids = {s["segment_id"] for s in approved}
        # Keep unreviewed segments + reviewed approved segments
        with open(final_manifest, encoding="utf-8") as f:
            current = json.load(f)

        unreviewed = [s for s in current if s["segment_id"] not in resume_ids
                      and s["segment_id"] not in reviewed_ids]
        final = approved + unreviewed

        with open(final_manifest, "w", encoding="utf-8") as f:
            json.dump(final, f, ensure_ascii=False, indent=2)

        print(f"\n  Final manifest updated: {len(final)} segments")


if __name__ == "__main__":
    main()
