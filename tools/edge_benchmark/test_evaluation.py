"""评测契约：缺失证据不推造、比较隔离、失败输出计错、静态页安全。"""

import copy
import json
import tempfile
import unittest
from pathlib import Path

from evaluation import (
    asr_samples,
    comparison,
    export,
    normalize_result,
    read_json,
    validate,
)
from evaluation_metrics import metric, normalize_text, quality, resource_window
from evaluation_report import render, safe_link


class EvaluationTest(unittest.TestCase):
    """验证结果消费者会依赖的语义，不需要加载模型。"""

    def test_reference_coverage_and_missing_output(self):
        fixtures = [
            dict(
                id="a",
                path="a",
                reference=dict(
                    kind="dataset_transcript",
                    source="dataset",
                    text="你好，Ａ！",
                ),
            ),
            dict(
                id="b",
                path="b",
                reference=dict(
                    kind="dataset_transcript", source="dataset", text="前进"
                ),
            ),
            dict(
                id="c",
                path="c",
                reference=dict(kind="model_consensus", text="猜测"),
            ),
            dict(id="s", path="s", expected_behavior="silence"),
        ]
        events = [
            dict(event="sample", input="a", transcript="你好a"),
            dict(event="sample", input="s", transcript=""),
        ]
        samples = asr_samples(events, fixtures)
        q = quality(samples)
        self.assertEqual((q["evaluated_samples"], q["total_samples"]), (2, 4))
        self.assertEqual(q["character_errors"], 2)
        self.assertEqual(q["reference_characters"], 5)
        self.assertEqual(q["cer"], 0.4)
        self.assertEqual(q["status"], "incomplete_outputs")
        self.assertEqual(samples[-1]["output_status"], "complete")
        self.assertNotEqual(normalize_text("20"), normalize_text("二十"))

    def test_phase_cpu_is_bracketed_and_unknown_stays_null(self):
        samples = [
            dict(
                monotonic_seconds=t,
                cpu_seconds=t * 2,
                pss_kib=1024,
                rss_kib=2048,
            )
            for t in (0, 1, 2, 3)
        ]
        window = resource_window(samples, 0.1, 2.9, 4, 10240)
        self.assertEqual(window["average_cpu_cores"]["value"], 2)
        self.assertEqual(window["cpu_capacity_percent"]["value"], 50)
        self.assertEqual(window["ram_percent"]["value"], 10)
        missing = resource_window(samples, 2.5, 4, 4, None)
        self.assertIsNone(missing["average_cpu_cores"]["value"])
        self.assertIsNone(missing["ram_percent"]["value"])
        for value in (float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                metric(value, "s", "test")

    def test_comparison_requires_control_evidence_and_splits_scenarios(self):
        config = dict(
            kind="streaming_asr",
            evaluation=dict(
                protocol_id="edge-asr-lite-v1",
                tier="qualification",
                comparison_type="deployment",
                comparison_group="g",
                device_id="d",
                candidate=dict(precision="int8"),
                preprocessing="p",
                output_normalization="n",
            ),
        )
        fixtures = [dict(sha256="abc")]
        fast = comparison(config, fixtures, "throughput")["key"]
        self.assertNotEqual(
            fast, comparison(config, fixtures, "realtime")["key"]
        )
        self.assertNotEqual(
            fast,
            comparison(config, [dict(sha256="different")], "throughput")[
                "key"
            ],
        )
        config["evaluation"]["comparison_type"] = "controlled_backend"
        with self.assertRaises(ValueError):
            comparison(config, fixtures, "throughput")
        config["evaluation"]["controls"] = dict(
            model_lineage="model",
            precision="fp16",
            verification="hash verification",
        )
        with self.assertRaises(ValueError):
            comparison(config, fixtures, "throughput")
        config["evaluation"]["controls"]["precision"] = "int8"
        self.assertIsNotNone(comparison(config, fixtures, "throughput")["key"])

    def test_export_is_read_only_unknown_ram_and_html_is_escaped(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            case = source / "case"
            case.mkdir(parents=True)
            result = dict(
                id="legacy",
                config=dict(id="<img src=x onerror=alert(1)>", kind="asr"),
                status="timeout",
                wall_seconds=2,
                cpu_seconds=1,
                peak_pss_mib=10,
                events=[
                    dict(
                        event="sample",
                        input="a",
                        transcript="<script>bad</script>",
                        rtf=0.5,
                    )
                ],
            )
            raw = case / "result.json"
            raw.write_text(json.dumps(result))
            before = raw.read_bytes()
            (case / "fixtures.json").write_text(
                json.dumps(
                    dict(
                        fixtures=[
                            dict(id="a", path="a", reference_text="unverified")
                        ]
                    )
                )
            )
            target = export([source], root / "view")
            data = read_json(target)
            record = data["records"][0]
            self.assertEqual(before, raw.read_bytes())
            self.assertIsNone(record["metrics"]["ram_percent"]["value"])
            self.assertIsNone(record["comparison"]["key"])
            self.assertEqual(record["phases"], {})
            self.assertEqual(record["quality"]["status"], "not_evaluated")
            page = (target.parent / "report.html").read_text()
            self.assertIn("&lt;img", page)
            self.assertNotIn("<script>bad", page)
            with self.assertRaises(FileExistsError):
                export([source], target.parent)
            invalid = copy.deepcopy(data)
            invalid["records"].append(record)
            with self.assertRaises(ValueError):
                validate(invalid)
            invalid = copy.deepcopy(data)
            invalid["records"][0]["metrics"]["ram_percent"]["reason"] = None
            with self.assertRaises(ValueError):
                validate(invalid)
            for path in (
                "javascript:alert(1)",
                "https://example.com",
                "//remote/x",
                "/etc/passwd",
            ):
                with self.assertRaises(ValueError):
                    safe_link(path)
            invalid = copy.deepcopy(data)
            invalid["records"][0]["evidence"]["result"]["path"] = (
                "javascript:bad"
            )
            target.write_text(json.dumps(invalid))
            with self.assertRaises(ValueError):
                render(target, root / "unsafe.html")

    def test_incomplete_and_silence_timing_do_not_gain_fake_latency(self):
        fixtures = [
            dict(id="a", path="a"),
            dict(id="s", path="s", expected_behavior="silence"),
        ]
        events = [
            dict(
                event="sample",
                input="a",
                transcript="未完成",
                eof_residual="未完成",
                endpoint_after_energy_seconds=0.2,
                energy_end_seconds=1,
            ),
            dict(
                event="sample",
                input="s",
                transcript="错误",
                endpoint_after_energy_seconds=1.2,
                energy_end_seconds=-1,
            ),
        ]
        samples = asr_samples(events, fixtures)
        self.assertEqual(samples[0]["output_status"], "partial")
        self.assertEqual(samples[1]["output_status"], "unexpected_text")
        self.assertTrue(
            all(s["endpoint_after_energy_seconds"] is None for s in samples)
        )

    def test_round_summary_keeps_failures_and_rejects_duplicate_round(self):
        from evaluation_metrics import summarize_records
        from evaluation_report import round_summaries

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "result.json"
            path.write_text(
                json.dumps(
                    dict(
                        config=dict(id="x", kind="streaming_asr"),
                        status="ok",
                        events=[],
                    )
                )
            )
            record = normalize_result(path, {}, path.parent)
            record["protocol"].update(origin="versioned", round=1)
            record["metrics"]["compute_rtf"]["value"] = 0.2
            second = copy.deepcopy(record)
            second["protocol"]["round"] = 2
            second["execution"]["status"] = "timeout"
            second["metrics"]["compute_rtf"]["value"] = 0.6
            page = round_summaries(
                [record, second], summarize_records([record, second])
            )
            self.assertIn("0.400 [0.200–0.600]", page)
            self.assertIn("执行成功 1/2", page)
            with self.assertRaises(ValueError):
                summarize_records([record, record])

    def test_suite_reuses_cases_and_verifies_hash_before_inference(self):
        import hashlib
        import wave

        from asr_suite import build

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            audio = root / "audio.wav"
            with wave.open(str(audio), "w") as wav:
                wav.setparams((1, 2, 16000, 0, "NONE", ""))
                wav.writeframes(b"\0" * 3200)
            fixtures = root / "fixtures.json"
            fixtures.write_text(
                json.dumps(
                    dict(
                        fixtures=[
                            dict(
                                id="a",
                                path=str(audio),
                                sha256=hashlib.sha256(
                                    audio.read_bytes()
                                ).hexdigest(),
                            )
                        ]
                    )
                )
            )
            config = dict(
                python="python3",
                device_id="device",
                fixtures=str(fixtures),
                comparison_type="deployment",
                comparison_group="group",
                screening_fixture_ids=["a"],
                qualification_fixture_ids=["a"],
                screening_budget_seconds=10,
                qualification_budget_seconds=30,
                adapter={},
                candidates=[],
            )
            for backend in ("cpu", "rknn"):
                config["candidates"].append(
                    dict(
                        identity=dict(
                            id=backend,
                            model="model",
                            framework="sdk",
                            backend=backend,
                            precision="int8" if backend == "cpu" else "fp16",
                        ),
                        adapter=dict(provider=backend, threads=1),
                    )
                )
            screening = build(config, "screening")
            repeated = build(config, "qualification")
            self.assertEqual(len(screening["cases"]), 4)
            self.assertEqual(len(repeated["cases"]), 12)
            self.assertEqual(
                {c["evaluation"]["round"] for c in repeated["cases"]},
                {1, 2, 3},
            )
            for case in repeated["cases"]:
                self.assertEqual(case["fixture_ids"], ["a"])
            audio.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
                build(config, "screening")

    def test_versioned_runner_finishes_with_json_and_static_page(self):
        """以原生命令替身验证运行结束自动导出，不将替身当模型测量。"""
        import hashlib
        import sys
        import wave

        from benchmark import run_suite
        from evaluation_metrics import NORMALIZATION

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            audio = root / "silence.wav"
            with wave.open(str(audio), "w") as wav:
                wav.setparams((1, 2, 16000, 0, "NONE", ""))
                wav.writeframes(b"\0" * 3200)
            fixtures = root / "fixtures.json"
            fixtures.write_text(
                json.dumps(
                    dict(
                        fixtures=[
                            dict(
                                id="silence",
                                path=str(audio),
                                sha256=hashlib.sha256(
                                    audio.read_bytes()
                                ).hexdigest(),
                                energy_end_s=-1,
                                expected_behavior="silence",
                            )
                        ]
                    )
                )
            )
            stand_in = root / "command.py"
            stand_in.write_text(
                "import json,pathlib,sys\n"
                "p=pathlib.Path(sys.argv[1])\n"
                "source=pathlib.Path(sys.argv[2]).read_text().split('\\t')[0]\n"
                "e=dict(event='sample', input=source, seconds=.01, "
                "audio_seconds=.1, supplied_audio_seconds=3.3, "
                "transcript='', eof_residual='', first_partial_seconds=-1, "
                "endpoint_after_energy_seconds=-1)\n"
                "(p/'events.jsonl').write_text(json.dumps(e)+'\\n')\n"
                "(p/'ready').touch()\n"
            )
            case = dict(
                id="contract-test",
                kind="streaming_asr",
                binary=sys.executable,
                model=str(stand_in),
                fixtures=str(fixtures),
                threads=1,
                provider="cpu",
                realtime=False,
                chunk_ms=100,
                tail_seconds=3.2,
                idle_seconds=3,
                endpoint_silence=1.2,
                timeout=5,
                evaluation=dict(
                    task="asr",
                    protocol_id="edge-asr-lite-v1",
                    tier="screening",
                    round=1,
                    device_id="test",
                    candidate=dict(
                        id="stand-in",
                        model="command-contract",
                        framework="test",
                        backend="cpu",
                        precision="test",
                    ),
                    comparison_type="deployment",
                    comparison_group="test",
                    preprocessing="mono16k-pcm16-v1",
                    output_normalization=NORMALIZATION,
                ),
            )
            page = run_suite(
                dict(python=sys.executable, budget_seconds=10, cases=[case]),
                root / "run",
            )
            data = read_json(page.with_name("results.json"))
            validate(data)
            self.assertEqual(data["records"][0]["execution"]["status"], "ok")
            self.assertEqual(
                data["records"][0]["completeness"]["status"], "complete"
            )
            self.assertEqual(len(data["summaries"]), 1)
            self.assertTrue(page.is_file())

    def test_device_context_changes_comparison(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "result.json"
            declared = dict(
                task="asr",
                protocol_id="edge-asr-lite-v1",
                tier="qualification",
                round=1,
                device_id="d",
                comparison_type="deployment",
                comparison_group="g",
                preprocessing="p",
                output_normalization="n",
                candidate={},
            )
            path.write_text(
                json.dumps(
                    dict(
                        config=dict(
                            id="case",
                            kind="streaming_asr",
                            evaluation=declared,
                        ),
                        status="ok",
                        events=[],
                    )
                )
            )
            first = normalize_result(path, dict(cpu_count=4), path.parent)
            second = normalize_result(path, dict(cpu_count=8), path.parent)
            self.assertNotEqual(
                first["comparison"]["key"], second["comparison"]["key"]
            )


if __name__ == "__main__":
    unittest.main()
