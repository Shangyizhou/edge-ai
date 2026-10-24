"""将冻结执行记录幂等同步到 MLflow，不导入或运行模型。"""

import math
import os
import statistics
import time
from pathlib import Path
from typing import Any, Dict

from tools.edge_benchmark.experiment import (
    digest,
    identity,
    read_json,
    write_json,
)


def verify_execution(directory: Path) -> dict:
    """验证已完成记录及证据；拒绝不确定的在途执行。"""
    record = read_json(directory / "execution.json")
    content = {
        key: value
        for key, value in record.items()
        if key not in {"synchronization", "content_id"}
    }
    if (
        record["status"] == "running"
        or identity(content) != record["content_id"]
    ):
        raise ValueError("execution is incomplete or changed")
    evidence = read_json(directory / "evidence.json")
    if identity(evidence) != record["evidence_id"]:
        raise ValueError("changed evidence manifest")
    for entry in evidence:
        path = (directory / entry["path"]).resolve()
        try:
            path.relative_to(directory.resolve())
        except ValueError as error:
            raise ValueError("evidence escapes execution directory") from error
        if digest(path) != entry["sha256"]:
            raise ValueError("changed execution evidence: " + entry["path"])
    return record


def metric_values(item: dict) -> dict:
    """只映射已有有限测量，未知值不伪装为零。"""
    summary = item.get("result", {}).get("summary", {})
    values = {
        key: value
        for key, value in summary.items()
        if type(value) in (int, float) and math.isfinite(value)
    }
    cases = item.get("result", {}).get("cases", [])
    values["planned_cases"] = item.get("planned_cases", len(cases))
    values["completed_cases"] = sum(
        row.get("status") == "completed" for row in cases
    )
    if values["planned_cases"]:
        values["completion_rate"] = (
            values["completed_cases"] / values["planned_cases"]
        )
    no_calls = [row for row in cases if row.get("kind") in {"chat", "persona"}]
    if no_calls:
        values["no_call_samples"] = len(no_calls)
        values["no_call_misroutes"] = sum(
            bool(row.get("assessment", {}).get("reply", {}).get("tool_calls"))
            for row in no_calls
        )
    latencies = [
        row["generation"]["wall_seconds"]
        for row in cases
        if row.get("status") == "completed"
        and isinstance(
            row.get("generation", {}).get("wall_seconds"), (int, float)
        )
    ]
    if latencies:
        values["response_seconds_median"] = statistics.median(latencies)
        values["response_latency_samples"] = len(latencies)
    for name in ("rss", "pss"):
        peaks = [
            row.get("resources", {}).get("peak_" + name + "_bytes")
            for row in cases
        ]
        peaks = [value for value in peaks if value is not None]
        if peaks:
            values["sampled_peak_" + name + "_mib"] = max(peaks) / 2**20
    return values


