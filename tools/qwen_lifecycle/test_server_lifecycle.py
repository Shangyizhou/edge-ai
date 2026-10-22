"""Public launcher contracts using offline fixtures."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from . import board_run, mac_run, server_lifecycle
from .benchmark import file_hash


class Response:
    status = 200

    def __init__(self, value):
        self.value = json.dumps(value).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self, *args):
        value, self.value = self.value, b""
        return value


class LifecycleContracts(unittest.TestCase):
    def test_platform_success_and_context_failure_cleanup(self):
        for module, probe in [(mac_run, "otool"), (board_run, "ldd")]:
            for overflow in [False, True]:
                with self.subTest(platform=probe, overflow=overflow):
                    self.exercise(module, probe, overflow)

    def exercise(self, module, probe, overflow):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / "binary"
            binary.write_bytes(b"fixture binary never executed")
            output = root / "output"
            request = {
                "server": {"binary": str(binary), "argv": ["-t", "2"]},
                "candidate": {"model_path": "fixture.gguf"},
                "suite": {"samples": [{"id": "one", "user": "hi"}]},
                "generation": {"max_tokens": 2, "context_tokens": 4},
                "runner": {"kind": "fixture"},
            }
            original = copy.deepcopy(request)
            process = SimpleNamespace(pid=123, returncode=None)
            process.poll = lambda: process.returncode
            process.terminate = lambda: setattr(process, "returncode", -15)
            process.wait = lambda **kwargs: process.returncode
            sampler = SimpleNamespace(
                start=lambda: sampler,
                stop=lambda: {"fixture": True},
                samples=[],
                thread=SimpleNamespace(is_alive=lambda: False),
            )

            def open_response(target, **kwargs):
                if isinstance(target, str):
                    self.assertEqual(target, "http://127.0.0.1:18082/health")
                    return Response({})
                body = json.loads(target.data)
                if target.full_url.endswith("/apply-template"):
                    self.assertEqual(body["messages"][1]["content"], "hi")
                    return Response({"prompt": "whole prompt"})
                self.assertEqual(body["content"], "whole prompt")
                return Response({"tokens": [1, 2, 3] if overflow else [1, 2]})

            raw = {
                "source": {"kind": "fixture"},
                "evidence": [{"path": "cases/one.json", "sha256": "fixture"}],
            }

            def benchmark_run(value, path):
                self.assertEqual(value["runner"]["monitor_pid"], 123)
                self.assertEqual(
                    value["runner"]["endpoint"], "http://127.0.0.1:18082"
                )
                path.mkdir()
                (path / "cases").mkdir()
                (path / "cases/one.json").write_text("immutable")
                (path / "results.json").write_text(json.dumps(raw))
                return raw

            def command(argv, **kwargs):
                if argv[0] == probe:
                    self.assertEqual(
                        argv,
                        [probe]
                        + (["-L"] if probe == "otool" else [])
                        + [str(binary)],
                    )
                return SimpleNamespace(stdout="fixture identity")

            with patch.object(server_lifecycle.socket, "socket"), patch.object(
                server_lifecycle, "asset_manifest", return_value={}
            ), patch.object(
                server_lifecycle.subprocess, "run", side_effect=command
            ), patch.object(
                server_lifecycle.subprocess, "Popen", return_value=process
            ), patch.object(
                server_lifecycle, "ResourceSampler", return_value=sampler
            ), patch.object(
                server_lifecycle.urllib.request,
                "build_opener",
                return_value=SimpleNamespace(open=open_response),
            ), patch.object(
                server_lifecycle, "run", side_effect=benchmark_run
            ), patch.object(
                server_lifecycle, "render", return_value="fixture"
            ):
                if overflow:
                    with self.assertRaisesRegex(ValueError, "context budget"):
                        module.execute(request, output)
                else:
                    handoff = module.execute(request, output)
                    self.assertEqual(
                        handoff["evidence"][0]["path"],
                        "benchmark/cases/one.json",
                    )
                    self.assertEqual(
                        handoff["benchmark_result"]["sha256"],
                        file_hash(output / "benchmark/results.json"),
                    )
                    self.assertEqual(
                        json.loads(
                            (output / "benchmark/results.json").read_text()
                        ),
                        raw,
                    )
                    self.assertEqual(
                        raw["evidence"][0]["path"], "cases/one.json"
                    )
            self.assertEqual(
                json.loads((output / "launcher-request.json").read_text()),
                original,
            )
            self.assertEqual(
                json.loads((output / "server-command.json").read_text()),
                [
                    str(binary),
                    "-m",
                    "fixture.gguf",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "18082",
                    "-t",
                    "2",
                ],
            )
            self.assertIn(
                probe, json.loads((output / "runtime.json").read_text())
            )
            self.assertEqual(process.returncode, -15)
            self.assertTrue((output / "owned-process-exit.json").is_file())
            self.assertEqual(
                (output / "launcher-failure.json").exists(), overflow
            )
