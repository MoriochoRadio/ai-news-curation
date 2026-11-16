"""curate.py 의 모델 선택·저장소 로테이션·arXiv 간격·같은 날 재실행 보존 테스트 (네트워크 없음).

실행: python -m unittest discover -s tests
"""
import datetime
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import curate  # noqa: E402

ROUTER = curate.ROUTER_FALLBACK


def ok_response(summaries, model="x"):
    return 200, {"model": model, "choices": [{"message": {"content": json.dumps({"summaries": summaries})},
                                              "finish_reason": "stop"}]}


def empty_response(finish="length"):
    return 200, {"choices": [{"message": {"content": ""}, "finish_reason": finish}],
                 "usage": {"completion_tokens": 1500}}


class TempDataDir(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._p = mock.patch.object(curate, "DATA_DIR", self.tmp)
        self._p.start()
        self._s = mock.patch.object(curate, "_sleep", lambda s: None)
        self._s.start()

    def tearDown(self):
        self._p.stop()
        self._s.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_issue(self, date, **kv):
        with open(os.path.join(self.tmp, f"{date}.json"), "w", encoding="utf-8") as f:
            json.dump({"date": date, **kv}, f)


class AttemptPlanTest(unittest.TestCase):
    def test_router_always_reserved_even_with_many_models(self):
        named = [f"m{i}:free" for i in range(13)]
        plan = curate.attempt_plan(named)
        self.assertEqual(plan[:curate.MAX_MODEL_TRIES], named[:curate.MAX_MODEL_TRIES])
        self.assertEqual(plan[-curate.ROUTER_TRIES:], [ROUTER] * curate.ROUTER_TRIES)
        self.assertEqual(len(plan), curate.MAX_MODEL_TRIES + curate.ROUTER_TRIES)

    def test_router_only_when_list_unavailable(self):
        self.assertEqual(curate.attempt_plan([]), [ROUTER] * curate.ROUTER_TRIES)

    def test_order_demotes_and_keeps_pinned_first(self):
        ranked = ["gemma-a:free", "gemma-b:free", "nemo:free", "other:free"]
        out = curate.order_candidates("pinned/x", ranked, {"gemma-a:free", "gemma-b:free"})
        self.assertEqual(out, ["pinned/x", "nemo:free", "other:free", "gemma-a:free", "gemma-b:free"])
        self.assertNotIn(ROUTER, curate.order_candidates(ROUTER, ranked + [ROUTER], set()))


class DemotionMemoryTest(TempDataDir):
    def test_repeat_429_demoted_but_mostly_ok_model_kept(self):
        today = "2026-11-16"
        for i, day in enumerate(["2026-11-15", "2026-11-14", "2026-11-13"]):
            self.write_issue(day, summary_attempts=[
                {"model": "google/gemma:free", "outcome": "rate_limited"},
                {"model": "nvidia/nemo:free", "outcome": "empty" if i == 0 else "ok"},
                {"model": ROUTER, "outcome": "rate_limited"},
            ])
        self.write_issue("2026-11-12", summary_attempts=[{"model": "gone/model:free", "outcome": "not_found"}])
        # 기간 밖(8일 전) 기록과 오늘 파일·날짜 아닌 파일은 무시
        self.write_issue("2026-11-08", summary_attempts=[{"model": "old/x:free", "outcome": "rate_limited"}] * 3)
        self.write_issue(today, summary_attempts=[{"model": "today/x:free", "outcome": "rate_limited"}] * 3)
        self.write_issue("model_state", summary_attempts=[{"model": "junk:free", "outcome": "rate_limited"}] * 3)
        demoted = curate.demoted_models(today)
        self.assertEqual(demoted, {"google/gemma:free", "gone/model:free"})

    def test_single_429_not_demoted(self):
        self.write_issue("2026-11-15", summary_attempts=[{"model": "a:free", "outcome": "rate_limited"}])
        self.assertEqual(curate.demoted_models("2026-11-16"), set())

    def test_issues_without_attempts_are_fine(self):
        self.write_issue("2026-11-15", summary_model=None, trending=[])
        self.assertEqual(curate.demoted_models("2026-11-16"), set())


class SummarizeBatchTest(unittest.TestCase):
    def setUp(self):
        self._s = mock.patch.object(curate, "_sleep", lambda s: None)
        self._s.start()
        self.items = [{"title": f"t{i}", "desc": ""} for i in range(5)]

    def tearDown(self):
        self._s.stop()

    def run_with(self, plan, responses):
        calls = []

        def fake_post(url, key, payload, timeout=120):
            calls.append(payload["model"])
            return responses.pop(0)
        with mock.patch.object(curate, "http_post_json", fake_post):
            out = curate.summarize_batch(self.items, "test-key", plan=plan)
        return out, calls

    def test_reaches_router_after_429s_and_empties(self):
        plan = curate.attempt_plan(["gemma1:free", "gemma2:free", "nemo1:free", "nemo2:free", "nemo3:free"])
        rl = (429, '{"error":{"code":429}}')
        (sums, model, problem, attempts), calls = self.run_with(
            plan, [rl, rl, empty_response(), empty_response(), ok_response(["가"] * 5, model="qwen/q:free")])
        self.assertEqual(calls[-1], ROUTER)
        self.assertNotIn("nemo3:free", calls)   # 이름 있는 모델은 상한까지만
        self.assertEqual(model, ROUTER)
        self.assertIsNone(problem)
        self.assertEqual([a["outcome"] for a in attempts], ["rate_limited", "rate_limited", "empty", "empty", "ok"])
        self.assertEqual(attempts[-1]["served_by"], "qwen/q:free")

    def test_all_429_is_transient_not_auth(self):
        plan = curate.attempt_plan(["a:free", "b:free"])
        rl = (429, "rate")
        (sums, model, problem, attempts), calls = self.run_with(plan, [rl] * len(plan))
        self.assertEqual((sums, model, problem), ([], None, "transient"))
        self.assertEqual(calls, plan)

    def test_200_with_upstream_error_body_is_transient(self):
        plan = ["nemo:free"]
        (_, _, problem, attempts), _ = self.run_with(
            plan, [(200, {"id": "gen", "error": {"message": "overloaded", "code": 503}})])
        self.assertEqual(problem, "transient")
        self.assertEqual(attempts[0], {"model": "nemo:free", "outcome": "error", "status": 503})

    def test_auth_failure_stops_immediately(self):
        plan = curate.attempt_plan(["a:free", "b:free"])
        (_, _, problem, attempts), calls = self.run_with(plan, [(401, "bad key")])
        self.assertEqual(problem, "auth")
        self.assertEqual(calls, ["a:free"])

    def test_404_recorded_as_not_found(self):
        plan = ["gone:free", ROUTER]
        (sums, model, problem, attempts), _ = self.run_with(plan, [(404, "no"), ok_response(["가"] * 5)])
        self.assertEqual(attempts[0]["outcome"], "not_found")
        self.assertEqual(model, ROUTER)

    def test_partial_success_kept(self):
        (sums, model, problem, _), _ = self.run_with(["a:free"], [ok_response(["가", "나"])])
        self.assertEqual(sums, ["가", "나"])
        self.assertEqual(model, "a:free")


class RepoRotationTest(TempDataDir):
    def test_fresh_first_then_repeats(self):
        items = [{"title": n, "stars": s} for n, s in [("big/a", 900), ("big/b", 800), ("new/c", 50), ("new/d", 40)]]
        picked, n_fresh = curate.rotate_repos(items, {"big/a", "big/b"}, 3)
        self.assertEqual([p["title"] for p in picked], ["new/c", "new/d", "big/a"])
        self.assertEqual(n_fresh, 2)

    def test_recently_featured_from_archive(self):
        self.write_issue("2026-11-15", tools=[{"title": "x/one"}, {"title": "x/two"}])
        self.write_issue("2026-11-01", tools=[{"title": "x/old"}])        # 기간 밖
        self.write_issue("2026-11-16", tools=[{"title": "x/today"}])      # 오늘 재실행은 비교 대상 아님
        self.assertEqual(curate.recently_featured_repos("2026-11-16"), {"x/one", "x/two"})

    def test_collect_github_prefers_unfeatured(self):
        repos = [{"full_name": f"r/{i}", "html_url": "", "stargazers_count": 100 - i} for i in range(12)]
        body = json.dumps({"items": repos})
        seen_urls = []

        def fake_get(url, timeout=30, headers=None):
            seen_urls.append(url)
            return 200, body
        with mock.patch.object(curate, "http_get", fake_get), mock.patch.object(curate.time, "sleep", lambda s: None):
            out = curate.collect_github(["a"], 8, recent={f"r/{i}" for i in range(6)})
        self.assertEqual([o["title"] for o in out], [f"r/{i}" for i in range(6, 12)] + ["r/0", "r/1"])
        self.assertIn(f"per_page={curate.GH_CANDIDATES_PER_TOPIC}", seen_urls[0])


class ArxivPacingTest(unittest.TestCase):
    def test_requests_spaced_and_429_retried_with_backoff(self):
        clock = [1000.0]
        sleeps = []

        def fake_sleep(s):
            sleeps.append(s)
            clock[0] += s
        responses = [(429, "slow down", {"Retry-After": "2"}), (503, "busy", None), (200, "<feed/>", None),
                     (200, "<feed/>", None)]
        stamps = []

        def fake_full(url, timeout=30, headers=None):
            stamps.append(clock[0])
            clock[0] += 0.2          # 응답 시간
            return responses.pop(0)
        with mock.patch.object(curate, "_sleep", fake_sleep), \
                mock.patch.object(curate, "_monotonic", lambda: clock[0]), \
                mock.patch.object(curate, "_http_get_full", fake_full), \
                mock.patch.object(curate, "_arxiv_last", [None]):
            s1, _ = curate.http_get_retry("u1", tries=curate.ARXIV_TRIES, base_wait=curate.ARXIV_BASE_WAIT,
                                          before_each=curate.arxiv_throttle)
            s2, _ = curate.http_get_retry("u2", tries=curate.ARXIV_TRIES, base_wait=curate.ARXIV_BASE_WAIT,
                                          before_each=curate.arxiv_throttle)
        self.assertEqual((s1, s2), (200, 200))
        self.assertEqual(len(stamps), 4)
        gaps = [b - a for a, b in zip(stamps, stamps[1:])]
        self.assertTrue(all(g >= curate.ARXIV_MIN_INTERVAL for g in gaps), gaps)
        self.assertIn(10, sleeps)    # 1차 재시도 대기 (Retry-After 2초보다 기본 대기가 길다)
        self.assertIn(20, sleeps)    # 2차 재시도 대기 (지수 증가)

    def test_retry_after_longer_than_backoff_is_honoured(self):
        sleeps = []
        responses = [(429, "", {"Retry-After": "45"}), (200, "ok", None)]
        with mock.patch.object(curate, "_sleep", sleeps.append), \
                mock.patch.object(curate, "_http_get_full", lambda *a, **k: responses.pop(0)):
            status, _ = curate.http_get_retry("u", tries=3, base_wait=10)
        self.assertEqual(status, 200)
        self.assertEqual(sleeps, [45])

    def test_non_retryable_status_returns_immediately(self):
        calls = []
        with mock.patch.object(curate, "_http_get_full", lambda *a, **k: calls.append(1) or (400, "bad", None)):
            self.assertEqual(curate.http_get_retry("u", tries=4)[0], 400)
        self.assertEqual(len(calls), 1)


class SameDayRerunTest(TempDataDir):
    def test_rerun_with_zero_summaries_keeps_earlier_results(self):
        today = datetime.datetime.now(curate.KST).date().isoformat()
        prev_trending = [{"title": f"t{i}", "url": f"https://e/{i}", "summary_ko": f"요약{i}"} for i in range(3)]
        prev_papers = [{"title": "p", "url": "https://arxiv/p"}]
        self.write_issue(today, summary_model="nemo:free", trending=prev_trending, papers=prev_papers,
                         tools=[], summary_attempts=[{"model": "nemo:free", "outcome": "ok"}])
        new_trending = [{"title": f"t{i}", "url": f"https://e/{i}"} for i in range(5)]
        summarized = []

        def fake_summarize(items, key, today=None):
            summarized.append([it["url"] for it in items])
            return [], None, "transient", [{"model": "a:free", "outcome": "rate_limited"}]
        env = {"OPENROUTER_API_KEY": "test-key", "GITHUB_OUTPUT": ""}
        with mock.patch.dict(os.environ, env), \
                mock.patch.object(curate, "collect_hackernews", lambda t, n: [dict(x) for x in new_trending]), \
                mock.patch.object(curate, "collect_arxiv", lambda t, n: []), \
                mock.patch.object(curate, "collect_github", lambda t, n, recent=None: [{"title": "g/x", "stars": 1}]), \
                mock.patch.object(curate, "summarize_batch", fake_summarize):
            path = curate.main()
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        self.assertEqual([it.get("summary_ko") for it in d["trending"]], ["요약0", "요약1", "요약2", None, None])
        self.assertEqual(summarized, [["https://e/3", "https://e/4"]])   # 빠진 항목만 요약 요청
        self.assertEqual(d["summary_model"], "nemo:free")
        self.assertEqual(d["papers"], prev_papers)                       # 이번 0건 섹션은 앞선 결과 유지
        self.assertEqual(d["counts"]["papers"], 1)
        self.assertEqual(d["summary_attempts"], [{"model": "a:free", "outcome": "rate_limited"}])


if __name__ == "__main__":
    unittest.main()
