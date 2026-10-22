"""Reject omitted cases, changed controls and unreviewed claims."""

import copy
import unittest

from .final_report import quantile, summarize_final


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

    def test_nearest_rank_uses_actual_observations(self):
        self.assertEqual(quantile([1, 2, 3, None], 0.95), 3)
        self.assertIsNone(quantile([], 0.95))


if __name__ == "__main__":
    unittest.main()
