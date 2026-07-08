#!/usr/bin/env python3
"""기존 daily/2026-06-13.md 를 data/2026-06-13.json 구조로 마이그레이션."""
import os, json, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "daily", "2026-06-13.md")
OUT = os.path.join(ROOT, "data", "2026-06-13.json")

with open(SRC, "r", encoding="utf-8") as f:
    text = f.read()

def section_items(header):
    m = re.search(rf"## .*{header}.*?\n(.*?)(?=\n## |\Z)", text, re.S)
    if not m: return []
    block = m.group(1).strip()
    items = []
    for line in block.splitlines():
        line = line.strip()
        if not line or line == "---": continue
        # markdown link
        lm = re.match(r"- \[([^\]]+)\]\(([^)]+)\)(.*)", line)
        if lm:
            items.append({"title": lm.group(1), "url": lm.group(2), "source": "GitHub", "desc": lm.group(3).strip(), "stars": 0, "language": ""})
            continue
        # numbered "1. **title**" + following "- desc" / "- url"
        nm = re.match(r"\d+\.\s+\*\*(.+?)\*\*", line)
        if nm:
            items.append({"title": nm.group(1), "url": "", "source": "HackerNews", "desc": "", "points": 0, "comments": 0, "author": ""})
    return items

papers = section_items("Papers")
tools = section_items("Tools")
trending = section_items("Trending")

# url 채우기: 뒤따르는 "- https://..." 줄에서
lines = [l.strip() for l in text.splitlines() if l.strip() and l.strip() != "---"]
for sec in (trending, papers, tools):
    for it in sec:
        if it.get("url"): continue
        # find url in subsequent lines within same section block — naive: search whole text
        pass

# better: extract urls right after each numbered entry
def extract_with_urls(header):
    m = re.search(rf"## .*{header}.*?\n(.*?)(?=\n## |\Z)", text, re.S)
    if not m: return []
    block = m.group(1)
    out = []
    cur = None
    for line in block.splitlines():
        line = line.strip()
        if not line or line == "---": continue
        nm = re.match(r"\d+\.\s+\*\*(.+?)\*\*", line)
        if nm:
            if cur: out.append(cur)
            cur = {"title": nm.group(1), "url": "", "source": "HackerNews", "desc": "", "points": 0, "comments": 0, "author": ""}
            continue
        if cur is None: continue
        um = re.match(r"- (https?://\S+)", line)
        if um:
            cur["url"] = um.group(1)
        else:
            dm = re.match(r"- (.+)", line)
            if dm and not cur["desc"]:
                cur["desc"] = dm.group(1)
    if cur: out.append(cur)
    return out

trending = extract_with_urls("Trending")
papers = extract_with_urls("Papers")

payload = {
    "date": "2026-06-13",
    "generated_at": "2026-06-13T03:59:08",
    "topics": ["AI agents", "LLM reasoning", "multimodal models", "open source AI", "AI safety"],
    "counts": {"trending": len(trending), "papers": len(papers), "tools": len(tools)},
    "trending": trending,
    "papers": papers,
    "tools": tools,
}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, indent=2)
print(f"[migrate] {OUT} (trending={len(trending)}, papers={len(papers)}, tools={len(tools)})")
