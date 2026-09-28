#!/usr/bin/env python3
"""Render data/alpha-<date>.md as a styled Chinese HTML email.

Lightweight markdown subset: # title, ## sections, - bullets,
| tables |, [links](url), > quotes, ---, **bold**.
"""
import argparse
import html
import os
import re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CSS = """
body{font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;
background:#0d1117;color:#e6edf3;margin:0;padding:24px}
.wrap{max-width:680px;margin:0 auto}
.hero{background:linear-gradient(135deg,#0d3327,#123f2c);border:1px solid #1f6f43;
border-radius:12px;padding:28px 24px;margin-bottom:20px}
.hero h1{margin:0 0 8px;font-size:22px;color:#7ee2a8}
.hero p{margin:4px 0;color:#9fb3a8;font-size:14px}
.sec{background:#161b22;border:1px solid #30363d;border-radius:10px;
padding:18px 20px;margin-bottom:14px}
.sec h2{margin:0 0 12px;font-size:17px;color:#f0b429}
.sec ul{margin:0;padding-left:20px}
.sec li{margin:7px 0;font-size:14.5px;line-height:1.65}
table{width:100%;border-collapse:collapse;font-size:13.5px;margin-top:6px}
th,td{border:1px solid #30363d;padding:7px 9px;text-align:left}
th{background:#1c2b22;color:#7ee2a8}
a{color:#58a6ff;text-decoration:none}
.src{font-size:13px;color:#8b949e}
.disc{background:#1a1a1a;border:1px solid #444;border-radius:10px;
padding:14px 18px;font-size:12.5px;color:#8b949e;margin-top:16px}
.mode{display:inline-block;font-size:12px;background:#1f6f43;color:#fff;
border-radius:20px;padding:2px 10px;margin-left:8px}
"""

SECTION_TITLES = {
    "本周共识": "🎯 本周共识",
    "分歧点": "⚔️ 分歧点",
    "关键点位": "📍 关键点位",
    "Ticker 追踪": "🏷️ Ticker 追踪",
    "下周行动清单": "✅ 下周行动清单",
    "风险提示": "⚠️ 风险提示",
}


def inline(text):
    text = html.escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    return text


def parse(md):
    """-> (title, intro_lines, [(section_title, blocks)])"""
    title, intro, sections = None, [], []
    cur_title, cur_blocks = None, None

    def flush_section():
        nonlocal cur_title, cur_blocks
        if cur_title is not None:
            sections.append((cur_title, cur_blocks or []))
        cur_title, cur_blocks = None, None

    def add_block(kind, payload):
        nonlocal cur_blocks
        if cur_blocks is None:
            cur_blocks = []
        if cur_blocks and cur_blocks[-1][0] == kind and kind in ("ul", "table"):
            cur_blocks[-1][1].append(payload)
        else:
            cur_blocks.append((kind, [payload] if kind in ("ul", "table") else payload))

    for raw in md.splitlines():
        line = raw.strip()
        if not line or line == "---":
            continue
        if line.startswith("# "):
            title = line[2:].strip()
        elif line.startswith("## "):
            flush_section()
            t = line[3:].strip()
            cur_title = SECTION_TITLES.get(t, t)
            cur_blocks = []
        elif line.startswith("> "):
            q = line[2:].strip()
            if cur_title is None:
                intro.append(q)
            else:
                add_block("quote", q)
        elif line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells):
                continue
            add_block("table", cells)
        elif line.startswith("- "):
            add_block("ul", line[2:].strip())
        else:
            if cur_title is None:
                intro.append(line)
            else:
                add_block("p", line)
    flush_section()
    return title, intro, sections


def render_block(kind, payload):
    if kind == "ul":
        items = "".join(f"<li>{inline(i)}</li>" for i in payload)
        return f"<ul>{items}</ul>"
    if kind == "table":
        rows = []
        first = True
        for cells in payload:
            tag = "th" if first else "td"
            first = False
            rows.append("<tr>" + "".join(
                f"<{tag}>{inline(c)}</{tag}>" for c in cells) + "</tr>")
        return "<table>" + "".join(rows) + "</table>"
    if kind == "quote":
        return f'<p class="src">{inline(payload)}</p>'
    return f"<p>{inline(payload)}</p>"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    args = ap.parse_args()
    md = open(os.path.join(BASE, "data", f"alpha-{args.date}.md"),
              encoding="utf-8").read()
    title, intro, sections = parse(md)

    parts = [f'<div class="hero"><h1>{html.escape(title or "Influencer Alpha")}'
             f'<span class="mode">每周交易前瞻</span></h1>']
    parts += [f"<p>{inline(q)}</p>" for q in intro]
    parts.append("</div>")
    for stitle, blocks in sections:
        parts.append(f'<div class="sec"><h2>{html.escape(stitle)}</h2>')
        parts += [render_block(k, p) for k, p in blocks]
        parts.append("</div>")

    body = "".join(parts)
    page = (f"<!DOCTYPE html><html lang='zh'><head><meta charset='utf-8'>"
            f"<style>{CSS}</style></head><body><div class='wrap'>{body}"
            f"<div class='disc'>免责声明：本期内容由 AI 根据公开 YouTube 视频转录文本整理生成，"
            f"仅供学习交流，不构成任何投资建议。转录与模型提炼可能存在误差，"
            f"请以原视频为准，投资有风险，决策请独立判断。</div>"
            f"</div></body></html>")
    out = os.path.join(BASE, "data", f"alpha-{args.date}.html")
    open(out, "w", encoding="utf-8").write(page)
    print(f"Wrote {out}", flush=True)


if __name__ == "__main__":
    main()
