"""Pure result-to-HTML view following the accepted measured-report layout."""

import base64
import html
import json
import statistics
from pathlib import Path


def esc(value):
    return html.escape(str(value), quote=True)


def number(value, digits=2):
    return "未测" if value is None else f"{value:.{digits}f}"


def median(cases, key):
    values = [c.get("generation", {}).get(key) for c in cases]
    values = [x for x in values if x is not None]
    return statistics.median(values) if values else None


def resources(cases):
    rows = [c["resources"] for c in cases if "resources" in c]
    wall = sum(r["wall_seconds"] for r in rows)
    cpu = sum(r["cpu_seconds"] for r in rows)
    cores = rows[0]["host_logical_cpus"] if rows else None
    pss = [r["peak_pss_bytes"] for r in rows
           if r["peak_pss_bytes"] is not None]
    rss = [r["peak_rss_bytes"] for r in rows]
    total = rows[0]["host_mem_total_bytes"] if rows else None
    peak = max(pss) if pss else (max(rss) if rss else None)
    return {"cpu": cpu / wall / cores * 100 if wall and cores else None,
            "memory": peak / 1024**2 if peak is not None else None,
            "memory_kind": "PSS" if pss else "RSS",
            "mlx_memory": max([c.get("generation", {}).get("mlx_peak_allocated_bytes")
                               or 0 for c in cases]) / 1024**2 or None,
            "memory_percent": peak / total * 100 if peak and total else None}


