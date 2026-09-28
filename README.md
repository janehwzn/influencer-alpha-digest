# 📈 influencer-alpha-digest

Trade with the influencer：每周自动追踪我关注的美股 YouTube 博主，
把他们过去一周的视频整理成一份中文**每周交易 Alpha**（当前为标题+简介的 roundup 模式），
在每周日晚发到邮箱。不用再把每个视频完整看完。

## 追踪的 Influencer

| 博主 | YouTube | 更新节奏 | 主要内容 |
|---|---|---|---|
| 猫姐美股交易 | https://www.youtube.com/@catstocktrading | 每周一更（周末美股周复盘） | 大盘复盘、指数关键点位、头部个股与板块轮动 |
| 藤缠树 | https://www.youtube.com/@bigtreesignal | 约每周一更（偶尔跳过） | 周末市场复盘、技术面信号、交易节奏 |
| Allen 的正念交易 | https://www.youtube.com/@Allen的正念交易 | 不定期（约每月 1–2 更） | 美股交易心态与市场观点评论 |

完整信息（含 channel id）在 [`influencers.yaml`](influencers.yaml)。想加新人？直接往这个文件里加一行即可。

## 每周 Alpha 包含

- 🎯 本周共识 — 几位博主都认同的市场方向与节奏判断
- ⚔️ 分歧点 — 博主之间观点不一致的地方
- 📍 关键点位 — 视频里明确提到的指数/个股支撑压力位
- 🏷️ Ticker 追踪 — 被提到的标的、观点倾向、来源
- ✅ 下周行动清单 — 可执行的观察/操作提示
- ⚠️ 风险提示

历史 Alpha 都在 [`data/`](data/) 目录（`alpha-YYYY-MM-DD.md`）。

## 工作原理

```
每周一 03:30 UTC（= 周日 20:30 PDT）GitHub Actions 自动运行：
 1. scripts/fetch_videos.py   列出过去 7 天各博主的新视频
 2. scripts/transcribe.py     下载音频 → faster-whisper 转录成中文文本（注：YouTube 会拦截 GitHub 服务器的媒体下载，
                             workflow 默认加 --skip-transcribe，走标题+简介的 roundup 模式；转录代码保留，
                             以后若下载恢复可用可去掉该 flag）
    （这些频道普遍没有字幕，所以走 ASR；已处理过的视频会跳过）
 3. scripts/analyze.py        Claude（ANTHROPIC_API_KEY）综合成 Alpha；
                              没有 key 时降级为启发式摘录（ticker 统计+关键词句）
 4. scripts/render_html.py    渲染成深色财经风 HTML 邮件
 5. scripts/send_email.py     经 Gmail 发到收件人
```

手动触发：在 Actions 页面用 `workflow_dispatch`，可指定回看天数。

## 需要的 Secrets

| Secret | 必填 | 说明 |
|---|---|---|
| `GMAIL_USER` | 是 | 发件 Gmail 地址 |
| `GMAIL_APP_PASSWORD` | 是 | Gmail 应用专用密码 |
| `RECIPIENT` | 否 | 收件人（逗号分隔，默认发给 `GMAIL_USER`） |
| `ANTHROPIC_API_KEY` | 否 | 强烈推荐；没有它 Alpha 会降级为启发式版本 |

## 免责声明

本项目所有内容由 AI 根据公开 YouTube 视频（标题/简介；转录可用时为转录文本）整理生成，仅供学习交流，
**不构成任何投资建议**。转录与模型提炼可能存在误差，请以原视频为准。
投资有风险，决策请独立判断。
