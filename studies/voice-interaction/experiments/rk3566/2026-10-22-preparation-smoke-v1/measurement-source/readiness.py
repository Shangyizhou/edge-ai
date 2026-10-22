#!/usr/bin/env python3
"""Create a preparation handoff or render readiness; never executes models."""
import argparse
import hashlib
import html
import json
import re
from pathlib import Path

GATES = ("assets", "runtime", "smoke", "benchmark")
STATES = {"PASS", "FAIL", "UNKNOWN", "NOT_RUN"}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def unique(rows, label):
    ids = [row["id"] for row in rows]
    if any(not isinstance(x, str) or not x.strip() for x in ids) or len(set(ids)) != len(ids):
        raise ValueError("Invalid or duplicate " + label + " IDs")
    return set(ids)


def handoff(selection, selected):
    source = json.loads(selection.read_text(encoding="utf-8"))
    candidates = [dict(c, id=c.get("id") or "candidate-" + str(i + 1))
                  for i, c in enumerate(source["candidates"])]
    known = unique(candidates, "candidate")
    if set(selected) - known:
        raise ValueError("Unknown requested candidate ID")
    candidates = [c for c in candidates if c["id"] in selected] if selected else [c for c in candidates if c["decision"] == "baseline"]
    if not candidates:
        raise ValueError("No selected candidates")
    return dict(schema="edge-model-prepare/request-v1", device=source["device"],
                requirements=source["requirements"], source_selection_sha256=digest(selection),
                candidates=candidates)


def status(checks):
    required = [checks[k]["status"] for k in GATES]
    if "FAIL" in required or checks.get("load", {}).get("status") == "FAIL":
        return "NOT_READY"
    if required[:2] != ["PASS", "PASS"]:
        return "NOT_READY"
    if checks["smoke"]["status"] != "PASS":
        return "LOADED_ONLY" if checks.get("load", {}).get("status") == "PASS" else "ENVIRONMENT_READY"
    return "READY_FOR_BENCHMARK" if checks["benchmark"]["status"] == "PASS" else "FUNCTIONAL_READY"


def evaluate(request_path, checks_path):
    request = json.loads(request_path.read_text(encoding="utf-8"))
    observed = json.loads(checks_path.read_text(encoding="utf-8"))
    if request["schema"] != "edge-model-prepare/request-v1" or observed["schema"] != "edge-model-prepare/checks-v1":
        raise ValueError("Unsupported schema")
    if observed["request_sha256"] != digest(request_path):
        raise ValueError("Checks refer to another request")
    ids = unique(request["candidates"], "candidate")
    if not ids or unique(observed["candidates"], "check candidate") != ids:
        raise ValueError("Checks must cover exactly the requested candidates")
    evidence = observed["evidence"]
    evidence_ids = unique(evidence, "evidence")
    evidence_by_id = {e["id"]: e for e in evidence}
    for e in evidence:
        if not e.get("kind") or not e.get("location") or not e.get("description") or not re.fullmatch(r"[0-9a-f]{64}", e["sha256"]):
            raise ValueError("Evidence needs location, description and SHA256")
    by_id = {row["id"]: row for row in observed["candidates"]}
    rows = []
    for candidate in request["candidates"]:
        observation = by_id[candidate["id"]]
        checks = observation["checks"]
        if not set(GATES).issubset(checks) or set(checks) - set(GATES) - {"load"}:
            raise ValueError("Invalid check gate set")
        for check in checks.values():
            if check["status"] not in STATES or not check.get("reason"):
                raise ValueError("Check needs valid status and reason")
            refs = check.get("evidence", [])
            if not isinstance(refs, list) or set(refs) - evidence_ids:
                raise ValueError("Unknown evidence reference")
            if check["status"] in {"PASS", "FAIL"} and not refs:
                raise ValueError("PASS/FAIL needs evidence")
        if checks["smoke"]["status"] == "PASS" and not any(evidence_by_id[x]["kind"] == "smoke" for x in checks["smoke"]["evidence"]):
            raise ValueError("Smoke PASS requires inference evidence, not loading evidence")
        configs = observation.get("benchmark_configs", [])
        if not isinstance(configs, list) or any(x not in evidence_ids or evidence_by_id[x]["kind"] != "benchmark_config" for x in configs):
            raise ValueError("Invalid benchmark configuration evidence")
        if checks["benchmark"]["status"] == "PASS" and not configs:
            raise ValueError("Benchmark PASS requires frozen configurations")
        acquisition = observation["acquisition"]
        if acquisition["runtime"] not in {"reuse", "binary", "build"} or acquisition["model"] not in {"reuse", "download"} or not acquisition.get("reason"):
            raise ValueError("Invalid acquisition strategy/reason")
        if not observation.get("next_action"):
            raise ValueError("Next action required")
        rows.append(dict(candidate=candidate, acquisition=acquisition, checks=checks,
                         status=status(checks), benchmark_configs=configs, next_action=observation["next_action"]))
    ready = [dict(candidate=r["candidate"], configurations=[evidence_by_id[x] for x in r["benchmark_configs"]]) for r in rows if r["status"] == "READY_FOR_BENCHMARK"]
    overall = "READY_FOR_BENCHMARK" if len(ready) == len(rows) else "PARTIALLY_READY" if ready else "NOT_READY"
    return dict(schema="edge-model-prepare/readiness-v1", status=overall,
                request_sha256=digest(request_path), device=request["device"],
                requirements=request["requirements"], candidates=rows, evidence=evidence,
                evidence_verification="references_only", product_acceptance="NOT_EVALUATED",
                benchmark_handoff=dict(candidates=ready, evidence=evidence))