def render(results, evidence_bundle=None):
    """Render data only. No imports or calls to a model runtime."""
    if not results or any(r.get("schema") != "edge-model-benchmark/result-v1"
                          for r in results):
        raise ValueError("expected one or more benchmark result-v1 records")
    style = Path(__file__).with_name("report.css").read_text()
    ids = ["run-" + str(i) for i in range(len(results))]
    out = ['<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">',
           '<meta name="viewport" content="width=device-width,initial-scale=1">',
           '<title>Qwen 原生调用 · 模型生命周期实测</title>',
           '<style>' + style + '</style></head><body>',
           '<nav class="rail" aria-label="章节导航"><strong>本页导航</strong>',
           '<a href="#summary">结论与选择</a>']
    for ident, result in zip(ids, results):
        out.append(f'<a href="#{ident}">{esc(result["run_id"])}</a>')
    out.extend(['<a href="#resources">精度与资源对比</a>',
                '<a href="#evidence">口径与原始证据</a>',
                '<a href="#top">回到顶部</a></nav><main id="top">',
                '<header><span class="badge">原生工具 / 角色事实 / 独立模型实验</span>',
                '<h1>Qwen：从未微调基线到部署制品</h1>',
                '<p class="muted">同一结构化结果生成 · 实际输入输出保留 · '
                '无硬件动作或完整交互验收</p></header>',
                '<section id="summary"><div class="eyebrow">先给结论</div>',
                '<h2>原生调用、角色设定和硬件资源分别判断</h2>',
                '<div class="scroll"><table class="deployment-table"><thead><tr>',
                '<th>候选部署方案</th><th>本轮能力观察</th>',
                '<th>CPU / 整机容量</th><th>采样峰值内存 / 实际内存</th>',
                '</tr></thead><tbody>'])
    for result in results:
        candidate = result["candidate"]
        summary = result["summary"]
        res = resources(result["cases"])
        runtime = candidate.get("actual_runtime", {})
        identity = (f'{candidate.get("model", "Qwen")} · '
                    f'{candidate.get("parameter_count", candidate.get("parameters", "参数量见制品"))}\n'
                    f'精度：{candidate.get("precision", "未注明")}\n'
                    f'框架：{runtime.get("name", "未知")} {runtime.get("version", "未知")}\n'
                    f'后端：{runtime.get("backend", "未知")} / {result["environment"]["system"]}\n'
                    f'阶段：{result["stage"]}')
        observation = (f'工具 Schema {summary["schema_valid"]}/{summary["tool_samples"]}；'
                       f'原生调用 {summary["native_calls"]}/{summary["tool_samples"]}；'
                       f'角色固定规则 {summary["persona_valid"]}/{summary["persona_samples"]}')
        if result["source"]["kind"] != "device_measurement":
            observation = "仅合成夹具，不是模型测量：" + observation
        out.append(f'<tr><td>{esc(identity)}</td><td>{esc(observation)}</td>'
                   f'<td>{number(res["cpu"])}%</td><td>{res["memory_kind"]} '
                   f'{number(res["memory"])} MiB / '
                   f'{number(res["memory_percent"])}%<br>'
                   f'MLX峰值分配 {number(res["mlx_memory"])} MiB（不相加）</td></tr>')
    out.extend(['</tbody></table></div><p class="foot">CPU为已声明进程树占整机逻辑核容量，'
                '内存为逐例窗口的采样峰值。CPU不包含Metal GPU利用率。Mac RSS 与 Linux PSS 不等价；'
                '资源窗口包含模板、推理、解析与纯校验。未将不同设备混成纯加速比较。</p></section>'])
    for ident, result in zip(ids, results):
        out.extend([f'<section id="{ident}"><div class="eyebrow">'
                    f'{esc(result["stage"])}</div><h2>{esc(result["run_id"])}</h2>',
                    '<div class="method"><strong>怎样测：</strong>固定工具、system和输入；'
                    '每例新建模型prompt cache；非思考模式。真实响应完整解析后，'
                    '只通过JSON Schema及可配置Registry纯校验，不执行设备。<br>',
                    '<strong>怎样读：</strong>prefill与decode tokens/s采用运行时计时，'
                    'TTFT为生成入口至首非空输出，完整有效调用等待包含模板/推理/解析/校验；'
                    '缺失字段为未测，失败/截断不是快速成功。角色采用预先固定文本规则，'
                    '不是独立人工整体人设评审。</div>',
                    '<h3>工具调用 · 实际输入与输出</h3>'])
        for kind in ("tool", "persona", "chat"):
            if kind != "tool":
                out.append('<h3>' + {"persona": "角色 / 背景 / 自我介绍",
                                      "chat": "普通聊天 · 无调用"}[kind] + '</h3>')
            for case in result["cases"]:
                if case["kind"] != kind:
                    continue
                assessed = case.get("assessment", {})
                generation = case.get("generation", {})
                passed = assessed.get("expected_behavior", False)
                raw = generation.get("raw", "")
                if generation.get("wire_calls"):
                    raw += "\n" + json.dumps(generation["wire_calls"], ensure_ascii=False)
                out.append(f'<article class="sample"><div class="sample-head">'
                           f'<h4>{esc(case["id"])}</h4><span class="badge">'
                           f'{"固定检查通过" if passed else "检查未通过 / 未完成"}</span></div>'
                           f'<small>输入</small><p>{esc(case["user"])}</p>'
                           f'<small>实际输出</small><div class="output '
                           f'{"" if passed else "fail"}">{esc(raw or case.get("error"))}</div>'
                           f'<small>预期</small><pre>{esc(json.dumps(case["expected"], ensure_ascii=False))}</pre>'
                           f'<div class="stats"><span>prompt {number(generation.get("prompt_tokens"), 0)} tokens</span>'
                           f'<span>首内容 {number(generation.get("ttft_seconds"))}s</span>'
                           f'<span>完整有效调用 {number(case.get("valid_call_seconds"))}s</span>'
                           f'<span>prefill {number(generation.get("prefill_tokens_per_second"))} tokens/s</span>'
                           f'<span>decode {number(generation.get("decode_tokens_per_second"))} tokens/s</span></div>'
                           f'<details><summary>解析、Schema与角色检查</summary><pre>'
                           f'{esc(json.dumps(assessed, ensure_ascii=False, indent=2))}</pre></details></article>')
        summary = result["summary"]
        out.append('<aside class="finding"><strong>本阶段发现</strong><p>'
                   f'工具调用Schema通过 {summary["schema_valid"]}/{summary["tool_samples"]}，'
                   f'与期望函数和参数一致 {summary["tool_expected_behavior"]}/{summary["tool_samples"]}；'
                   f'角色规则通过 {summary["persona_valid"]}/{summary["persona_samples"]}。'
                   '这些是当前固定样例的观察，不能外推完整业务或所有人设已学入。'
                   '失败输出保留，作为下一阶段数据与协议诊断依据。</p></aside></section>')
    out.append('<section id="resources"><h2>精度与资源对比</h2>'
               '<p>只有模型、输入、设备、运行时、context/KV和解码可比时才解释精度差异。'
               '模型文件大小不等于运行内存。没有测量的精度不推算成绩。</p>'
               '<div class="scroll"><table><thead><tr><th>候选 / 阶段</th><th>文件MiB</th>'
               '<th>prefill tokens/s 中位数</th><th>decode tokens/s 中位数</th>'
               '<th>TTFT中位数 s</th><th>CPU容量</th><th>采样峰值</th></tr></thead><tbody>')
    for result in results:
        cases = result["cases"]
        res = resources(cases)
        out.append(f'<tr><td>{esc(result["run_id"])}</td>'
                   f'<td>{number(result["artifacts"]["total_bytes"] / 1024**2)}</td>'
                   f'<td>{number(median(cases, "prefill_tokens_per_second"))}</td>'
                   f'<td>{number(median(cases, "decode_tokens_per_second"))}</td>'
                   f'<td>{number(median(cases, "ttft_seconds"))}</td>'
                   f'<td>{number(res["cpu"])}%</td><td>{res["memory_kind"]} '
                   f'{number(res["memory"])}MiB / MLX {number(res["mlx_memory"])}MiB</td></tr>')
    out.append('</tbody></table></div></section><section id="evidence">'
               '<h2>口径与原始证据</h2><p>统计覆盖本页全部样例，而非挑选成功项；'
               '单轮小样本不能宣称稳定尾延迟。MLX峰值分配与RSS可能重叠，不相加。'
               '未执行生产集成、ROS共跑或完整交互验收。</p>')
    payload = json.dumps(results, ensure_ascii=False, indent=2)
    encoded = base64.b64encode(payload.encode()).decode()
    out.append('<p><a download="benchmark-results.json" '
               f'href="data:application/json;base64,{encoded}">下载本页原始结果 JSON</a></p>')
    if evidence_bundle:
        data = base64.b64encode(evidence_bundle).decode()
        out.append(f'<p><a download="raw-evidence.zip" href="data:application/zip;base64,{data}">'
                   '下载冻结请求、逐例流事件与资源采样</a></p>')
    out.append('<details><summary>完整配置、资产哈希与逐例结果</summary>'
               '<pre>' + esc(payload) + '</pre></details></section>'
               '<footer class="foot">Qwen lifecycle · 自包含离线报告 · '
               '渲染只读数据，不执行模型</footer></main><script>'
               'const links=[...document.querySelectorAll(".rail a")];'
               'function nav(){let id="summary";for(const a of links){'
               'const s=document.querySelector(a.getAttribute("href"));'
               'if(s&&s.getBoundingClientRect().top<=150)id=s.id;}'
               'for(const a of links)a.classList.toggle("active",'
               'a.getAttribute("href")==="#"+id);}'
               'addEventListener("scroll",nav,{passive:true});nav();'
               '</script></body></html>')
    return "\n".join(out)
