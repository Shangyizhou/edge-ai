"""The board launcher rejects overrides before launching any process."""

import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.qwen_lifecycle.board_run import execute, main


class LauncherTests(unittest.TestCase):
    def request(self, argv=None, port=18082):
        return {
            "server": {
                "binary": "must-not-execute",
                "argv": argv or [],
                "port": port,
            }
        }

    def test_loopback_and_identity_cannot_be_overridden(self):
        with tempfile.TemporaryDirectory() as directory:
            for index, flag in enumerate(
                ("--host=0.0.0.0", "--port", "-m", "--hf-repo=x")
            ):
                with self.assertRaises(ValueError):
                    execute(self.request([flag]), Path(directory) / str(index))

    def test_occupied_port_does_not_attach_to_unowned_service(self):
        with tempfile.TemporaryDirectory() as directory:
            self.check_occupied_port(Path(directory))

    def test_cli_failure_does_not_rewrite_existing_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "existing"
            evidence.mkdir()
            (evidence / "sentinel.json").write_text("immutable")
            argv = ["board_run", str(root / "missing.json"), str(evidence)]
            with patch("sys.argv", argv), self.assertRaises(FileNotFoundError):
                main()
            self.assertEqual(
                list(evidence.iterdir()), [evidence / "sentinel.json"]
            )

    def check_occupied_port(self, directory):
        with socket.socket() as server:
            server.bind(("127.0.0.1", 0))
            server.listen()
            with self.assertRaises(OSError):
                execute(
                    self.request(port=server.getsockname()[1]),
                    Path(directory) / "run",
                )


if __name__ == "__main__":
    unittest.main()
