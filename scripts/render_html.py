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
body{font-family:-apple-system,'PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif;
background:#f6f8fa;color:#1f2328;margin:0;padding:24px}
.wrap{max-width:680px;margin:0 auto}
.hero{background:linear-gradient(135deg,#e6f4ea,#c8e6c9);border:1px solid #a3c9a8;
border-radius:12px;padding:28px 24px;margin-bottom:20px}
.hero h1{margin:0 0 8px;font-size:23px;color:#0d5c2e}
.hero p{margin:4px 0;color:#3d5a45;font-size:14.5px;line-height:1.6}
.sec{background:#ffffff;border:1px solid #d0d7de;border-radius:10px;
padding:18px 22px;margin-bottom:14px}
.sec h2{margin:0 0 12px;font-size:18px;color:#0d5c2e}
.sec h3{margin:20px 0 10px;font-size:16px;color:#0d5c2e;padding:7px 12px;
background:#eef6f0;border-left:4px solid #1f6f43;border-radius:0 6px 6px 0}
.sec ul{margin:0;padding-left:20px}
.sec li{margin:8px 0;font-size:15.5px;line-height:1.75;color:#1f2328}
.sec p{font-size:15.5px;line-height:1.75;color:#1f2328}
table{width:100%;border-collapse:collapse;font-size:14.5px;margin-top:6px;color:#1f2328}
th,td{border:1px solid #d0d7de;padding:8px 10px;text-align:left}
th{background:#e6f4ea;color:#0d5c2e}
a{color:#0969da;text-decoration:none}
.src{font-size:13.5px;color:#57606a;line-height:1.6}
.disc{background:#fff8e1;border:1px solid #e0b93c;border-radius:10px;
padding:14px 18px;font-size:13.5px;line-height:1.7;color:#5c4a00;margin-top:16px}
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
        elif line.startswith("### "):
            add_block("h3", line[4:].strip())
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
    if kind == "h3":
        return f"<h3>{inline(payload)}</h3>"
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
