"""顺序运行冻结候选，保留中断事实，MLflow 同步不触发推理。"""

import copy
import json
import platform
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from .experiment import digest, identity, read_json, validate_plan, write_json

ROOT = Path(__file__).resolve().parents[2]


def active_case_started(output: Path) -> Optional[float]:
    """读取现有执行器的活动案例；中途写入时等待下次轮询。"""
    for path in output.rglob("active-case.json"):
        try:
            event = read_json(path)
        except (OSError, ValueError):
            continue
        if event.get("active"):
            return event["started_monotonic"]
    # ASR 原生事件区分加载、首轮、预热与正式推理窗口。
    for path in output.rglob("events.jsonl"):
        start = None
        try:
            lines = path.read_text().splitlines()
            for line in lines:
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if (
                    start is not None
                    and event.get("event") == "sample"
                    and "end_monotonic" in event
                ):
                    start = event["end_monotonic"]
                if (
                    event.get("event") == "phase"
                    and event.get("name") == "inference"
                ):
                    start = (
                        event["monotonic_seconds"]
                        if event.get("state") == "start"
                        else None
                    )
        except OSError:
            continue
        if start is not None:
            return start
    return None


def execute_candidate(
    task: str,
    item: dict,
    suite: dict,
    output: Path,
    seconds: float,
    case_seconds: float,
) -> dict:
    """子进程执行隔离依赖；超时只停止本次拥有的进程树。"""
    # 控制端依赖只在真实执行边界导入，plan 不需 psutil。
    import psutil

    if task == "asr_transcription" and platform.system() != "Linux":
        return {
            "status": "failed",
            "reason": "ASR native sampler requires Linux",
        }
    request = copy.deepcopy(item["request"])
    request["run_id"] = output.name
    if task == "qwen_tool_calls":
        request["generation"]["timeout_seconds"] = case_seconds
    else:
        request.update(
            candidate_timeout_seconds=seconds, worker_python=item["python"]
        )
    input_path = output.parent / (item["id"] + "-input.json")
    write_json(input_path, {"task": task, "request": request, "suite": suite})
    command = [
        item["python"],
        "-m",
        "tools.edge_benchmark.task_adapters",
        str(input_path),
        str(output),
    ]
    tracked = {}
    reason = None
    started = time.monotonic()
    returncode = None
    with (output.parent / (item["id"] + ".log")).open("w") as log:
        child = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            while child.poll() is None:
                try:
                    parent = psutil.Process(child.pid)
                    for process in [parent] + parent.children(recursive=True):
                        tracked[(process.pid, process.create_time())] = process
                except psutil.NoSuchProcess:
                    pass
                if time.monotonic() - started >= seconds:
                    reason = "total_budget"
                    break
                active = (
                    active_case_started(output) if output.exists() else None
                )
                if (
                    active is not None
                    and time.monotonic() - active >= case_seconds
                ):
                    reason = "case_timeout"
                    break
                time.sleep(0.05)
        except KeyboardInterrupt:
            reason = "cancelled"
        finally:
            # 先停止拥有的后代，再停止控制 worker；不按名称查杀服务。
            alive = []
            for process in reversed(list(tracked.values())):
                try:
                    if process.is_running():
                        process.terminate()
                        alive.append(process)
                except psutil.NoSuchProcess:
                    pass
            _, pending = psutil.wait_procs(alive, timeout=2)
            for process in pending:
                try:
                    process.kill()
                except psutil.NoSuchProcess:
                    pass
            psutil.wait_procs(pending, timeout=2)
            if child.poll() is None:
                child.kill()
            returncode = child.wait()
    result_path = output / "results.json"
    if (
        not result_path.exists()
        and (output / "benchmark/results.json").exists()
    ):
        result_path = output / "benchmark/results.json"
    try:
        result = read_json(result_path) if result_path.exists() else {}
    except ValueError:
        result = {}
    if task == "qwen_tool_calls" and not result:
        cases = []
        for path in sorted(output.rglob("cases/*.json")):
            try:
                cases.append(read_json(path))
            except ValueError:
                continue
        if cases:
            result = {
                "status": "partial",
                "cases": cases,
                "summary": {},
                "recovery": "valid case files; aggregate was incomplete",
            }

    if (
        task == "asr_transcription"
        and not result
        and (output / "manifest.json").exists()
    ):
        from .task_adapters import read_asr_result

        result = read_asr_result(suite, output)
    if reason:
        status = "cancelled" if reason == "cancelled" else "partial"
    elif returncode == 0 and result.get("status") == "completed":
        status = "completed"
    else:
        status = "partial" if result.get("cases") else "failed"
    return {
        "status": status,
        "reason": reason,
        "returncode": returncode,
        "wall_seconds": time.monotonic() - started,
        "result": result,
        "command": command,
    }


def run_plan(
    plan_path: Path, output: Path, executor: Optional[Callable] = None
) -> Dict[str, Any]:
    """逐候选执行；总预算耗尽时保留未执行项，不自动重试。"""
    plan = read_json(plan_path)
    validate_plan(plan)
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "plan.json", plan)
    source = output / "source"
    source.mkdir()
    for asset in plan["assets"]:
        module = Path(asset["path"])
        if module.suffix == ".py" and ROOT in module.parents:
            target = source / module.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(module.read_bytes())
    comparison_id = "bench-" + uuid.uuid4().hex
    record = {
        "schema": "edge-benchmark/execution-v1",
        "comparison_id": comparison_id,
        "plan_id": plan["plan_id"],
        "task": plan["request"]["task"],
        "protocol_id": plan["request"]["protocol_id"],
        "source_kind": (
            "synthetic_fixture"
            if executor is not None
            else "device_measurement"
        ),
        "status": "running",
        "candidates": [],
        "synchronization": "pending",
    }
    write_json(output / "execution.json", record)
    started = time.monotonic()
    cancelled = False
    for item in plan["request"]["candidates"]:
        remaining = plan["request"]["budget"]["total_seconds"] - (
            time.monotonic() - started
        )
        if remaining <= 0 or cancelled:
            result = {
                "status": "not_run",
                "reason": "cancelled" if cancelled else "total_budget",
            }
        else:
            try:
                result = (executor or execute_candidate)(
                    record["task"],
                    item,
                    plan["suite"],
                    output / item["id"],
                    remaining,
                    plan["request"]["budget"]["case_timeout_seconds"],
                )
            except OSError as error:
                result = {"status": "failed", "reason": str(error)}
        result.update(
            planned_cases=plan["case_count_per_candidate"],
            id=item["id"],
            model_id=item["model_id"],
            precision=item["precision"],
        )
        record["candidates"].append(result)
        cancelled = cancelled or result["status"] == "cancelled"
        write_json(output / "execution.json", record)
    record["status"] = (
        "cancelled"
        if cancelled
        else "completed"
        if all(item["status"] == "completed" for item in record["candidates"])
        else "partial"
    )
    record["wall_seconds"] = time.monotonic() - started
    evidence = [
        {"path": str(path.relative_to(output)), "sha256": digest(path)}
        for path in sorted(output.rglob("*"))
        if path.is_file() and path.name != "execution.json"
    ]
    write_json(output / "evidence.json", evidence)
    record["evidence_id"] = identity(evidence)
    # 结果身份不包含可变同步状态，补同步时不得修改测量。
    record["content_id"] = identity(
        {
            key: value
            for key, value in record.items()
            if key != "synchronization"
        }
    )
    write_json(output / "execution.json", record)
    return record
