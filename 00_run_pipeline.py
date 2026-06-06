"""
=============================================================
Script 00 — Master Pipeline Runner
=============================================================
Runs all scripts in sequence with progress tracking,
error handling, and a final summary.

HOW TO USE:
    python 00_run_pipeline.py                    # full pipeline
    python 00_run_pipeline.py --start 4          # start from step 4
    python 00_run_pipeline.py --steps 3 4 5      # run only steps 3,4,5
    python 00_run_pipeline.py --skip-review      # skip manual review step
    python 00_run_pipeline.py --dry-run          # test without HF upload
=============================================================
"""
import argparse, json, os, subprocess, sys, time
from datetime import datetime

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")
LOGS_DIR    = os.path.join(BASE_DIR, "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

PIPELINE = [
    (1, "01_sources.py",        [],                "Generate source URL lists"),
    (2, "02_download.py",       [],                "Download YouTube audio"),
    (3, "03_segment.py",        [],                "VAD segmentation + SNR filter"),
    (4, "04_transcribe.py",     ["--resume"],      "Sarvam ASR transcription"),
    (5, "05_tag_emotions.py",   ["--resume"],      "LLM emotion/style tagging"),
    (6, "06_quality_filter.py", [],                "Deep quality filter + normalize"),
    (7, "07_manual_review.py",  ["--sample","30"], "Manual review (30 samples)"),
    (8, "08_stats.py",          ["--detailed"],    "Generate quality report"),
    (9, "09_push_hf.py",        [],                "Push to HuggingFace Hub"),
]

STATUS_FILE = os.path.join(LOGS_DIR, "pipeline_status.json")


def load_status() -> dict:
    if os.path.exists(STATUS_FILE):
        with open(STATUS_FILE) as f:
            return json.load(f)
    return {}


def save_status(status: dict):
    with open(STATUS_FILE, "w") as f:
        json.dump(status, f, indent=2)


def run_step(step_num: int, script: str, extra_args: list) -> bool:
    script_path = os.path.join(SCRIPTS_DIR, script)
    log_path    = os.path.join(LOGS_DIR, f"step{step_num:02d}_{script.replace('.py','')}.log")
    cmd         = [sys.executable, script_path] + extra_args

    print(f"\n{'─'*60}")
    print(f"  STEP {step_num}: {script}")
    print(f"  Command: {' '.join(cmd)}")
    print(f"{'─'*60}")

    start = time.time()
    try:
        with open(log_path, "w") as log_file:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            for line in process.stdout:
                print(f"  {line}", end="")
                log_file.write(line)
            process.wait()

        elapsed = time.time() - start
        if process.returncode == 0:
            print(f"\n  ✅ Step {step_num} completed in {elapsed:.1f}s")
            return True
        else:
            print(f"\n  ❌ Step {step_num} FAILED (exit code {process.returncode})")
            print(f"     See log: {log_path}")
            return False

    except KeyboardInterrupt:
        print(f"\n  ⚠ Step {step_num} interrupted by user")
        return False
    except Exception as e:
        print(f"\n  ❌ Step {step_num} error: {e}")
        return False


def print_banner():
    print("""
╔══════════════════════════════════════════════════════════╗
║       INDIAN TTS DATASET PIPELINE                        ║
║       English (30 min) + Tamil (30 min)                  ║
║       Powered by Sarvam AI APIs                          ║
╚══════════════════════════════════════════════════════════╝
    """)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start",       type=int, default=1,
                        help="Start from step N")
    parser.add_argument("--steps",       type=int, nargs="+",
                        help="Run only these step numbers")
    parser.add_argument("--skip-review", action="store_true",
                        help="Skip manual review step (step 7)")
    parser.add_argument("--dry-run",     action="store_true",
                        help="Pass --dry-run to push step")
    parser.add_argument("--status",      action="store_true",
                        help="Show pipeline status and exit")
    args = parser.parse_args()

    print_banner()

    # Show status
    if args.status:
        status = load_status()
        print("Pipeline status:")
        for num, script, _, desc in [(s[0],s[1],s[2],s[3]) for s in PIPELINE]:
            s = status.get(str(num), {})
            icon = "✅" if s.get("success") else ("❌" if s.get("ran") else "○")
            t = f"  ({s.get('duration','?')})" if s.get("ran") else ""
            print(f"  {icon}  Step {num}: {desc}{t}")
        return

    # Determine which steps to run
    if args.steps:
        steps_to_run = set(args.steps)
    else:
        steps_to_run = set(range(args.start, 10))

    if args.skip_review:
        steps_to_run.discard(7)

    status  = load_status()
    results = []

    print(f"  Steps to run: {sorted(steps_to_run)}")
    print(f"  Start time  : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    for step_num, script, extra_args, desc in PIPELINE:
        if step_num not in steps_to_run:
            continue

        print(f"\n  {'='*55}")
        print(f"  📌 STEP {step_num}/9: {desc.upper()}")

        # Modify args for dry-run
        step_args = list(extra_args)
        if step_num == 9 and args.dry_run:
            step_args.append("--dry-run")

        start = time.time()
        success = run_step(step_num, script, step_args)
        elapsed = time.time() - start

        status[str(step_num)] = {
            "ran"     : True,
            "success" : success,
            "duration": f"{elapsed:.0f}s",
            "timestamp": datetime.now().isoformat(),
        }
        save_status(status)
        results.append((step_num, desc, success, elapsed))

        if not success:
            print(f"\n  ⚠ Pipeline halted at step {step_num}.")
            print(f"    Fix the issue and re-run with: --start {step_num}")
            break

    # ── Final summary ─────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  PIPELINE SUMMARY")
    print(f"{'='*60}")
    for num, desc, ok, dur in results:
        icon = "✅" if ok else "❌"
        print(f"  {icon}  Step {num}: {desc:40s} [{dur:.0f}s]")

    total_ok = all(ok for _, _, ok, _ in results)
    if total_ok:
        print(f"\n  🎉 All steps completed successfully!")
        print(f"  Check your HuggingFace dataset and run 08_stats.py for the report.")
    else:
        print(f"\n  ⚠ Some steps failed. Check logs in: {LOGS_DIR}")

    print(f"  End time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
