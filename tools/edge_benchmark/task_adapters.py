"""在独立模型环境中执行两种明确任务，不加载 MLflow。"""

import argparse
import copy
import importlib.metadata
import json
import platform
import statistics
import subprocess
import time
from pathlib import Path
from typing import Any, Dict

from .experiment import digest, read_json, write_json


def execute_qwen(request: dict, suite: dict, output: Path) -> dict:
    """复用原生调用测量核心，默认关闭报告，只管理自有服务。"""
    # 模型依赖仅在执行阶段加载，plan/sync 不承担其初始化成本。
    from tools.qwen_lifecycle.benchmark import run
    from tools.qwen_lifecycle.server_lifecycle import execute

    request = copy.deepcopy(request)
    request.update(schema="edge-model-benchmark/request-v1", suite=suite)
    if request["runner"]["kind"] == "llama-http":
        probe = (
            ("otool", ["otool", "-L"])
            if platform.system() == "Darwin"
            else ("ldd", ["ldd"])
        )
        return execute(request, output, probe, render_reports=False)
    return run(request, output)


def execute_asr(request: dict, suite: dict, output: Path) -> dict:
    """复用 Linux 原生 ASR 执行器，保留完成率和参考覆盖分母。"""
    if platform.system() != "Linux":
        raise ValueError(
            "existing ASR sampler requires Linux; no SSH dispatch"
        )
    from .benchmark import inventory, run_case

    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "fixtures.json", suite)
    config = copy.deepcopy(request)
    config.update(
        fixtures=str(output / "fixtures.json"),
        fixture_ids=[row["id"] for row in suite["fixtures"]],
    )
    config.setdefault("idle_seconds", 0)
    config["timeout"] = request["candidate_timeout_seconds"]
    config.pop("candidate_timeout_seconds")
    config.pop("run_id")
    worker_python = config.pop("worker_python")
    config["id"] = "asr"
    dependencies = subprocess.run(
        ["ldd", config["binary"]],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    libraries = {
        word
        for word in dependencies.stdout.split()
        if word.startswith("/") and Path(word).is_file()
    }
    write_json(
        output / "runtime-libraries.json",
        {
            "ldd": dependencies.stdout,
            "stderr": dependencies.stderr,
            "returncode": dependencies.returncode,
            "libraries": [
                {"path": path, "sha256": digest(Path(path))}
                for path in sorted(libraries)
            ],
        },
    )
    manifest = inventory({"cases": [config], "extra_assets": []})
    manifest["cpuinfo"] = "\n".join(
        row
        for row in manifest.get("cpuinfo", "").splitlines()
        if not row.lower().startswith("serial")
    )
    write_json(output / "manifest.json", manifest)
    run_case(config, output, worker_python)
    return read_asr_result(suite, output)


def read_asr_result(suite: dict, output: Path) -> dict:
    """从已有事件恢复正式样本；超时也保留已完成的转写。"""
    from .evaluation_metrics import quality, resource_window

    manifest = read_json(output / "manifest.json")
    raw_path = output / "asr/result.json"
    event_path = output / "asr/events.jsonl"
    raw = (
        read_json(raw_path)
        if raw_path.exists()
        else {"status": "interrupted", "events": []}
    )
    if event_path.exists():
        events = []
        for line in event_path.read_text().splitlines():
            try:
                events.append(json.loads(line))
            except ValueError:
                continue
        raw["events"] = events
    samples = []
    resource_file = output / "asr/resources.jsonl"
    if resource_file.exists():
        lines = resource_file.read_text().splitlines()
        for index, line in enumerate(lines):
            try:
                samples.append(json.loads(line))
            except ValueError:
                if index != len(lines) - 1:
                    raise
                # 超时可能打断最后一次写入，先前完整资源样本仍保留。
    observed = {}
    for event in raw["events"]:
        if event.get("event") != "sample":
            continue
        if event.get("stage") == "inference":
            observed[event["fixture"]] = event
        elif "transcript" in event and "index" in event:
            # 现有 probe 使用 input/index/rtf，显式映射而不改原事件。
            index = event["index"]
            if type(index) is not int or not 0 <= index < len(
                suite["fixtures"]
            ):
                raise ValueError("ASR event has unknown sample index")
            fixture = suite["fixtures"][index]
            if (
                Path(event["input"]).resolve()
                != Path(fixture["path"]).resolve()
            ):
                raise ValueError(
                    "ASR event input does not match frozen fixture"
                )
            observed[fixture["id"]] = dict(
                event,
                fixture=fixture["id"],
                stage="inference",
                final_text=event["transcript"],
                compute_rtf=event["rtf"],
            )
    cases = []
    for row in suite["fixtures"]:
        event = observed.get(row["id"])
        cases.append(
            {
                "id": row["id"],
                "status": "completed" if event else "failed",
                "reference": row.get("reference"),
                "transcript": event.get("final_text", "") if event else None,
                "event": event,
            }
        )
    quality_rows = [
        {
            "case_id": row["id"],
            "reference": row["reference"],
            "transcript": row["transcript"],
            "output_status": "complete",
        }
        for row in cases
        if row["status"] == "completed"
    ]
    scored = quality(quality_rows)
    rtfs = [row["event"]["compute_rtf"] for row in cases if row["event"]]
    windows = []
    start = None
    for event in raw["events"]:
        if event.get("event") != "phase" or event.get("name") != "inference":
            continue
        if event["state"] == "start":
            start = event["monotonic_seconds"]
        elif start is not None:
            windows.append(
                resource_window(
                    samples,
                    start,
                    event["monotonic_seconds"],
                    manifest["cpu_count"],
                    manifest["host_memory"]["MemTotal"],
                )
            )
            start = None
    completed = sum(row["status"] == "completed" for row in cases)
    metrics = {
        "samples": len(cases),
        "completed": completed,
        "reference_samples": scored["evaluated_samples"],
        "cer_reference_characters": scored["reference_characters"],
        "cer_character_errors": scored["character_errors"],
        "cer": scored["cer"],
        "compute_rtf_median": statistics.median(rtfs) if rtfs else None,
    }
    valid = [
        w for w in windows if w["cpu_capacity_percent"]["value"] is not None
    ]
    duration = sum(w["duration_seconds"] for w in valid)
    metrics["cpu_capacity_percent"] = (
        sum(
            w["duration_seconds"] * w["cpu_capacity_percent"]["value"]
            for w in valid
        )
        / duration
        if duration
        else None
    )
    metrics["peak_pss_mib"] = max(
        (
            w["peak_pss_mib"]["value"]
            for w in windows
            if w["peak_pss_mib"]["value"] is not None
        ),
        default=None,
    )
    result = {
        "status": "completed"
        if completed == len(cases) and raw["status"] == "ok"
        else "partial",
        "cases": cases,
        "summary": metrics,
        "quality": scored,
        "resource_windows": windows,
        "measurement": {
            "timing": (
                "native compute RTF; pacing/load excluded; "
                "configured tail included"
            ),
            "resource_scope": (
                "sampled inference windows; first/warmup excluded"
            ),
            "quality_scope": (
                "completed independently referenced samples only; "
                "inspect coverage"
            ),
        },
    }
    write_json(output / "results.json", result)
    return result


def execute(
    task: str, request: Dict[str, Any], suite: dict, output: Path
) -> dict:
    """显式分派已支持任务，不允许动态模块或任意命令。"""
    adapters = {
        "qwen_tool_calls": execute_qwen,
        "asr_transcription": execute_asr,
    }
    return adapters[task](request, suite, output)


def main() -> None:
    """执行控制端冻结的单个候选，异常保留失败事实。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    data = read_json(args.input)
    started = time.monotonic()
    packages = {
        dist.metadata["Name"]: dist.version
        for dist in importlib.metadata.distributions()
        if dist.metadata["Name"]
    }
    write_json(
        args.output.parent / (args.output.name + "-runtime.json"),
        {"packages": packages, "platform": platform.platform()},
    )
    result = execute(data["task"], data["request"], data["suite"], args.output)
    result["runtime_packages"] = packages
    result["adapter_wall_seconds"] = time.monotonic() - started
    write_json(args.output / "results.json", result)
    if result["status"] != "completed":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
