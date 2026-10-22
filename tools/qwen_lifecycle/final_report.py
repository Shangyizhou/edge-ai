# ruff: noqa: E501, W505
# Report literals preserve complete measurement qualifications.
"""Read-only final-cohort accounting and lifecycle HTML; never starts models."""

import argparse
import base64
import html
import json
import math
import statistics
from pathlib import Path

from .benchmark import summarize
from .precision_report import paired
from .report import number, resources


def quantile(values, fraction):
    """Nearest-rank empirical percentile; no stable-tail claim."""
    values = sorted(v for v in values if v is not None)
    return (
        values[max(0, math.ceil(len(values) * fraction) - 1)]
        if values
        else None
    )


def summarize_final(results, suite, review):
    """Fail closed on omitted samples, cohort drift or missing claim review."""
    paired(results)
    expected = [(s["id"], s["user"], s["expected"]) for s in suite["samples"]]
    reviews = {(r["run_id"], r["case_id"]): r for r in review["cases"]}
    if len(reviews) != len(review["cases"]):
        raise ValueError("duplicate contextual review")
    cohorts = {s["id"]: s["cohort"] for s in suite["samples"]}
    if len(cohorts) != len(suite["samples"]):
        raise ValueError("duplicate suite case")
    output = []
    for result in results:
        actual = [(c["id"], c["user"], c["expected"]) for c in result["cases"]]
        if actual != expected:
            raise ValueError("incomplete or changed final cohort")
        groups = []
        for cohort in (
            "original-holdout",
            "supplemental-multicall",
            "combined",
        ):
            cases = [
                c
                for c in result["cases"]
                if cohort == "combined" or cohorts[c["id"]] == cohort
            ]
            group = summarize(cases)
            group["cohort"] = cohort
            group["expected_calls"] = sum(
                len(c["expected"].get("calls", [])) for c in cases
            )
            group["actual_native_calls_in_tool_requests"] = sum(
                len(
                    c.get("assessment", {})
                    .get("reply", {})
                    .get("tool_calls", [])
                )
                for c in cases
                if c["kind"] == "tool"
            )
            group["contextual_persona_pass"] = 0
            for c in cases:
                if c["kind"] != "persona":
                    continue
                key = result["run_id"], c["id"]
                if (
                    key not in reviews
                    or type(reviews[key].get("passed")) is not bool
                ):
                    raise ValueError("missing contextual persona review")
                if not reviews[key].get("reason") or not reviews[key].get(
                    "claims"
                ):
                    raise ValueError("missing claim-level rationale")
                group["contextual_persona_pass"] += reviews[key]["passed"]
            group["no_call_pass"] = sum(
                not c.get("assessment", {}).get("reply", {}).get("tool_calls")
                and c.get("assessment", {}).get("response_complete") is True
                for c in cases
                if c["kind"] != "tool"
            )
            group["persona_unintended_tool_requests"] = sum(
                bool(
                    c.get("assessment", {}).get("reply", {}).get("tool_calls")
                )
                for c in cases
                if c["kind"] == "persona"
            )
            group["chat_unintended_tool_requests"] = sum(
                bool(
                    c.get("assessment", {}).get("reply", {}).get("tool_calls")
                )
                for c in cases
                if c["kind"] == "chat"
            )
            group["persona_gate"] = (
                "PASS"
                if group["persona_samples"]
                and group["contextual_persona_pass"]
                == group["persona_samples"]
                and not group["persona_unintended_tool_requests"]
                else "NOT_APPLICABLE"
                if not group["persona_samples"]
                else "UNMET"
            )
            group["chat_gate"] = (
                "PASS"
                if group["chat_samples"]
                and group["chat_valid"] == group["chat_samples"]
                and not group["chat_unintended_tool_requests"]
                else "NOT_APPLICABLE"
                if not group["chat_samples"]
                else "UNMET"
            )
            group["resources"] = resources(cases)
            rows = [c["resources"] for c in cases if "resources" in c]
            group["resource_window"] = {
                "inference_and_pure_intake_seconds": sum(
                    r["wall_seconds"] for r in rows
                ),
                "sample_count": sum(r["sample_count"] for r in rows),
                "minimum_host_mem_available_bytes": min(
                    (r["minimum_host_mem_available_bytes"] for r in rows),
                    default=None,
                ),
                "host_swap_in_delta_bytes_sum": sum(
                    r["host_swap_in_delta_bytes"] for r in rows
                ),
                "host_swap_out_delta_bytes_sum": sum(
                    r["host_swap_out_delta_bytes"] for r in rows
                ),
                "scope": "per-case windows only; host swap system-wide, not model attributable",
            }
            group["timing"] = {}
            for key in (
                "ttft_seconds",
                "wall_seconds",
                "prompt_tokens",
                "evaluated_prefill_tokens",
                "output_tokens",
                "prefill_tokens_per_second",
                "decode_tokens_per_second",
            ):
                values = [c.get("generation", {}).get(key) for c in cases]
                present = [v for v in values if v is not None]
                group["timing"][key] = {
                    "n": len(present),
                    "p50": statistics.median(present) if present else None,
                    "p95_nearest_rank": quantile(present, 0.95),
                }
            valid = [
                c.get("valid_call_seconds")
                for c in cases
                if c["kind"] == "tool"
                and c.get("assessment", {}).get("native_parse") is True
                and c.get("assessment", {}).get("json_valid") is True
                and c.get("assessment", {}).get("schema_valid") is True
                and c.get("assessment", {}).get("registry_valid") is True
                and c.get("assessment", {}).get("response_complete") is True
            ]
            valid = [v for v in valid if v is not None]
            group["valid_call_latency"] = {
                "n": len(valid),
                "p50": statistics.median(valid) if valid else None,
                "p95_nearest_rank": quantile(valid, 0.95),
                "boundary": "request through complete native JSON/Schema/Registry; semantics separate",
            }
            group["completed_tool_requests"] = sum(
                c.get("status") == "completed"
                and c.get("assessment", {}).get("response_complete") is True
                for c in cases
                if c["kind"] == "tool"
            )
            group["format_gate"] = (
                "PASS"
                if group["tool_samples"]
                and group["completed_tool_requests"] == group["tool_samples"]
                and all(
                    group[k] == group["tool_samples"]
                    for k in (
                        "native_calls",
                        "json_valid",
                        "schema_valid",
                        "registry_valid",
                    )
                )
                else "UNMET"
            )
            groups.append(group)
        output.append(
            {
                "run_id": result["run_id"],
                "candidate": result["candidate"],
                "cohorts": groups,
            }
        )
    return {
        "schema": "edge-model-final-summary/v1",
        "runs": output,
        "reviewer": review["reviewer"],
        "human_review": False,
        "percentile_method": "nearest rank; single synthetic suite, not stable tail estimate",
    }


