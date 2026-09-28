#!/usr/bin/env python3
"""Download audio and transcribe fresh videos with faster-whisper.

Reads the manifest written by fetch_videos.py, skips video IDs already in
state.json, and for each new video:
  1. downloads 360p mp4 with yt-dlp (android player client),
  2. extracts 16kHz mono wav with ffmpeg,
  3. transcribes with faster-whisper (Chinese),
  4. saves transcripts/<video_id>.txt and updates state.json.

Usage: python3 scripts/transcribe.py --manifest data/videos-2026-09-28.json
       [--model small] [--limit 8]
"""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

YTDLP = [
    "yt-dlp", "--no-warnings", "--no-check-certificates",
    "--extractor-args", "youtube:player_client=android",
    "--retries", "50", "--retry-sleep", "5", "--continue",
]


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=3600)


def transcribe_wav(wav_path, model_name="small"):
    from faster_whisper import WhisperModel
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segments, info = model.transcribe(
        wav_path, language="zh", beam_size=5, vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500))
    lines = []
    for s in segments:
        ts = f"[{int(s.start // 60):02d}:{int(s.start % 60):02d}]"
        lines.append(f"{ts} {s.text.strip()}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--model", default="small")
    ap.add_argument("--limit", type=int, default=8,
                    help="max videos to transcribe per run")
    args = ap.parse_args()

    manifest = json.load(open(args.manifest, encoding="utf-8"))
    state_path = os.path.join(BASE, "data", "state.json")
    state = json.load(open(state_path, encoding="utf-8")) \
        if os.path.exists(state_path) else {"processed": {}}

    tdir = os.path.join(BASE, "transcripts")
    os.makedirs(tdir, exist_ok=True)
    tmpdir = os.path.join(BASE, "data", "tmp")
    os.makedirs(tmpdir, exist_ok=True)

    done = 0
    for item in manifest["items"]:
        vid = item["id"]
        if vid in state["processed"]:
            continue
        if done >= args.limit:
            break
        print(f"== {item['channel']}: {item['title'][:60]} ==", flush=True)
        mp4 = os.path.join(tmpdir, f"{vid}.mp4")
        wav = os.path.join(tmpdir, f"{vid}.wav")
        txt = os.path.join(tdir, f"{vid}.txt")
        ok = False
        try:
            r = run(YTDLP + ["-f", "18", "-o", mp4, item["url"]])
            if r.returncode != 0 or not os.path.exists(mp4):
                print(f"  download failed: {r.stderr[-300:]}", flush=True)
                continue
            r = run(["ffmpeg", "-y", "-v", "error", "-i", mp4,
                     "-ar", "16000", "-ac", "1", wav])
            if r.returncode != 0:
                print("  ffmpeg failed", flush=True)
                continue
            text = transcribe_wav(wav, args.model)
            header = (f"CHANNEL: {item['channel']}\nTITLE: {item['title']}\n"
                      f"URL: {item['url']}\nUPLOAD_DATE: {item['upload_date']}\n\n")
            open(txt, "w", encoding="utf-8").write(header + text)
            chars = len(text)
            print(f"  transcribed {chars} chars -> {txt}", flush=True)
            state["processed"][vid] = {
                "title": item["title"], "channel": item["channel"],
                "url": item["url"], "upload_date": item["upload_date"],
                "transcript": f"transcripts/{vid}.txt",
                "chars": chars, "date": dt.date.today().isoformat(),
            }
            ok = True
        except Exception as e:
            print(f"  error: {e}", flush=True)
        finally:
            for p in (mp4, wav):
                if os.path.exists(p):
                    os.remove(p)
        if ok:
            done += 1
            json.dump(state, open(state_path, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)

    json.dump(state, open(state_path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"Transcribed {done} new video(s); state -> {state_path}", flush=True)


if __name__ == "__main__":
    main()
