"""Renderer cache and token-counter regression checks."""

import copy
import json
import unittest

from tools.qwen_lifecycle.report import render


def fixture():
    return {
        "schema": "edge-model-benchmark/result-v1",
        "run_id": "synthetic-cache-render-only",
        "source": {"kind": "synthetic_fixture"},
        "candidate": {},
        "environment": {"system": "fixture"},
        "stage": "render test only",
        "artifacts": {"total_bytes": 0},
        "measurement": {"cache": "HTTP cache_prompt=true <fixture>"},
        "summary": {
            "schema_valid": 1,
            "tool_samples": 1,
            "native_calls": 1,
            "persona_valid": 0,
            "persona_samples": 0,
            "tool_expected_behavior": 1,
        },
        "cases": [
            {
                "id": "one",
                "kind": "tool",
                "user": "test",
                "expected": {"kind": "tool"},
                "assessment": {"expected_behavior": True},
                "generation": {
                    "raw": "fixture",
                    "prompt_tokens": 925,
                    "evaluated_prefill_tokens": 7,
                    "cache_prompt": True,
                    "native_usage": {"prompt_tokens": 925},
                    "native_timings": {"prompt_n": 7, "cache_n": 918},
                    "timing_source": "fixture evaluated prefill <counter>",
                },
            }
        ],
    }


class ReportTests(unittest.TestCase):
    def test_cached_http_usage_and_evaluated_work_remain_distinct(self):
        result = fixture()
        before = json.dumps(result, sort_keys=True)
        rendered = render([result])
        self.assertIn("HTTP cache_prompt=true &lt;fixture&gt;", rendered)
        self.assertNotIn("每例新建模型prompt cache", rendered)
        stats = rendered.split('<div class="stats">', 1)[1].split("</div>", 1)[
            0
        ]
        self.assertIn("完整输入 usage 925 tokens", stats)
        self.assertIn("实际 prefill 7 tokens", stats)
        self.assertIn("cache_prompt True", stats)
        self.assertIn("fixture evaluated prefill &lt;counter&gt;", rendered)
        self.assertIn("不等于服务端prefill或decode计时", rendered)
        self.assertIn("不用输入减prefill推算", rendered)
        self.assertEqual(before, json.dumps(result, sort_keys=True))

    def test_missing_usage_is_not_replaced_by_evaluated_or_zero(self):
        result = copy.deepcopy(fixture())
        del result["measurement"]["cache"]
        del result["cases"][0]["generation"]["prompt_tokens"]
        rendered = render([result])
        stats = rendered.split('<div class="stats">', 1)[1].split("</div>", 1)[
            0
        ]
        self.assertIn("缓存策略：未记录", rendered)
        self.assertIn("完整输入 usage 未测 tokens", stats)
        self.assertIn("实际 prefill 7 tokens", stats)

    def test_back_to_top_is_not_a_chapter_candidate(self):
        rendered = render([fixture()])
        self.assertIn('<a href="#top">回到顶部</a>', rendered)
        script = rendered.split("<script>", 1)[1]
        self.assertIn(
            'links.filter(a=>a.getAttribute("href")!=="#top")', script
        )
        self.assertIn("for(const a of chapters)", script)
        self.assertNotIn('let id="summary";for(const a of links)', script)


if __name__ == "__main__":
    unittest.main()
