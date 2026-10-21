"""从有版本的评测JSON生成静态页面，展示层不重新测量。"""

import html
import json
import os
from collections import defaultdict
from pathlib import Path
from string import Template
from urllib.parse import quote, urlsplit


def escaped(value) -> str:
    """模型输出、配置和来源统一按纯文本转义。"""
    return html.escape(str(value))


def display(value, digits=2) -> str:
    """缺失保持可见，不用零占位。"""
    return "未测" if value is None else f"{value:.{digits}f}"


def safe_link(value: str) -> str:
    """只允许本地相对证据链接，拒绝可执行或远端URI。"""
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or value.startswith("/"):
        raise ValueError("evidence links must be relative local paths")
    return quote(value, safe="/._-")


def resource_cells(record: dict):
    """推理窗口优先；历史记录显示全case，待机另列。"""
    active = record["phases"].get("inference")
    metrics = active if active else record["metrics"]
    idle = record["phases"].get("idle", {})
    cpu = display(metrics["cpu_capacity_percent"]["value"])
    pss = display(metrics["peak_pss_mib"]["value"])
    ram = display(metrics["ram_percent"]["value"])
    idle_pss = display(idle.get("peak_pss_mib", {}).get("value"))
    return cpu, pss, ram, idle_pss, "推理窗口" if active else "全case"


def round_summaries(records: list, summaries: list) -> str:
    """只渲染JSON中的逐轮汇总，不在页面层计算指标。"""
    ids = {record["id"] for record in records}
    labels = {
        "cpu_capacity_percent": "CPU容量%",
        "peak_pss_mib": "PSS MiB",
        "ram_percent": "RAM%",
        "compute_rtf": "计算RTF",
        "endpoint_after_energy_seconds": "能量锚点等待s",
    }
    paragraphs = []
    for summary in summaries:
        if (
            len(summary["record_ids"]) < 2
            or not set(summary["record_ids"]) <= ids
        ):
            continue
        cells = [
            escaped(summary["candidate_id"]) + f" · {len(summary['rounds'])}轮"
        ]
        for name, label in labels.items():
            item = summary["metrics"][name]
            if item["n"]:
                cells.append(
                    f"{label} {item['median']:.3f} "
                    f"[{item['min']:.3f}–{item['max']:.3f}] (n={item['n']})"
                )
        cells.append(
            f"执行成功 {summary['successful_runs']}/{len(summary['rounds'])}"
            "；失败轮次仍保留"
        )
        paragraphs.append("<p>" + " · ".join(cells) + "</p>")
    return (
        (
            "<div class='muted'>各轮中位数 [最小–最大]；不合并为更多独立语料。"
            + "".join(paragraphs)
            + "</div>"
        )
        if paragraphs
        else ""
    )


