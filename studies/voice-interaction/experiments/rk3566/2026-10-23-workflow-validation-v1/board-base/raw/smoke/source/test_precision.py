"""Pairing and local lifecycle safety at observable boundaries."""

import copy
import json
import tempfile
import unittest
from pathlib import Path

from .mac_run import execute
from .normalize_tied import normalize
from .precision_report import paired, render


class PrecisionTests(unittest.TestCase):
    def test_pairing_rejects_prompt_or_target_drift(self):
        original = {
            "cases": [
                {"id": "x", "user": "你好", "expected": {}, "messages": []}
            ]
        }
        paired([original, copy.deepcopy(original)])
        for key, value in [
            ("user", "别的输入"),
            ("expected", {"kind": "chat"}),
            ("messages", [{"role": "system", "content": "facts"}]),
        ]:
            changed = copy.deepcopy(original)
            changed["cases"][0][key] = value
            with self.assertRaisesRegex(ValueError, "unpaired"):
                paired([original, changed])

    def test_report_requires_contextual_persona_review(self):
        result = {
            "run_id": "real",
            "cases": [
                {
                    "id": "p",
                    "user": "姓名",
                    "expected": {},
                    "messages": [],
                    "kind": "persona",
                }
            ],
        }
        with self.assertRaisesRegex(ValueError, "contextual review"):
            render([result], {"cases": []}, [], {})

    def test_mac_launcher_rejects_remote_or_model_override(self):
        with tempfile.TemporaryDirectory() as directory:
            for i, argument in enumerate(
                ["--host=0.0.0.0", "-m", "--hf-repo=x"]
            ):
                with self.assertRaises(ValueError):
                    execute(
                        {
                            "server": {
                                "argv": [argument],
                                "binary": "forbidden",
                            }
                        },
                        Path(directory) / str(i),
                    )


class TiedNormalizationTests(unittest.TestCase):
    def fixture(self, directory, head):
        import mlx.core as mx

        source = Path(directory) / "source"
        source.mkdir()
        (source / "config.json").write_text(
            json.dumps({"model_type": "qwen3", "tie_word_embeddings": True})
        )
        mx.save_safetensors(
            str(source / "model.safetensors"),
            {
                "model.embed_tokens.weight": mx.array([[1.0, 2.0]]),
                "lm_head.weight": mx.array([head]),
                "retained.weight": mx.array([3.0]),
            },
        )
        return source

    def test_exact_tied_serialization_preserves_all_retained_values(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.fixture(directory, [1.0, 2.0])
            proof = normalize(source, Path(directory) / "normalized")
            self.assertEqual(proof["output_unique_parameters"], 3)
            self.assertTrue(
                proof["all_retained_tensors_value_and_dtype_equal"]
            )
            self.assertTrue((source / "model.safetensors").is_file())

    def test_unequal_head_is_never_deduplicated(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.fixture(directory, [9.0, 2.0])
            target = Path(directory) / "normalized"
            with self.assertRaisesRegex(ValueError, "not bit-value identical"):
                normalize(source, target)
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
