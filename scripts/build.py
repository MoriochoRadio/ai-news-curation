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

# 섹션 한국어 라벨
SECTION_KO = {
    "trending": ("트렌딩", "지금 주목받는 AI 이야기"),
    "papers": ("논문", "새로 나온 연구"),
    "tools": ("오픈소스", "움직이는 프로젝트"),
}


def load_config():
    """config.yaml 의 topic_labels 를 읽는다."""
    try:
        import yaml
        with open(os.path.join(ROOT, "config.yaml"), "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


CONFIG = load_config()
TOPIC_LABELS = CONFIG.get("topic_labels", {}) or {}


def ko_topic(t):
    return TOPIC_LABELS.get(t, t)


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


def section(section_key, inner, empty_msg):
    title, subtitle = SECTION_KO.get(section_key, (section_key, ""))
    body = inner if inner.strip() else f'<p class="empty">{esc(empty_msg)}</p>'
    return f'''
    <section class="block" data-section="{esc(section_key)}">
      <header class="block-head">
        <h2>{esc(title)}</h2>
        <span class="block-sub">{esc(subtitle)}</span>
      </header>
      <div class="block-body">{body}</div>
    </section>'''


def render_tldr(d):
    """호 한 편을 요약하는 '핵심정리' 블록 (빌드 시점 생성, 키 불필요)."""
    c = d.get("counts", {})
    labels = [ko_topic(t) for t in d.get("topics", [])]
    topics_html = " · ".join(esc(x) for x in labels)
    top_t = d.get("trending", [])
    top_p = d.get("papers", [])
    top_g = d.get("tools", [])
    picks = []
    if top_t:
        picks.append(("오늘의 관심", top_t[0].get("title", "")))
    if top_p:
        picks.append(("논문 픽", top_p[0].get("title", "")))
    if top_g:
        picks.append(("프로젝트 픽", top_g[0].get("title", "")))
    picks_html = "".join(
        f'<li><span class="tldr-tag">{esc(k)}</span> {esc(v)}</li>' for k, v in picks
    )
    return f'''
    <section class="block tldr">
      <header class="block-head">
        <h2>한눈에 요약</h2>
        <span class="block-sub">TL;DR</span>
      </header>
      <div class="block-body">
        <p class="tldr-count">트렌딩 <b>{c.get('trending',0)}</b> · 논문 <b>{c.get('papers',0)}</b> · 프로젝트 <b>{c.get('tools',0)}</b> 건 수집</p>
        <p class="tldr-topics">오늘 살펴본 주제 — {topics_html}</p>
        <ul class="tldr-picks">{picks_html}</ul>
      </div>
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
{TOOLBAR_CSS}
</head>
<body>
{TOOLBAR_HTML}
<div class="wrap">
  <header class="masthead">
    <div class="brand">{esc(SITE_TITLE)}</div>
    <div class="issue-date">{pretty}</div>
    <p class="tagline">{esc(SITE_TAGLINE)}</p>
    <p class="topics">오늘의 주제 — {topics}</p>
  </header>

  {render_tldr(d)}
  {section("trending", f'<div class="grid">{trending}</div>', "오늘 수집된 트렌딩 기사가 없습니다.")}
  {section("papers", f'<div class="rows">{papers}</div>', "오늘 수집된 논문이 없습니다.")}
  {section("tools", f'<div class="grid">{tools}</div>', "오늘 수집된 프로젝트가 없습니다.")}

  <footer class="site-foot">
    <a href="../index.html">← 최신 호로</a> · <a href="../archive.html">전체 아카이브</a>
    <p>자동 수집 · HackerNews · ArXiv · GitHub</p>
  </footer>
</div>
{TOOLBAR_JS}
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
        {render_tldr(latest)}
        {section("trending", f'<div class="grid">{trending}</div>', "")}
        {section("papers", f'<div class="rows">{papers}</div>', "")}
        {section("tools", f'<div class="grid">{tools}</div>', "")}'''
    else:
        lead = '<header class="masthead"><div class="brand">The AI Brief</div><p class="tagline">아직 발행된 호가 없습니다.</p></header>'

    return f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{esc(SITE_TITLE)} — 매일 아침 AI 브리프</title>
<link rel="stylesheet" href="assets/style.css" />
{TOOLBAR_CSS}
</head>
<body>
{TOOLBAR_HTML}
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
{TOOLBAR_JS}
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
{TOOLBAR_CSS}
</head>
<body>
{TOOLBAR_HTML}
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
{TOOLBAR_JS}
</body>
</html>'''


# --------------------------------------------------------------------------
# 공통 툴바: 검색 · 다크모드 · 한국어 번역
# (전부 키 없이 클라이언트에서 동작)
# --------------------------------------------------------------------------
TOOLBAR_CSS = """
<style>
.tb-fixed{position:fixed;top:0;left:0;right:0;z-index:50;display:flex;gap:8px;align-items:center;
  padding:8px 14px;background:var(--paper,#fffdf8);border-bottom:1px solid var(--line,#e3ddd0);
  box-shadow:0 1px 6px rgba(0,0,0,.05);font-family:var(--sans);}
.tb-fixed input{flex:1;max-width:340px;padding:7px 12px;border:1px solid var(--line,#e3ddd0);
  border-radius:20px;font-size:13px;background:var(--bg,#f4f1ea);color:var(--ink,#1c1a17);outline:none;}
.tb-fixed .tb-btn{border:1px solid var(--line,#e3ddd0);background:transparent;color:var(--ink,#1c1a17);
  border-radius:20px;padding:6px 12px;font-size:13px;cursor:pointer;line-height:1;}
.tb-fixed .tb-btn:hover{border-color:var(--accent,#b4451f);color:var(--accent,#b4451f);}
body.has-tb{padding-top:52px;}
mark.hl{background:var(--accent-soft,#f3e7df);color:var(--accent,#b4451f);border-radius:3px;padding:0 2px;}
#goog-gt-tt,#goog-te-banner{display:none!important;}
.goog-te-gadget{font-size:0!important;}
.goog-te-gadget .goog-te-combo{font-size:12px!important;padding:5px 6px;border-radius:14px;
  border:1px solid var(--line,#e3ddd0);background:var(--bg,#f4f1ea);color:var(--ink,#1c1a17);}
</style>
"""

TOOLBAR_HTML = """
<div class="tb-fixed">
  <input id="siteSearch" type="search" placeholder="호 내 검색 (제목·설명)…" aria-label="검색" />
  <button class="tb-btn" id="darkToggle" type="button">🌙 다크</button>
  <div id="gt-mount"></div>
</div>
"""

TOOLBAR_JS = """
<script>
(function(){
  var b=document.body; b.classList.add('has-tb');
  // 다크모드
  var dt=document.getElementById('darkToggle');
  var saved=localStorage.getItem('aibrief-theme');
  if(saved==='dark'){document.documentElement.setAttribute('data-theme','dark');dt.textContent='☀️ 라이트';}
  dt.addEventListener('click',function(){
    var dark=dt.textContent.indexOf('라이트')===-1;
    if(dark){localStorage.setItem('aibrief-theme','dark');document.documentElement.setAttribute('data-theme','dark');dt.textContent='☀️ 라이트';}
    else{localStorage.setItem('aibrief-theme','light');document.documentElement.removeAttribute('data-theme');dt.textContent='🌙 다크';}
  });
  // 검색 (호 내 하이라이팅 + 필터)
  var s=document.getElementById('siteSearch');
  s.addEventListener('input',function(){
    var q=s.value.trim().toLowerCase();
    var cards=document.querySelectorAll('.card,.row');
    cards.forEach(function(c){
      var t=c.textContent.toLowerCase();
      var hit=!q||t.indexOf(q)>-1;
      c.style.display=hit?'':'none';
      c.querySelectorAll('mark.hl').forEach(function(m){c.replaceChild(document.createTextNode(m.textContent),m);c.normalize();});
      if(q&&hit){var tt=c.innerHTML;
        try{c.innerHTML=tt.replace(new RegExp('('+q.replace(/[.*+?^${}()|[\\]\\\\]/g,'\\\\$&')+')','ig'),'<mark class=\"hl\">$1</mark>');}catch(e){}}
    });
    document.querySelectorAll('.block').forEach(function(bl){
      var any=[].slice.call(bl.querySelectorAll('.card,.row')).some(function(c){return c.style.display!=='none';});
      bl.style.display=(q&&!any)?'none':'';
    });
  });
  // Google 번역 위젯 (키 불필요)
  var g=document.createElement('script');
  g.src='https://translate.google.com/translate_a/element.js?cb=__aibT';
  window.__aibT=function(){
    new google.translate.TranslateElement({pageLanguage:'en',includedLanguages:'ko,en',layout:google.translate.TranslateElement.InlineLayout.SIMPLE,autoDisplay:false},'gt-mount');
    var sel=document.querySelector('#gt-mount .goog-te-combo');
    if(sel){var o=document.createElement('option');o.value='ko';o.text='한국어';sel.add(o,sel.options[0]);}
  };
  document.body.appendChild(g);
})();
</script>
"""


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
