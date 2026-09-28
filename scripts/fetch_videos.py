#!/usr/bin/env python3
"""List videos published in the last N days for each influencer in influencers.yaml.

Primary: yt-dlp flat-playlist on the channel /videos tab, then per-video
upload_date resolution.
Fallback: scrape the /videos tab HTML for relative ages ("3 days ago"),
used when upload_date can't be resolved (e.g. datacenter IP bot checks).

Writes a manifest JSON with the fresh videos (id, title, url, upload_date,
description).

Usage: python3 scripts/fetch_videos.py --days 7 --out data/videos-2026-09-28.json
"""
import argparse
import datetime as dt
import json
import os
import re
import subprocess
import urllib.parse
import urllib.request

import yaml

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

YTDLP_BASE = [
    "yt-dlp", "--no-warnings", "--no-check-certificates",
    "--extractor-args", "youtube:player_client=android",
    "--retries", "10",
]

REL_PATTERNS = [
    (r"(\d+)\s*(?:秒|second)s?\s*前|(\d+)\s*seconds?\s*ago", "seconds"),
    (r"(\d+)\s*(?:分|minute)s?\s*前|(\d+)\s*minutes?\s*ago", "minutes"),
    (r"(\d+)\s*(?:小?时|hour)s?\s*前|(\d+)\s*hours?\s*ago", "hours"),
    (r"(\d+)\s*天前|(\d+)\s*days?\s*ago|(\d+)d ago", "days"),
    (r"(\d+)\s*周前|(\d+)\s*weeks?\s*ago|(\d+)w ago", "weeks"),
    (r"(\d+)\s*月前|(\d+)\s*months?\s*ago|(\d+)mo ago", "months"),
    (r"(\d+)\s*年前|(\d+)\s*years?\s*ago", "years"),
]


def rel_to_days(text):
    t = text or ""
    for pat, unit in REL_PATTERNS:
        m = re.search(pat, t)
        if m:
            n = int(next(g for g in m.groups() if g is not None))
            mult = {"seconds": 1 / 86400, "minutes": 1 / 1440, "hours": 1 / 24,
                    "days": 1, "weeks": 7, "months": 30, "years": 365}[unit]
            return n * mult
    return None


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=300)


def flat_list(handle, limit=12):
    """[(video_id, title)] newest-first from the channel /videos tab."""
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


def tab_relative_ages(handle, limit=12):
    """{video_id: age_days} from the /videos tab HTML (fallback source)."""
    try:
        req = urllib.request.Request(
            "https://www.youtube.com/"
            + urllib.parse.quote(f"{handle}/videos"),
            headers={"User-Agent": UA})
        html = urllib.request.urlopen(req, timeout=30).read().decode(
            "utf-8", "ignore")
    except Exception as e:
        print(f"  tab scrape failed for {handle}: {e}", flush=True)
        return {}
    m = re.search(r"var ytInitialData = (\{.*?\});</script>", html, re.S)
    if not m:
        return {}
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return {}

    def _text(node):
        if isinstance(node, dict):
            if "content" in node and isinstance(node["content"], str):
                return node["content"]
            return "".join(_text(x.get("text", ""))
                           for x in node.get("runs", []))
        return str(node or "")

    out = {}

    def walk(o):
        if isinstance(o, dict):
            lm = o.get("lockupViewModel")
            if isinstance(lm, dict) and \
                    lm.get("contentType") == "LOCKUP_CONTENT_TYPE_VIDEO":
                vid = lm.get("contentId")
                try:
                    md = lm["metadata"]["lockupMetadataViewModel"]
                    parts = []
                    for row in md.get("metadata", {}).get(
                            "contentMetadataViewModel", {}).get(
                            "metadataRows", []):
                        for p in row.get("metadataParts", []):
                            t = _text(p.get("text"))
                            if t:
                                parts.append(t)
                    age = rel_to_days(" ".join(parts))
                    if vid and age is not None and vid not in out:
                        out[vid] = age
                except (KeyError, TypeError):
                    pass
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(data)
    return out


def video_meta(vid, debug=False):
    """(upload_date YYYYMMDD or None, description)."""
    r = run(YTDLP_BASE + [
        "--skip-download", "--print", "%(upload_date)s",
        "--print", "%(description)s",
        f"https://www.youtube.com/watch?v={vid}",
    ])
    if r.returncode != 0:
        if debug:
            print(f"  meta failed for {vid}: {r.stderr[-200:]}", flush=True)
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

    today = dt.date.today()
    cutoff = (today - dt.timedelta(days=args.days)).strftime("%Y%m%d")
    influencers = yaml.safe_load(open(os.path.join(BASE, "influencers.yaml"),
                                     encoding="utf-8"))
    items = []
    for inf in influencers:
        print(f"== {inf['name']} ==", flush=True)
        listed = flat_list(inf["handle"])
        rel_ages = {}
        if listed:
            # pre-fetch fallback ages once per channel (cheap, one request)
            rel_ages = tab_relative_ages(inf["handle"])
        fresh = []
        for vid, title in listed:
            d, desc = video_meta(vid)
            src = "upload_date"
            if d is None and vid in rel_ages and rel_ages[vid] <= args.days:
                # fallback: relative age within window; approximate date
                approx = today - dt.timedelta(days=int(rel_ages[vid]))
                d = approx.strftime("%Y%m%d")
                src = "relative_age"
                print(f"  (fallback date ~{d} from relative age)",
                      flush=True)
            if d is None:
                print(f"  date unknown, skipping: {title[:60]}", flush=True)
                continue
            if d >= cutoff:
                fresh.append({
                    "channel": inf["name"], "handle": inf["handle"],
                    "id": vid, "title": title,
                    "url": f"https://www.youtube.com/watch?v={vid}",
                    "upload_date": f"{d[:4]}-{d[4:6]}-{d[6:8]}",
                    "description": desc,
                    "date_source": src,
                })
                if len(fresh) >= args.max_per_channel:
                    break
            else:
                break  # newest-first; older ones won't match
        # mark which dates came from the fallback
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
