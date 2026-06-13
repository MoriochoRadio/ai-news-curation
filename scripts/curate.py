import os, json, datetime, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAILY_DIR = os.path.join(ROOT, "daily")

def load_key(path):
    if not os.path.exists(path):
        return ""
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

def post(url, headers, payload, timeout=120):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            try:
                return json.loads(resp.read().decode("utf-8"))
            except Exception:
                return {"_raw": resp.read().decode("utf-8", errors="ignore")}
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
        "sources": ["web", "news"],
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
        "Keep each item to 1-3 sentences. Preserve source URLs. Use markdown.",
        "",
    ]
    for idx, item in enumerate(items[:20], 1):
        title = item.get("title") or item.get("name") or "(untitled)"
        link = item.get("url") or item.get("link") or item.get("html_url") or ""
        prompt_lines.append(f"{idx}. {title}")
        prompt_lines.append(f"   {link}")

    prompt_lines.append("\nWrite in clean Korean markdown.")
    messages = [
        {"role": "user", "content": "\n".join(prompt_lines)}
    ]
    payload = {
        "model": "nvidia/nemotron-3-ultra-550b-a55b:free",
        "messages": messages,
        "max_completion_tokens": 4000,
    }
    result = post(url, headers, payload)
    return result.get("choices", [{}])[0].get("message", {}).get("content", "")

def build_daily_markdown(date_str, summary, raw_results, errors=None):
    os.makedirs(DAILY_DIR, exist_ok=True)
    md_path = os.path.join(DAILY_DIR, f"{date_str}.md")
    header = f"# AI News Curation - {date_str}\n\n"
    header += f"- Generated at: {datetime.datetime.now().isoformat()}\n"
    header += "- Sources: Firecrawl + OpenRouter (free tier)\n"

    if errors:
        header += "- Errors:\n"
        for e in errors:
            header += f"  - {e}\n"
    header += "\n"

    body = summary.strip() if summary else "_No summary generated._"
    if raw_results:
        body += "\n\n## Raw Results\n\n"
        for item in raw_results[:30]:
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
    if not os.path.exists(readme_path):
        text = "# Daily AI News Curation\n\n## 최신 큐레이션\n"
    else:
        text = open(readme_path, "r", encoding="utf-8").read()
    marker = "## 최신 큐레이션\n"
    if marker in text:
        prefix, rest = text.split(marker, 1)
        lines = [ln for ln in rest.splitlines() if ln.strip()]
        keep = [entry]
        for ln in lines:
            if ln.strip() == keep[0].strip():
                continue
            keep.append(ln)
        new_text = prefix + marker + "\n" + "\n".join(keep[:20]) + "\n"
    else:
        new_text = text.rstrip() + "\n\n## 최신 큐레이션\n\n" + entry
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(new_text)

def main():
    today = datetime.date.today().isoformat()
    firecrawl_key = env_key("FIRECRAWL_API_KEY")
    openrouter_key = env_key("OPENROUTER_API_KEY")

    errors = []
    if not firecrawl_key:
        errors.append("Missing FIRECRAWL_API_KEY")
    if not openrouter_key:
        errors.append("Missing OPENROUTER_API_KEY")

    queries = [
        "AI agents latest news",
        "LLM reasoning 2025",
        "open source LLM",
        "multimodal AI models",
        "AI safety news",
        "GitHub trending AI",
    ]

    collected = []
    if firecrawl_key:
        for q in queries:
            print(f"[search] {q}")
            try:
                data = search_firecrawl(q, firecrawl_key)
            except Exception as e:
                msg = f"{q}: {e}"
                print(f"[search error] {msg}")
                errors.append(msg)
                continue
            results = data.get("data", {}).get("web") or data.get("data", []) or []
            collected.extend(results)
    else:
        errors.append("Skipped Firecrawl search because FIRECRAWL_API_KEY is missing")

    # deduplicate by URL
    seen = set()
    unique = []
    for item in collected:
        link = item.get("url") or item.get("link") or item.get("html_url") or ""
        if not link or link in seen:
            continue
        seen.add(link)
        unique.append(item)

    summary = ""
    if openrouter_key and unique:
        print(f"[summarize] items={len(unique)}")
        try:
            summary = summarize_openrouter(unique, openrouter_key) or ""
        except Exception as e:
            msg = f"summarize failed: {e}"
            print(f"[summarize error] {msg}")
            errors.append(msg)
    else:
        if not unique:
            errors.append("No search results available to summarize")
        else:
            errors.append("Skipped OpenRouter summary because OPENROUTER_API_KEY is missing")

    md_path = build_daily_markdown(today, summary, unique, errors=errors)
    update_readme(today)
    print(f"[done] {md_path}")

if __name__ == "__main__":
    main()
