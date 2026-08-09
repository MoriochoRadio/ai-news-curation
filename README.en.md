# The AI Brief

🇰🇷 [한국어](README.md) · 🇬🇧 English

> A newsletter-style curation that sums up the AI industry at a glance, every morning.

[🌐 Live site](https://MoriochoRadio.github.io/ai-news-curation/)

---

## One-Line Summary

From three free, keyless sources (HackerNews, ArXiv, GitHub), it automatically
collects the day's AI-related **trending stories / papers / open source** and
publishes them as a static newsletter. It runs free forever, with no API keys or credits.

## Key Features

- **Fully keyless**: no paid keys (Firecrawl, OpenAI, etc.) required at all.
- **3 sections**: Trending (HN) · Papers (ArXiv) · Open Source (GitHub)
- **Korean-friendly UX** (the site targets Korean readers):
  - Section names shown in Korean (트렌딩/논문/오픈소스 — Trending/Papers/Open Source)
  - 📌 **At-a-glance summary (TL;DR)**: per-issue counts, topics, and 3 top picks
  - 🔎 **In-issue search**: live highlighting across titles and descriptions
  - 🌙 **Dark mode**: toggle (preference stored locally)
  - 🌐 **Korean translation**: Google Translate widget (English original → Korean)
- **Static site**: HTML generated at build time → no browser-side parser bugs
- **Archive**: every issue kept by date

## View on the Web

- Main: https://MoriochoRadio.github.io/ai-news-curation/
- Archive: https://MoriochoRadio.github.io/ai-news-curation/archive.html
- Sample individual issue: `issues/2026-07-08.html`

## Configuration / Keywords

| Item | Details |
|------|------|
| Topics collected | AI agents, LLM reasoning, multimodal, open-source AI, Rust in AI tooling, AI safety |
| Sources | HackerNews Algolia API · ArXiv API · GitHub Search API |
| Outputs | `data/YYYY-MM-DD.json` → `index.html` / `archive.html` / `issues/*.html` |
| Deployment | GitHub Pages (automatic) |
| Execution | GitHub Actions (daily at 08:00 KST — Korea Standard Time) |

## Automation

- GitHub Actions runs daily at **08:00 KST** (23:00 UTC).
- The entire pipeline — collect → build (static HTML) → commit → GitHub Pages deploy — is automatic.
- Manual runs are also possible via `workflow_dispatch` (Actions tab → Run workflow).

## Why It's Built This Way — Technical Choices Q&A

**Q. Why a static site?**
A. The content updates once a day, so there's no reason to render on every request. Completing the HTML at build time means deployment needs nothing but GitHub Pages — no server, no DB — and with no reliance on browser-side JavaScript parsing and rendering, it doesn't break in any environment.

**Q. Why these three sources — HackerNews, ArXiv, GitHub?**
A. All three are public APIs callable without API keys or credits, and they complement each other with distinct perspectives: trending (community reaction), papers (research), and open source (real implementations). Credit-based sources like Firecrawl, used early on, were removed because running out of credits means the service stops.

**Q. Why is the collection script built mostly on the standard library?**
A. The only external dependency is `pyyaml`, and HTTP calls are made directly with `urllib`. Fewer dependencies mean faster installs on the GitHub Actions runner that fires daily, and less that can break years from now. Even without `pyyaml`, it falls back to built-in default settings and keeps working.

**Q. Why are LLM Korean summaries designed as "optional"?**
A. If `OPENROUTER_API_KEY` is present, a one-line summary is added using a free model; if it's absent or the call fails, the issue is published with the original text as-is. This prevents an external paid service from becoming a single point of failure that breaks the "free forever, no downtime" principle.

**Q. Why collect on a GitHub Actions schedule?**
A. It runs on a daily 08:00 KST cron with no separate server, and since results are committed to the repository, every issue's data history lives in git. If a collection run yields zero items, the run is deliberately failed, so a source outage surfaces via Actions notifications instead of passing silently.

**Q. Why save collection results as JSON first and build HTML separately?**
A. To separate collection (`curate.py`) from presentation (`build.py`). `data/*.json` serves as the archive of record, so even after a redesign, every past issue can be rebuilt with the new template.

## Running It Locally

```bash
# 1) Clone the repository
git clone https://github.com/MoriochoRadio/ai-news-curation.git
cd ai-news-curation

# 2) Collect (no key needed)
pip install pyyaml
python scripts/curate.py

# 3) Build the static site
python scripts/build.py

# 4) Check locally
python -m http.server 8000
# Open http://localhost:8000 in a browser
```

> 💡 If you set the `OPENROUTER_API_KEY` environment variable,
> a **one-line Korean summary** is automatically added to trending items (optional).
> The pipeline works fine without the key.

## Customizing the Configuration

You can change the collected topics and their Korean labels in `config.yaml`.

```yaml
topics:
  - "AI agents"
  - "LLM reasoning"
topic_labels:
  "AI agents": "AI 에이전트"
  "LLM reasoning": "LLM 추론"
```

## Contributing / Feedback

Suggestions for topics of interest, new keyless sources, and design/UX improvements
are welcome via issues or PRs.

---

*Automated collection · HackerNews · ArXiv · GitHub — published daily, no keys required*
