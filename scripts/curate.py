#!/usr/bin/env python3
"""
AI News Curation — collector

키 없이 동작하는 무료 소스 3종에서 AI 관련 콘텐츠를 수집한다.
  - HackerNews Algolia API  (뉴스/토론)
  - ArXiv API               (논문)
  - GitHub Search API       (오픈소스 프로젝트)

수집 결과는 data/YYYY-MM-DD.json 으로 구조화해 저장한다.
선택적으로 OPENROUTER_API_KEY 가 있으면 한국어 요약을 덧붙인다
(키가 없으면 원문 제목/설명을 그대로 사용한다 — 파이프라인은 항상 동작).

Firecrawl 등 유료/크레딧 소스는 더 이상 사용하지 않는다.
"""
import os
import json
import datetime
import urllib.request
import urllib.error
import urllib.parse
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
CONFIG_PATH = os.path.join(ROOT, "config.yaml")

UA = {"User-Agent": "ai-news-curation/2.0 (+https://github.com/MoriochoRadio/ai-news-curation)"}


def log(msg):
    print(f"[curate] {msg}", flush=True)


# --------------------------------------------------------------------------
# config
# --------------------------------------------------------------------------
def load_config():
    """config.yaml 에서 topics/sources 를 읽는다 (yaml 미설치 시 폴백 내장)."""
    defaults = {
        "topics": ["AI agents", "LLM reasoning", "open source AI", "multimodal models", "AI safety"],
        "sources": ["hackernews", "arxiv", "github"],
        "max_per_section": 8,
    }
    try:
        import yaml
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        defaults.update({k: cfg[k] for k in defaults if k in cfg})
    except Exception as e:
        log(f"config.yaml 미사용(폴백): {e}")
    return defaults


# --------------------------------------------------------------------------
# http helpers
# --------------------------------------------------------------------------
def http_get(url, timeout=30, headers=None):
    req = urllib.request.Request(url, headers=headers or UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="ignore")[:300]
    except Exception as e:
        return 0, str(e)[:200]


def http_post_json(url, api_key, payload, timeout=120):
    data = json.dumps(payload).encode("utf-8")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        return {"_error": str(e)[:300]}


# --------------------------------------------------------------------------
# source collectors
# --------------------------------------------------------------------------
def collect_hackernews(topics, limit):
    items = []
    seen = set()
    for topic in topics[:3]:
        q = urllib.parse.quote(topic)
        url = f"https://hn.algolia.com/api/v1/search_by_date?query={q}&tags=story&hitsPerPage={limit}"
        status, body = http_get(url, timeout=30)
        if status != 200:
            log(f"HN 실패({topic}): {status}")
            continue
        try:
            hits = json.loads(body).get("hits", [])
        except Exception:
            continue
        for h in hits:
            title = (h.get("title") or "").strip()
            if not title:
                continue
            link = h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}"
            key = link
            if key in seen:
                continue
            seen.add(key)
            items.append({
                "title": title,
                "url": link,
                "source": "HackerNews",
                "points": h.get("points") or 0,
                "comments": h.get("num_comments") or 0,
                "author": h.get("author") or "",
                "date": h.get("created_at", "")[:10],
                "desc": "",
            })
        time.sleep(0.5)
    return items[:limit]


