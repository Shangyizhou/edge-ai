"""Dataset construction checks without model inference."""

import json
import tempfile
import unittest
from pathlib import Path

from .datasets import build


class DatasetTests(unittest.TestCase):
    def test_families_counts_and_provenance(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            # Tests supply small schemas; real runs use source schemas.
            tools = [
                {
                    "type": "function",
                    "function": {"name": n, "parameters": {"type": "object"}},
                }
                for n in (
                    "start_camera",
                    "stop_camera",
                    "enable_lidar",
                    "disable_lidar",
                    "enable_tracking",
                    "disable_tracking",
                    "following_status",
                    "volume_set",
                    "play_music",
                )
            ]
            (root / "tools.json").write_text(json.dumps(tools))
            (root / "persona.json").write_text("{}")
            result = build(
                root / "data",
                root / "tools.json",
                root / "persona.json",
                "full",
                set(),
            )
            self.assertEqual(
                [
                    result["splits"][s]["samples"]
                    for s in ("train", "valid", "holdout")
                ],
                [300, 60, 120],
            )
            self.assertEqual(
                result["splits"]["valid"]["kinds"],
                {"tool": 36, "persona": 18, "chat": 6},
            )
            rows = {
                s: [
                    json.loads(x)
                    for x in (root / "data" / (s + ".jsonl"))
                    .read_text()
                    .splitlines()
                ]
                for s in ("train", "valid", "holdout")
            }
            train = {r["source_group"] for r in rows["train"]}
            self.assertFalse(
                train & {r["source_group"] for r in rows["valid"]}
            )
            self.assertTrue(
                any(
                    len(r["messages"][-1].get("tool_calls", [])) == 2
                    for r in rows["train"]
                )
            )
            arguments = [
                call["arguments"]
                for row in rows["valid"]
                for call in row["expected"].get("calls", [])
            ]
            self.assertIn({"song_name": 'a"b'}, arguments)
            self.assertIn({"song_name": "海\\浪"}, arguments)
            self.assertIn({"level": 23.5}, arguments)
            with self.assertRaises(FileExistsError):
                build(
                    root / "data",
                    root / "tools.json",
                    root / "persona.json",
                    "full",
                    set(),
                )

    def test_excluded_prompt_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "tools.json").write_text("[]")
            (root / "persona.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "leakage"):
                build(
                    root / "data",
                    root / "tools.json",
                    root / "persona.json",
                    "full",
                    {"请执行：恢复摄像头采集。"},
                )


class PairingTests(unittest.TestCase):
    def test_unpaired_or_unreviewed_data_cannot_render(self):
        import copy

        from .adaptation_report import render

        case = {
            "id": "one",
            "user": "介绍",
            "expected": {"kind": "persona"},
            "kind": "persona",
        }
        result = {"run_id": "base", "cases": [case]}
        with self.assertRaisesRegex(ValueError, "missing contextual"):
            render([result], {"cases": []}, {}, {}, "")
        other = copy.deepcopy(result)
        other["run_id"] = "lora"
        other["cases"][0]["user"] = "different"
        review = {"cases": [{"run_id": "base", "case_id": "one"}]}
        with self.assertRaisesRegex(ValueError, "unpaired"):
            render([result, other], review, {}, {}, "")


if __name__ == "__main__":
    unittest.main()
