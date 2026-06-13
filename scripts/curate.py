import os, datetime

today = datetime.date.today().isoformat()
out_path = os.path.join(os.path.dirname(__file__), "..", "daily", f"{today}.md")

os.makedirs(os.path.dirname(out_path), exist_ok=True)

with open(out_path, "w", encoding="utf-8") as f:
    f.write(
        f"# AI News Curation - {today}\n\n"
        f"- Generated at: {datetime.datetime.now().isoformat()}\n"
        f"- Status: placeholder\n\n"
        "## Trending\n"
        "- TODO: add curated links\n\n"
        "## Papers\n"
        "- TODO: add arxiv highlights\n\n"
        "## Tools & Projects\n"
        "- TODO: add repos and tools\n\n"
        "## Notes\n"
        "- TODO: add insights\n"
    )

print(f"Wrote {out_path}")
