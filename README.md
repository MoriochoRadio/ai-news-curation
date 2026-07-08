# The AI Brief

> 매일 아침, AI 업계의 흐름을 한눈에 정리하는 뉴스레터형 큐레이션.

[🌐 라이브 사이트](https://MoriochoRadio.github.io/ai-news-curation/)

---

## 한 줄 요약

키 없이 동작하는 무료 소스 3곳(HackerNews · ArXiv · GitHub)에서
매일 AI 관련 **트렌딩 / 논문 / 오픈소스**를 자동 수집해
정적 뉴스레터로 발행합니다. 별도 API 키·크레딧 없이 영구 무료로 운영됩니다.

## 주요 특징

- **완전 키리스(Keyless)**: Firecrawl·OpenAI 등 유료 키가 전혀 필요 없습니다.
- **3개 섹션**: 트렌딩(HN) · 논문(ArXiv) · 오픈소스(GitHub)
- **한국어 친화 UX**:
  - 섹션명 한국어 표기(트렌딩/논문/오픈소스)
  - 📌 **한눈에 요약(TL;DR)**: 매 호의 건수·주제·픽 3선 요약
  - 🔎 **호 내 검색**: 제목·설명 실시간 하이라이팅
  - 🌙 **다크모드**: 토글(설정 로컬 저장)
  - 🌐 **한국어 번역**: Google 번역 위젯(원문 영어 → 한국어)
- **정적 사이트**: 빌드 시점에 HTML 생성 → 브라우저 파서 버그 없음
- **아카이브**: 모든 호를 날짜별로 보관

## 웹으로 보기

- 메인: https://MoriochoRadio.github.io/ai-news-curation/
- 아카이브: https://MoriochoRadio.github.io/ai-news-curation/archive.html
- 개별 호 예시: `issues/2026-07-08.html`

## 구성 / 키워드

| 항목 | 내용 |
|------|------|
| 수집 주제 | AI 에이전트, LLM 추론, 멀티모달, 오픈소스 AI, AI 도구의 Rust, AI 안전성 |
| 소스 | HackerNews Algolia API · ArXiv API · GitHub Search API |
| 산출물 | `data/YYYY-MM-DD.json` → `index.html` / `archive.html` / `issues/*.html` |
| 배포 | GitHub Pages (자동) |
| 실행 | GitHub Actions (매일 KST 08:00) |

## 자동화

- 매일 **KST 08:00**(UTC 23:00)에 GitHub Actions가 실행됩니다.
- 수집 → 빌드(정적 HTML) → 커밋 → GitHub Pages 배포까지全自动.
- `workflow_dispatch`로 수동 실행도 가능합니다(Actions 탭 → Run workflow).

## 로컬에서 직접 실행하기

```bash
# 1) 저장소 복제
git clone https://github.com/MoriochoRadio/ai-news-curation.git
cd ai-news-curation

# 2) 수집 (키 불필요)
pip install pyyaml
python scripts/curate.py

# 3) 정적 사이트 빌드
python scripts/build.py

# 4) 로컬 확인
python -m http.server 8000
# 브라우저에서 http://localhost:8000 접속
```

> 💡 `OPENROUTER_API_KEY` 환경변수를 설정하면
> 트렌딩 항목에 **한국어 한 줄 요약**이 자동 추가됩니다(선택 사항).
> 키가 없어도 파이프라인은 정상 동작합니다.

## 설정 커스터마이징

`config.yaml`에서 수집 주제와 한국어 라벨을 바꿀 수 있습니다.

```yaml
topics:
  - "AI agents"
  - "LLM reasoning"
topic_labels:
  "AI agents": "AI 에이전트"
  "LLM reasoning": "LLM 추론"
```

## 기여 / 피드백

관심 주제, 새로운 키리스 소스 제안, 디자인/UX 개선 의견은
이슈나 PR로 자유롭게 남겨주세요.

---

*자동 수집 · HackerNews · ArXiv · GitHub — 키 없이 매일 발행*
