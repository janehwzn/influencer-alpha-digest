#!/usr/bin/env python3
"""List videos published in the last N days for each influencer in influencers.yaml.

Uses yt-dlp flat-playlist on the channel /videos tab (YouTube's public RSS
endpoint is unreliable), then resolves each candidate's upload_date
individually. Writes a manifest JSON with the fresh videos.

Usage: python3 scripts/fetch_videos.py --days 7 --out data/videos-2026-09-28.json
"""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys

import yaml

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

YTDLP_BASE = [
    "yt-dlp", "--no-warnings", "--no-check-certificates",
    "--extractor-args", "youtube:player_client=android",
    "--retries", "10",
]


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=300)


def flat_list(handle, limit=12):
    """Return [(video_id, title)] newest-first from the channel /videos tab."""
    r = run(YTDLP_BASE + [
        "--flat-playlist", "--print", "%(id)s\t%(title)s",
        "--playlist-end", str(limit),
        f"https://www.youtube.com/{handle}/videos",
    ])
    if r.returncode != 0:
        print(f"  flat list failed for {handle}: {r.stderr[-300:]}", flush=True)
        return []
    out = []
    for line in r.stdout.splitlines():
        if "\t" not in line:
            continue
        vid, title = line.split("\t", 1)
        if vid and not vid.startswith("["):
            out.append((vid.strip(), title.strip()))
    return out


def video_meta(vid):
    """Resolve (upload_date YYYYMMDD, description) for one video; (None, "") on failure."""
    r = run(YTDLP_BASE + [
        "--skip-download", "--print", "%(upload_date)s",
        "--print", "%(description)s",
        f"https://www.youtube.com/watch?v={vid}",
    ])
    if r.returncode != 0:
        return None, ""
    out = r.stdout.strip().splitlines()
    date = out[0].strip() if out else ""
    desc = "\n".join(out[1:]).strip()[:2000]
    if len(date) != 8 or not date.isdigit():
        return None, desc
    return date, desc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--out", default=None)
    ap.add_argument("--max-per-channel", type=int, default=4)
    args = ap.parse_args()

    cutoff = (dt.date.today() - dt.timedelta(days=args.days)).strftime("%Y%m%d")
    influencers = yaml.safe_load(open(os.path.join(BASE, "influencers.yaml"),
                                     encoding="utf-8"))
    items = []
    for inf in influencers:
        print(f"== {inf['name']} ==", flush=True)
        fresh = []
        for vid, title in flat_list(inf["handle"]):
            d, desc = video_meta(vid)
            if d is None:
                print(f"  date unknown, skipping: {title[:60]}", flush=True)
                continue
            if d >= cutoff:
                fresh.append({"channel": inf["name"], "handle": inf["handle"],
                              "id": vid, "title": title,
                              "url": f"https://www.youtube.com/watch?v={vid}",
                              "upload_date": f"{d[:4]}-{d[4:6]}-{d[6:8]}",
                              "description": desc})
                if len(fresh) >= args.max_per_channel:
                    break
            else:
                break  # list is newest-first; older ones won't match
        print(f"  {len(fresh)} video(s) in last {args.days}d", flush=True)
        items.extend(fresh)

    manifest = {"date": args.date, "days": args.days, "items": items}
    out = args.out or os.path.join(BASE, "data", f"videos-{args.date}.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(manifest, open(out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"Wrote {out} with {len(items)} video(s)", flush=True)


if __name__ == "__main__":
    main()
