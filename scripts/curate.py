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

요약 모델은 이름을 고정하지 않는다. OpenRouter 무료 모델은 몇 달 단위로
생기고 사라지므로(2026 여름 hermes-3 :free 삭제로 요약이 조용히 끊겼다),
실행할 때마다 공개 모델 목록에서 살아 있는 무료 모델을 골라 쓴다.
사람이 손봐야 하는 상황(키 오류, 며칠째 요약 0건 등)만 GITHUB_OUTPUT 의
alert 로 내보내고, 워크플로의 마지막 health 잡이 이를 실패로 드러낸다.

Firecrawl 등 유료/크레딧 소스는 더 이상 사용하지 않는다.
"""
import os
import re
import glob
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

# 호 날짜는 발행 기준인 한국 시간으로 매긴다 (UTC 로 매기면 스케줄 지연 시 같은 날짜가 두 번 생긴다)
KST = datetime.timezone(datetime.timedelta(hours=9))

# 며칠 연속 0건이면 사람이 봐야 하는지 — 소스 장애는 대개 며칠 안에 스스로 풀리므로 여유를 둔다
ALERT_STREAK = {"summaries": 3, "trending": 7, "papers": 7, "tools": 7}


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
        "topic_labels": {},
        "max_per_section": 8,
    }
    try:
        import yaml
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        for k in ("topics", "sources", "topic_labels", "max_per_section"):
            if k in cfg:
                defaults[k] = cfg[k]
    except Exception as e:
        log(f"config.yaml 미사용(폴백): {e}")
    return defaults


# --------------------------------------------------------------------------
# http helpers
# --------------------------------------------------------------------------
# 테스트에서 바꿔 끼울 수 있도록 시간 함수를 한곳에 둔다
_sleep = time.sleep
_monotonic = time.monotonic


def _http_get_full(url, timeout=30, headers=None):
    """(상태, 본문, 응답 헤더) — 헤더는 Retry-After 를 읽을 때만 쓴다."""
    req = urllib.request.Request(url, headers=headers or UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", errors="ignore"), r.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="ignore")[:300], e.headers
    except Exception as e:
        return 0, str(e)[:200], None


def http_get(url, timeout=30, headers=None):
    status, body, _ = _http_get_full(url, timeout=timeout, headers=headers)
    return status, body


def _retry_after_seconds(hdrs):
    try:
        return max(0.0, float((hdrs or {}).get("Retry-After") or 0))
    except (TypeError, ValueError):
        return 0.0   # 날짜 형식 Retry-After 는 무시하고 기본 대기를 쓴다


RETRY_STATUSES = (0, 406, 429)   # + 5xx


def http_get_retry(url, timeout=30, headers=None, tries=3, base_wait=5, max_wait=60, before_each=None):
    """429·406·5xx·네트워크 오류는 점점 길게 쉬었다가 다시 시도한다 (Retry-After 가 있으면 따른다).

    before_each: 매 요청 직전에 부르는 함수 (arXiv 요청 간격 지키기용)
    """
    status, body = 0, ""
    for attempt in range(tries):
        if before_each:
            before_each()
        status, body, hdrs = _http_get_full(url, timeout=timeout, headers=headers)
        if status not in RETRY_STATUSES and status < 500:
            break
        if attempt < tries - 1:
            wait = min(max_wait, max(base_wait * (2 ** attempt), _retry_after_seconds(hdrs)))
            log(f"  {status} — {wait:.0f}초 뒤 재시도 ({attempt + 2}/{tries})")
            _sleep(wait)
    return status, body


def http_post_json(url, api_key, payload, timeout=120):
    """(HTTP 상태, 응답 JSON 또는 오류 본문 문자열) 을 돌려준다. 네트워크 오류는 상태 0."""
    data = json.dumps(payload).encode("utf-8")
    headers = {**UA, "Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
               "X-Title": "ai-news-curation"}
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8", errors="ignore"))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="ignore")[:300]
    except Exception as e:
        return 0, str(e)[:300]


# --------------------------------------------------------------------------
# source collectors
# --------------------------------------------------------------------------
# '트렌딩'은 최근 이틀 안에 반응(▲)이 붙은 글만 — 최신순 검색은 ▲1짜리 글로 채워졌다
HN_WINDOW_HOURS = 48
HN_MIN_POINTS = 15


def _hn_hits(topic, limit, popular):
    q = urllib.parse.quote(topic)
    if popular:
        since = int(time.time()) - HN_WINDOW_HOURS * 3600
        nf = urllib.parse.quote(f"created_at_i>{since},points>={HN_MIN_POINTS}")
        url = f"https://hn.algolia.com/api/v1/search?query={q}&tags=story&numericFilters={nf}&hitsPerPage={limit}"
    else:
        url = f"https://hn.algolia.com/api/v1/search_by_date?query={q}&tags=story&hitsPerPage={limit}"
    status, body = http_get(url, timeout=30)
    if status != 200:
        log(f"HN 실패({topic}): {status}")
        return []
    try:
        return json.loads(body).get("hits", [])
    except Exception:
        return []


def collect_hackernews(topics, limit):
    items = collect_hackernews_once(topics, limit, popular=True)
    if not items:  # 조용한 날엔 예전처럼 최신순으로라도 채워 빈 섹션을 피한다
        log("HN: 최근 반응 있는 글 없음 — 최신순으로 대체")
        items = collect_hackernews_once(topics, limit, popular=False)
    return items


def collect_hackernews_once(topics, limit, popular):
    items = []
    seen = set()
    for topic in topics[:3]:
        hits = _hn_hits(topic, limit, popular)
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
    if popular:  # 주제 순서가 아니라 반응 큰 순으로
        items.sort(key=lambda it: -it["points"])
    return items[:limit]


# "agents" 같은 검색어가 경제학·게임이론 논문까지 잡지 않도록 컴퓨터과학 AI 계열로 한정한다
ARXIV_CATS = "cat:cs.AI OR cat:cs.CL OR cat:cs.LG OR cat:cs.MA OR cat:cs.CV OR cat:cs.RO"
# arXiv API 이용 규칙: 연속 요청은 3초 이상 띄운다 (재시도 포함 모든 요청). 0.5초 간격일 때 429 가 잦았다.
ARXIV_MIN_INTERVAL = 3.0
ARXIV_TRIES = 4            # 첫 시도 + 재시도 3번 (10·20·40초 대기)
ARXIV_BASE_WAIT = 10
_arxiv_last = [None]       # 마지막 arXiv 요청 시각 (monotonic)


def arxiv_throttle():
    """직전 arXiv 요청에서 ARXIV_MIN_INTERVAL 초가 안 지났으면 그만큼 기다린다."""
    last = _arxiv_last[0]
    if last is not None:
        wait = ARXIV_MIN_INTERVAL - (_monotonic() - last)
        if wait > 0:
            _sleep(wait)
    _arxiv_last[0] = _monotonic()


def collect_arxiv(topics, limit):
    items = []
    seen = set()
    for topic in topics[:3]:
        q = urllib.parse.quote(f'({ARXIV_CATS}) AND all:"{topic}"')
        url = f"https://export.arxiv.org/api/query?search_query={q}&sortBy=submittedDate&sortOrder=descending&max_results={limit}"
        status, body = http_get_retry(url, timeout=30, tries=ARXIV_TRIES, base_wait=ARXIV_BASE_WAIT,
                                      before_each=arxiv_throttle)
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
    return items[:limit]


# '움직이는 프로젝트'는 최근 생긴 저장소 중 별이 빠르게 붙은 것 — 누적 별 순은 매일 같은 대형 저장소만 나왔다
GH_WINDOW_DAYS = 30
# 최근 며칠 안에 이미 실린 저장소는 뒤로 미룬다 — 별 순만 쓰면 같은 저장소가 2~3주씩 매일 반복됐다
GH_ROTATION_DAYS = 7
GH_CANDIDATES_PER_TOPIC = 30   # 겹치지 않는 후보를 넉넉히 받으려고 (주제당 요청 1번은 그대로)


def recent_issues(today, days):
    """today 이전 최근 days 일 안의 지난 호(data/YYYY-MM-DD.json)를 최신순으로 돌려준다."""
    start = (datetime.date.fromisoformat(today) - datetime.timedelta(days=days)).isoformat()
    out = []
    for path in sorted(glob.glob(os.path.join(DATA_DIR, "*.json")), reverse=True):
        name = os.path.basename(path)[:-5]
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", name) or name >= today:
            continue
        if name < start:
            break
        try:
            with open(path, "r", encoding="utf-8") as f:
                out.append(json.load(f))
        except Exception:
            continue
    return out


def recently_featured_repos(today, days=GH_ROTATION_DAYS):
    return {t.get("title") for d in recent_issues(today, days) for t in d.get("tools") or [] if t.get("title")}


def rotate_repos(items, recent, limit):
    """최근에 안 실린 저장소를 먼저(별 순 유지), 모자라면 최근 실린 저장소로 채운다."""
    fresh = [it for it in items if it["title"] not in recent]
    repeat = [it for it in items if it["title"] in recent]
    picked = fresh[:limit]
    if len(picked) < limit:
        picked += repeat[:limit - len(picked)]
    return picked, min(len(fresh), limit)


def collect_github(topics, limit, recent=None):
    items = []
    seen = set()
    since = (datetime.datetime.now(KST).date() - datetime.timedelta(days=GH_WINDOW_DAYS)).isoformat()
    headers = {**UA, "Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:  # 비인증 검색은 분당 10회라 가끔 403 — Actions 기본 토큰으로 한도를 넉넉히
        headers["Authorization"] = f"Bearer {token}"
    for topic in topics[:3]:
        q = urllib.parse.quote(f"{topic} created:>{since}")
        per_page = max(limit, GH_CANDIDATES_PER_TOPIC)
        url = f"https://api.github.com/search/repositories?q={q}&sort=stars&order=desc&per_page={per_page}"
        status, body = http_get(url, timeout=30, headers=headers)
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
    items.sort(key=lambda it: -it["stars"])
    picked, n_fresh = rotate_repos(items, recent or set(), limit)
    if recent is not None:
        log(f"GitHub: 후보 {len(items)}개 중 최근 {GH_ROTATION_DAYS}일 안 실린 저장소 {n_fresh}개 + 재등장 {len(picked) - n_fresh}개")
    return picked


# --------------------------------------------------------------------------
# optional summarizer (Korean) — keyless safe, 모델 자동 선택
# --------------------------------------------------------------------------
OR_API = "https://openrouter.ai/api/v1"

# 무료 모델 후보를 고를 때의 계열 선호 순서 (앞일수록 우선). 목록에 없는 계열도 뒤에서 시도한다.
FAMILY_PREF = ["gemma", "qwen", "llama", "nemotron", "deepseek", "mistral", "glm", "gpt-oss"]
# 요약에 맞지 않는 특수 목적 모델
EXCLUDE_WORDS = ("safety", "guard", "code", "coder", "lyria", "audio", "tts", "embed", "moderation")
# 무료 라우터 (그때 살아 있는 무료 모델로 알아서 보낸다). 예전엔 후보 목록 맨 끝(14번째)에 붙어
# 5번 시도 상한에 걸려 한 번도 불리지 않았다 → 이제 상한과 별개로 마지막 시도를 항상 라우터에 남긴다.
ROUTER_FALLBACK = "openrouter/free"
MAX_MODEL_TRIES = 4        # 목록에서 고른 이름 있는 모델을 시도하는 상한
ROUTER_TRIES = 2           # 그 뒤에 항상 붙는 무료 라우터 시도 횟수 (라우터는 부를 때마다 다른 모델로 갈 수 있다)
# 지난 호에 남긴 시도 기록(summary_attempts)으로 '요즘 계속 막히는' 모델을 뒤로 미룬다.
# 예: gemma-4 :free 는 2026-10~11 동안 매 실행 429 였는데 선호 1·2순위라 매번 시도 칸 2개를 먹었다.
MODEL_MEMORY_DAYS = 7
DEMOTE_MIN_FAILS = 2       # 이 기간 실패 점수가 이 이상이고 성공보다 많으면 뒤로 (404 는 2점, 429·빈 응답·시간 초과 1점)
FAIL_WEIGHT = {"not_found": 2, "rate_limited": 1, "empty": 1, "error": 1}

SUMMARY_SYSTEM = (
    "You are a concise tech editor for Korean developers. For each numbered AI news item, "
    "write ONE natural Korean sentence (40~90 characters) saying what it is and why it matters. "
    'Reply with JSON only: {"summaries": ["...", "..."]} — same count and order as the input. '
    "No markdown, no preamble."
)


def is_free(m):
    p = m.get("pricing") or {}
    return m.get("id", "").endswith(":free") or (str(p.get("prompt")) == "0" and str(p.get("completion")) == "0")


def outputs_text_only(m):
    modality = (m.get("architecture") or {}).get("modality", "")
    return modality.endswith("->text") if modality else True


def rank_free_models(models):
    """무료·텍스트 출력 모델을 계열 선호 → 컨텍스트 크기 순으로 정렬한다."""
    def family_rank(mid):
        name = mid.lower()
        for i, fam in enumerate(FAMILY_PREF):
            if fam in name:
                return i
        return len(FAMILY_PREF)

    picked = [m for m in models
              if is_free(m) and outputs_text_only(m) and m.get("id") != ROUTER_FALLBACK
              and not any(w in m["id"].lower() for w in EXCLUDE_WORDS)]
    def size_b(mid):
        # "gemma-4-31b-it" → 31, "…-120b-a12b" → 120 (첫 번째 파라미터 크기 표기)
        m = re.search(r"[-/](\d+(?:\.\d+)?)b(?![a-z])", mid.lower())
        return float(m.group(1)) if m else 0.0

    # 'stealth/'·preview 류는 예고 없이 사라지므로 같은 계열 안에서 뒤로 보내고, 같은 계열이면 큰 모델부터
    picked.sort(key=lambda m: (family_rank(m["id"]),
                               m["id"].startswith("stealth/") or "preview" in m["id"],
                               -size_b(m["id"]),
                               -(m.get("context_length") or 0)))
    return [m["id"] for m in picked]


def demoted_models(today, days=MODEL_MEMORY_DAYS):
    """최근 지난 호의 시도 기록에서 실패가 반복되고 성공은 그보다 적은 모델 집합 (라우터는 제외)."""
    fails, oks = {}, {}
    for d in recent_issues(today, days):
        for a in d.get("summary_attempts") or []:
            m, outcome = a.get("model"), a.get("outcome")
            if not m or m == ROUTER_FALLBACK:
                continue
            if outcome == "ok":
                oks[m] = oks.get(m, 0) + 1
            elif outcome in FAIL_WEIGHT:
                fails[m] = fails.get(m, 0) + FAIL_WEIGHT[outcome]
    return {m for m, n in fails.items() if n >= DEMOTE_MIN_FAILS and n > oks.get(m, 0)}


def order_candidates(pinned, ranked, demoted):
    """SUMMARY_MODEL(선택 고정) → 목록 기반 무료 모델(최근 반복 실패 모델은 뒤로). 라우터는 넣지 않는다."""
    ordered, seen = [], {ROUTER_FALLBACK}
    for c in ([pinned] if pinned else []) + [m for m in ranked if m not in demoted] + [m for m in ranked if m in demoted]:
        if c and c not in seen:
            seen.add(c)
            ordered.append(c)
    return ordered


def attempt_plan(named):
    """실제 시도 순서: 이름 있는 모델 MAX_MODEL_TRIES 개 + (상한과 별개로) 무료 라우터 ROUTER_TRIES 번."""
    return named[:MAX_MODEL_TRIES] + [ROUTER_FALLBACK] * ROUTER_TRIES


def candidate_models(today=None):
    """이번 실행에서 시도할 모델 순서 (attempt_plan 적용 전, 라우터 제외)."""
    pinned = os.environ.get("SUMMARY_MODEL", "").strip()
    ranked = []
    status, body = http_get(f"{OR_API}/models", timeout=30)
    if status == 200:
        try:
            ranked = rank_free_models(json.loads(body).get("data", []))
        except Exception as e:
            log(f"모델 목록 파싱 실패(무료 라우터로 진행): {e}")
    else:
        log(f"모델 목록 조회 실패({status}) — 무료 라우터로 진행")
    demoted = demoted_models(today) if today else set()
    if demoted & set(ranked):
        log(f"최근 {MODEL_MEMORY_DAYS}일 반복 실패로 뒤로 미룬 모델: {', '.join(sorted(demoted & set(ranked)))}")
    return order_candidates(pinned, ranked, demoted)


def classify_status(status):
    """실패한 호출의 HTTP 상태 → 시도 기록 분류."""
    if status in (401, 402, 403):
        return "auth"
    if status == 404:
        return "not_found"
    if status == 429:
        return "rate_limited"
    return "error"     # 0(네트워크·시간 초과)·5xx·기타


def parse_summaries(content, n):
    """모델 응답에서 요약 n개를 꺼낸다. JSON 이 아니면 줄 단위로라도 건진다."""
    text = (content or "").strip()
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            arr = json.loads(m.group(0)).get("summaries")
            if isinstance(arr, list):
                return [s.strip().strip('*"') if isinstance(s, str) else "" for s in arr][:n]
        except Exception:
            pass
    lines = [re.sub(r"^\s*(\d+[.)]|[-*•])\s*", "", l).strip().strip('*"') for l in text.splitlines()]
    return [l for l in lines if l][:n]


def _error_code(res):
    """OpenRouter 는 상류 오류를 HTTP 200 + {"error": {"code": 503, ...}} 로 돌려줄 때가 있다."""
    err = res.get("error") if isinstance(res, dict) else None
    if not isinstance(err, dict):
        return None
    try:
        return int(err.get("code"))
    except (TypeError, ValueError):
        return 502


def summarize_batch(items, api_key, today=None, plan=None):
    """HN 상위 항목을 한 번의 호출로 요약한다 (무료 한도 50회/일을 아끼려고 묶어서 보냄).

    반환: (요약 리스트, 사용한 모델, 문제 분류, 시도 기록)
      분류는 None | "transient" | "auth" | "no_model"
      시도 기록은 [{"model", "outcome"(ok|rate_limited|not_found|empty|error|auth), ...}] — 다음 실행의 순서 조정용
    """
    numbered = "\n".join(f"{i + 1}. {it['title']}. {it.get('desc', '')}"[:600] for i, it in enumerate(items))
    auth_failed, transient = False, False
    attempts = []
    plan = plan if plan is not None else attempt_plan(candidate_models(today))
    log(f"시도 순서: {' → '.join(plan)}")
    for idx, model in enumerate(plan):
        is_last = idx == len(plan) - 1
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": SUMMARY_SYSTEM},
                {"role": "user", "content": numbered},
            ],
            "max_tokens": 1500,
            "temperature": 0.3,
            # 추론 모델이 토큰을 다 쓰고 빈 답을 내지 않도록 (지원하지 않는 모델은 무시한다)
            "reasoning": {"effort": "low", "exclude": True},
        }
        status, res = http_post_json(f"{OR_API}/chat/completions", api_key, payload, timeout=90)
        if status == 200 and isinstance(res, dict) and not res.get("choices") and _error_code(res):
            status = _error_code(res)
        if status == 200 and isinstance(res, dict) and res.get("choices"):
            choice = res["choices"][0] or {}
            msg = choice.get("message") or {}
            served = res.get("model") or model
            sums = parse_summaries(msg.get("content"), len(items))
            if any(sums):
                n_ok = sum(1 for s in sums if s)
                via = f" → {served}" if served != model else ""
                log(f"요약 모델: {model}{via} ({n_ok}/{len(items)})")
                attempts.append({"model": model, "outcome": "ok", "served_by": served, "n": n_ok})
                return sums, model, None, attempts
            # 원인 추적용: 추론에 토큰을 다 썼는지(length), 상류 오류(error)인지
            fr, nfr = choice.get("finish_reason"), choice.get("native_finish_reason")
            usage = res.get("usage") or {}
            log(f"{model}: 빈 응답 (finish={fr}/{nfr}, completion_tokens={usage.get('completion_tokens')}, "
                f"reasoning={'있음' if msg.get('reasoning') else '없음'}, served={served}) — 다음 모델")
            attempts.append({"model": model, "outcome": "empty", "finish": fr})
            if fr == "error":
                transient = True
            continue
        outcome = classify_status(status)
        attempts.append({"model": model, "outcome": outcome, "status": status})
        log(f"{model}: 실패 {status} {str(res)[:160]}")
        if outcome == "auth":
            auth_failed = True     # 키 문제는 모델을 바꿔도 같으므로 바로 멈춘다
            break
        if status in (0, 429) or status >= 500:
            transient = True
            if not is_last:
                _sleep(10 if model == ROUTER_FALLBACK else 5)
    if auth_failed:
        return [], None, "auth", attempts
    return [], None, "transient" if transient else "no_model", attempts


def zero_streak(key, today_count, today, days):
    """오늘 포함 최근 호들에서 key 가 연속으로 0 이었던 호 수 (저장소에 남은 과거 호 기준)."""
    streak = 1 if today_count == 0 else 0
    if streak == 0:
        return 0
    for path in sorted(glob.glob(os.path.join(DATA_DIR, "*.json")), reverse=True):
        if os.path.basename(path)[:10] >= today:
            continue
        if streak >= days:
            break
        try:
            with open(path, "r", encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            break
        if key == "summaries":
            if "summary_model" not in d:   # 모델 자동 선택 이전 형식의 호는 비교 대상에서 뺀다
                break
            n = sum(1 for it in d.get("trending", []) if it.get("summary_ko"))
        else:
            n = (d.get("counts") or {}).get(key, 0)
        if n:
            break
        streak += 1
    return streak


def load_issue(date_str):
    """data/<date>.json 이 있으면 읽어 돌려준다 (없거나 깨졌으면 None)."""
    path = os.path.join(DATA_DIR, f"{date_str}.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def carry_over_summaries(trending, prev):
    """같은 날 앞선 실행이 만든 요약을 URL 기준으로 이어받는다 (재실행이 요약 0건이어도 지우지 않도록).

    이어받은 개수를 돌려준다.
    """
    old = {it.get("url"): it.get("summary_ko") for it in (prev or {}).get("trending") or [] if it.get("summary_ko")}
    n = 0
    for it in trending:
        if not it.get("summary_ko") and old.get(it.get("url")):
            it["summary_ko"] = old[it["url"]]
            n += 1
    return n


SUMMARY_TOP_N = 5


def emit_output(**kv):
    """워크플로의 다음 잡이 읽도록 GITHUB_OUTPUT 에 기록한다 (로컬 실행 시엔 출력만)."""
    out = os.environ.get("GITHUB_OUTPUT")
    for k, v in kv.items():
        log(f"output {k}={v}")
        if out:
            with open(out, "a", encoding="utf-8") as f:
                f.write(f"{k}={v}\n")


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def main():
    now = datetime.datetime.now(KST)
    today = now.date().isoformat()
    cfg = load_config()
    topics = cfg["topics"]
    max_n = cfg.get("max_per_section", 8)

    log(f"수집 시작 — {today} (KST) topics={topics}")

    trending = collect_hackernews(topics, max_n)
    papers = collect_arxiv(topics, max_n)
    tools = collect_github(topics, max_n, recent=recently_featured_repos(today))

    # 같은 날 다시 돌린 경우(수동 실행 등) 앞선 실행 결과를 지우지 않는다:
    # 이번에 0건인 섹션은 앞선 결과를 그대로 쓰고, 요약은 이어받은 뒤 빠진 항목만 새로 요약한다
    prev_today = load_issue(today)
    if prev_today:
        sections = {"trending": trending, "papers": papers, "tools": tools}
        for key, items in sections.items():
            if not items and prev_today.get(key):
                log(f"{key}: 이번 실행 0건 — 오늘 앞선 실행 결과 {len(prev_today[key])}건 유지")
                items.extend(prev_today[key])
    carried = carry_over_summaries(trending, prev_today) if prev_today else 0
    if carried:
        log(f"오늘 앞선 실행의 요약 {carried}건을 이어받음")

    or_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    summary_model, summary_problem, summary_attempts = None, None, []
    if or_key and trending:
        targets = [it for it in trending[:SUMMARY_TOP_N] if not it.get("summary_ko")]
        if targets:
            log("한국어 요약 생성 중(옵션)...")
            sums, summary_model, summary_problem, summary_attempts = summarize_batch(targets, or_key, today=today)
            for it, s in zip(targets, sums):   # 일부만 요약돼도 된 것은 그대로 싣는다
                if s:
                    it["summary_ko"] = s
        else:
            log("상위 항목 요약이 이미 있음 — 요약 호출 생략")
    elif not or_key:
        log("OPENROUTER_API_KEY 없음 — 요약 없이 발행")
    if not summary_model and carried:
        summary_model = (prev_today or {}).get("summary_model")
    if not summary_attempts and prev_today:   # 이번에 호출을 안 했으면 앞선 실행의 시도 기록을 남긴다
        summary_attempts = prev_today.get("summary_attempts") or []

    payload = {
        "date": today,
        "generated_at": now.isoformat(timespec="seconds"),
        "topics": topics,
        "topic_labels": cfg.get("topic_labels", {}),
        "counts": {"trending": len(trending), "papers": len(papers), "tools": len(tools)},
        "summary_model": summary_model,
        "summary_attempts": summary_attempts,
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

    # 사람이 손봐야 하는 경우만 alert 로 올린다. 일시 장애는 다음 날 스스로 풀리므로 연속 일수로 거른다.
    alerts = []
    if summary_problem == "auth":
        alerts.append("OpenRouter 키가 거부됨(401/402/403) — openrouter.ai 에서 키를 새로 만들어 OPENROUTER_API_KEY 시크릿을 교체하세요")
    if or_key and trending:
        n_sum = sum(1 for it in trending if it.get("summary_ko"))
        streak = zero_streak("summaries", n_sum, today, ALERT_STREAK["summaries"])
        if streak >= ALERT_STREAK["summaries"] and summary_problem != "auth":
            alerts.append(f"한국어 요약이 {streak}회 연속 0건 (마지막 원인: {summary_problem}) — 로그 확인 필요")
    for key, items in (("trending", trending), ("papers", papers), ("tools", tools)):
        streak = zero_streak(key, len(items), today, ALERT_STREAK[key])
        if streak >= ALERT_STREAK[key]:
            alerts.append(f"{key} 수집이 {streak}회 연속 0건 — 소스 API 변경 가능성")
    emit_output(alert=" / ".join(alerts))
    return out_path


if __name__ == "__main__":
    main()
