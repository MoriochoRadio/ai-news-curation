#!/usr/bin/env python3
"""
AI News Curation — static site builder

data/YYYY-MM-DD.json 파일들을 읽어 정적 HTML을 생성한다.
  - index.html        : 최신 호 + 최근 아카이브 목록
  - archive.html      : 전체 호 목록
  - issues/YYYY-MM-DD.html : 각 호 개별 페이지

디자인은 뉴스레터/매거진 풍. 자바스크립트 파서 의존성을 완전히 제거한다.
"""
import os
import json
import html
import datetime
import glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
ISSUES_DIR = os.path.join(ROOT, "issues")
SITE_TITLE = "The AI Brief"
SITE_TAGLINE = "매일 아침, AI 업계의 흐름을 한눈에"


def load_all_data():
    files = sorted(glob.glob(os.path.join(DATA_DIR, "*.json")), reverse=True)
    issues = []
    for fp in files:
        try:
            with open(fp, "r", encoding="utf-8") as f:
                issues.append(json.load(f))
        except Exception as e:
            print(f"[build] skip {fp}: {e}")
    return issues


def esc(s):
    return html.escape(str(s or ""), quote=True)


def fmt_num(n):
    n = int(n or 0)
    if n >= 1000:
        return f"{n/1000:.1f}k"
    return str(n)


def trending_card(it):
    ko = it.get("summary_ko")
    meta = []
    if it.get("points"):
        meta.append(f"▲ {fmt_num(it['points'])}")
    if it.get("comments"):
        meta.append(f"💬 {fmt_num(it['comments'])}")
    meta_html = f'<span class="meta-line">{" · ".join(meta)}</span>' if meta else ""
    desc = f'<p class="item-desc">{esc(ko)}</p>' if ko else ""
    return f'''
    <article class="card">
      <a class="card-title" href="{esc(it.get('url'))}" target="_blank" rel="noopener">{esc(it.get('title'))}</a>
      {desc}
      <div class="card-foot">{meta_html}<span class="src">HackerNews</span></div>
    </article>'''


def paper_item(it):
    authors = f'<span class="byline">{esc(it.get("authors"))}</span>' if it.get("authors") else ""
    desc = f'<p class="item-desc">{esc(it.get("desc"))}</p>' if it.get("desc") else ""
    date = f'<span class="date">{esc(it.get("date"))}</span>' if it.get("date") else ""
    return f'''
    <article class="row">
      <div class="row-main">
        <a class="row-title" href="{esc(it.get('url'))}" target="_blank" rel="noopener">{esc(it.get('title'))}</a>
        {desc}
        <div class="card-foot">{authors}{date}<span class="src">ArXiv</span></div>
      </div>
    </article>'''


def tool_item(it):
    badges = []
    if it.get("stars"):
        badges.append(f"★ {fmt_num(it['stars'])}")
    if it.get("language"):
        badges.append(esc(it["language"]))
    badge_html = f'<span class="badges">{" · ".join(badges)}</span>' if badges else ""
    desc = f'<p class="item-desc">{esc(it.get("desc"))}</p>' if it.get("desc") else ""
    return f'''
    <article class="card">
      <a class="card-title" href="{esc(it.get('url'))}" target="_blank" rel="noopener">{esc(it.get('title'))}</a>
      {desc}
      <div class="card-foot">{badge_html}<span class="src">GitHub</span></div>
    </article>'''


def section(title, subtitle, inner, empty_msg):
    body = inner if inner.strip() else f'<p class="empty">{esc(empty_msg)}</p>'
    return f'''
    <section class="block">
      <header class="block-head">
        <h2>{esc(title)}</h2>
        <span class="block-sub">{esc(subtitle)}</span>
      </header>
      <div class="block-body">{body}</div>
    </section>'''


def render_issue(d):
    date = d.get("date", "")
    dt = datetime.date.fromisoformat(date) if date else datetime.date.today()
    pretty = dt.strftime("%Y년 %m월 %d일")
    trending = "".join(trending_card(it) for it in d.get("trending", []))
    papers = "".join(paper_item(it) for it in d.get("papers", []))
    tools = "".join(tool_item(it) for it in d.get("tools", []))
    topics = " · ".join(esc(t) for t in d.get("topics", []))

    return f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{esc(SITE_TITLE)} — {pretty}</title>
<link rel="stylesheet" href="../assets/style.css" />
</head>
<body>
<div class="wrap">
  <header class="masthead">
    <div class="brand">{esc(SITE_TITLE)}</div>
    <div class="issue-date">{pretty}</div>
    <p class="tagline">{esc(SITE_TAGLINE)}</p>
    <p class="topics">오늘의 주제 — {topics}</p>
  </header>

  {section("Trending", "지금 주목받는 AI 이야기", f'<div class="grid">{trending}</div>', "오늘 수집된 트렌딩 기사가 없습니다.")}
  {section("Papers", "새로 나온 연구", f'<div class="rows">{papers}</div>', "오늘 수집된 논문이 없습니다.")}
  {section("Open Source", "움직이는 프로젝트", f'<div class="grid">{tools}</div>', "오늘 수집된 프로젝트가 없습니다.")}

  <footer class="site-foot">
    <a href="../index.html">← 최신 호로</a> · <a href="../archive.html">전체 아카이브</a>
    <p>자동 수집 · HackerNews · ArXiv · GitHub</p>
  </footer>
