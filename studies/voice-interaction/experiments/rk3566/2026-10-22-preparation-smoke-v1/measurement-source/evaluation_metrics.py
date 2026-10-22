"""轻量评测的指标口径、阶段资源和参考文本评分。"""

import math
import statistics
import unicodedata

VERSION = "1.0"
ASR_PROTOCOL = "edge-asr-lite-v1"
NORMALIZATION = "nfkc-casefold-no-punctuation-space-v1"


def metric(value, unit: str, scope: str, reason=None) -> dict:
    """缺失指标必须说明原因，拒绝NaN等不可移植数值。"""
    if value is not None and (
        type(value) not in (int, float) or not math.isfinite(value)
    ):
        raise ValueError("metric must be finite or null")
    if value is None and not reason:
        raise ValueError("missing metric requires a reason")
    return dict(
        value=value,
        unit=unit,
        scope=scope,
        reason=reason if value is None else None,
    )


def normalize_text(text: str) -> str:
    """固定中文CER归一口径，保留数字及汉字的实际表达差异。"""
    return "".join(
        c
        for c in unicodedata.normalize("NFKC", text).casefold()
        if not c.isspace() and not unicodedata.category(c).startswith("P")
    )


def edit_distance(reference: str, hypothesis: str) -> int:
    """用线性空间计算字符编辑距离，空输出保留为删除错误。"""
    previous = list(range(len(hypothesis) + 1))
    for i, expected in enumerate(reference, 1):
        current = [i]
        for j, actual in enumerate(hypothesis, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[j] + 1,
                    previous[j - 1] + (expected != actual),
                )
            )
        previous = current
    return previous[-1]


def quality(samples: list) -> dict:
    """仅对有独立可靠参考的子集评分，来源与覆盖分母保持可见。"""
    evaluated = []
    for sample in samples:
        reference = sample.get("reference") or {}
        if reference.get("kind") not in {
            "dataset_transcript",
            "manual_verified",
        }:
            continue
        if not reference.get("source"):
            raise ValueError("trusted reference requires a source")
        expected = normalize_text(reference["text"])
        if not expected:
            raise ValueError("trusted reference must contain scoreable text")
        actual = normalize_text(sample.get("transcript") or "")
        evaluated.append(
            dict(
                case_id=sample["case_id"],
                errors=edit_distance(expected, actual),
                characters=len(expected),
                exact=expected == actual,
                output_status=sample["output_status"],
            )
        )
    characters = sum(e["characters"] for e in evaluated)
    complete = all(e["output_status"] == "complete" for e in evaluated)
    return {
        "status": (
            "not_evaluated"
            if not evaluated
            else "evaluated_subset"
            if complete
            else "incomplete_outputs"
        ),
        "normalization": NORMALIZATION,
        "evaluated_samples": len(evaluated),
        "total_samples": len(samples),
        "reference_characters": characters,
        "character_errors": sum(e["errors"] for e in evaluated),
        "cer": (
            sum(e["errors"] for e in evaluated) / characters
            if characters
            else None
        ),
        "exact_matches": sum(e["exact"] for e in evaluated),
        "samples": evaluated,
    }