def render(result):
    def h(value):
        return html.escape(str(value), quote=True)
    out = ['<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>模型部署准备报告</title><style>body{font:16px/1.65 system-ui;background:#f3f6fa;color:#183044;max-width:1080px;margin:32px auto;padding:20px}article,header,section{background:white;border:1px solid #d8e2ea;border-radius:12px;padding:22px;margin:18px 0}table{border-collapse:collapse;width:100%}td,th{text-align:left;vertical-align:top;border-bottom:1px solid #ddd;padding:10px;overflow-wrap:anywhere}pre,p,li{white-space:pre-wrap;overflow-wrap:anywhere}pre{font-size:13px}code{overflow-wrap:anywhere}.scroll{overflow-x:auto}</style></head><body>',
           '<header><h1>模型部署准备</h1><p>整体状态：<strong>' + h(result['status']) + '</strong></p><p>结论依据：准备检查及引用的证据。渲染器仅校验引用结构，不独立验证文件或推理。性能、质量和完整交互：未验收。</p></header>']
    for row in result['candidates']:
        c = row['candidate']
        out += ['<article><h2>' + h(c.get('name', c['id'])) + '</h2><p><strong>' + h(row['status']) + '</strong> · ' + h(c['id']) + '</p>',
                '<p>获取方式：' + h(json.dumps(row['acquisition'], ensure_ascii=False)) + '</p>',
                '<div class="scroll"><table><tr><th>检查</th><th>状态</th><th>依据与缺口</th><th>证据</th></tr>']
        for key in (*GATES, 'load'):
            if key not in row['checks']: continue
            check = row['checks'][key]
            out.append('<tr><td>' + h(key) + '</td><td>' + h(check['status']) + '</td><td>' + h(check['reason']) + '</td><td>' + h(', '.join(check.get('evidence', []))) + '</td></tr>')
        out += ['</table></div><p>下一步：' + h(row['next_action']) + '</p><details><summary>部署身份</summary><pre>' + h(json.dumps(c, ensure_ascii=False, indent=2)) + '</pre></details></article>']
    out += ['<section><h2>证据索引</h2>']
    for e in result['evidence']:
        out.append('<p><strong>' + h(e['id']) + '</strong>：' + h(e['description']) + '<br>' + h(e['location']) + '<br>SHA256: ' + h(e['sha256']) + '</p>')
    out += ['</section><section><h2>设备与需求</h2><pre>' + h(json.dumps(dict(device=result['device'], requirements=result['requirements']), ensure_ascii=False, indent=2)) + '</pre></section></body></html>']
    return '\n'.join(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    a = sub.add_parser("handoff")
    a.add_argument("selection", type=Path)
    a.add_argument("request", type=Path)
    a.add_argument("--candidate", action="append", default=[])
    b = sub.add_parser("report")
    b.add_argument("request", type=Path)
    b.add_argument("checks", type=Path)
    b.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.command == "handoff":
        if args.request.exists(): raise ValueError("Request already exists; use a new path")
        write(args.request, handoff(args.selection, args.candidate))
    else:
        result = evaluate(args.request, args.checks)
        args.output.mkdir(parents=True, exist_ok=False)
        write(args.output / "readiness.json", result)
        (args.output / "report.html").write_text(render(result), encoding="utf-8")


if __name__ == "__main__":
    main()
