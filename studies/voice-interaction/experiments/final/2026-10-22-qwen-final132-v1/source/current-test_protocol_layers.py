"""Native transport, JSON and Schema are separate layers."""

import unittest

from tools.qwen_lifecycle.protocol import intake

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "x",
            "parameters": {
                "type": "object",
                "properties": {"n": {"type": "number"}},
                "additionalProperties": False,
            },
        },
    }
]
EXPECTED = {"kind": "tool", "calls": [{"name": "x", "arguments": {}}]}
VALID = '<tool_call>{"name":"x","arguments":{}}</tool_call>'


class LayerTests(unittest.TestCase):
    def test_legal_json_bad_native_envelope_is_not_json_failure(self):
        for payload in [
            '{"name":"x","arguments":[]}',
            '{"name":"x"}',
            '{"arguments":{}}',
            '{"name":7,"arguments":{}}',
            '{"name":"x","arguments":{},"extra":1}',
            "[]",
        ]:
            with self.subTest(payload=payload):
                result = intake(
                    "<tool_call>" + payload + "</tool_call>",
                    "stop",
                    TOOLS,
                    EXPECTED,
                )
                self.assertTrue(result["json_valid"])
                self.assertFalse(result["native_parse"])
                self.assertIsNone(result["schema_valid"])
                self.assertFalse(result["expected_behavior"])

    def test_wire_envelope_and_argument_contract_separate_from_json(self):
        for call in [
            {"type": "function", "function": {"name": "x", "arguments": "[]"}},
            {"type": "function", "function": {"name": "x"}},
            {"type": "function", "function": "x"},
            {"type": "function"},
        ]:
            with self.subTest(call=call):
                result = intake("", "tool_calls", TOOLS, EXPECTED, [call])
                self.assertTrue(result["json_valid"])
                self.assertFalse(result["native_parse"])
                self.assertIsNone(result["schema_valid"])

    def test_complete_json_is_not_made_invalid_by_length_finish(self):
        for raw, wire in [
            (VALID, None),
            (
                "",
                [
                    {
                        "type": "function",
                        "function": {"name": "x", "arguments": "{}"},
                    }
                ],
            ),
        ]:
            result = intake(raw, "length", TOOLS, EXPECTED, wire)
            self.assertTrue(result["json_valid"])
            self.assertFalse(result["response_complete"])
            self.assertFalse(result["native_parse"])
            self.assertIsNone(result["schema_valid"])

    def test_missing_or_malformed_markers_do_not_change_json_legality(self):
        for raw in [
            VALID.replace("</tool_call>", ""),
            VALID.replace("</tool_call>", "</tool_call"),
        ]:
            result = intake(raw, "stop", TOOLS, EXPECTED)
            self.assertTrue(result["json_valid"])
            self.assertFalse(result["native_parse"])
        for raw in ["</tool_call>", "<tool_call bad>", "<tool_call"]:
            result = intake(raw, "stop", TOOLS, EXPECTED)
            self.assertIsNone(result["json_valid"])
            self.assertFalse(result["native_parse"])

    def test_invalid_json_fragments_duplicate_and_nonfinite_remain_rejected(
        self,
    ):
        for payload in [
            '{"name":',
            '{"name":"x","arguments":NaN}',
            '{"name":"x","arguments":{},"name":"x"}',
        ]:
            for finish in ["stop", "length"]:
                result = intake(
                    "<tool_call>" + payload + "</tool_call>",
                    finish,
                    TOOLS,
                    EXPECTED,
                )
                self.assertFalse(result["json_valid"])
                self.assertFalse(result["native_parse"])
            wire = [
                {
                    "type": "function",
                    "function": {"name": "x", "arguments": payload},
                }
            ]
            self.assertFalse(
                intake("", "tool_calls", TOOLS, EXPECTED, wire)["json_valid"]
            )

    def test_numeric_overflow_cannot_bypass_nonfinite_policy(self):
        raw = '<tool_call>{"name":"x","arguments":{"n":1e999}}</tool_call>'
        result = intake(raw, "stop", TOOLS, EXPECTED)
        self.assertFalse(result["json_valid"])
        self.assertFalse(result["native_parse"])

    def test_wrong_schema_type_is_native_and_json_valid(self):
        result = intake(
            VALID.replace("{}", '{"n":"bad"}'), "stop", TOOLS, EXPECTED
        )
        self.assertTrue(result["json_valid"])
        self.assertTrue(result["native_parse"])
        self.assertFalse(result["schema_valid"])

    def test_plain_content_and_empty_wire_have_no_tool_json_evidence(self):
        for raw, wire in [('{"name":"x"}', None), ("hello", [])]:
            result = intake(raw, "stop", TOOLS, EXPECTED, wire)
            self.assertIsNone(result["json_valid"])
            self.assertTrue(result["native_parse"])


if __name__ == "__main__":
    unittest.main()
