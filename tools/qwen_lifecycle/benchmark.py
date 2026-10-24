"""执行原生调用评测，逐例保存输出、工具目录和资源证据。"""

import hashlib
import json
import os
import platform
import time
from pathlib import Path
from typing import Any

from .measure import ResourceSampler
from .protocol import intake
from .runners import LlamaHttpRunner, MlxRunner

REQUEST_SCHEMA = "edge-model-benchmark/request-v1"
RESULT_SCHEMA = "edge-model-benchmark/result-v1"


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    Path(path).write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def asset_manifest(candidate):
    path = Path(candidate["model_path"])
    if path.is_file():
        files = [path]
    elif path.is_dir():
        files = sorted(p for p in path.iterdir() if p.is_file())
    else:
        raise FileNotFoundError(path)
    return {
        "root": str(path),
        "total_bytes": sum(p.stat().st_size for p in files),
        "files": [
            {"name": p.name, "bytes": p.stat().st_size, "sha256": file_hash(p)}
            for p in files
        ],
    }


def run(
    request: dict,
    output: Path,
    runner: Any = None,
    source_kind: str = "device_measurement",
) -> dict:
    """通过同一推理边界测量全部案例，保留失败和逐例实际工具。"""
    if request.get("schema") != REQUEST_SCHEMA:
        raise ValueError("unsupported benchmark request schema")
    if source_kind not in {"device_measurement", "synthetic_fixture"}:
        raise ValueError("unknown source kind")
    if runner is not None and source_kind != "synthetic_fixture":
        raise ValueError("injected runner must be declared synthetic_fixture")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "request.json", request)
    suite = request.get("suite")
    if suite is None:
        suite = read_json(request["suite_ref"])
    if isinstance(suite.get("tools"), str):
        suite["tools"] = read_json(suite["tools"])
    write_json(output / "suite.json", suite)
    tools = suite.get("tools", [])
    ids = [sample["id"] for sample in suite["samples"]]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("nonempty suite requires unique sample IDs")
    for name in ids:
        if not name or any(
            char not in "abcdefghijklmnopqrstuvwxyz"
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
            for char in name
        ):
            raise ValueError("sample ID must be a portable filename component")
    generation = request.get("generation", {})
    interval = request.get("sampling_interval_seconds", 0.2)
    if not 0.02 <= interval <= 10:
        raise ValueError(
            "sampling interval must be between .02 and 10 seconds"
        )
    candidate = dict(request["candidate"])
    assets = asset_manifest(candidate)
    write_json(output / "assets-manifest.json", assets)
    started = time.perf_counter()
    load_sampler = ResourceSampler(
        request.get("runner", {}).get("monitor_pid"), interval
    ).start()
    try:
        if runner is None:
            kind = request["runner"]["kind"]
            runner_type = {"mlx": MlxRunner, "llama-http": LlamaHttpRunner}[
                kind
            ]
            runner = runner_type(request)
    finally:
        loading_resources = load_sampler.stop()
    load_seconds = time.perf_counter() - started
    candidate["actual_runtime"] = runner.identity
    result = {
        "schema": RESULT_SCHEMA,
        "run_id": request["run_id"],
        "source": {
            "kind": source_kind,
            "raw_evidence": "cases/ and events/ within this run",
        },
        "candidate": candidate,
        "stage": request.get("stage", "baseline"),
        "request_sha256": file_hash(output / "request.json"),
        "suite_sha256": file_hash(output / "suite.json"),
        "artifacts": assets,
        "environment": {
            "system": platform.system(),
            "machine": platform.machine(),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "logical_cpus": os.cpu_count(),
        },
        "loading": {
            "wall_seconds": load_seconds,
            "resources": loading_resources,
        },
        "measurement": {
            "resources": "per-case sampled process tree",
            "cache": "new MLX prompt cache per case / "
            "llama cache_prompt="
            + str(generation.get("cache_prompt", False)).lower(),
            "timing": "request to complete response; "
            "valid-call latency only if native+schema pass",
            "sampling_interval_seconds": interval,
            "quality_scope": "frozen deterministic fixture "
            "rules; no hardware execution or product acceptance",
        },
        "cases": [],
    }
    (output / "cases").mkdir()
    (output / "events").mkdir()
    for sample in suite["samples"]:
        tools = sample.get("tools", suite.get("tools", []))
        write_json(
            output / "active-case.json",
            {
                "id": sample["id"],
                "started_monotonic": time.monotonic(),
                "active": True,
            },
        )
        events = []
        messages = [
            {"role": "system", "content": suite.get("system", "")},
            {"role": "user", "content": sample["user"]},
        ]
        row = {
            "id": sample["id"],
            "user": sample["user"],
            "expected": sample["expected"],
            "messages": messages,
            "kind": sample["expected"]["kind"],
            "status": "failed",
        }
        monitor = ResourceSampler(
            request.get("runner", {}).get("monitor_pid"), interval
        ).start()
        case_started = time.perf_counter()
        try:
            generated = runner.generate(
                messages, tools, generation, events.append
            )
            row["generation"] = generated
            assessed = intake(
                generated["raw"],
                generated["finish_reason"],
                tools,
                sample["expected"],
                generated.get("wire_calls"),
                request.get("registry_validator"),
            )
            row["assessment"] = assessed
            row["status"] = (
                "completed"
                if generated["finish_reason"] in ("stop", "tool_calls")
                else "truncated"
            )
            row["valid_call_seconds"] = (
                time.perf_counter() - case_started
                if assessed.get("schema_valid")
                and assessed.get("registry_valid") is not False
                else None
            )
        except (ValueError, RuntimeError, OSError, KeyError) as error:
            row["error"] = {
                "type": type(error).__name__,
                "message": str(error),
            }
        finally:
            row["resources"] = monitor.stop()
        write_json(output / "cases" / (sample["id"] + ".json"), row)
        write_json(
            output / "events" / (sample["id"] + ".json"),
            {"events": events, "resources": monitor.samples},
        )
        write_json(
            output / "active-case.json", {"id": sample["id"], "active": False}
        )
        result["cases"].append(row)
        result["summary"] = summarize(result["cases"])
        write_json(output / "results.json", result)
    result["status"] = (
        "completed"
        if all(row["status"] == "completed" for row in result["cases"])
        else "partial"
    )
    result["evidence"] = [
        {"path": str(path.relative_to(output)), "sha256": file_hash(path)}
        for path in sorted(output.rglob("*.json"))
        if path.name != "results.json"
    ]
    write_json(output / "results.json", result)
    return result


def summarize(cases):
    tools = [c for c in cases if c["kind"] == "tool"]
    personas = [c for c in cases if c["kind"] == "persona"]
    chats = [c for c in cases if c["kind"] == "chat"]

    def passed(rows, key):
        return sum(c.get("assessment", {}).get(key) is True for c in rows)

    return {
        "samples": len(cases),
        "tool_samples": len(tools),
        "native_calls": sum(
            bool(c.get("assessment", {}).get("reply", {}).get("tool_calls"))
            and c.get("assessment", {}).get("native_parse") is True
            for c in tools
        ),
        "json_valid": passed(tools, "json_valid"),
        "schema_valid": passed(tools, "schema_valid"),
        "registry_valid": passed(tools, "registry_valid"),
        "tool_expected_behavior": passed(tools, "expected_behavior"),
        "persona_samples": len(personas),
        "persona_valid": passed(personas, "persona_valid"),
        "chat_samples": len(chats),
        "chat_valid": passed(chats, "expected_behavior"),
    }