def render(results_path: Path, output: Path) -> None:
    """校验数据后按可比组展示，HTML只负责格式与证据导航。"""
    from evaluation import read_json, validate

    document = read_json(results_path)
    validate(document)
    groups = defaultdict(list)
    for record in document["records"]:
        comparison = record["comparison"]
        protocol = record["protocol"]
        key = (
            record["task"],
            record["workload"],
            protocol["id"],
            protocol["scenario"],
            protocol["tier"],
            comparison["type"],
            comparison["key"],
        )
        groups[key].append(record)
    sections = []
    for key, records in groups.items():
        task, workload, protocol, scenario, tier, kind, comparison_key = key
        rows = []
        detail = []
        for record in records:
            cpu, pss, ram, idle, window = resource_cells(record)
            m = record["metrics"]
            q = record["quality"]
            cer = display(q["cer"] * 100 if q["cer"] is not None else None)
            quality = (
                f"CER {cer}% · "
                f"{q['evaluated_samples']}/{q['total_samples']}有参考"
            )
            if q["cer"] is None:
                quality = "未评估 · 无可靠参考"
            if task == "llm":
                performance = (
                    display(m.get("ttft_seconds", {}).get("value"), 3)
                    + " s / "
                    + display(
                        m.get("generation_tokens_per_second", {}).get("value")
                    )
                    + " tokens/s"
                )
            elif task == "vision":
                performance = (
                    display(m.get("output_fps", {}).get("value"))
                    + " fps / "
                    + display(m.get("processed_frames", {}).get("value"), 0)
                    + " / "
                    + display(m.get("dropped_frames", {}).get("value"), 0)
                )
            else:
                performance = display(m["compute_rtf"]["value"], 3)
            e = record["evidence"]["result"]
            link = safe_link(e["path"])
            status = record["execution"]["status"]
            rows.append(
                "<tr><td>"
                + escaped(record["label"])
                + "<br><small>"
                + escaped(record["candidate"]["backend"] or "历史未声明")
                + " · 轮次 "
                + escaped(record["protocol"]["round"] or "—")
                + "</small></td><td>"
                + cpu
                + "%<br><small>"
                + window
                + "</small></td><td>"
                + pss
                + " MiB<br><small>"
                + ram
                + "% RAM</small></td><td>"
                + idle
                + " MiB</td><td>"
                + performance
                + "</td><td>"
                + display(m["endpoint_after_energy_seconds"]["value"], 3)
                + " s</td><td>"
                + escaped(quality)
                + "</td><td>"
                + escaped(status)
                + "<br><small>输出："
                + escaped(record["completeness"]["status"])
                + "</small></td><td><a href='"
                + link
                + "'>原始结果</a></td></tr>"
            )
            detail.append(
                "<details><summary>"
                + escaped(record["label"])
                + " · 计时口径、缺失原因与逐例输出</summary><pre>"
                + escaped(
                    json.dumps(
                        {
                            k: record[k]
                            for k in (
                                "candidate",
                                "comparison",
                                "metrics",
                                "phases",
                                "quality",
                                "samples",
                            )
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
                + "</pre></details>"
            )
        title = " · ".join((task.upper(), workload, scenario, tier))
        compatibility = (
            "历史口径，未声明新版可比性"
            if kind == "legacy"
            else kind + " · 比较键 " + comparison_key
        )
        sections.append(
            "<section><h2>"
            + escaped(title)
            + "</h2><p class='muted'>"
            + escaped(protocol)
            + " · "
            + escaped(compatibility)
            + "</p>"
            + round_summaries(records, document["summaries"])
            + "<div class='scroll'><table><tr><th>配置</th>"
            + "<th>CPU容量占比</th>"
            + "<th>峰值PSS / RAM占比</th><th>待机PSS</th><th>"
            + (
                "TTFT / 生成速度"
                if task == "llm"
                else "输出FPS / 完成 / 丢帧"
                if task == "vision"
                else "计算RTF"
            )
            + "</th>"
            + "<th>能量锚点最终等待</th><th>质量与覆盖</th>"
            + "<th>执行 / 输出</th>"
            + "<th>证据</th></tr>"
            + "".join(rows)
            + "</table></div>"
            + "".join(detail)
            + "</section>"
        )
    counts = [
        ("执行记录", len(document["records"])),
        (
            "版本化协议",
            sum(
                r["protocol"]["origin"] == "versioned"
                for r in document["records"]
            ),
        ),
        (
            "历史记录",
            sum(
                r["protocol"]["origin"] == "legacy"
                for r in document["records"]
            ),
        ),
        ("比较面板", len(groups)),
    ]
    template = Template(
        Path(__file__)
        .with_name("templates")
        .joinpath("evaluation.html")
        .read_text()
    )
    output.write_text(
        template.substitute(
            version=escaped(document["schema_version"]),
            created=escaped(document["generated_at"]),
            data_link=safe_link(
                os.path.relpath(
                    results_path.resolve(), output.parent.resolve()
                )
            ),
            cards="".join(
                f"<div class='card'><b>{n}</b>{name}</div>"
                for name, n in counts
            ),
            groups="".join(sections),
        )
    )