def resource_window(samples: list, start, end, cpu_count, mem_total) -> dict:
    """按同一单调钟窗口求资源；边界不足时不伪造阶段CPU占比。"""
    rows = [
        s for s in samples if start <= s.get("monotonic_seconds", -1) <= end
    ]
    before = [s for s in samples if s.get("monotonic_seconds", -1) <= start]
    after = [s for s in samples if s.get("monotonic_seconds", -1) >= end]
    cores = None
    reason = "phase boundaries were not bracketed by resource samples"
    cpu_scope = "sample_bracket"
    bounds = (before[-1], after[0]) if before and after else None
    if bounds is None and len(rows) >= 2:
        bounds = (rows[0], rows[-1])
        cpu_scope = "phase_interior_samples"
    if bounds:
        first, last = bounds
        delta = last["cpu_seconds"] - first["cpu_seconds"]
        seconds = last["monotonic_seconds"] - first["monotonic_seconds"]
        if delta >= 0 and seconds > 0:
            cores = delta / seconds
            reason = None
    pss = max((s["pss_kib"] / 1024 for s in rows), default=None)
    rss = max((s["rss_kib"] / 1024 for s in rows), default=None)
    missing = "no resource samples in phase"
    capacity = (
        cores / cpu_count * 100 if cores is not None and cpu_count else None
    )
    ram = (
        pss * 1024 / mem_total * 100 if pss is not None and mem_total else None
    )
    return {
        "duration_seconds": end - start,
        "sample_count": len(rows),
        "average_cpu_cores": metric(cores, "cores", cpu_scope, reason),
        "cpu_capacity_percent": metric(
            capacity, "%", "process_tree", reason or "CPU count unavailable"
        ),
        "peak_pss_mib": metric(pss, "MiB", "process_tree_sampled", missing),
        "peak_rss_mib": metric(rss, "MiB", "process_tree_sampled", missing),
        "ram_percent": metric(
            ram, "%", "sampled_pss/MemTotal", "MemTotal or PSS unavailable"
        ),
    }


def phases(events: list, resources: list, cpu_count, mem_total) -> dict:
    """消费显式阶段事件，旧记录缺失边界时保持空阶段。"""
    active = {}
    output = {}
    for event in events:
        if event.get("event") != "phase":
            continue
        name = event["name"]
        if event["state"] == "start":
            active[name] = event["monotonic_seconds"]
        elif event["state"] == "end" and name in active:
            start = active.pop(name)
            end = event["monotonic_seconds"]
            if end < start:
                raise ValueError("phase ends before it starts")
            output[name] = resource_window(
                resources, start, end, cpu_count, mem_total
            )
    return output


def median(values: list):
    """空集合显式缺失，不把未测变成零。"""
    return statistics.median(values) if values else None


def summarize_records(records: list) -> list:
    """将独立轮次的汇总也写入JSON，页面只渲染已导出的统计。"""
    import json
    from collections import defaultdict

    groups = defaultdict(list)
    for record in records:
        if record["protocol"]["origin"] != "versioned":
            continue
        key = json.dumps(
            [
                record["task"],
                record["workload"],
                record["protocol"]["id"],
                record["protocol"]["scenario"],
                record["protocol"]["tier"],
                record["comparison"]["key"],
                record["candidate"],
            ],
            sort_keys=True,
        )
        groups[key].append(record)
    result = []
    for rows in groups.values():
        rounds = [row["protocol"]["round"] for row in rows]
        if len(rounds) != len(set(rounds)):
            raise ValueError("duplicate candidate round in comparison group")
        metrics = {}
        for name in (
            "cpu_capacity_percent",
            "peak_pss_mib",
            "ram_percent",
            "compute_rtf",
            "endpoint_after_energy_seconds",
        ):
            selected = []
            for row in rows:
                window = row["phases"].get("inference", row["metrics"])
                selected.append(
                    window[name] if name in window else row["metrics"][name]
                )
            numbers = [m["value"] for m in selected if m["value"] is not None]
            metrics[name] = dict(
                median=median(numbers),
                min=min(numbers) if numbers else None,
                max=max(numbers) if numbers else None,
                n=len(numbers),
                unit=selected[0]["unit"],
                reason=None if numbers else "no measurements",
            )
        result.append(
            dict(
                record_ids=[r["id"] for r in rows],
                candidate_id=rows[0]["candidate"]["id"],
                comparison_key=rows[0]["comparison"]["key"],
                rounds=rounds,
                successful_runs=sum(
                    r["execution"]["status"] == "ok" for r in rows
                ),
                metrics=metrics,
            )
        )
    return result
