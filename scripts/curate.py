import os, json, datetime, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAILY_DIR = os.path.join(ROOT, "daily")

def load_key(path):
    with open(path, "r", encoding="utf-8") as f:
        for line in f.read().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and len(line) > 10:
                return line
    return ""

def env_key(*names):
    for name in names:
        v = os.environ.get(name, "").strip()
        if v:
            return v
    return ""

def post(url, headers, payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {e.code}: {body[:500]}")

def search_firecrawl(query, api_key):
    url = "https://api.firecrawl.dev/v2/search"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "query": query,
        "limit": 8,
        "sources": ["web", "news", "images"],
        "categories": [{"type": "github"}, {"type": "research"}],
        "timeout": 60000,
        "scrapeOptions": {
            "formats": [{"type": "markdown"}],
            "onlyMainContent": True,
            "removeBase64Images": True,
            "blockAds": True,
            "timeout": 60000,
        },
    }
    return post(url, headers, payload)

def summarize_openrouter(items, api_key):
    if not items:
        return ""

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    prompt_lines = [
        "You are a helpful AI news curator.",
        "Group these search results into 4 sections: Trending, Papers, Tools & Projects, Insights.",
        "Keep each item to 1-3 sentences. Preserve source URLs.",
        "",
    ]
    for idx, item in enumerate(items[:20], 1):
        title = item.get("title") or item.get("name") or "(untitled)"
        link = item.get("url") or item.get("link") or item.get("html_url") or ""
        prompt_lines.append(f"{idx}. {title}\n   {link}")

    prompt_lines.append("\nWrite in clean markdown.")
    messages = [
        {"role": "user", "content": "\n".join(prompt_lines)}
    ]
    payload = {
        "model": "mistralai/mistral-7b-instruct:free",
        "messages": messages,
        "max_completion_tokens": 4000,
    }
    result = post(url, headers, payload)
    return result.get("choices", [{}])[0].get("message", {}).get("content", "")

def build_daily_markdown(date_str, summary, raw_results):
    os.makedirs(DAILY_DIR, exist_ok=True)
    md_path = os.path.join(DAILY_DIR, f"{date_str}.md")
    header = f"# AI News Curation - {date_str}\n\n"
    header += f"- Generated at: {datetime.datetime.now().isoformat()}\n"
    header += f"- Sources: Firecrawl + OpenRouter (free tier)\n\n"

    body = summary.strip() or "_No summary generated._"
    if raw_results:
        body += "\n\n## Raw Results\n\n"
        for item in raw_results[:20]:
            title = item.get("title") or item.get("name") or "(untitled)"
            link = item.get("url") or item.get("link") or item.get("html_url") or ""
            if link:
                body += f"- [{title}]({link})\n"

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(header + body + "\n")
    return md_path

def update_readme(date_str):
    readme_path = os.path.join(ROOT, "README.md")
    entry = f"- [{date_str}](daily/{date_str}.md)\n"
    if os.path.exists(readme_path):
        text = open(readme_path, "r", encoding="utf-8").read()
    else:
        text = "# Daily AI News Curation\n\n## 최신 큐레이션\n"
    marker = "## 최신 큐레이션\n"
    if marker in text:
        prefix, rest = text.split(marker, 1)
        # keep only one latest line after marker
        lines = [ln for ln in rest.splitlines() if ln.strip()]
        keep = [entry]
        for ln in lines:
            if ln.strip() == keep[0].strip():
                continue
            keep.append(ln)
        new_text = prefix + marker + "\n".join(keep[:20]) + "\n"
    else:
        new_text = text + "\n## 최신 큐레이션\n\n" + entry
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(new_text)

def main():
    today = datetime.date.today().isoformat()
    firecrawl_key = env_key("FIRECRAWL_API_KEY")
    openrouter_key = env_key("OPENROUTER_API_KEY")

    if not firecrawl_key:
        raise RuntimeError("Missing FIRECRAWL_API_KEY")
    if not openrouter_key:
        raise RuntimeError("Missing OPENROUTER_API_KEY")

    queries = [
        "AI agents latest news",
        "LLM reasoning 2025",
        "open source LLM",
        "multimodal AI models",
        "AI safety news",
        "GitHub trending AI",
    ]

    collected = []
    for q in queries:
        print(f"[search] {q}")
        try:
            data = search_firecrawl(q, firecrawl_key)
        except Exception as e:
            print(f"[search error] {q}: {e}")
            continue
        results = data.get("data", {}).get("web") or data.get("data", []) or []
        collected.extend(results)

    # deduplicate by URL
    seen = set()
    unique = []
    for item in collected:
        link = item.get("url") or item.get("link") or item.get("html_url") or ""
        if not link or link in seen:
            continue
        seen.add(link)
        unique.append(item)

    print(f"[summarize] items={len(unique)}")
    summary = summarize_openrouter(unique, openrouter_key)
    md_path = build_daily_markdown(today, summary, unique)
    update_readme(today)
    print(f"[done] {md_path}")

if __name__ == "__main__":
    main()
