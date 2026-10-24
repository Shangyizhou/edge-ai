"""冻结任务配置和本地资产；本模块不导入模型或执行子进程。"""

import hashlib
import json
import math
import os
import re
import wave
from pathlib import Path
from typing import Any, Dict

SCHEMA = "edge-benchmark/request-v1"
TASKS = {"qwen_tool_calls", "asr_transcription"}


def read_json(path: Path) -> Any:
    """拒绝重复键和非有限数字，避免配置产生歧义。"""

    def pairs(items: list) -> dict:
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key: " + key)
            result[key] = value
        return result

    def invalid(value: str) -> None:
        raise ValueError("non-finite JSON value: " + value)

    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=pairs,
        parse_constant=invalid,
    )


def write_json(path: Path, value: Any) -> None:
    """原子替换运行记录，避免中断留下半个 JSON。"""
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def digest(path: Path) -> str:
    """流式计算文件身份，不把模型权重整块读入内存。"""
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def identity(value: Any) -> str:
    """计算与 JSON 展示顺序无关的配置身份。"""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()


def fields(value: dict, allowed: set, required: set) -> None:
    """在输入边界拒绝拼错或缺失的字段。"""
    if not isinstance(value, dict):
        raise ValueError("expected a JSON object")
    unknown = set(value) - allowed
    missing = required - set(value)
    if unknown or missing:
        raise ValueError(f"unknown fields: {unknown}; missing: {missing}")


