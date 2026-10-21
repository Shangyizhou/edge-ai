"""验证量化开关实际传给SDK、失败证据保留且不覆盖旧候选。"""

import argparse
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from asr_ptq import build


class QuantizationContractTest(unittest.TestCase):
    def test_sdk_receives_quantization_and_keeps_failed_stage(self):
        """SDK替身只验证调用和证据契约，不当作真实量化成功。"""
        for quantized, returncode in ((False, 0), (True, 0), (True, -1)):
            with self.subTest(quantized=quantized, returncode=returncode):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    model = root / "onnx"
                    model.mkdir()
                    source = model / "joiner-epoch-99-avg-1.onnx"
                    source.write_bytes(b"original fixture model")
                    calibration = root / "calibration"
                    calibration.mkdir()
                    (calibration / "manifest.json").write_text("{}")
                    (calibration / "joiner.txt").write_text("input.npy\n")
                    calls = []
                    configurations = []

                    class SDK:
                        def __init__(self, **kwargs):
                            pass

                        def config(self, **kwargs):
                            configurations.append(kwargs)
                            return 0

                        def load_onnx(self, **kwargs):
                            return 0

                        def build(self, **kwargs):
                            calls.append(kwargs)
                            return returncode

                        def export_rknn(self, path):
                            Path(path).write_bytes(b"candidate")
                            return 0

                        def release(self):
                            pass

                    module = types.ModuleType("rknn.api")
                    module.RKNN = SDK
                    args = argparse.Namespace(
                        model=model,
                        output=root / "output",
                        component="joiner",
                        int8=quantized,
                        calibration=calibration,
                        optimization_level=0,
                    )
                    with patch.dict(
                        sys.modules,
                        {"rknn": types.ModuleType("rknn"), "rknn.api": module},
                    ):
                        if returncode:
                            with self.assertRaises(RuntimeError):
                                build(args)
                        else:
                            build(args)
                        document = json.loads(
                            (args.output / "joiner-build.json").read_text()
                        )
                        self.assertEqual(
                            document["status"], "error" if returncode else "ok"
                        )
                        self.assertEqual(
                            configurations[0]["optimization_level"], 0
                        )
                        self.assertEqual(
                            calls[0]["do_quantization"], quantized
                        )
                        self.assertEqual(
                            calls[0]["dataset"],
                            str((calibration / "joiner.txt").resolve())
                            if quantized
                            else None,
                        )
                        self.assertEqual(
                            source.read_bytes(), b"original fixture model"
                        )
                        with self.assertRaises(FileExistsError):
                            build(args)