def collect_arxiv(topics, limit):
    items = []
    seen = set()
    for topic in topics[:3]:
        q = urllib.parse.quote(f"all:{topic.replace(' ', '+')}")
        url = f"http://export.arxiv.org/api/query?search_query={q}&sortBy=submittedDate&sortOrder=descending&max_results={limit}"
        status, body = http_get(url, timeout=30)
        if status != 200:
            log(f"ArXiv 실패({topic}): {status}")
            continue
        entries = body.split("<entry>")[1:]
        for e in entries:
            def tag(name):
                start = e.find(f"<{name}>")
                end = e.find(f"</{name}>")
                if start == -1 or end == -1:
                    return ""
                return e[start + len(f"<{name}>"):end].strip()
            title = " ".join(tag("title").split())
            link = ""
            for part in e.split("<link")[1:]:
                if 'title="pdf"' in part:
                    link = part.split('href="', 1)[1].split('"', 1)[0]
                    break
            if not link:
                link = tag("id")
            if not title or link in seen:
                continue
            seen.add(link)
            items.append({
                "title": title,
                "url": link,
                "source": "ArXiv",
                "authors": ", ".join([a.split("<name>")[1].split("</name>")[0] for a in e.split("<author>")[1:] if "<name>" in a][:3]),
                "date": tag("published")[:10],
                "desc": " ".join(tag("summary").split())[:280],
            })
        time.sleep(0.5)
    return items[:limit]


def collect_github(topics, limit):
    items = []
    seen = set()
    for topic in topics[:3]:
        q = urllib.parse.quote(topic)
        url = f"https://api.github.com/search/repositories?q={q}&sort=stars&order=desc&per_page={limit}"
        status, body = http_get(url, timeout=30, headers={**UA, "Accept": "application/vnd.github+json"})
        if status != 200:
            log(f"GitHub 실패({topic}): {status}")
            continue
        try:
            repos = json.loads(body).get("items", [])
        except Exception:
            continue
        for r in repos:
            name = r.get("full_name", "")
            if name in seen:
                continue
            seen.add(name)
            items.append({
                "title": name,
                "url": r.get("html_url", ""),
                "source": "GitHub",
                "stars": r.get("stargazers_count") or 0,
                "language": r.get("language") or "",
                "desc": (r.get("description") or "").strip(),
            })
        time.sleep(1.0)
    return items[:limit]


# --------------------------------------------------------------------------
# optional summarizer (Korean) — keyless safe
# --------------------------------------------------------------------------
def summarize(text, api_key):
    if not api_key:
        return ""
    url = "https://openrouter.ai/api/v1/chat/completions"
    payload = {
        "model": os.environ.get("SUMMARY_MODEL", "nousresearch/hermes-3-llama-3.1-405b:free"),
        "messages": [
            {"role": "system", "content": "You are a concise tech editor. Summarize the given AI news item in one natural Korean sentence. No markdown, no preamble."},
            {"role": "user", "content": text[:600]},
        ],
        "max_completion_tokens": 120,
    }
    for attempt in range(2):
        res = http_post_json(url, api_key, payload, timeout=60)
        if "_error" not in res and res.get("choices"):
            return res["choices"][0]["message"]["content"].strip().strip('*"')
        time.sleep(3)
    return ""


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def main():
    today = datetime.date.today().isoformat()
    cfg = load_config()
    topics = cfg["topics"]
    max_n = cfg.get("max_per_section", 8)

    log(f"수집 시작 — topics={topics}")

    trending = collect_hackernews(topics, max_n)
    papers = collect_arxiv(topics, max_n)
    tools = collect_github(topics, max_n)

    or_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if or_key and trending:
        log("한국어 요약 생성 중(옵션)...")
        for it in trending[:5]:
            s = summarize(f"{it['title']}. {it['desc']}", or_key)
            if s:
                it["summary_ko"] = s
            time.sleep(1)

    payload = {
        "date": today,
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "topics": topics,
        "counts": {"trending": len(trending), "papers": len(papers), "tools": len(tools)},
        "trending": trending,
        "papers": papers,
        "tools": tools,
    }

    os.makedirs(DATA_DIR, exist_ok=True)
    out_path = os.path.join(DATA_DIR, f"{today}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    if len(trending) + len(papers) + len(tools) == 0:
        log("수집 결과 0건 — 런을 실패 처리합니다 (원인은 위 Errors 참조)")
        raise SystemExit(1)

    log(f"저장 완료: {out_path} (trending={len(trending)}, papers={len(papers)}, tools={len(tools)})")
    return out_path


if __name__ == "__main__":
    main()