def positive(value: Any, label: str) -> None:
    """预算和超时必须是有限正数。"""
    if (
        type(value) not in (int, float)
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError(label + " must be positive and finite")


def local_file(value: str, base: Path) -> Path:
    """只解析显式本地文件，不下载、不启动设备连接。"""
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    path = path.resolve(strict=True)
    if not path.is_file():
        raise ValueError("not a file: " + str(path))
    return path


def code_commit(root: Path) -> str:
    """只读 Git 元数据定位提交；实际执行代码仍以源码哈希为准。"""
    git = root / ".git"
    if git.is_file():
        git = (root / git.read_text().strip()[8:]).resolve()
    if not (git / "HEAD").exists():
        return "unrecorded"
    head = (git / "HEAD").read_text().strip()
    if not head.startswith("ref: "):
        return head
    reference = head[5:]
    common_file = git / "commondir"
    common = (
        (git / common_file.read_text().strip()).resolve()
        if common_file.exists()
        else git
    )
    for base in (git, common):
        path = base / reference
        if path.exists():
            return path.read_text().strip()
    packed = common / "packed-refs"
    if packed.exists():
        for line in packed.read_text().splitlines():
            if line.endswith(" " + reference):
                return line.split()[0]
    return "unrecorded"


def freeze(request_path: Path, output: Path) -> dict:
    """校验配置并冻结实际请求、题集、资产和执行源码的身份。"""
    source = request_path.resolve(strict=True)
    request = read_json(source)
    fields(
        request,
        {
            "schema",
            "name",
            "task",
            "protocol_id",
            "suite",
            "budget",
            "candidates",
            "device",
            "source_kind",
            "data_use",
        },
        {
            "schema",
            "name",
            "task",
            "protocol_id",
            "suite",
            "budget",
            "candidates",
            "device",
        },
    )
    if request["schema"] != SCHEMA or request["task"] not in TASKS:
        raise ValueError("unsupported benchmark schema or task")
    if "<" in json.dumps(request) or ">" in json.dumps(request):
        raise ValueError("replace template placeholders before planning")
    if request["device"] != "local":
        raise ValueError(
            "execute locally on target host; SSH is not supported"
        )
    if (
        request.get("source_kind", "device_measurement")
        != "device_measurement"
    ):
        raise ValueError("production CLI does not execute synthetic fixtures")
    if request.get("data_use", "regression") not in {
        "development",
        "regression",
        "independent_test",
    }:
        raise ValueError("unknown evaluation data use")
    request.setdefault("data_use", "regression")
    fields(request["suite"], {"path", "sha256"}, {"path", "sha256"})
    budget = request["budget"]
    fields(
        budget,
        {"total_seconds", "case_timeout_seconds"},
        {"total_seconds", "case_timeout_seconds"},
    )
    for label, value in budget.items():
        positive(value, label)
    assets = {}
    model_trees = {}

    def asset(value: str, base: Path = source.parent) -> str:
        path = local_file(value, base)
        assets[str(path)] = {"path": str(path), "sha256": digest(path)}
        return str(path)

    def executable(value: str) -> str:
        path = asset(value)
        if not os.access(path, os.X_OK):
            raise ValueError("runtime file is not executable: " + path)
        return path

    def model(value: str) -> str:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = source.parent / path
        path = path.resolve(strict=True)
        if path.is_file():
            return asset(str(path))
        files = sorted(p for p in path.rglob("*") if p.is_file())
        if not files:
            raise ValueError("empty model directory")
        model_trees[str(path)] = [str(file.resolve()) for file in files]
        for file in files:
            asset(str(file))
        return str(path)

    suite_path = asset(request["suite"]["path"])
    if assets[suite_path]["sha256"] != request["suite"]["sha256"]:
        raise ValueError("suite hash mismatch")
    suite = read_json(Path(suite_path))
    if request["task"] == "qwen_tool_calls":
        fields(suite, {"system", "tools", "samples", "schema"}, {"samples"})
        rows = suite["samples"]
        if isinstance(suite.get("tools"), str):
            suite["tools"] = read_json(
                Path(asset(suite["tools"], Path(suite_path).parent))
            )
        for row in rows:
            fields(
                row,
                {"id", "user", "expected", "tools", "source_group"},
                {"id", "user", "expected"},
            )
            if not isinstance(row["user"], str):
                raise ValueError("Qwen user input must be text")
            if row["expected"].get("kind") not in {"tool", "chat", "persona"}:
                raise ValueError("unsupported Qwen expected kind")
            if not isinstance(row.get("tools", suite.get("tools", [])), list):
                raise ValueError("tools must be a list")
    else:
        fields(suite, {"schema_version", "fixtures"}, {"fixtures"})
        rows = suite["fixtures"]
        for row in rows:
            fields(
                row,
                {"id", "path", "energy_end_s", "reference"},
                {"id", "path", "energy_end_s"},
            )
            row["path"] = asset(row["path"], Path(suite_path).parent)
            with wave.open(row["path"], "rb") as audio:
                if (
                    audio.getnchannels(),
                    audio.getframerate(),
                    audio.getsampwidth(),
                    audio.getcomptype(),
                ) != (1, 16000, 2, "NONE"):
                    raise ValueError("ASR requires mono 16k PCM16 WAV")
                duration = audio.getnframes() / 16000
            if duration <= 0 or not 0 <= row["energy_end_s"] <= duration:
                raise ValueError("invalid ASR energy endpoint")
            ref = row.get("reference") or {}
            if ref and (
                ref.get("kind")
                not in {"dataset_transcript", "manual_verified"}
                or not ref.get("source")
                or not ref.get("text")
            ):
                raise ValueError(
                    "ASR reference requires verified kind/source/text"
                )
    ids = [row["id"] for row in rows]
    if (
        not ids
        or len(ids) != len(set(ids))
        or any(not re.fullmatch(r"[A-Za-z0-9_-]+", item) for item in ids)
    ):
        raise ValueError("nonempty suite requires unique portable IDs")
    if (
        not isinstance(request["candidates"], list)
        or not request["candidates"]
    ):
        raise ValueError("at least one candidate is required")
    candidates = []
    for item in request["candidates"]:
        fields(
            item,
            {"id", "model_id", "precision", "python", "request"},
            {"id", "model_id", "precision", "python", "request"},
        )
        if not re.fullmatch(r"[A-Za-z0-9_-]+", item["id"]):
            raise ValueError("invalid candidate ID")
        item["python"] = executable(item["python"])
        native = item["request"]
        if request["task"] == "qwen_tool_calls":
            fields(
                native,
                {
                    "candidate",
                    "generation",
                    "runner",
                    "server",
                    "sampling_interval_seconds",
                    "registry_validator",
                },
                {"candidate", "generation", "runner"},
            )
            native["candidate"]["model_path"] = model(
                native["candidate"]["model_path"]
            )
            if native["candidate"].get("adapter_path"):
                native["candidate"]["adapter_path"] = model(
                    native["candidate"]["adapter_path"]
                )
            fields(
                native["generation"],
                {
                    "max_tokens",
                    "context_tokens",
                    "temperature",
                    "cache_prompt",
                    "prefill_step_size",
                },
                {"max_tokens", "context_tokens", "temperature"},
            )
            runner = native["runner"]
            fields(runner, {"kind", "network"}, {"kind"})
            if runner["kind"] not in {"mlx", "llama-http"}:
                raise ValueError("unsupported Qwen runner")
            if runner["kind"] == "llama-http":
                if not native.get("server"):
                    raise ValueError("HTTP benchmark requires an owned server")
                fields(
                    native["server"],
                    {"binary", "argv", "port"},
                    {"binary", "argv"},
                )
                if not isinstance(native["server"]["argv"], list) or any(
                    not isinstance(arg, str)
                    for arg in native["server"]["argv"]
                ):
                    raise ValueError("server argv must be a list of strings")
                if any(
                    arg.split("=")[0]
                    in {
                        "--host",
                        "--port",
                        "-m",
                        "--model",
                        "-hf",
                        "--hf-repo",
                    }
                    for arg in native["server"]["argv"]
                ):
                    raise ValueError("server argv cannot override ownership")
                native["server"]["binary"] = executable(
                    native["server"]["binary"]
                )
            elif native.get("server"):
                raise ValueError("MLX does not use a server")
            for key in ("max_tokens", "context_tokens"):
                positive(native["generation"][key], key)
                if type(native["generation"][key]) is not int:
                    raise ValueError(key + " must be an integer")
            temperature = native["generation"]["temperature"]
            if type(temperature) not in (int, float) or temperature < 0:
                raise ValueError("temperature must be nonnegative")
            if (
                "cache_prompt" in native["generation"]
                and type(native["generation"]["cache_prompt"]) is not bool
            ):
                raise ValueError("cache_prompt must be boolean")
            validator = native.get("registry_validator")
            if validator is not None:
                if not isinstance(validator, list) or not validator:
                    raise ValueError(
                        "registry validator must be explicit argv"
                    )
                validator[0] = executable(validator[0])
                for index, argument in enumerate(validator[1:], 1):
                    if (
                        Path(argument).is_file()
                        or (source.parent / argument).is_file()
                    ):
                        validator[index] = asset(argument)
        else:
            fields(
                native,
                {
                    "kind",
                    "binary",
                    "model",
                    "threads",
                    "provider",
                    "realtime",
                    "chunk_ms",
                    "tail_seconds",
                    "idle_seconds",
                    "endpoint_silence",
                    "max_as_mib",
                    "min_memavailable_mib",
                },
                {
                    "kind",
                    "binary",
                    "model",
                    "threads",
                    "provider",
                    "realtime",
                    "chunk_ms",
                    "tail_seconds",
                    "endpoint_silence",
                },
            )
            if native["kind"] != "streaming_asr" or native["provider"] not in {
                "cpu",
                "rknn",
            }:
                raise ValueError(
                    "only existing streaming_asr CPU/RKNN is supported"
                )
            native["binary"] = executable(native["binary"])
            native["model"] = model(native["model"])
            directory = Path(native["model"])
            required_assets = (
                ["encoder.rknn", "decoder.rknn", "joiner.rknn"]
                if native["provider"] == "rknn"
                else [
                    "encoder-epoch-99-avg-1.int8.onnx",
                    "decoder-epoch-99-avg-1.onnx",
                    "joiner-epoch-99-avg-1.int8.onnx",
                ]
            )
            for filename in required_assets + ["tokens.txt"]:
                asset(str(directory / filename))
            if native["provider"] == "rknn" and native["threads"] != 1:
                raise ValueError("existing RKNN adapter requires one thread")
            for key in ("threads", "chunk_ms", "endpoint_silence"):
                positive(native[key], key)
            if type(native["realtime"]) is not bool:
                raise ValueError("realtime must be boolean")
            if native["tail_seconds"] < 0:
                raise ValueError("tail_seconds cannot be negative")
        candidates.append(item)
    if len({item["id"] for item in candidates}) != len(candidates):
        raise ValueError("duplicate candidate IDs")
    # 1. 冻结执行源码；运行时不依赖已卸载的 Skill。
    root = Path(__file__).resolve().parents[2]
    for directory in (
        "edge_benchmark",
        "qwen_lifecycle",
        "edge_workflow",
        "experiment_tracking",
    ):
        for path in (root / "tools" / directory).glob("*.py"):
            asset(str(path))
    plan = {
        "schema": "edge-benchmark/plan-v1",
        "code_commit": code_commit(root),
        "source_identity": (
            "frozen source hashes; commit alone may not include local changes"
        ),
        "request": request,
        "suite": suite,
        "assets": list(assets.values()),
        "model_trees": model_trees,
        "source_kind": "device_measurement",
        "case_count_per_candidate": len(rows),
        "maximum_requests": len(rows) * len(candidates),
    }
    plan["plan_id"] = identity(plan)
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "request.json", read_json(source))
    write_json(output / "plan.json", plan)
    return plan


def validate_plan(plan: Dict[str, Any]) -> None:
    """执行前重查配置身份及全部已冻结文件；不重新解释请求。"""
    content = dict(plan)
    plan_id = content.pop("plan_id")
    if (
        plan.get("schema") != "edge-benchmark/plan-v1"
        or identity(content) != plan_id
    ):
        raise ValueError("changed or unsupported plan")
    for root, expected in plan.get("model_trees", {}).items():
        actual = sorted(
            str(path.resolve())
            for path in Path(root).rglob("*")
            if path.is_file()
        )
        if sorted(expected) != actual:
            raise ValueError("changed model directory: " + root)
    for item in plan["assets"]:
        if digest(Path(item["path"])) != item["sha256"]:
            raise ValueError("changed asset: " + item["path"])
