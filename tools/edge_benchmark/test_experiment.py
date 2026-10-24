"""统一入口的离线契约测试；替身不会加载任何真实模型。"""

import copy
import json
import sys
import tempfile
import time
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from tools.edge_benchmark.execution import execute_candidate, run_plan
from tools.edge_benchmark.experiment import (
    digest,
    freeze,
    read_json,
    validate_plan,
    write_json,
)
from tools.experiment_tracking.record_execution import (
    metric_values,
    verify_execution,
)


class ExperimentTests(unittest.TestCase):
    """验证计划、身份、失败分母与只读同步边界。"""

    def setUp(self) -> None:
        """创建独立的合成资产与题集。"""
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.model = self.root / "model.gguf"
        self.model.write_bytes(b"synthetic; not a real model")
        self.suite = self.root / "suite.json"
        write_json(
            self.suite,
            {
                "tools": [],
                "samples": [
                    {
                        "id": "one",
                        "user": "你好",
                        "expected": {"kind": "chat"},
                        "tools": [],
                    }
                ],
            },
        )
        self.request = {
            "schema": "edge-benchmark/request-v1",
            "name": "synthetic",
            "task": "qwen_tool_calls",
            "protocol_id": "fixture-v1",
            "device": "local",
            "suite": {"path": str(self.suite), "sha256": digest(self.suite)},
            "budget": {"total_seconds": 1, "case_timeout_seconds": 0.1},
            "candidates": [
                {
                    "id": "first",
                    "model_id": "synthetic-model",
                    "precision": "synthetic",
                    "python": sys.executable,
                    "request": {
                        "candidate": {"model_path": str(self.model)},
                        "runner": {"kind": "mlx"},
                        "generation": {
                            "max_tokens": 8,
                            "context_tokens": 128,
                            "temperature": 0,
                        },
                    },
                }
            ],
        }

    def plan(self, request=None, name="plan") -> dict:
        """仅执行冻结，不允许启动子进程。"""
        path = self.root / (name + "-request.json")
        write_json(path, request or self.request)
        with patch(
            "subprocess.Popen", side_effect=AssertionError("execution")
        ):
            return freeze(path, self.root / name)

    def test_plan_is_offline_and_detects_asset_change(self) -> None:
        """模型只参与哈希，内容变更时禁止执行。"""
        plan = self.plan()
        validate_plan(plan)
        self.assertEqual(plan["maximum_requests"], 1)
        self.model.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "changed asset"):
            validate_plan(plan)

    def test_directory_additions_invalidate_plan(self) -> None:
        """新增 adapter 文件也必须改变模型身份。"""
        directory = self.root / "model"
        directory.mkdir()
        (directory / "config.json").write_text("{}")
        self.request["candidates"][0]["request"]["candidate"]["model_path"] = (
            str(directory)
        )
        plan = self.plan()
        (directory / "new.safetensors").write_bytes(b"synthetic")
        with self.assertRaisesRegex(ValueError, "changed model directory"):
            validate_plan(plan)

    def test_bad_configuration_never_executes(self) -> None:
        """拒绝拼错字段、预算、占位符和远程调度。"""
        variants = []
        for key, value in [
            ("typo", 1),
            ("device", "orangepi-ts"),
            ("task", "arbitrary"),
            ("name", "<replace>"),
        ]:
            item = copy.deepcopy(self.request)
            item[key] = value
            variants.append(item)
        item = copy.deepcopy(self.request)
        item["budget"]["total_seconds"] = -1
        variants.append(item)
        item = copy.deepcopy(self.request)
        item["candidates"][0]["request"]["generation"]["typo"] = 1
        variants.append(item)
        for index, item in enumerate(variants):
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.plan(item, "invalid" + str(index))

    def test_duplicate_json_keys_are_rejected(self) -> None:
        """配置不可通过重复键改变含义。"""
        path = self.root / "duplicate.json"
        path.write_text('{"task":1,"task":2}')
        with self.assertRaises(ValueError):
            read_json(path)

    def test_hash_mismatch_and_duplicate_ids(self) -> None:
        """输入身份和候选身份均需唯一。"""
        self.request["suite"]["sha256"] = "wrong"
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self.plan()
        self.request["suite"]["sha256"] = digest(self.suite)
        self.request["candidates"] *= 2
        with self.assertRaisesRegex(ValueError, "duplicate candidate"):
            self.plan()

    def test_synthetic_run_preserves_unrun_candidates(self) -> None:
        """取消保留后续未运行项，替身证据明确标识合成。"""
        second = copy.deepcopy(self.request["candidates"][0])
        second["id"] = "second"
        self.request["candidates"].append(second)
        self.plan()
        calls = []

        def cancelled(*args):
            calls.append(args)
            return {"status": "cancelled"}

        result = run_plan(
            self.root / "plan/plan.json", self.root / "run", cancelled
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["source_kind"], "synthetic_fixture")
        self.assertEqual(result["candidates"][1]["status"], "not_run")
        verify_execution(self.root / "run")
        self.assertFalse(list((self.root / "run").rglob("*.html")))

    def test_total_budget_preserves_remaining_candidate(self) -> None:
        """总预算耗尽不继续第二候选，也不丢弃首个结果。"""
        second = copy.deepcopy(self.request["candidates"][0])
        second["id"] = "second"
        self.request["candidates"].append(second)
        self.plan()
        with patch(
            "tools.edge_benchmark.execution.time.monotonic",
            side_effect=[0, 0, 2, 2],
        ):
            result = run_plan(
                self.root / "plan/plan.json",
                self.root / "run",
                lambda *args: {"status": "completed"},
            )
        self.assertEqual(result["candidates"][0]["status"], "completed")
        self.assertEqual(result["candidates"][1]["status"], "not_run")
        self.assertEqual(result["status"], "partial")

    def test_changed_evidence_cannot_sync(self) -> None:
        """已保存结果被改动后拒绝补同步。"""
        self.plan()
        run_plan(
            self.root / "plan/plan.json",
            self.root / "run",
            lambda *args: {"status": "failed"},
        )
        (self.root / "run/plan.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "changed execution evidence"):
            verify_execution(self.root / "run")

    def test_completion_denominator_includes_failed_and_unrun(self) -> None:
        """没有结果的案例仍保留在请求分母内。"""
        values = metric_values(
            {
                "planned_cases": 3,
                "result": {
                    "cases": [{"id": "one", "status": "completed"}],
                    "summary": {"cer": None},
                },
            }
        )
        self.assertEqual(values["completion_rate"], 1 / 3)
        self.assertNotIn("cer", values)

    def test_asr_plan_validates_audio_and_references(self) -> None:
        """ASR 计划验证音频格式，不导入识别引擎。"""
        audio = self.root / "one.wav"
        with wave.open(str(audio), "wb") as stream:
            stream.setparams((1, 2, 16000, 0, "NONE", ""))
            stream.writeframes(b"\x00\x00" * 160)
        write_json(
            self.suite,
            {
                "fixtures": [
                    {
                        "id": "one",
                        "path": "one.wav",
                        "energy_end_s": 0.005,
                        "reference": {
                            "kind": "manual_verified",
                            "source": "synthetic",
                            "text": "你好",
                        },
                    }
                ]
            },
        )
        model = self.root / "asr-model"
        model.mkdir()
        for name in (
            "encoder-epoch-99-avg-1.int8.onnx",
            "decoder-epoch-99-avg-1.onnx",
            "joiner-epoch-99-avg-1.int8.onnx",
            "tokens.txt",
        ):
            (model / name).write_bytes(b"synthetic")
        self.request.update(task="asr_transcription")
        self.request["suite"]["sha256"] = digest(self.suite)
        self.request["candidates"][0]["request"] = {
            "kind": "streaming_asr",
            "binary": sys.executable,
            "model": str(model),
            "threads": 2,
            "provider": "cpu",
            "realtime": True,
            "chunk_ms": 100,
            "tail_seconds": 3.2,
            "endpoint_silence": 1.2,
        }
        plan = self.plan()
        self.assertTrue(
            any(
                item["path"] == str(audio.resolve()) for item in plan["assets"]
            )
        )
        self.request["candidates"][0]["request"]["provider"] = "unknown"
        with self.assertRaises(ValueError):
            self.plan(name="bad-asr")

    def test_asr_recovery_keeps_reference_coverage_and_failures(self) -> None:
        """只读事件恢复采用总字符 CER，失败和无参考分别计数。"""
        from tools.edge_benchmark.task_adapters import read_asr_result

        output = self.root / "asr-result"
        (output / "asr").mkdir(parents=True)
        write_json(output / "manifest.json", {})
        rows = []
        events = []
        for index, (reference, transcript) in enumerate(
            [("a", "b"), ("abc", "abd"), (None, "你好"), ("失效", None)]
        ):
            row = {"id": str(index), "path": str(self.root / f"{index}.wav")}
            if reference is not None:
                row["reference"] = {
                    "kind": "manual_verified",
                    "source": "synthetic",
                    "text": reference,
                }
            rows.append(row)
            if transcript is not None:
                events.append(
                    {
                        "event": "sample",
                        "index": index,
                        "input": row["path"],
                        "transcript": transcript,
                        "rtf": 0.2,
                    }
                )
        (output / "asr/events.jsonl").write_text(
            "\n".join(json.dumps(event) for event in events)
        )
        (output / "asr/resources.jsonl").write_text('{"incomplete":')
        result = read_asr_result({"fixtures": rows}, output)
        self.assertEqual(result["summary"]["samples"], 4)
        self.assertEqual(result["summary"]["completed"], 3)
        self.assertEqual(result["summary"]["reference_samples"], 2)
        self.assertEqual(result["summary"]["cer"], 0.5)
        self.assertEqual(result["status"], "partial")

    def test_qwen_uses_each_cases_actual_tools(self) -> None:
        """缺工具题不得悄悄继承整套目录；不执行真实模型。"""
        from tools.qwen_lifecycle import benchmark

        tool = {
            "type": "function",
            "function": {
                "name": "ping",
                "parameters": {"type": "object", "properties": {}},
            },
        }
        seen = []

        class Runner:
            identity = {"name": "synthetic"}

            def generate(self, messages, tools, generation, on_event):
                """仅返回固定合成调用，记录收到的工具目录。"""
                seen.append(tools)
                return {
                    "raw": (
                        '<tool_call>{"name":"ping","arguments":{}}</tool_call>'
                    ),
                    "finish_reason": "stop",
                }

        class Sampler:
            def __init__(self, *args):
                """无资源测量的显式测试替身。"""
                self.samples = []

            def start(self):
                """返回无副作用采样器。"""
                return self

            def stop(self):
                """替身不伪造资源数字。"""
                return {}

        request = {
            "schema": "edge-model-benchmark/request-v1",
            "run_id": "synthetic",
            "candidate": {"model_path": str(self.model)},
            "suite": {
                "tools": [tool],
                "samples": [
                    {
                        "id": "one",
                        "user": "调用",
                        "expected": {
                            "kind": "tool",
                            "calls": [{"name": "ping", "arguments": {}}],
                        },
                    },
                    {
                        "id": "two",
                        "user": "缺工具",
                        "tools": [],
                        "expected": {"kind": "chat"},
                    },
                ],
            },
        }
        with patch.object(benchmark, "ResourceSampler", Sampler):
            result = benchmark.run(
                request, self.root / "qwen", Runner(), "synthetic_fixture"
            )
        self.assertEqual(seen, [[tool], []])
        self.assertTrue(result["cases"][0]["assessment"]["schema_valid"])
        self.assertFalse(result["cases"][1]["assessment"]["schema_valid"])

    def test_case_timeout_stops_only_owned_dummy_worker(self) -> None:
        """只启动休眠替身，验证硬超时，无真实模型推理。"""
        script = self.root / "dummy-python"
        script.write_text(
            "#!" + sys.executable + "\n"
            "import pathlib,sys,time,json\n"
            "out=pathlib.Path(sys.argv[-1]);out.mkdir()\n"
            "(out/'cases').mkdir()\n"
            "(out/'cases/one.json').write_text(json.dumps({"
            "'id':'one','status':'completed'}))\n"
            "(out/'results.json').write_text('{')\n"
            "(out/'active-case.json').write_text(json.dumps({"
            "'active':True,'started_monotonic':time.monotonic()}))\n"
            "time.sleep(30)\n"
        )
        script.chmod(0o700)
        item = copy.deepcopy(self.request["candidates"][0])
        item["python"] = str(script)
        started = time.monotonic()
        result = execute_candidate(
            "qwen_tool_calls", item, {}, self.root / "dummy-output", 5, 0.1
        )
        self.assertLess(time.monotonic() - started, 5)
        self.assertEqual(result["result"]["cases"][0]["id"], "one")
        self.assertEqual(result["reason"], "case_timeout")
        self.assertEqual(result["status"], "partial")


if __name__ == "__main__":
    unittest.main()
