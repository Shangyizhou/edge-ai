"""Reject omitted cases, changed controls and unreviewed claims."""

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from .final_report import quantile, render, summarize_final
from .mac_run import launcher_handoff


class FinalAccountingTests(unittest.TestCase):
    def fixture(self):
        cases = []
        for ident, kind in [
            ("single", "tool"),
            ("persona", "persona"),
            ("multi", "tool"),
        ]:
            expected = {"kind": kind}
            if kind == "tool":
                expected["calls"] = [{}] * (2 if ident == "multi" else 1)
            cases.append(
                {
                    "id": ident,
                    "kind": kind,
                    "user": ident,
                    "messages": [],
                    "expected": expected,
                    "assessment": {"response_complete": True},
                }
            )
        suite = {
            "samples": [
                dict(
                    c,
                    cohort=(
                        "supplemental-multicall"
                        if c["id"] == "multi"
                        else "original-holdout"
                    ),
                )
                for c in cases
            ]
        }
        result = {"run_id": "frozen", "candidate": {}, "cases": cases}
        review = {
            "reviewer": "Codex assistant",
            "human_review": False,
            "cases": [
                {
                    "run_id": "frozen",
                    "case_id": "persona",
                    "passed": False,
                    "reason": "fabricated name",
                    "claims": [{"claim": "name", "passed": False}],
                }
            ],
        }
        return result, suite, review

    def test_separate_request_and_call_denominators_and_review(self):
        r, s, v = self.fixture()
        groups = summarize_final([r], s, v)["runs"][0]["cohorts"]
        self.assertEqual([g["samples"] for g in groups], [2, 1, 3])
        self.assertEqual([g["expected_calls"] for g in groups], [1, 2, 3])
        self.assertEqual(groups[-1]["contextual_persona_pass"], 0)
        self.assertEqual(groups[-1]["valid_call_latency"]["n"], 0)
        self.assertEqual(groups[-1]["format_gate"], "UNMET")

    def test_persona_misroute_latency_never_enters_tool_success_stats(self):
        result, suite, review = self.fixture()
        persona = result["cases"][1]
        persona["status"] = "completed"
        persona["valid_call_seconds"] = 0.001
        persona["assessment"].update(
            {
                key: True
                for key in (
                    "native_parse",
                    "json_valid",
                    "schema_valid",
                    "registry_valid",
                )
            }
        )
        persona["assessment"]["reply"] = {
            "tool_calls": [{"name": "following_status"}]
        }
        combined = summarize_final([result], suite, review)["runs"][0][
            "cohorts"
        ][-1]
        self.assertEqual(combined["valid_call_latency"]["n"], 0)
        self.assertEqual(combined["persona_unintended_tool_requests"], 1)
        self.assertEqual(combined["persona_gate"], "UNMET")

    def test_omitted_case_or_changed_target_rejected(self):
        r, s, v = self.fixture()
        for mutation in ("omit", "target"):
            changed = copy.deepcopy(r)
            if mutation == "omit":
                changed["cases"].pop()
            else:
                changed["cases"][0]["expected"]["calls"] = []
            with self.assertRaisesRegex(ValueError, "cohort"):
                summarize_final([changed], s, v)

    def test_missing_duplicate_or_keyword_only_review_rejected(self):
        r, s, v = self.fixture()
        for reviews in ([], v["cases"] * 2, [dict(v["cases"][0], claims=[])]):
            with self.assertRaises(ValueError):
                summarize_final([r], s, dict(v, cases=reviews))

    def test_launcher_evidence_resolves_without_rewriting_raw(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            benchmark = root / "benchmark"
            benchmark.mkdir()
            evidence = benchmark / "case.json"
            evidence.write_text("immutable output")
            digest = hashlib.sha256(evidence.read_bytes()).hexdigest()
            raw = {
                "source": {"kind": "device_measurement"},
                "evidence": [{"path": "case.json", "sha256": digest}],
            }
            result_path = benchmark / "results.json"
            result_path.write_text(json.dumps(raw))
            before = result_path.read_bytes()
            handoff = launcher_handoff(raw, result_path)
            ref = handoff["evidence"][0]
            self.assertEqual(
                hashlib.sha256((root / ref["path"]).read_bytes()).hexdigest(),
                ref["sha256"],
            )
            self.assertEqual(raw["evidence"][0]["path"], "case.json")
            self.assertEqual(result_path.read_bytes(), before)
            self.assertEqual(
                handoff["benchmark_result"]["sha256"],
                hashlib.sha256(before).hexdigest(),
            )

    def test_html_escapes_outputs_and_keeps_all_cohorts_offline(self):
        result, suite, review = self.fixture()
        result["candidate"] = {
            "parameter_count": 1,
            "precision": "Q4",
            "runtime_version": "pinned",
            "backend": "CPU",
            "context_tokens": 2048,
            "kv_type": "q8",
        }
        result["artifacts"] = {"total_bytes": 1}
        for c in result["cases"]:
            c["assessment"]["reply"] = {
                "content": "<script>alert('model')</script>",
                "tool_calls": [],
            }
        stage = {
            "method": "method",
            "finding": "observed",
            "table": [],
            "examples": [],
            "limit": "limit",
            "evidence": {},
        }
        document = {
            "results": [result],
            "suite": suite,
            "review": review,
            "conclusion": "measured",
            "stages": {
                name: stage
                for name in ("baseline", "training", "merge", "quantization")
            },
            "limitations": ["visual unverified"],
            "freeze": {},
        }
        with self.assertRaisesRegex(ValueError, "four-run"):
            render(document)
        cases = []
        for kind, count in (
            ("tool", 72),
            ("persona", 36),
            ("chat", 12),
            ("multi", 12),
        ):
            for i in range(count):
                c = copy.deepcopy(result["cases"][0])
                c.update(
                    id=f"{kind}_{i}", kind="tool" if kind == "multi" else kind
                )
                c["expected"] = {"kind": c["kind"]}
                if c["kind"] == "tool":
                    c["expected"]["calls"] = [{}] * (
                        3
                        if kind == "multi" and i < 4
                        else 2
                        if kind == "multi"
                        else 1
                    )
                cases.append(c)
        suite["samples"] = [
            dict(
                c,
                cohort="supplemental-multicall"
                if c["id"].startswith("multi")
                else "original-holdout",
            )
            for c in cases
        ]
        result["cases"] = cases
        document["results"] = [
            dict(copy.deepcopy(result), run_id=f"run{i}") for i in range(4)
        ]
        review["cases"] = [
            dict(review["cases"][0], run_id=r["run_id"], case_id=c["id"])
            for r in document["results"]
            for c in cases
            if c["kind"] == "persona"
        ]
        output, _ = render(document)
        self.assertNotIn("<script>alert('model')", output)
        self.assertIn("&lt;script&gt;", output)
        self.assertIn("supplemental-multicall", output)
        self.assertIn("data:application/json;base64,", output)
        self.assertIn('id="top"', output)
        self.assertIn("@media(max-width:760px)", output)
        self.assertNotIn('src="http', output)

    def test_nearest_rank_uses_actual_observations(self):
        self.assertEqual(quantile([1, 2, 3, None], 0.95), 3)
        self.assertIsNone(quantile([], 0.95))


if __name__ == "__main__":
    unittest.main()
