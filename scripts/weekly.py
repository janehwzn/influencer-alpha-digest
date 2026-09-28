#!/usr/bin/env python3
"""Weekly orchestrator: fetch -> transcribe -> analyze -> render.

Usage: python3 scripts/weekly.py [--days 7] [--date 2026-09-28] [--model small]
"""
import argparse
import datetime as dt
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(BASE, "scripts")


def sh(*args):
    print("+ " + " ".join(args), flush=True)
    r = subprocess.run(args, cwd=BASE)
    if r.returncode != 0:
        raise SystemExit(f"command failed ({r.returncode}): {' '.join(args)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--model", default="small",
                    help="faster-whisper model size")
    ap.add_argument("--skip-transcribe", action="store_true")
    args = ap.parse_args()

    manifest = os.path.join(BASE, "data", f"videos-{args.date}.json")
    sh(sys.executable, os.path.join(SCRIPTS, "fetch_videos.py"),
       "--days", str(args.days), "--date", args.date,
       "--out", manifest)
    if not args.skip_transcribe:
        sh(sys.executable, os.path.join(SCRIPTS, "transcribe.py"),
           "--manifest", manifest, "--model", args.model)
    sh(sys.executable, os.path.join(SCRIPTS, "analyze.py"),
       "--date", args.date)
    sh(sys.executable, os.path.join(SCRIPTS, "render_html.py"),
       "--date", args.date)
    print("weekly pipeline done", flush=True)


if __name__ == "__main__":
    main()
