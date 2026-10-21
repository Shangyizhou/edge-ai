"""导出有版本的轻量评测视图，保留历史证据且不重新推理。"""

import argparse
import hashlib
import json
import os
import wave
from datetime import datetime, timezone
from pathlib import Path

from evaluation_metrics import (
    ASR_PROTOCOL,
    NORMALIZATION,
    VERSION,
    median,
    metric,
    phases,
    quality,
    summarize_records,
)

PROFILES = {
    "asr": ("asr-python-100ms-tail2.5", "compute_with_tail/original_audio"),
    "native_asr": ("asr-cli-reload-tail0.8", "CLI_reported_rounded"),
    "streaming_asr": ("asr-c-api-tail3.2", "compute_with_tail/original_audio"),
    "summer": ("summer-native", "generate_only/output_audio"),
    "sherpa_tts": ("sherpa-tts", "generate_only/output_audio"),
    "piper": ("piper-cli", "subprocess_to_wav_ready/output_audio"),
    "llama": ("llama-server", "request_to_content"),
    "yolo": ("yolo", "frame_completion"),
    "yolo_cpu": ("yolo-cpu", "frame_completion"),
    "vision_asr": ("vision-asr", "combined_process_tree"),
    "ros_asr": ("asr-ros", "ROS_event_receipt"),
    "coexistence": ("asr-llm-tts", "combined_process_tree"),
}


def validate_case_config(config: dict) -> None:
    """在运行前检查ASR新版协议及素材身份，旧配置保持兼容。"""
    declared = config.get("evaluation")
    if declared is None:
        return
    required = {
        "task",
        "protocol_id",
        "tier",
        "round",
        "device_id",
        "candidate",
        "comparison_type",
        "comparison_group",
        "preprocessing",
        "output_normalization",
    }
    if not required <= set(declared):
        raise ValueError("evaluation contract missing required fields")
    if declared["task"] != "asr" or declared["protocol_id"] != ASR_PROTOCOL:
        raise ValueError(
            "v1 execution currently supports the ASR lite protocol"
        )
    if config["kind"] != "streaming_asr":
        raise ValueError("ASR v1 requires streaming_asr adapter")
    if declared["tier"] not in {"screening", "qualification"}:
        raise ValueError("unknown evaluation tier")
    if type(declared["round"]) is not int or declared["round"] not in {
        1,
        2,
        3,
    }:
        raise ValueError("round must be 1..3")
    if declared["tier"] == "screening" and declared["round"] != 1:
        raise ValueError("screening runs once")
    if (
        declared["output_normalization"] != NORMALIZATION
        or declared["preprocessing"] != "mono16k-pcm16-v1"
    ):
        raise ValueError("ASR v1 normalization/preprocessing mismatch")
    candidate = declared["candidate"]
    if not {"id", "model", "framework", "backend", "precision"} <= set(
        candidate
    ):
        raise ValueError("candidate identity missing")
    if not all(
        isinstance(candidate[key], str) and candidate[key]
        for key in ("id", "model", "framework", "backend", "precision")
    ):
        raise ValueError("candidate identity requires nonempty strings")
    if (
        type(config.get("realtime")) is not bool
        or type(config.get("threads")) is not int
        or config["threads"] < 1
    ):
        raise ValueError(
            "ASR needs boolean realtime and positive thread count"
        )
    if candidate["backend"] != config.get("provider"):
        raise ValueError("candidate backend contradicts adapter provider")
    if config.get("provider") not in {"cpu", "rknn"}:
        raise ValueError("ASR provider must be cpu or rknn")
    if config.get("provider") == "rknn" and config["threads"] != 1:
        raise ValueError("RKNN uses one core selection on RK3566")
    if config.get("chunk_ms") != 100 or config.get("tail_seconds") != 3.2:
        raise ValueError("ASR v1 requires 100ms chunks and 3.2s tail")
    if (
        config.get("idle_seconds") != 3
        or config.get("endpoint_silence") != 1.2
    ):
        raise ValueError("ASR v1 requires 3s idle and 1.2s rule2")
    fixture = read_json(Path(config["fixtures"]))
    selected = config.get("fixture_ids")
    rows = [
        f
        for f in fixture["fixtures"]
        if selected is None or f["id"] in selected
    ]
    if not rows or len({f["id"] for f in rows}) != len(rows):
        raise ValueError("fixtures must be nonempty and have unique ids")
    if selected is not None and set(selected) != {f["id"] for f in rows}:
        raise ValueError("unknown fixture id")
    for item in rows:
        if digest(Path(item["path"])) != item["sha256"]:
            raise ValueError("fixture SHA256 mismatch: " + item["id"])
        with wave.open(item["path"]) as audio:
            if (
                audio.getnchannels(),
                audio.getsampwidth(),
                audio.getframerate(),
            ) != (1, 2, 16000):
                raise ValueError("ASR v1 requires mono 16kHz PCM16")
            if audio.getnframes() == 0:
                raise ValueError("empty audio fixture")
        reference = item.get("reference")
        if reference and reference.get("kind") in {
            "dataset_transcript",
            "manual_verified",
        }:
            if not reference.get("text") or not reference.get("source"):
                raise ValueError("trusted reference needs text and source")
    comparison(
        config,
        rows,
        "realtime" if config.get("realtime", True) else "throughput",
    )


