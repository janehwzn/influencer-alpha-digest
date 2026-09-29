#!/usr/bin/env python3
"""Fetch transcripts via Supadata API (fast, no YouTube download needed).

Reads the manifest written by fetch_videos.py, skips video IDs already in
state.json, and for each new video:
  1. GET https://api.supadata.ai/v1/transcript?url=...&text=false&lang=zh&mode=auto
     (mode=auto: native captions first, AI-generate fallback for no-caption videos)
  2. polls the job endpoint if the API returns 202 (async AI transcription),
  3. saves transcripts/<video_id>.txt (same format as transcribe.py) and
     updates state.json identically, so analyze.py works unchanged.

Usage: SUPADATA_API_KEY=... python3 scripts/supadata_transcribe.py \
         --manifest data/videos-2026-09-28.json [--limit 8]
"""
import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import urllib.error

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_BASE = "https://api.supadata.ai/v1"
POLL_INTERVAL = 15
POLL_TIMEOUT = 1500


def api_get(path, params, api_key, retries=5):
    qs = urllib.parse.urlencode(params)
    for attempt in range(retries):
        req = urllib.request.Request(
            f"{API_BASE}{path}?{qs}",
            headers={"x-api-key": api_key, "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.status, json.load(resp)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:500]
            if e.code == 429 and attempt < retries - 1:
                wait = 60 * (attempt + 1)
                print(f"  429 rate-limited, waiting {wait}s "
                      f"(attempt {attempt + 1}/{retries})...", flush=True)
                time.sleep(wait)
                continue
            return e.code, {"_error": body}
    return 429, {"_error": "retries exhausted"}


def fetch_transcript(url, api_key, lang="zh"):
    """Returns (chunks, lang_used) or raises."""
    status, data = api_get("/transcript",
                           {"url": url, "text": "false", "lang": lang,
                            "mode": "auto"}, api_key)
    if status == 202 and data.get("jobId"):
        job_id = data["jobId"]
        print(f"  async job {job_id}, polling...", flush=True)
        deadline = time.time() + POLL_TIMEOUT
        while time.time() < deadline:
            time.sleep(POLL_INTERVAL)
            s2, d2 = api_get(f"/transcript/{job_id}", {}, api_key)
            if s2 == 200 and d2.get("content"):
                return d2["content"], d2.get("lang", lang)
            if s2 not in (200, 202):
                raise RuntimeError(f"job poll failed: {s2} {str(d2)[:200]}")
        raise RuntimeError("transcript job timed out")
    if status == 200 and data.get("content"):
        return data["content"], data.get("lang", lang)
    raise RuntimeError(f"transcript request failed: {status} {str(data)[:300]}")


def chunks_to_lines(chunks):
    lines = []
    for c in chunks:
        off = int(c.get("offset", 0)) // 1000
        ts = f"[{off // 60:02d}:{off % 60:02d}]"
        text = (c.get("text") or "").strip()
        if text:
            lines.append(f"{ts} {text}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--limit", type=int, default=8,
                    help="max videos to transcribe per run")
    ap.add_argument("--lang", default="zh")
    args = ap.parse_args()

    api_key = os.environ.get("SUPADATA_API_KEY")
    if not api_key:
        sys.exit("SUPADATA_API_KEY env var is required")

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
            chunks, lang_used = fetch_transcript(item["url"], api_key, args.lang)
            text = chunks_to_lines(chunks)
            if not text.strip():
                print("  empty transcript, skipping", flush=True)
                continue
            header = (f"CHANNEL: {item['channel']}\nTITLE: {item['title']}\n"
                      f"URL: {item['url']}\nUPLOAD_DATE: {item['upload_date']}\n\n")
            open(txt, "w", encoding="utf-8").write(header + text)
            chars = len(text)
            print(f"  got {chars} chars (lang={lang_used}) -> {txt}", flush=True)
            state["processed"][vid] = {
                "title": item["title"], "channel": item["channel"],
                "url": item["url"], "upload_date": item["upload_date"],
                "transcript": f"transcripts/{vid}.txt",
                "chars": chars, "date": dt.date.today().isoformat(),
                "via": "supadata",
            }
            done += 1
            json.dump(state, open(state_path, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
        except Exception as e:
            print(f"  error: {e}", flush=True)

    json.dump(state, open(state_path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"Fetched {done} new transcript(s) via Supadata; state -> {state_path}",
          flush=True)


if __name__ == "__main__":
    main()