</div>
</body>
</html>'''


def render_index(issues):
    latest = issues[0] if issues else None
    recent = "".join(
        f'<li><a href="issues/{esc(i.get("date"))}.html">{esc(datetime.date.fromisoformat(i.get("date")).strftime("%m.%d"))}</a>'
        f'<span class="r-title">{esc(datetime.date.fromisoformat(i.get("date")).strftime("%Y년 %m월 %d일"))}</span>'
        f'<span class="r-count">T{i.get("counts", {}).get("trending",0)} · P{i.get("counts", {}).get("papers",0)} · G{i.get("counts", {}).get("tools",0)}</span></li>'
        for i in issues[:12] if i.get("date")
    ) or '<li class="empty">아직 발행된 호가 없습니다.</li>'

    if latest:
        dt = datetime.date.fromisoformat(latest.get("date"))
        pretty = dt.strftime("%Y년 %m월 %d일")
        trending = "".join(trending_card(it) for it in latest.get("trending", [])[:6])
        papers = "".join(paper_item(it) for it in latest.get("papers", [])[:4])
        tools = "".join(tool_item(it) for it in latest.get("tools", [])[:4])
        topics = " · ".join(esc(t) for t in latest.get("topics", []))
        lead = f'''
        <header class="masthead">
          <div class="brand">{esc(SITE_TITLE)}</div>
          <div class="issue-date">{pretty} · 최신 호</div>
          <p class="tagline">{esc(SITE_TAGLINE)}</p>
          <p class="topics">오늘의 주제 — {topics}</p>
        </header>
        {section("Trending", "지금 주목받는 AI 이야기", f'<div class="grid">{trending}</div>', "")}
        {section("Papers", "새로 나온 연구", f'<div class="rows">{papers}</div>', "")}
        {section("Open Source", "움직이는 프로젝트", f'<div class="grid">{tools}</div>', "")}'''
    else:
        lead = '<header class="masthead"><div class="brand">The AI Brief</div><p class="tagline">아직 발행된 호가 없습니다.</p></header>'

    return f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{esc(SITE_TITLE)} — 매일 아침 AI 브리프</title>
<link rel="stylesheet" href="assets/style.css" />
</head>
<body>
<div class="wrap">
  {lead}
  <section class="block archive-preview">
    <header class="block-head"><h2>최근 호</h2><a class="more" href="archive.html">전체 보기 →</a></header>
    <ul class="issue-list">{recent}</ul>
  </section>
  <footer class="site-foot">
    <p>자동 수집 · HackerNews · ArXiv · GitHub</p>
  </footer>
</div>
</body>
</html>'''


def render_archive(issues):
    rows = "".join(
        f'''<li><a class="a-date" href="issues/{esc(i.get('date'))}.html">{esc(datetime.date.fromisoformat(i.get('date')).strftime('%Y년 %m월 %d일'))}</a>
        <span class="a-count">트렌딩 {i.get('counts', {}).get('trending',0)} · 논문 {i.get('counts', {}).get('papers',0)} · 프로젝트 {i.get('counts', {}).get('tools',0)}</span></li>'''
        for i in issues if i.get("date")
    ) or '<li class="empty">아직 발행된 호가 없습니다.</li>'
    return f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{esc(SITE_TITLE)} — 아카이브</title>
<link rel="stylesheet" href="assets/style.css" />
</head>
<body>
<div class="wrap">
  <header class="masthead">
    <div class="brand">{esc(SITE_TITLE)}</div>
    <p class="tagline">발행된 모든 호</p>
    <a href="index.html">← 최신 호로</a>
  </header>
  <section class="block">
    <ul class="archive-list">{rows}</ul>
  </section>
</div>
</body>
</html>'''


def main():
    issues = load_all_data()
    os.makedirs(ISSUES_DIR, exist_ok=True)

    for d in issues:
        if not d.get("date"):
            continue
        html_out = render_issue(d)
        with open(os.path.join(ISSUES_DIR, f"{d['date']}.html"), "w", encoding="utf-8") as f:
            f.write(html_out)

    with open(os.path.join(ROOT, "index.html"), "w", encoding="utf-8") as f:
        f.write(render_index(issues))
    with open(os.path.join(ROOT, "archive.html"), "w", encoding="utf-8") as f:
        f.write(render_archive(issues))

    print(f"[build] 완료 — 호 {len(issues)}개, index/archive/issues 생성")


if __name__ == "__main__":
    main()