def read_json(path: Path):
    """拒绝非标准JSON数值，避免静态结果含NaN。"""

    def invalid(value):
        """将非有限字面量定位为输入错误。"""
        raise ValueError("non-finite JSON value: " + value)

    return json.loads(path.read_text(), parse_constant=invalid)


def digest(path: Path) -> str:
    """保留源结果身份，导出后可以核对证据未被改写。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evidence(path: Path, output: Path) -> dict:
    """证据链接相对导出目录，可随仓库一起浏览。"""
    return {
        "path": os.path.relpath(path.resolve(), output.resolve()),
        "sha256": digest(path),
    }


def fixture_rows(directory: Path) -> list:
    """只消费测量时冻结的素材清单，不读取可能已变化的外部文件。"""
    path = directory / "fixtures.json"
    if path.exists():
        return read_json(path)["fixtures"]
    return []


def asr_samples(events: list, fixtures: list) -> list:
    """按冻结输入匹配样本；缺失输出和无参考分别保留。"""
    measured = [
        e for e in events if e.get("event") == "sample" and "input" in e
    ]
    if not fixtures:
        fixtures = [
            {"id": str(i), "path": e["input"]} for i, e in enumerate(measured)
        ]
    result = []
    for fixture in fixtures:
        matches = [e for e in measured if e["input"] == fixture["path"]]
        event = matches[0] if matches else {}
        transcript = event.get("transcript") or ""
        delay = event.get("endpoint_after_energy_seconds")
        valid_delay = (
            delay is not None
            and delay >= 0
            and not event.get("eof_residual")
            and event.get("energy_end_seconds", 0) >= 0
        )
        silent = fixture.get("expected_behavior") == "silence"
        result.append(
            {
                "case_id": fixture["id"],
                "input": fixture["path"],
                "input_sha256": fixture.get("sha256"),
                "reference": fixture.get("reference"),
                "transcript": transcript,
                "output_status": (
                    "missing"
                    if not event
                    else "unexpected_text"
                    if silent and transcript
                    else "complete"
                    if silent and not transcript
                    else "partial"
                    if event.get("eof_residual")
                    else "empty"
                    if not transcript
                    else "complete"
                ),
                "compute_seconds": event.get("seconds"),
                "audio_seconds": event.get("audio_seconds"),
                "energy_end_seconds": event.get("energy_end_seconds"),
                "endpoint_count": event.get("endpoint_count"),
                "early_endpoint_count": event.get("early_endpoint_count"),
                "eof_residual": event.get("eof_residual"),
                "supplied_audio_seconds": event.get("supplied_audio_seconds"),
                "first_partial_seconds": (
                    event["first_partial_seconds"]
                    if event.get("first_partial_seconds", -1) >= 0
                    else None
                ),
                "endpoint_after_energy_seconds": delay
                if valid_delay
                else None,
            }
        )
    return result


def identity(config: dict, manifest: dict) -> dict:
    """用声明和资产身份描述部署，不用文件名猜模型精度。"""
    declared = config.get("evaluation", {}).get("candidate", {})
    paths = {str(config.get(k)) for k in ("model", "binary") if config.get(k)}
    assets = [
        a
        for a in manifest.get("assets", [])
        if a["path"] in paths
        or any(a["path"].startswith(p.rstrip("/") + "/") for p in paths)
    ]
    return {
        "id": declared.get("id", config["id"]),
        "model": declared.get("model"),
        "precision": declared.get("precision"),
        "framework": declared.get("framework"),
        "backend": declared.get("backend", config.get("provider")),
        "assets": assets,
        "parameters": {
            key: config.get(key)
            for key in (
                "threads",
                "endpoint_silence",
                "chunk_ms",
                "tail_seconds",
                "idle_seconds",
                "realtime",
            )
        },
    }


def comparison(config: dict, fixtures: list, scenario: str) -> dict:
    """比较组键覆盖协议、输入和执行条件，受控归因额外要求谱系。"""
    declared = config.get("evaluation")
    if not declared:
        return {
            "type": "legacy",
            "group": None,
            "key": None,
            "conditions": {},
            "reason": "no versioned comparison contract",
        }
    kind = declared["comparison_type"]
    if kind not in {"deployment", "controlled_backend"}:
        raise ValueError("unknown comparison_type")
    conditions = {
        "protocol": declared["protocol_id"],
        "scenario": scenario,
        "tier": declared["tier"],
        "adapter": config["kind"],
        "input_hashes": [f["sha256"] for f in fixtures],
        "chunk_ms": config.get("chunk_ms", 100),
        "tail_seconds": config.get("tail_seconds", 3.2),
        "endpoint_silence": config.get("endpoint_silence"),
        "idle_seconds": config.get("idle_seconds", 3),
        "decode": "greedy_search",
        "preprocessing": declared["preprocessing"],
        "output_normalization": declared["output_normalization"],
        "group": declared["comparison_group"],
        "device_id": declared["device_id"],
        "references": [f.get("reference") for f in fixtures],
        "startup_policy": "first-silence2s+warm-silence2s+idle3s-v1",
    }
    if kind == "controlled_backend":
        controls = declared.get("controls", {})
        required = {"model_lineage", "precision", "verification"}
        if not required <= set(controls) or not all(
            controls[k] for k in required
        ):
            raise ValueError(
                "controlled comparison requires verified lineage and precision"
            )
        if controls["precision"] != declared["candidate"]["precision"]:
            raise ValueError("controlled precision contradicts candidate")
        conditions["controls"] = controls
    key = hashlib.sha256(
        json.dumps(conditions, sort_keys=True).encode()
    ).hexdigest()[:16]
    return {
        "type": kind,
        "group": declared["comparison_group"],
        "key": key,
        "conditions": conditions,
        "reason": None,
    }


def normalize_result(
    path: Path, manifest: dict, output: Path, supplied=None
) -> dict:
    """将一次案例转换为可比较视图，不改写或推造原始测量。"""
    raw = read_json(path) if supplied is None else supplied
    config = raw["config"]
    kind = config["kind"]
    events = raw.get("events", [])
    fixtures = fixture_rows(path.parent)
    declared = config.get("evaluation", {})
    scenario = (
        ("realtime" if config.get("realtime", True) else "throughput")
        if kind == "streaming_asr"
        else kind
    )
    task = declared.get("task") or (
        "asr"
        if kind in {"asr", "native_asr", "streaming_asr", "ros_asr"}
        else "coexistence"
        if kind in {"vision_asr", "coexistence"}
        else "tts"
        if kind in {"summer", "sherpa_tts", "piper"}
        else "llm"
        if kind == "llama"
        else "vision"
    )
    samples = asr_samples(events, fixtures) if task == "asr" else []
    profile, scope = PROFILES.get(kind, (kind, "adapter_defined"))
    cpu_count = manifest.get("cpu_count")
    mem_total = manifest.get("host_memory", {}).get("MemTotal")
    wall = raw.get("wall_seconds")
    cpu = raw.get("cpu_seconds")
    cores = cpu / wall if cpu is not None and wall and wall > 0 else None
    ram = raw.get("peak_pss_mib")
    values = {
        "peak_rss_mib": metric(
            raw.get("peak_rss_mib"),
            "MiB",
            "whole_case_process_tree_sampled",
            "not sampled",
        ),
        "peak_pss_mib": metric(
            ram, "MiB", "whole_case_process_tree_sampled", "not sampled"
        ),
        "ram_percent": metric(
            ram * 1024 / mem_total * 100
            if ram is not None and mem_total
            else None,
            "%",
            "whole_case_pss/MemTotal",
            "measured MemTotal unavailable",
        ),
        "average_cpu_cores": metric(
            cores, "cores", "whole_case", "CPU or wall time unavailable"
        ),
        "cpu_capacity_percent": metric(
            cores / cpu_count * 100
            if cores is not None and cpu_count
            else None,
            "%",
            "whole_case_process_tree",
            "measured CPU count unavailable",
        ),
        "peak_swap_mib": metric(
            raw.get("peak_swap_mib"),
            "MiB",
            "whole_case_sampled",
            "not sampled",
        ),
        "min_host_available_mib": metric(
            raw.get("min_host_available_mib"),
            "MiB",
            "host_whole_case_sampled",
            "not sampled",
        ),
        "npu_utilization_percent": metric(
            None, "%", "device", "no reliable busy/load measurement"
        ),
        "npu_memory_mib": metric(
            None, "MiB", "device", "no device-exclusive memory measurement"
        ),
    }
    ready_samples = [e for e in events if e.get("event") == "sample"]
    if kind == "streaming_asr":
        duration = sum(e["audio_seconds"] for e in ready_samples)
        compute = sum(e["seconds"] for e in ready_samples)
        rtf = compute / duration if duration else None
    elif kind in {"asr", "native_asr", "summer", "sherpa_tts", "piper"}:
        rtf = median([e["rtf"] for e in ready_samples if "rtf" in e])
        scope += ";median_of_samples"
    else:
        rtf = None
    if kind == "llama":
        for name, unit, getter in (
            ("ttft_seconds", "s", lambda e: e.get("ttft_seconds")),
            (
                "generation_tokens_per_second",
                "tokens/s",
                lambda e: e.get("timings", {}).get("predicted_per_second"),
            ),
            ("request_seconds", "s", lambda e: e.get("seconds")),
        ):
            numbers = [
                getter(e) for e in ready_samples if getter(e) is not None
            ]
            values[name] = metric(
                median(numbers),
                unit,
                "legacy_request;median_of_samples",
                "not recorded",
            )
    if kind in {"yolo", "yolo_cpu"}:
        counts = [e for e in ready_samples if "processed" in e]
        for name, unit, getter in (
            ("processed_frames", "frames", lambda e: e.get("processed")),
            ("dropped_frames", "frames", lambda e: e.get("dropped")),
            (
                "output_fps",
                "frames/s",
                lambda e: e["processed"] / e["seconds"]
                if e.get("seconds")
                else None,
            ),
        ):
            numbers = [getter(e) for e in counts if getter(e) is not None]
            values[name] = metric(
                median(numbers),
                unit,
                "legacy_adapter_window;median_of_samples",
                "not recorded",
            )
    values["compute_rtf"] = metric(
        rtf, "ratio", scope, "no compatible RTF measurement"
    )
    delays = [
        s["endpoint_after_energy_seconds"]
        for s in samples
        if s["endpoint_after_energy_seconds"] is not None
    ]
    values["endpoint_after_energy_seconds"] = metric(
        median(delays),
        "s",
        "energy_anchor;median_of_nonempty_final_endpoints",
        "no valid energy-relative final endpoint",
    )
    values["first_partial_seconds"] = metric(
        median(
            [
                s["first_partial_seconds"]
                for s in samples
                if s["first_partial_seconds"] is not None
            ]
        ),
        "s",
        "replay_start;median_of_samples",
        "not measured",
    )
    blocks = [e for e in events if e.get("event") == "asr_block"]
    realtime = kind == "streaming_asr" and config.get("realtime", True)
    for name in ("submit_lateness_seconds", "completion_lag_seconds"):
        values["max_" + name] = metric(
            max((e[name] for e in blocks if name in e), default=None)
            if realtime
            else None,
            "s",
            "maximum_over_realtime_blocks",
            "no realtime block timing",
        )
    loaded = [e for e in events if e.get("event") == "loaded"]
    load_scope = {
        "asr": "model_constructor",
        "streaming_asr": "model_constructor",
        "llama": "subprocess_to_health_ready",
        "piper": "native_child_startup",
        "sherpa_tts": "model_constructor",
    }.get(kind, "adapter_defined")
    values["model_load_seconds"] = metric(
        loaded[0].get("load_seconds") if loaded else None,
        "s",
        load_scope,
        "no separate load measurement",
    )
    resource_file = path.parent / "resources.jsonl"
    resources = (
        [json.loads(line) for line in resource_file.read_text().splitlines()]
        if resource_file.exists()
        else []
    )
    q = quality(samples)
    expected = len(fixtures) if fixtures else len(samples)
    missing = sum(s["output_status"] != "complete" for s in samples)
    completeness = (
        "not_assessed"
        if task != "asr"
        else "no_output"
        if not samples
        else "incomplete"
        if missing
        else "complete"
    )
    comparable = comparison(config, fixtures, scenario)
    if comparable["key"] is not None:
        comparable["conditions"]["environment"] = {
            "platform": manifest.get("platform"),
            "cpu_count": cpu_count,
            "mem_total_kib": mem_total,
        }
        comparable["key"] = hashlib.sha256(
            json.dumps(comparable["conditions"], sort_keys=True).encode()
        ).hexdigest()[:16]
    return {
        "schema_version": VERSION,
        "id": digest(path)[:16],
        "label": config["id"],
        "task": task,
        "workload": "coexistence"
        if kind in {"vision_asr", "coexistence"} or config.get("co_running")
        else "integration"
        if kind == "ros_asr"
        else "single_module",
        "protocol": {
            "id": declared.get("protocol_id", "legacy-" + profile),
            "scenario": scenario,
            "tier": declared.get("tier", "legacy"),
            "round": declared.get("round"),
            "origin": "versioned" if declared else "legacy",
        },
        "device": {
            "id": declared.get("device_id", "legacy-recorded-platform"),
            "platform": manifest.get("platform"),
            "cpu_count": cpu_count,
            "mem_total_kib": mem_total,
        },
        "candidate": identity(config, manifest),
        "comparison": comparable,
        "execution": {
            "status": raw["status"],
            "returncode": raw.get("returncode"),
        },
        "completeness": {
            "status": completeness,
            "expected_samples": expected,
            "incomplete_samples": missing,
        },
        "quality": q,
        "assessment": {
            "performance": "not_assessed",
            "reason": "no application thresholds specified",
        },
        "metrics": values,
        "phases": phases(events, resources, cpu_count, mem_total),
        "samples": samples,
        "evidence": {"result": evidence(path, output)},
    }


def ros_legacy(raw: dict, path: Path) -> dict:
    """迁移独立ROS回放，缺失的资源与人工参考仍为未测。"""
    summary_path = path.parent / "summary.json"
    summaries = (
        read_json(summary_path).get("turns", [])
        if summary_path.exists()
        else []
    )
    coordination = path.parent.parent / "coordination.json"
    co_running = coordination.exists() and "vision_returncode" in read_json(
        coordination
    )
    samples = []
    for turn in raw["turns"]:
        events = [
            e for e in raw["events"] if e["stream_id"] == turn["stream_id"]
        ]
        finals = [e for e in events if e["kind"] == "final"]
        partials = [e for e in events if e["kind"] == "partial" and e["text"]]
        summary = next(
            (s for s in summaries if s["stream_id"] == turn["stream_id"]), {}
        )
        delays = summary.get("endpoint_after_energy_seconds", [])
        samples.append(
            {
                "event": "sample",
                "input": turn["stream_id"],
                "transcript": "".join(e["text"] for e in finals),
                "first_partial_seconds": partials[0]["received"]
                - turn["start"]
                if partials
                else -1,
                "endpoint_after_energy_seconds": delays[-1] if delays else -1,
            }
        )
    return {
        "id": path.parent.name,
        "config": {
            "id": "ros-" + path.parent.name,
            "kind": "ros_asr",
            "co_running": co_running,
            "provider": "rknn"
            if "provider:=rknn" in raw.get("command", [])
            else None,
        },
        "status": "ok" if raw["returncode"] == 0 else "error",
        "returncode": raw["returncode"],
        "events": samples,
    }


def source_results(root: Path):
    """逐层寻找运行结果，组合报告使用保留的原始manifest。"""
    if not root.is_dir():
        raise ValueError("source directory does not exist: " + str(root))
    inherited = {}
    manifest = root / "manifest.json"
    if manifest.exists():
        inherited = read_json(manifest)
        if "source_runs" in inherited:
            for name in inherited["source_runs"]:
                origin = root / "manifests" / (Path(name).name + ".json")
                if origin.exists():
                    source = read_json(origin)
                    for case in source.get("suite", {}).get("cases", []):
                        inherited.setdefault("case_manifests", {})[
                            case["id"]
                        ] = source
    direct = root / "result.json"
    paths = ([direct] if direct.exists() else []) + sorted(
        root.glob("*/result.json")
    )
    for path in paths:
        data = read_json(path)
        if "config" in data or "turns" in data:
            yield (
                path,
                inherited.get("case_manifests", {}).get(
                    data.get("id"), inherited
                ),
            )


def validate(document: dict) -> None:
    """校验公开结果契约的必要约束，错误数据不进入Dashboard。"""
    if document.get("schema_version") != VERSION:
        raise ValueError("unsupported evaluation schema_version")
    schema = read_json(
        Path(__file__).with_name("schemas") / "evaluation-v1.schema.json"
    )

    def required(value, declaration):
        if (
            not isinstance(value, dict)
            or not set(declaration.get("required", [])) <= value.keys()
        ):
            raise ValueError("missing required contract fields")

    required(document, schema)
    if not isinstance(document["records"], list):
        raise ValueError("records must be an array")
    ids = set()
    for record in document["records"]:
        declaration = schema["$defs"]["record"]
        required(record, declaration)
        for name, field in declaration["properties"].items():
            if field.get("type") == "object":
                required(record[name], field)
        if record["schema_version"] != VERSION or record["id"] in ids:
            raise ValueError("duplicate record id or schema version mismatch")
        ids.add(record["id"])
        windows = [record["metrics"]] + list(record["phases"].values())
        for window in windows:
            for value in window.values():
                if not isinstance(value, dict):
                    if window is record["metrics"]:
                        raise ValueError("metric must be a typed object")
                    continue
                required(value, schema["$defs"]["metric"])
                if not value["unit"] or not value["scope"]:
                    raise ValueError("metrics require unit and scope")
                metric(
                    value["value"],
                    value["unit"],
                    value["scope"],
                    value["reason"],
                )
        q = record["quality"]
        if not 0 <= q["evaluated_samples"] <= q["total_samples"]:
            raise ValueError("invalid reference coverage")
        if q["reference_characters"]:
            expected_cer = q["character_errors"] / q["reference_characters"]
            if q["cer"] != expected_cer:
                raise ValueError("CER contradicts character counts")
        elif q["cer"] is not None:
            raise ValueError("CER requires reference characters")
        if record["comparison"]["type"] not in {
            "legacy",
            "deployment",
            "controlled_backend",
        }:
            raise ValueError("unknown comparison type")
        if (
            record["protocol"]["origin"] == "versioned"
            and not record["comparison"]["key"]
        ):
            raise ValueError("versioned record requires a comparison key")
        if (
            record["quality"]["status"] == "not_evaluated"
            and record["quality"]["cer"] is not None
        ):
            raise ValueError("unassessed quality cannot contain CER")
        if (
            record["comparison"]["type"] == "legacy"
            and record["comparison"]["key"] is not None
        ):
            raise ValueError(
                "legacy data cannot claim versioned comparability"
            )
    if document["summaries"] != summarize_records(document["records"]):
        raise ValueError("summary contradicts per-round records")
    json.dumps(document, allow_nan=False)


def export(sources: list, output: Path) -> Path:
    """从原始运行新建评测视图，拒绝覆盖历史或现有导出。"""
    records = []
    seen = set()
    for source in sources:
        for path, manifest in source_results(source):
            resolved = path.resolve()
            identity_hash = digest(resolved)
            if identity_hash in seen:
                continue
            seen.add(identity_hash)
            raw = read_json(path)
            if "turns" in raw and "config" not in raw:
                raw = ros_legacy(raw, path)
            records.append(normalize_result(path, manifest, output, raw))
    if not records:
        raise ValueError("no supported case result.json found")
    document = {
        "schema_version": VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "producer": {
            name: digest(Path(__file__).parent / name)
            for name in (
                "evaluation.py",
                "evaluation_metrics.py",
                "evaluation_report.py",
                "schemas/evaluation-v1.schema.json",
                "templates/evaluation.html",
            )
        },
        "records": records,
        "summaries": summarize_records(records),
    }
    validate(document)
    output.mkdir(parents=True)
    target = output / "results.json"
    target.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False)
        + "\n"
    )
    from evaluation_report import render  # 输出层不参与采集或推理。

    render(target, output / "report.html")
    return target


def main() -> None:
    """提供导出、校验和仅从数据重建静态页面的入口。"""
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="operation", required=True)
    convert = commands.add_parser("export")
    convert.add_argument("output", type=Path)
    convert.add_argument("sources", nargs="+", type=Path)
    check = commands.add_parser("validate")
    check.add_argument("results", type=Path)
    page = commands.add_parser("report")
    page.add_argument("results", type=Path)
    page.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.operation == "export":
        print(export(args.sources, args.output))
    elif args.operation == "validate":
        validate(read_json(args.results))
        print("valid", args.results)
    else:
        from evaluation_report import render

        render(args.results, args.output)
        print(args.output)


if __name__ == "__main__":
    main()
