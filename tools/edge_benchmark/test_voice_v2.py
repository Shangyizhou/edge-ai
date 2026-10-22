"""Exercise v2 output boundaries without launching inference engines."""

import json
import sys
import tempfile
import types
import unittest
import wave
from pathlib import Path
from unittest.mock import patch
import voice_v2


class VoiceV2Tests(unittest.TestCase):
    def test_modified_audio_is_rejected_before_model_load(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)
            (p / "audio.wav").write_bytes(b"changed")
            (p / "fixtures.json").write_text(
                json.dumps(
                    {
                        "fixtures": [
                            {
                                "id": "x",
                                "path": str(p / "audio.wav"),
                                "sha256": "wrong",
                            }
                        ]
                    }
                )
            )
            with patch.dict(
                sys.modules,
                {
                    "numpy": types.ModuleType("numpy"),
                    "sherpa_onnx": types.ModuleType("sherpa_onnx"),
                },
            ):
                with self.assertRaisesRegex(
                    ValueError, "fixture hash mismatch"
                ):
                    voice_v2.asr({"fixtures": str(p / "fixtures.json")}, p)

    def test_pcm_rejects_wrong_rate(self):
        # numpy is loaded only by actual adapters; test via board venv for this case.
        try:
            import numpy
        except ImportError:
            self.skipTest("numpy not in test interpreter")
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "bad.wav"
            with wave.open(str(p), "wb") as f:
                f.setparams((1, 2, 8000, 0, "NONE", ""))
                f.writeframes(b"\0\0" * 80)
            with self.assertRaisesRegex(ValueError, "16kHz"):
                voice_v2.pcm(p)

    def test_phase_events_share_monotonic_clock(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)
            with patch.object(
                voice_v2.time, "monotonic", side_effect=[10.0, 12.0]
            ):
                voice_v2.phase(p, "inference", "start")
                voice_v2.phase(p, "inference", "end")
            rows = [
                json.loads(x)
                for x in (p / "events.jsonl").read_text().splitlines()
            ]
            self.assertEqual(
                [r["monotonic_seconds"] for r in rows], [10.0, 12.0]
            )
            self.assertEqual([r["state"] for r in rows], ["start", "end"])

    def test_llm_v2_uses_chatml_greedy_and_records_first_sentence(self):
        import workers

        class Server:
            def poll(self):
                return None

            def terminate(self):
                pass

            def wait(self, timeout=None):
                return 0

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def __iter__(self):
                for chunk in [
                    {"content": "你好"},
                    {"content": "。"},
                    {"content": "", "stop_type": "eos"},
                ]:
                    yield b"data: " + json.dumps(chunk).encode() + b"\n"

        requests = []

        def open_stream(request, timeout):
            requests.append(json.loads(request.data))
            return Response()

        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)
            config = dict(
                binary="/fake/server",
                model="/fake/model",
                threads=2,
                texts=["测试"],
                system="系统",
                protocol_id="rk3566-voice-screen-v2",
                chat_template="chatml",
                temperature=0,
            )
            with patch.object(
                workers.subprocess, "Popen", return_value=Server()
            ), patch.object(
                workers, "request_json", return_value={"status": "ok"}
            ), patch.object(
                workers, "urlopen", side_effect=open_stream
            ), patch.object(
                workers.time, "sleep"
            ):
                workers.llama(config, p)
            self.assertEqual(requests[0]["temperature"], 0)
            self.assertFalse(requests[0]["cache_prompt"])
            self.assertEqual(
                requests[0]["prompt"],
                "<|im_start|>system\n系统<|im_end|>\n<|im_start|>user\n测试<|im_end|>\n<|im_start|>assistant\n",
            )
            rows = [
                json.loads(x)
                for x in (p / "events.jsonl").read_text().splitlines()
            ]
            sample = next(r for r in rows if r["event"] == "sample")
            self.assertEqual(sample["reply"], "你好。")
            self.assertIsNotNone(sample["first_sentence_seconds"])
            self.assertGreaterEqual(
                sample["first_sentence_seconds"], sample["ttft_seconds"]
            )

    def test_preflight_rejects_tampered_weight(self):
        import hashlib
        import voice_preflight

        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)
            weight = p / "model.gguf"
            weight.write_bytes(b"original")
            row = dict(
                path=str(weight),
                sha256=hashlib.sha256(b"original").hexdigest(),
            )
            (p / "assets-manifest.json").write_text(json.dumps([row]))
            (p / "runtime-manifest.json").write_text(json.dumps({"files": []}))
            (p / "asr-fixtures.json").write_text(json.dumps({"fixtures": []}))
            for module in ("asr", "tts", "llm"):
                (p / (module + "-screening.json")).write_text(
                    json.dumps({"budget_seconds": 600, "cases": []})
                )
            self.assertEqual(
                voice_preflight.verify(p)["status"], "READY_FOR_SCREENING"
            )
            weight.write_bytes(b"changed")
            result = voice_preflight.verify(p)
            self.assertEqual(result["status"], "NOT_READY")
            self.assertIn("hash mismatch " + str(weight), result["errors"])


if __name__ == "__main__":
    unittest.main()
