"""HTTP counter boundaries and explicit cache control."""

import json
import unittest
from unittest.mock import patch

from tools.qwen_lifecycle.runners import LlamaHttpRunner


class HTTPTests(unittest.TestCase):
    def test_cache_and_usage_are_preserved_without_conflating_prefill(self):
        for cache in (False, True):
            captured = []

            class Response:
                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    pass

                def __iter__(self):
                    event = {
                        "choices": [
                            {
                                "delta": {"content": "好"},
                                "finish_reason": "stop",
                            }
                        ],
                        "usage": {
                            "prompt_tokens": 400,
                            "completion_tokens": 2,
                        },
                        "timings": {
                            "prompt_n": 10,
                            "prompt_ms": 20,
                            "predicted_n": 2,
                        },
                    }
                    yield ("data: " + json.dumps(event)).encode()
                    yield b"data: [DONE]"

            class Opener:
                def open(self, request, **kwargs):
                    captured.append(json.loads(request.data))
                    return Response()

            with patch("urllib.request.build_opener", return_value=Opener()):
                runner = LlamaHttpRunner(
                    {
                        "runner": {"endpoint": "http://127.0.0.1:1"},
                        "candidate": {},
                    }
                )
            result = runner.generate(
                [], [], {"cache_prompt": cache}, lambda e: None
            )
            self.assertEqual(captured[0]["cache_prompt"], cache)
            self.assertEqual(result["prompt_tokens"], 400)
            self.assertEqual(result["evaluated_prefill_tokens"], 10)
            self.assertEqual(result["native_usage"]["completion_tokens"], 2)
            self.assertEqual(result["prefill_seconds"], 0.02)


if __name__ == "__main__":
    unittest.main()