def render(document):
    """Render only the supplied immutable evidence and explicit reviews."""
    results, suite, review = (
        document[k] for k in ("results", "suite", "review")
    )
    summary = summarize_final(results, suite, review)

    def e(value):
        return html.escape(str(value), quote=True)

    def js(value):
        return e(json.dumps(value, ensure_ascii=False, indent=2))

    sections = [
        ("summary", "结论"),
        ("baseline", "未微调基线"),
        ("training", "LoRA训练"),
        ("merge", "合并转换"),
        ("quantization", "同权重量化"),
        ("board", "最终独立回归"),
        ("limits", "限制与证据"),
    ]
    style = Path(__file__).with_name("report.css").read_text()
    out = [
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        "<title>Qwen3 模型生命周期最终实测</title><style>"
        + style
        + "</style></head><body>",
        '<nav class="rail" aria-label="章节导航"><strong>模型生命周期</strong>',
    ]
    out += ['<a href="#' + i + '">' + title + "</a>" for i, title in sections]
    out += [
        '<a href="#top">回到顶部</a></nav><main id="top"><header>',
        '<span class="badge">596049920参数 · Qwen3-0.6B · 原生调用试点</span>',
        "<h1>从基线到微调 Q4：独立测试与部署边界</h1>",
        "<p>120封存样本 + 独立12多调用；每模型设备132例，共528次最终请求。"
        '原始分组保留，无设备执行。</p></header><section id="summary"><h2>结论与候选</h2>',
        '<p class="method">Q4与精简路由提示由验证集预选。最终结果不用于改提示、训练或选择精度。'
        "工具格式与语义、角色审核、生产集成分别判断。采样对象是实际模型server及其递归子进程；CPU为整机逻辑核容量占比，内存为采样峰值。Registry/client进程CPU不包含在server树，窗口包含等待纯校验。</p>",
        '<aside class="finding">' + e(document["conclusion"]) + "</aside>",
        '<div class="scroll"><table><tr><th>候选部署方案</th><th>最终能力 / 分母</th>'
        "<th>CPU / 内存 / RAM</th><th>格式门槛</th></tr>",
    ]
    for r, s in zip(results, summary["runs"]):
        g = s["cohorts"][-1]
        p = r["candidate"]
        res = g["resources"]
        identity = f"{r['run_id']} / {p['parameter_count']}参数 / {p['precision']} / llama.cpp {p['runtime_version']} / {p['backend']} / context {p['context_tokens']} / KV {p['kv_type']} / {r['artifacts']['total_bytes']} bytes"
        out.append(
            "<tr><td>"
            + e(identity)
            + "</td><td>"
            + e(
                f"原生/JSON/Schema/Registry {g['native_calls']}/{g['json_valid']}/{g['schema_valid']}/{g['registry_valid']} /84请求；精确 {g['tool_expected_behavior']}/84；角色 {g['contextual_persona_pass']}/36；聊天 {g['chat_valid']}/12"
            )
            + "</td><td>"
            + e(
                f"{number(res['cpu'])}% / {res['memory_kind']} {number(res['memory'])} MiB / {number(res['memory_percent'])}%"
            )
            + "</td><td>"
            + e(
                "工具格式 "
                + g["format_gate"]
                + " / 角色 "
                + g["persona_gate"]
                + " / 聊天 "
                + g["chat_gate"]
            )
            + "</td></tr>"
        )
    out.append(
        "</table></div><p>角色为Codex assistant逐项上下文审核，未作人工验收。"
        "Mac RSS与Linux PSS口径不同；CPU不代表GPU利用率。无共跑或整链路等待结论。</p></section>"
    )
    for ident, title in sections[1:5]:
        stage = document["stages"][ident]
        out.append(
            '<section id="'
            + ident
            + '"><h2>'
            + title
            + '</h2><p class="method">'
            + e(stage["method"])
            + "</p><p>"
            + e(stage["finding"])
            + "</p>"
        )
        out.append('<div class="scroll"><table>')
        for row in stage["table"]:
            out.append(
                "<tr>"
                + "".join("<td>" + e(v) + "</td>" for v in row)
                + "</tr>"
            )
        out.append("</table></div>")
        for sample in stage["examples"]:
            out.append(
                '<article class="sample"><strong>'
                + e(sample["input"])
                + '</strong><div class="pair">'
            )
            for label, value in sample["outputs"].items():
                out.append(
                    "<div><h4>"
                    + e(label)
                    + '</h4><div class="output">'
                    + e(value)
                    + "</div></div>"
                )
            out.append("</div><p>" + e(sample["judgment"]) + "</p></article>")
        out.append(
            '<aside class="finding">' + e(stage["limit"]) + "</aside>"
            "<details><summary>阶段身份、成本与不可变来源</summary><pre>"
            + js(stage["evidence"])
            + "</pre></details></section>"
        )
    out.append(
        '<section id="board"><h2>四组最终独立回归</h2><p class="method">'
        "原120含72单工具、36角色、12聊天；补充12含28目标调用。工具JSON/Schema以84请求为分母，"
        "精确完整计划另行判断100个预期调用及次序/重复/转义。原120与补充12分别列出。"
        "Mac 8192/f16 KV/cache off/4线程/Metal；板端2048/q8 KV/cache on/2线程/CPU，"
        "模型在同设备串行。首例为新server的KV/前缀冷，不是受控OS页缓存冷启动；后例按实际匹配缓存，不强制清缓存。"
        "full prompt usage与实际evaluated prefill、cached tokens分列；缓存减少计算量，不能当吞吐提高。"
        "llama native decode速率按输出n_gen−1解码步，原始n_gen保留。"
        "TTFT为首content；完整有效调用包括纯Registry；无效输出不进成功延迟分母。"
        "P95为最近秩经验分位数，单轮合成样本不表示稳定尾延迟。</p>"
    )
    for r, s in zip(results, summary["runs"]):
        out.append(
            "<h3>" + e(r["run_id"]) + '</h3><div class="scroll"><table>'
            "<tr><th>分组/样本/预期调用</th><th>原生/JSON/Schema/Registry/精确</th>"
            "<th>角色/聊天</th><th>有效工具P50/P95 s (n)</th></tr>"
        )
        for g in s["cohorts"]:
            lat = g["valid_call_latency"]
            out.append(
                "<tr>"
                + "".join(
                    "<td>" + e(x) + "</td>"
                    for x in [
                        f"{g['cohort']} / {g['samples']} / {g['expected_calls']}",
                        f"{g['native_calls']}/{g['json_valid']}/{g['schema_valid']}/{g['registry_valid']}/{g['tool_expected_behavior']} /{g['tool_samples']}",
                        f"{g['contextual_persona_pass']}/{g['persona_samples']} · {g['chat_valid']}/{g['chat_samples']}",
                        f"{number(lat['p50'])}/{number(lat['p95_nearest_rank'])} ({lat['n']})",
                    ]
                )
                + "</tr>"
            )
        out.append(
            '</table></div><div class="scroll"><table><tr><th>指标（全部132；可用n见附录）</th><th>P50</th><th>P95最近秩</th></tr>'
        )
        combined = s["cohorts"][-1]
        for metric, values in combined["timing"].items():
            out.append(
                "<tr><td>"
                + e(metric)
                + "</td><td>"
                + number(values["p50"])
                + "</td><td>"
                + number(values["p95_nearest_rank"])
                + "</td></tr>"
            )
        out.append("</table></div>")
        audit = next(
            (
                a
                for a in document.get("resource_audit", {}).get("runs", [])
                if a["run_id"] == r["run_id"]
            ),
            None,
        )
        if audit:
            first = audit["cold_prefix_first_case"]
            sampling = audit["actual_sampling_intervals_seconds"]
            out.append(
                '<p class="method">新server首例：full/evaluated/cached '
                + e(
                    f"{first['prompt_full_usage']}/{first['evaluated_prefill']}/{first['cached_native_usage']}"
                )
                + "；TTFT/完整响应/有效工具 s "
                + e(
                    f"{number(first['ttft_seconds'])}/{number(first['complete_response_seconds'])}/{number(first['valid_call_seconds'])}"
                )
                + "。实际采样间隔中位 s "
                + number(sampling["median"])
                + "（200ms等待加采样开销，终止边界可更短）；最低整机余量 bytes "
                + e(
                    combined["resource_window"][
                        "minimum_host_mem_available_bytes"
                    ]
                )
                + "；整机swap-in/out bytes "
                + e(
                    f"{combined['resource_window']['host_swap_in_delta_bytes_sum']}/{combined['resource_window']['host_swap_out_delta_bytes_sum']}"
                )
                + "。可用thermal zone摄氏度："
                + js(audit["thermal_zone_celsius"])
                + "；GPU利用率未测，Mac无PSS。加载资源单列原始审计。</p>"
            )
        out.append(
            "<details><summary>完整资源、token、计时与计数</summary><pre>"
            + js(s)
            + "</pre></details>"
        )
    reviews = {(x["run_id"], x["case_id"]): x for x in review["cases"]}
    for i, sample in enumerate(suite["samples"]):
        out.append(
            '<article class="sample"><h3>'
            + e(sample["id"] + " · " + sample["cohort"])
            + "</h3><p>"
            + e(sample["user"])
            + '</p><p class="reference">期望：'
            + js(sample["expected"])
            + '</p><div class="pair">'
        )
        for r in results:
            c = r["cases"][i]
            a = c.get("assessment", {})
            rev = reviews.get((r["run_id"], c["id"]))
            raw = c.get("generation", {})
            verdict = rev["passed"] if rev else a.get("expected_behavior")
            out.append(
                "<div><h4>"
                + e(r["run_id"])
                + '</h4><div class="output'
                + (" fail" if verdict is not True else "")
                + '">'
                + js(a.get("reply", raw.get("raw", c.get("error"))))
                + "</div><p>"
                + e(
                    rev["reason"]
                    if rev
                    else f"精确目标 {verdict}；原生 {a.get('native_parse')} / JSON {a.get('json_valid')} / Schema {a.get('schema_valid')} / Registry {a.get('registry_valid')}"
                )
                + '</p><p class="foot">'
                + e(
                    f"TTFT {number(raw.get('ttft_seconds'))}s；完整 {number(raw.get('wall_seconds'))}s；有效工具 {number(c.get('valid_call_seconds'))}s；full/evaluated/output {raw.get('prompt_tokens')}/{raw.get('evaluated_prefill_tokens')}/{raw.get('output_tokens')}"
                )
                + "</p></div>"
            )
        out.append("</div></article>")
    out.append('</section><section id="limits"><h2>限制、复现与携带证据</h2>')
    out += ["<p>" + e(s) + "</p>" for s in document["limitations"]]
    out.append(
        "<details><summary>配置冻结、哈希与来源</summary><pre>"
        + js(document["freeze"])
        + "</pre></details>"
    )
    payload = base64.b64encode(
        json.dumps(document, ensure_ascii=False).encode()
    ).decode()
    out.append(
        '<p><a download="lifecycle.json" href="data:application/json;base64,'
        + payload
        + '">下载内嵌完整结构化输入</a>：本页核心阅读、全部最终输出、审核与阶段表均已内嵌，无网络依赖。</p>'
    )
    for link in document.get("links", []):
        out.append(
            '<p><a href="'
            + e(link["href"])
            + '">'
            + e(link["label"])
            + "</a>（随目录交付的伴随证据；不是单HTML内嵌）</p>"
        )
    out.append(
        '</section></main><script>const links=[...document.querySelectorAll(".rail a")];const observer=new IntersectionObserver(entries=>{for(const x of entries){if(x.isIntersecting){links.forEach(a=>a.classList.toggle("active",a.hash==="#"+x.target.id));}}},{rootMargin:"-10% 0px -75% 0px"});document.querySelectorAll("section[id]").forEach(x=>observer.observe(x));</script></body></html>'
    )
    return "".join(out), summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    rendered, _ = render(json.loads(args.input.read_text()))
    args.output.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
