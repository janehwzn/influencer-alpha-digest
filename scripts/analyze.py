#!/usr/bin/env python3
"""Generate the weekly trading alpha from video transcripts.

If ANTHROPIC_API_KEY is set, Claude writes a structured Chinese alpha.
Otherwise a heuristic fallback extracts tickers and key sentences so the
weekly email still ships with useful content.

Reads:  data/state.json (processed videos + transcript paths)
Writes: data/alpha-<date>.md

Usage: python3 scripts/analyze.py --date 2026-09-28
"""
import argparse
import datetime as dt
import json
import os
import re
from collections import Counter

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DISCLAIMER = (
    chr(10) + "---" + chr(10)
    + "> 免责声明：本期内容由 AI 根据公开 YouTube 视频转录文本整理生成，"
    + "仅供学习交流，不构成任何投资建议。转录与模型提炼可能存在误差，"
    + "请以原视频为准，投资有风险，决策请独立判断。" + chr(10)
)

SYSTEM_PROMPT = (
    "你是资深美股交易分析师，擅长把中文财经视频内容提炼成可执行的交易前瞻。"
    "输入是几位美股博主过去一周视频的转录文本（ASR 转录，可能有错别字）。"
    "请输出一份中文每周交易 Alpha，严格使用以下六个二级标题（emoji 和文字都要完全一致），"
    "每个标题下用简洁的 bullet points（- 开头），数字、点位、标的代码务必具体："
    + chr(10) + chr(10)
    + "## 本周共识" + chr(10)
    + "## 分歧点" + chr(10)
    + "## 关键点位" + chr(10)
    + "## Ticker 追踪" + chr(10)
    + "## 下周行动清单" + chr(10)
    + "## 风险提示" + chr(10) + chr(10)
    + "要求：综合多位博主都认同的市场方向为共识；观点不一致处列入分歧点；"
    + "关键点位只写视频里明确提到的数字；Ticker 追踪用表格列出 ticker、观点倾向（看多/看空/中性/仅提及）、来源博主；"
    + "下周行动清单 3-6 条可执行提示，不要编造视频没提过的点位；风险提示 2-4 条。"
    + "全文简洁，1200 字以内。不要输出六个标题之外的内容。"
)

STOPWORDS = set(
    "THE AND FOR ARE BUT NOT YOU ALL CAN HAD HER WAS ONE OUR OUT DAY HAS HAVE "
    "MORE WITH FROM THIS THAT THEY WHAT WHEN WHERE WHICH THEIR THERE THESE "
    "THOSE THEN THAN INTO OVER SUCH ONLY WILL JUST NOW TODAY WEEK VIDEO MARKET "
    "STOCK BULL BEAR ETF FED CPI GDP USA LONG SHORT BUY SELL HOLD CALL PUT "
    "LIVE QQQ SPY DIA IWM TLT GLD USO BTC ETH AI CEO IPO NEW TOP HOT".split()
)

TICKER_RE = re.compile(r"\b[A-Z]{1,5}\b")
KEYWORDS = ["指数", "加息", "降息", "突破", "跌破", "支撑", "压力", "阻力",
            "买入", "卖出", "加仓", "减仓", "止损", "反弹", "回调", "新高",
            "新低", "风险", "机会", "财报", "利率", "通胀", "衰退", "牛市",
            "熊市", "震荡", "放量", "缩量", "均线", "缺口", "趋势"]


def load_videos(state):
    """Videos with transcripts available: text + metadata."""
    vids = []
    for vid, info in state.get("processed", {}).items():
        tpath = os.path.join(BASE, info.get("transcript", ""))
        if not os.path.exists(tpath):
            continue
        text = open(tpath, encoding="utf-8").read()
        body = chr(10).join(text.splitlines()[4:])  # skip 4-line header
        vids.append({"id": vid, "channel": info["channel"],
                     "title": info["title"], "url": info["url"],
                     "upload_date": info.get("upload_date", ""),
                     "text": body})
    return vids


def call_claude(videos):
    import anthropic
    model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")
    client = anthropic.Anthropic()
    parts = []
    for v in videos:
        t = v["text"][:15000]
        parts.append(
            "【" + v["channel"] + "｜" + v["upload_date"] + "｜"
            + v["title"] + "｜" + v["url"] + "】" + chr(10) + t)
    user_msg = ("以下是过去一周美股博主视频的转录文本，请生成本周交易 Alpha："
                + chr(10) + chr(10) + (chr(10) + chr(10)).join(parts))
    resp = client.messages.create(
        model=model, max_tokens=3000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}])
    return resp.content[0].text


def key_sentences(text, limit=5):
    sents = re.split(r"[。！？\n]+", text)
    scored = []
    for s in sents:
        s = s.strip()
        if len(s) < 15 or len(s) > 120:
            continue
        score = sum(1 for k in KEYWORDS if k in s)
        if score:
            scored.append((score, s))
    scored.sort(key=lambda x: -x[0])
    return [s for _, s in scored[:limit]]


