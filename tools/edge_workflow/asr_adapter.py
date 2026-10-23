"""Adapt actual sherpa ASR process evidence to the generic experiment envelope."""

import argparse
import hashlib
import html
import json
import platform
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/edge_benchmark"))
from benchmark import inventory, run_case, write_json
from evaluation_metrics import quality


def execute(path, output):
    path = Path(path)
    d = json.loads(path.read_text())
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    suite = d["execution_suite"]
    measured = output / "measurements"
    measured.mkdir()
    info = inventory(suite)
    info["cpuinfo"] = "\n".join(
        line
        for line in info.get("cpuinfo", "").splitlines()
        if not line.lower().startswith("serial")
    )
    write_json(measured / "manifest.json", info)
    started = time.monotonic()
    for config in suite["cases"]:
        remaining = suite["budget_seconds"] - (time.monotonic() - started)
        if remaining <= 0:
            break
        limited = dict(config, timeout=min(config["timeout"], remaining))
        run_case(limited, measured, suite["python"])
    records = []
    cases = []
    for config in suite["cases"]:
        recordpath = output / "measurements" / config["id"] / "result.json"
        record = (
            json.loads(recordpath.read_text())
            if recordpath.exists()
            else {"events": [], "status": "not_run"}
        )
        records.append(record)
        observed = {
            e["fixture"]: e
            for e in record["events"]
            if e["event"] == "sample" and e.get("stage") == "inference"
        }
        for fixture in config["fixture_ids"]:
            event = observed.get(fixture)
            cases.append(
                {
                    "id": config["id"] + "-" + fixture,
                    "candidate": config["id"],
                    "status": "completed" if event else "failed",
                    "event": event,
                    "error": None if event else "no completed inference event",
                }
            )
    qs = [
        {
            "case_id": c["id"],
            "reference": c["event"].get("reference"),
            "transcript": c["event"]["final_text"],
            "output_status": "complete",
        }
        for c in cases
        if c["event"]
    ]
    q = quality(qs)
    summary = {
        "samples": len(cases),
        "completed": sum(c["status"] == "completed" for c in cases),
        "reference_samples": q["evaluated_samples"],
        "cer_reference_characters": q["reference_characters"],
        "cer_character_errors": q["character_errors"],
        "cer": q["cer"],
        "compute_rtf_median": statistics.median(
            c["event"]["compute_rtf"] for c in cases if c["event"]
        )
        if qs
        else None,
    }
    result = {
        "schema": "edge-ai-asr/result-v1",
        "run_id": d["run_id"],
        "source": {"kind": "device_measurement"},
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "backend": "CPU",
        },
        "cases": cases,
        "summary": summary,
        "quality": q,
        "measurement": {
            "resource_scope": "original per-process-tree samples; phase-specific values in measurements",
            "timing": "100ms paced input; RTF includes 3.2s tail computation, excludes pacing wait/loading; first/warmup separate",
            "reference_scope": "only dataset/manual independent references; command user review is separate",
            "raw_records": len(records),
        },
        "evidence": [
            {
                "path": str(p.relative_to(output)),
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            }
            for p in (output / "measurements").rglob("*")
            if p.is_file()
        ],
    }
    (output / "results.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2)
    )
    body = "".join(
        "<tr><td>"
        + html.escape(c["id"])
        + "</td><td>"
        + html.escape(c["status"])
        + "</td><td>"
        + html.escape((c["event"] or {}).get("final_text", "未完成"))
        + "</td></tr>"
        for c in cases
    )
    (output / "report.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>ASR逐例记录</title><h1>ASR 实际输出</h1><p>原始事件与资源保存在 measurements；CER只取独立参考子集。</p><table>'
        + body
        + "</table>"
    )
    if summary["completed"] != summary["samples"]:
        raise SystemExit(2)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("request", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    execute(a.request, a.output)


if __name__ == "__main__":
    main()
