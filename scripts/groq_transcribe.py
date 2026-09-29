#!/usr/bin/env python3
"""Fetch transcripts via Groq Whisper API (free tier: ~8h audio/day, no card).

Reads the manifest written by fetch_videos.py, skips video IDs already in
state.json, and for each new video:
  1. downloads audio-only with yt-dlp,
  2. compresses to 15-min m4a chunks (each ~7MB, under Groq's 25MB/request cap),
  3. POSTs each chunk to https://api.groq.com/openai/v1/audio/transcriptions
     (model=whisper-large-v3-turbo, language=zh, verbose_json segments),
  4. saves transcripts/<video_id>.txt (same format as transcribe.py) and
     updates state.json identically, so analyze.py works unchanged.

Usage: GROQ_API_KEY=<redacted> python3 scripts/groq_transcribe.py
         --manifest data/videos-2026-09-28.json [--limit 8]
"""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
MODEL = "whisper-large-v3-turbo"
CHUNK_MIN = 15          # minutes per audio chunk (keeps each well under 25MB)
BITRATE = "64k"
REQ_PAUSE = 4           # seconds between API calls (free tier: 20 RPM)


def sh(*args, **kwargs):
    r = subprocess.run(args, capture_output=True, text=True, **kwargs)
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(args[:3])} failed: {r.stderr[-300:]}")
    return r


def download_audio(url, workdir):
    """Download best audio track, return path to media file (with retries).

    If GROQ_TEST_MEDIA is set (local test path), copies it instead of
    downloading - avoids re-downloading over a throttled connection.
    """
    test_media = os.environ.get("GROQ_TEST_MEDIA")
    if test_media:
        import shutil
        dest = os.path.join(workdir, "audio" + os.path.splitext(test_media)[1])
        shutil.copy(test_media, dest)
        return dest
    out = os.path.join(workdir, "audio.%(ext)s")
    last_err = None
    for attempt in range(3):
        try:
            sh("yt-dlp", "--no-warnings", "--no-check-certificates",
               "--extractor-args", "youtube:player_client=android",
               "-f", "bestaudio/best", "-o", out, url)
            break
        except RuntimeError as e:
            last_err = e
            print(f"  download attempt {attempt + 1} failed, retrying...",
                  flush=True)
            time.sleep(10 * (attempt + 1))
    else:
        raise RuntimeError(f"yt-dlp failed 3x: {last_err}")
    files = [f for f in os.listdir(workdir) if f.startswith("audio.")]
    if not files:
        raise RuntimeError("yt-dlp produced no audio file")
    return os.path.join(workdir, files[0])


def split_chunks(media, workdir):
    """Split audio into <= CHUNK_MIN minute m4a chunks. Returns [paths]."""
    r = sh("ffprobe", "-v", "error", "-show_entries", "format=duration",
           "-of", "csv=p=0", media)
    total_min = float(r.stdout.strip()) / 60
    n = max(1, int(total_min // CHUNK_MIN) + (1 if total_min % CHUNK_MIN else 0))
    chunks = []
    for i in range(n):
        start = i * CHUNK_MIN * 60
        out = os.path.join(workdir, f"chunk{i:02d}.m4a")
        sh("ffmpeg", "-y", "-v", "error", "-ss", str(int(start)),
           "-t", str(CHUNK_MIN * 60), "-i", media,
           "-ac", "1", "-ar", "16000", "-b:a", BITRATE, out)
        chunks.append((out, int(start)))
    return chunks


def groq_transcribe(chunk_path, api_key, lang="zh"):
    """POST one audio chunk to Groq via curl (handles the egress proxy where
    Python's urllib TLS fails). Returns parsed verbose_json."""
    hdr = tempfile.NamedTemporaryFile("w", suffix=".hdr", delete=False)
    hdr.write(f"Authorization: Bearer {api_key}\n")
    hdr.close()
    try:
        for attempt in range(4):
            r = subprocess.run(
                ["curl", "-s", "--fail-with-body", "--max-time", "600",
                 "-w", "\n%{http_code}", "-X", "POST", API_URL,
                 "-H", f"@{hdr.name}",
                 "-F", f"file=@{chunk_path};type=audio/mp4",
                 "-F", f"model={MODEL}",
                 "-F", f"language={lang}",
                 "-F", "response_format=verbose_json",
                 "-F", "timestamp_granularities[]=segment"],
                capture_output=True, text=True)
            out = r.stdout
            code = out.rsplit("\n", 1)[-1].strip()
            body = out[:out.rfind("\n")]
            if code == "200":
                return json.loads(body)
            if code == "429" and attempt < 3:
                wait = 30 * (attempt + 1)
                print(f"  429, waiting {wait}s...", flush=True)
                time.sleep(wait)
                continue
            raise RuntimeError(f"Groq API {code}: {body[:300]}")
        raise RuntimeError("Groq API retries exhausted")
    finally:
        os.unlink(hdr.name)


def segments_to_lines(data, offset_sec):
    lines = []
    for s in data.get("segments", []) or []:
        start = int(s.get("start", 0)) + offset_sec
        text = (s.get("text") or "").strip()
        if text:
            lines.append(f"[{start // 60:02d}:{start % 60:02d}] {text}")
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--limit", type=int, default=8,
                    help="max videos to transcribe per run")
    ap.add_argument("--lang", default="zh")
    args = ap.parse_args()

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        sys.exit("GROQ_API_KEY env var is required")

    manifest = json.load(open(args.manifest, encoding="utf-8"))
    state_path = os.path.join(BASE, "data", "state.json")
    state = json.load(open(state_path, encoding="utf-8")) \
        if os.path.exists(state_path) else {"processed": {}}

    tdir = os.path.join(BASE, "transcripts")
    os.makedirs(tdir, exist_ok=True)

    done = 0
    for item in manifest["items"]:
        vid = item["id"]
        if vid in state["processed"]:
            continue
        if done >= args.limit:
            break
        print(f"== {item['channel']}: {item['title'][:60]} ==", flush=True)
        txt = os.path.join(tdir, f"{vid}.txt")
        try:
            with tempfile.TemporaryDirectory() as workdir:
                media = download_audio(item["url"], workdir)
                chunks = split_chunks(media, workdir)
                print(f"  {len(chunks)} audio chunk(s)", flush=True)
                lines = []
                for path, offset in chunks:
                    data = groq_transcribe(path, api_key, args.lang)
                    lines += segments_to_lines(data, offset)
                    time.sleep(REQ_PAUSE)
            text = "\n".join(lines)
            if not text.strip():
                print("  empty transcript, skipping", flush=True)
                continue
            header = (f"CHANNEL: {item['channel']}\nTITLE: {item['title']}\n"
                      f"URL: {item['url']}\nUPLOAD_DATE: {item['upload_date']}\n\n")
            open(txt, "w", encoding="utf-8").write(header + text)
            chars = len(text)
            print(f"  got {chars} chars -> {txt}", flush=True)
            state["processed"][vid] = {
                "title": item["title"], "channel": item["channel"],
                "url": item["url"], "upload_date": item["upload_date"],
                "transcript": f"transcripts/{vid}.txt",
                "chars": chars, "date": dt.date.today().isoformat(),
                "via": "groq-whisper",
            }
            done += 1
            json.dump(state, open(state_path, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
        except Exception as e:
            print(f"  error: {e}", flush=True)

    json.dump(state, open(state_path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"Fetched {done} new transcript(s) via Groq; state -> {state_path}",
          flush=True)


if __name__ == "__main__":
    main()
