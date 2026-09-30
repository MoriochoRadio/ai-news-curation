# The AI Brief

🇰🇷 한국어 · 🇬🇧 [English](README.en.md)

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
| 실행 | GitHub Actions (매일 KST 07:23 예약 — 스케줄 지연 감안) |

## 자동화

- 매일 **KST 07:23**(UTC 22:23)에 GitHub Actions가 실행되도록 예약돼 있습니다(정각 혼잡을 피하고, GitHub 스케줄의 평균 2시간대 지연을 감안).
- 수집 → 빌드(정적 HTML) → 커밋·push → GitHub Pages 배포까지 전 과정이 자동입니다.
- **사람이 손봐야 할 때만 실패합니다.** 마지막 `health` 잡이 키 거부, 며칠 연속 요약 0건, 일주일 연속 소스 0건, push 실패 같은 경우에만 빨간불을 켜고 GitHub이 실패 메일을 보냅니다. 일시 장애는 재시도와 다음 날 실행으로 스스로 풀리므로 알리지 않습니다.
- `workflow_dispatch`로 수동 실행도 가능합니다(Actions 탭 → Run workflow).

## 왜 이렇게 만들었나 — 기술 선택 Q&A

**Q. 왜 정적 사이트인가?**
A. 하루 한 번 갱신되는 콘텐츠라 요청마다 렌더링할 이유가 없습니다. 빌드 시점에 HTML을 완성해 두면 서버·DB 없이 GitHub Pages만으로 배포되고, 브라우저 쪽 자바스크립트 파싱·렌더링 의존이 없어 어떤 환경에서도 깨지지 않습니다.

**Q. 왜 HackerNews·ArXiv·GitHub 세 소스인가?**
A. 셋 다 API 키·크레딧 없이 호출할 수 있는 공개 API이면서, 트렌딩(커뮤니티 반응)·논문(연구)·오픈소스(실제 구현)라는 서로 다른 관점을 보완적으로 커버합니다. 초기에 쓰던 Firecrawl 같은 크레딧제 소스는 크레딧 소진이 곧 서비스 중단이라 제거했습니다.

**Q. 수집 스크립트는 왜 표준 라이브러리 위주인가?**
A. 외부 의존성은 `pyyaml` 하나뿐이고 HTTP 호출도 `urllib`로 직접 합니다. 의존성이 적을수록 매일 도는 GitHub Actions 러너에서 설치가 빠르고, 몇 년 뒤에도 깨질 여지가 적기 때문입니다. `pyyaml`조차 없으면 내장 기본 설정으로 폴백해 동작합니다.

**Q. LLM 한국어 요약은 왜 '옵션'으로 설계했나?**
A. `OPENROUTER_API_KEY`가 있으면 무료 모델로 한 줄 요약을 덧붙이고, 없거나 호출이 실패해도 원문 그대로 발행합니다. 외부 유료 서비스가 단일 실패 지점이 되어 "영구 무료·무중단" 원칙을 깨는 일을 막기 위해서입니다. 무료 모델은 몇 달 단위로 생기고 사라지므로 모델 이름을 고정하지 않고, 실행할 때마다 OpenRouter 공개 모델 목록에서 살아 있는 무료 모델을 골라 씁니다(목록 조회가 안 되면 무료 라우터 `openrouter/free`).

**Q. 왜 GitHub Actions 스케줄로 수집하나?**
A. 별도 서버 없이 매일 크론으로 실행되고, 결과를 저장소에 커밋·push하므로 매 호의 데이터 이력이 git 히스토리로 남습니다. 수집 결과가 0건이면 런을 의도적으로 실패 처리해, 소스 장애를 조용히 넘기지 않고 Actions 알림으로 드러냅니다.

**Q. 수집 결과를 왜 JSON으로 먼저 저장하고 HTML은 따로 빌드하나?**
A. 수집(`curate.py`)과 표현(`build.py`)을 분리하기 위해서입니다. `data/*.json`이 원본 아카이브 역할을 하므로, 디자인을 바꿔도 과거 호 전체를 새 템플릿으로 재빌드할 수 있습니다.

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
