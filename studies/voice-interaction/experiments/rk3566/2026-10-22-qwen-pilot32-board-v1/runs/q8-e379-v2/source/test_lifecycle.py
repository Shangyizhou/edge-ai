"""Observable native intake and read-only evidence/report contracts."""

import json
import tempfile
import unittest
from pathlib import Path

from tools.qwen_lifecycle.benchmark import run
from tools.qwen_lifecycle.protocol import intake, native_reply, ProtocolError
from tools.qwen_lifecycle.report import render


TOOLS = [{"type": "function", "function": {"name": "volume_set",
    "parameters": {"type": "object", "properties": {"level": {"type": "number"}},
                   "required": ["level"], "additionalProperties": False}}}]
EXPECTED = {"kind": "tool", "calls": [{"name": "volume_set", "arguments": {"level": 30}}]}
VALID = '<tool_call>{"name":"volume_set","arguments":{"level":30}}</tool_call>'


class ProtocolTests(unittest.TestCase):
    def test_native_marker_and_wire_transport_reach_same_intake(self):
        marked = intake(VALID, "stop", TOOLS, EXPECTED)
        wire = intake("", "tool_calls", TOOLS, EXPECTED, [{"type": "function",
            "function": {"name": "volume_set", "arguments": '{"level":30}'}}])
        self.assertTrue(marked["schema_valid"])
        self.assertTrue(marked["expected_behavior"])
        self.assertEqual(marked["reply"]["tool_calls"], wire["reply"]["tool_calls"])

    def test_plain_json_never_creates_native_calls(self):
        plain = intake('{"tool_calls":[{"name":"volume_set","arguments":{"level":30}}]}',
                       "stop", TOOLS, EXPECTED)
        self.assertEqual(plain["reply"]["tool_calls"], [])
        self.assertIsNone(plain["schema_valid"])
        self.assertFalse(plain["expected_behavior"])

    def test_unknown_and_wrong_type_are_json_valid_but_rejected(self):
        for raw in [VALID.replace("volume_set", "unknown"),
                    VALID.replace('"level":30', '"level":"30"')]:
            result = intake(raw, "stop", TOOLS, EXPECTED)
            self.assertTrue(result["json_valid"])
            self.assertFalse(result["schema_valid"])

    def test_duplicate_nonfinite_and_truncated_output_are_rejected(self):
        for raw, finish in [
            (VALID.replace('"level":30', '"level":30,"level":40'), "stop"),
            (VALID.replace('"level":30', '"level":NaN'), "stop"),
            (VALID, "length"), (VALID[:-12], "stop")]:
            self.assertFalse(intake(raw, finish, TOOLS, EXPECTED)["native_parse"])

    def test_order_repeat_unicode_and_persona_rules(self):
        reply = native_reply(VALID + "\n" + VALID)
        self.assertEqual(len(reply["tool_calls"]), 2)
        self.assertNotEqual(reply["tool_calls"][0]["call_id"], reply["tool_calls"][1]["call_id"])
        persona = intake("我是小沫，科研AI。", "stop", TOOLS,
                         {"kind": "persona", "contains_all": ["小沫", "科研"]})
        self.assertTrue(persona["persona_valid"])
        self.assertIsNone(persona["schema_valid"])


class ExperimentTests(unittest.TestCase):
    def test_synthetic_runner_preserves_all_failures_and_embedded_results(self):
        class FakeRunner:
            identity = {"name": "fixture", "version": "test", "backend": "none"}
            def generate(self, messages, tools, config, on_event):
                on_event({"text": VALID})
                return {"raw": VALID, "finish_reason": "stop", "wire_calls": None,
                        "wall_seconds": 0.01, "prompt_tokens": 10,
                        "output_tokens": 5, "ttft_seconds": 0.001,
                        "prefill_tokens_per_second": None,
                        "decode_tokens_per_second": None}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model = root / "model.gguf"
            model.write_bytes(b"synthetic test model, never inference")
            request = {"schema": "edge-model-benchmark/request-v1", "run_id": "fixture",
                "candidate": {"model_path": str(model), "model": "<script>"},
                "runner": {}, "suite": {"tools": TOOLS, "samples": [
                    {"id": "one", "user": "音量30", "expected": EXPECTED},
                    {"id": "two", "user": "介绍", "expected": {"kind": "persona",
                     "contains_all": ["小沫"]}}]}}
            result = run(request, root / "out", FakeRunner(), "synthetic_fixture")
            self.assertEqual(result["summary"]["schema_valid"], 1)
            self.assertEqual(result["summary"]["persona_valid"], 0)
            self.assertTrue((root / "out/events/one.json").exists())
            before = (root / "out/results.json").read_bytes()
            rendered = render([result])
            self.assertIn("仅合成夹具", rendered)
            self.assertIn("&lt;script&gt;", rendered)
            self.assertIn("data:application/json;base64,", rendered)
            self.assertEqual(before, (root / "out/results.json").read_bytes())
            with self.assertRaises(ValueError):
                run(request, root / "bad", FakeRunner())


if __name__ == "__main__":
    unittest.main()