def heuristic_alpha(videos):
    """Fallback when no ANTHROPIC_API_KEY: tickers + key sentences."""
    lines = [
        "## 本周共识",
        "- （启发式版本：未配置 ANTHROPIC_API_KEY，以下为各视频关键词句摘录。）",
        "",
        "## 分歧点",
        "- （启发式版本暂不做跨博主分歧判断。）",
        "",
        "## 关键点位",
        "- （启发式版本：请查看关键词句中的数字。）",
        "",
        "## Ticker 追踪",
        "| Ticker | 提及次数 | 来源 |",
        "|---|---|---|",
    ]
    tickers = Counter()
    ticker_src = {}
    for v in videos:
        for m in TICKER_RE.findall(v["text"]):
            if m not in STOPWORDS and not m.isdigit():
                tickers[m] += 1
                ticker_src.setdefault(m, set()).add(v["channel"])
    for t, c in tickers.most_common(25):
        lines.append("| " + t + " | " + str(c) + " | "
                     + "、".join(sorted(ticker_src[t])) + " |")
    lines += ["", "## 下周行动清单"]
    for v in videos:
        lines.append("- **" + v["channel"] + "**《" + v["title"][:40] + "》：")
        for s in key_sentences(v["text"]):
            lines.append("  - " + s)
        lines.append("  - 原视频：" + v["url"])
    lines += ["", "## 风险提示",
              "- 启发式摘录未经 LLM 综合校验，可能断章取义，请以原视频为准。",
              "- ASR 转录可能存在错别字，数字与代码请回看原视频确认。"]
    return chr(10).join(lines)


def description_alpha(items):
    """Last-resort alpha when no transcripts could be fetched: use titles +
    descriptions so the weekly email still ships a useful roundup."""
    lines = [
        "## 本周共识",
        "- （本期未能获取视频转录文本，以下基于视频标题与简介整理。）",
        "",
        "## 分歧点",
        "- （暂无转录文本，无法判断分歧。）",
        "",
        "## 关键点位",
        "- （暂无转录文本，请观看原视频获取具体点位。）",
        "",
        "## Ticker 追踪",
        "| Ticker | 来源 |",
        "|---|---|",
    ]
    tickers = Counter()
    ticker_src = {}
    for it in items:
        blob = it["title"] + "\n" + it.get("description", "")
        for m in TICKER_RE.findall(blob):
            if m not in STOPWORDS and not m.isdigit():
                tickers[m] += 1
                ticker_src.setdefault(m, set()).add(it["channel"])
    for t, c in tickers.most_common(20):
        lines.append("| " + t + " | " + "、".join(sorted(ticker_src[t])) + " |")
    lines += ["", "## 下周行动清单"]
    for it in items:
        lines.append("- **" + it["channel"] + "**《" + it["title"] + "》"
                     + "（" + it["upload_date"] + "）")
        desc = it.get("description", "").strip()
        if desc:
            first = desc.split(chr(10))[0][:200]
            lines.append("  - 简介：" + first)
        for s in key_sentences(desc, limit=3):
            lines.append("  - " + s)
        lines.append("  - 原视频：" + it["url"])
    lines += ["", "## 风险提示",
              "- 本期 Alpha 仅基于标题与简介，未经转录文本校验，信息有限。",
              "- 具体点位与操作建议请以原视频为准。"]
    return chr(10).join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--week-start", default=None,
                    help="week start date for the title, defaults to date-6d")
    args = ap.parse_args()

    state_path = os.path.join(BASE, "data", "state.json")
    state = json.load(open(state_path, encoding="utf-8")) \
        if os.path.exists(state_path) else {}
    videos = load_videos(state)

    manifest_path = os.path.join(BASE, "data", "videos-" + args.date + ".json")
    manifest_items = []
    if os.path.exists(manifest_path):
        manifest_items = json.load(
            open(manifest_path, encoding="utf-8")).get("items", [])

    if videos:
        source_label = str(len(videos)) + " 个视频的转录文本"
        byline_items = [
            {"channel": v["channel"], "title": v["title"], "url": v["url"],
             "upload_date": v["upload_date"]} for v in videos]
    elif manifest_items:
        print("No transcripts; falling back to titles+descriptions.",
              flush=True)
        body = description_alpha(manifest_items)
        mode = "roundup"
        source_label = None
        byline_items = manifest_items
    else:
        print("No transcripts and no videos; writing empty alpha.",
              flush=True)
        body = ("## 本周共识" + chr(10) + "- 本期三位博主均无新视频。"
                + chr(10) + chr(10) + "## 分歧点" + chr(10) + "- 无。"
                + chr(10) + chr(10) + "## 关键点位" + chr(10) + "- 无。"
                + chr(10) + chr(10) + "## Ticker 追踪" + chr(10) + "- 无。"
                + chr(10) + chr(10) + "## 下周行动清单" + chr(10)
                + "- 本期无更新。" + chr(10) + chr(10) + "## 风险提示"
                + chr(10) + "- 无。")
        mode = "empty"
        source_label = None
        byline_items = []

    if source_label is not None:
        if os.environ.get("ANTHROPIC_API_KEY"):
            print("Calling Claude for alpha synthesis...", flush=True)
            try:
                body = call_claude(videos)
                mode = "claude"
            except Exception as e:
                print("Claude call failed (" + str(e)
                      + "); using heuristic fallback.", flush=True)
                body = heuristic_alpha(videos)
                mode = "heuristic"
        else:
            print("No ANTHROPIC_API_KEY; using heuristic fallback.", flush=True)
            body = heuristic_alpha(videos)
            mode = "heuristic"

    week_start = args.week_start or (
        dt.date.fromisoformat(args.date) - dt.timedelta(days=6)).isoformat()

    header = ("# Influencer Alpha｜" + week_start + " ~ " + args.date + chr(10)
              + chr(10))
    if source_label:
        header += ("> 基于 " + source_label + "（" + mode + " 模式）"
                   + chr(10) + chr(10))
    else:
        header += ("> 本期为简版（" + mode + " 模式）" + chr(10) + chr(10))
    for v in byline_items:
        header += ("- **" + v["channel"] + "**：[" + v["title"] + "]("
                   + v["url"] + ")（" + v["upload_date"] + "）" + chr(10))
    header += chr(10)
    out = os.path.join(BASE, "data", "alpha-" + args.date + ".md")
    open(out, "w", encoding="utf-8").write(header + body + DISCLAIMER)
    print("Wrote " + out, flush=True)


if __name__ == "__main__":
    main()