def synchronize(directory: Path, uri: str) -> Dict[str, Any]:
    """同执行身份重复同步不重复建 Run；同步失败保留待同步事实。"""
    # MLflow 是控制端可选依赖，模型子进程和离线计划不需要安装它。
    from mlflow import MlflowClient

    directory = directory.resolve()
    record = verify_execution(directory)
    lock = directory / ".sync.lock"
    descriptor = os.open(
        str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
    )
    os.close(descriptor)
    receipt = {"status": "pending", "uri": uri, "runs": {}}
    try:
        client = MlflowClient(tracking_uri=uri)
        suffix = (
            "/synthetic"
            if record["source_kind"] != "device_measurement"
            else ""
        )
        experiment_name = "edge-ai/" + record["task"] + suffix
        experiment = client.get_experiment_by_name(experiment_name)
        experiment_id = (
            experiment.experiment_id
            if experiment
            else client.create_experiment(experiment_name)
        )
        plan = read_json(directory / "plan.json")
        for item in record["candidates"]:
            key = record["comparison_id"] + ":" + item["id"]
            matches = client.search_runs(
                [experiment_id],
                filter_string=f"tags.edge_execution_id = '{key}'",
            )
            if len(matches) > 1:
                raise ValueError("duplicate existing execution binding")
            if matches:
                run = matches[0]
                if run.data.tags.get("source_digest") != record["content_id"]:
                    raise ValueError(
                        "existing execution has different content"
                    )
            else:
                run = client.create_run(
                    experiment_id,
                    tags={
                        "mlflow.runName": plan["request"]["name"]
                        + " / "
                        + item["id"],
                        "edge_execution_id": key,
                        "comparison_id": record["comparison_id"],
                        "source_digest": record["content_id"],
                        "source_kind": record["source_kind"],
                        "model_id": item["model_id"],
                        "protocol_id": record["protocol_id"],
                        "plan_id": record["plan_id"],
                        "mlflow.source.git.commit": plan["code_commit"],
                        "dataset_id": "suite-"
                        + plan["request"]["suite"]["sha256"],
                        "task": record["task"],
                        "data_use": plan["request"]["data_use"],
                        "comparison_view": "evaluation",
                        "execution_status": item["status"],
                    },
                )
            run_id = run.info.run_id
            receipt["runs"][item["id"]] = run_id
            candidate = next(
                c
                for c in plan["request"]["candidates"]
                if c["id"] == item["id"]
            )
            params = {
                "precision": item["precision"],
                "model_id": item["model_id"],
                "suite_sha256": plan["request"]["suite"]["sha256"],
                "case_timeout_seconds": plan["request"]["budget"][
                    "case_timeout_seconds"
                ],
            }
            native = candidate["request"]
            params.update(
                {
                    key: value
                    for key, value in native.items()
                    if type(value) in (str, int, float, bool)
                }
            )
            params.update(native.get("generation", {}))
            for key_name, value in params.items():
                client.log_param(run_id, key_name, str(value))
            for key_name, value in metric_values(item).items():
                history = client.get_metric_history(run_id, key_name)
                if history:
                    if any(point.value != value for point in history):
                        raise ValueError("metric content conflict")
                else:
                    client.log_metric(
                        run_id,
                        key_name,
                        value,
                        step=0,
                        timestamp=int(time.time() * 1000),
                    )
            client.log_dict(run_id, candidate, "configuration.json")
            client.log_dict(run_id, item.get("result", {}), "results.json")
            rows = item.get("result", {}).get("cases", [])
            if not any(
                entry.path == "cases.json"
                for entry in client.list_artifacts(run_id)
            ):
                client.log_table(
                    run_id,
                    {
                        "id": [row["id"] for row in rows],
                        "status": [row.get("status") for row in rows],
                        "detail": [str(row) for row in rows],
                    },
                    "cases.json",
                )
            client.log_artifact(run_id, str(directory / "plan.json"))
            client.log_artifact(run_id, str(directory / "evidence.json"))
            # 只同步本次目录的文本证据，绝不递归上传外部模型或音频。
            for entry in read_json(directory / "evidence.json"):
                path = directory / entry["path"]
                if path.suffix in {".json", ".jsonl", ".log", ".py", ".txt"}:
                    client.log_artifact(
                        run_id,
                        str(path),
                        artifact_path=str(
                            Path("evidence") / Path(entry["path"]).parent
                        ),
                    )
            state = (
                "FINISHED"
                if item["status"] == "completed"
                else "KILLED"
                if item["status"] in {"cancelled", "not_run"}
                else "FAILED"
            )
            client.set_terminated(run_id, status=state)
        receipt["status"] = "synced"
    except Exception as error:
        # 测量已完成；同步异常单独记录并交给调用者决定退出状态。
        receipt.update(
            status="error", error=f"{type(error).__name__}: {error}"
        )
        raise
    finally:
        write_json(directory / "sync.json", receipt)
        lock.unlink()
    return receipt
