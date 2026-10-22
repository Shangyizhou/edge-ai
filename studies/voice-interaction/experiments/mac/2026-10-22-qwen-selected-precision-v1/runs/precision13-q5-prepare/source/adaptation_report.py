# ruff: noqa: E501, W505
# Long source sentences and HTML literals retain exact experiment text.
"""Read-only paired adaptation report with explicit contextual persona review."""

import base64
import html
import json
from pathlib import Path

from .report import median, number, resources


def render(results, review, decision, training, loss_svg):
    def e(value):
        return html.escape(str(value))

    style = Path(__file__).with_name("report.css").read_text()
    by_review = {(x["run_id"], x["case_id"]): x for x in review["cases"]}
    signature = [
        (c["id"], c["user"], c["expected"]) for c in results[0]["cases"]
    ]
    for result in results:
        if [
            (c["id"], c["user"], c["expected"]) for c in result["cases"]
        ] != signature:
            raise ValueError("unpaired inputs or targets")
        for case in result["cases"]:
            if (
                case["kind"] == "persona"
                and (result["run_id"], case["id"]) not in by_review
            ):
                raise ValueError("missing contextual persona review")
    out = [
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>小沫 · 关键工具与角色适配</title><style>'
        + style
        + ".paired{display:grid;grid-template-columns:1fr 1fr;gap:14px}.paired .output{white-space:pre-wrap} @media(max-width:800px){.paired{grid-template-columns:1fr}}</style></head><body>",
        '<nav class="rail"><strong>关键工具 LoRA</strong><a href="#summary">结论与候选</a><a href="#data">数据与审核</a><a href="#train">训练</a><a href="#paired">60条配对输出</a><a href="#evidence">证据与边界</a><a href="#top">回到顶部</a></nav><main id="top"><header><span class="badge">Mac / MLX / BF16 / 9 工具</span><h1>关键工具与固定角色：微调前后</h1><p>同一60条验证输入 × 相同工具、运行时、精度与解码；最终120条封存。</p></header><section id="summary"><h2>结论与选定候选</h2><aside class="finding"><p>'
        + e(
            decision.get(
                "conclusion",
                decision.get(
                    "reason", decision.get("result", decision.get("status"))
                ),
            )
        )
        + "</p><p>"
        + e(decision.get("selection_basis", ""))
        + '</p><p class="foot">'
        + e(decision.get("counterfactual_warning", ""))
        + "</p></aside><details><summary>候选选择与配置依据</summary><pre>"
        + e(json.dumps(decision, ensure_ascii=False, indent=2))
        + '</pre></details><div class="scroll"><table><tr><th>候选</th><th>原生 / JSON / Schema / 精确工具</th><th>角色完整审核</th><th>prompt / prefill / decode 中位数</th><th>CPU / RSS / MLX分配</th></tr>',
    ]
    for r in results:
        s = r["summary"]
        res = resources(r["cases"])
        reviews = [x for x in review["cases"] if x["run_id"] == r["run_id"]]
        out.append(
            "<tr><td>"
            + e(r["run_id"])
            + "</td><td>"
            + e(
                f"{s['native_calls']}/{s['tool_samples']} · {s['json_valid']}/{s['tool_samples']} · {s['schema_valid']}/{s['tool_samples']} · {s['tool_expected_behavior']}/{s['tool_samples']}"
            )
            + "</td><td>"
            + e(
                f"{sum(x['passed'] for x in reviews)}/{len(reviews)} assistant审核；关键词辅助 {s['persona_valid']}/{s['persona_samples']}"
            )
            + "</td><td>"
            + e(
                f"{number(median(r['cases'], 'prompt_tokens'), 0)} tokens / {number(median(r['cases'], 'prefill_tokens_per_second'))} / {number(median(r['cases'], 'decode_tokens_per_second'))} tokens/s"
            )
            + "</td><td>"
            + e(
                f"{number(res['cpu'])}% / {number(res['memory'])}MiB / {number(res['mlx_memory'])}MiB"
            )
            + "</td></tr>"
        )
    out.append(
        '</table></div><p class="foot">单轮 n=60，非稳定尾延迟。CPU为进程树占10逻辑核容量，不含Metal利用率。RSS与MLX分配重叠，不相加。prefill包括首模型token，decode计数可含EOS。所有失败保留分母；工具精确匹配不等于完整业务语义验收。</p></section><section id="data"><h2>冻结数据与角色审核</h2><p>300训练、60验证、120封存最终测试；完整句式家族及其参数变体同分区。独立表达家族并不意味着新工具意图：各分区覆盖相同9个工具。数据为assistant构造的合成样本，未代表真实用户分布。旧39条开发输入排除；最终集未运行、未用于选择。</p><p>角色事实仅含小沫、科研AI与机器人助手、用户创造角色；创建者真实姓名、生日、年龄、地点、履历未知。审核逐条检查断言、遗漏、矛盾、未知信息处理及角色/模型来源区分。审核者为assistant GPT-6 Codex，无人工验收；自动关键词仅辅助，不能代替完整审核。</p><details><summary>预先冻结角色标准与审核身份</summary><pre>'
        + e(json.dumps(review["rubric"], ensure_ascii=False, indent=2))
        + '</pre></details></section><section id="train"><h2>实际训练与资源</h2><p>seed同时应用NumPy/MLX；仅assistant目标loss，完整样本与非思考推理前缀匹配，拒绝截断。以验证行为选择，不以loss单独决定。</p>'
        + loss_svg
        + "<details><summary>完整训练结果与资源</summary><pre>"
        + e(json.dumps(training, ensure_ascii=False, indent=2))
        + '</pre></details></section><section id="paired"><h2>60条相同输入的四组配对</h2><p>真实输出和预期默认可见。工具审核为纯JSON/Schema/Registry及精确目标比较；角色另列完整上下文审核结论。</p>'
    )
    for index, reference in enumerate(results[0]["cases"]):
        out.append(
            '<article class="sample"><h3>'
            + e(reference["id"])
            + " · "
            + e(reference["kind"])
            + "</h3><small>输入</small><p>"
            + e(reference["user"])
            + "</p><small>预期</small><pre>"
            + e(json.dumps(reference["expected"], ensure_ascii=False))
            + '</pre><div class="paired">'
        )
        for r in results:
            c = r["cases"][index]
            if c["id"] != reference["id"] or c["user"] != reference["user"]:
                raise ValueError("unpaired inputs")
            g = c.get("generation", {})
            a = c.get("assessment", {})
            rev = by_review.get((r["run_id"], c["id"]))
            verdict = (
                (str(rev["passed"]) + " · " + rev["reason"])
                if rev
                else ("精确预期匹配 " + str(a.get("expected_behavior")))
            )
            out.append(
                "<div><h4>"
                + e(r["run_id"])
                + '</h4><div class="output">'
                + e(g.get("raw", c.get("error")))
                + "</div><p>"
                + e(verdict)
                + '</p><div class="stats"><span>prompt '
                + e(g.get("prompt_tokens"))
                + "</span><span>TTFT "
                + number(g.get("ttft_seconds"))
                + "s</span><span>有效工具 "
                + number(c.get("valid_call_seconds"))
                + "s</span><span>prefill "
                + number(g.get("prefill_tokens_per_second"))
                + "</span><span>decode "
                + number(g.get("decode_tokens_per_second"))
                + "</span></div></div>"
            )
        out.append("</div></article>")
    out.append(
        '</section><section id="evidence"><h2>原始证据与限制</h2><p>未触发设备动作、未集成生产、未验收整链路。完整system沿用冻结基线源文；short沿用已确认短指令。动态工具目录、Schema、权限、设备状态、用户会话和执行结果仍需运行时输入。浏览器视觉预览因file策略不可用，未作替代绕行；仅静态HTML/CSS/引用验证。</p>'
    )
    data = json.dumps(
        {"results": results, "review": review, "decision": decision},
        ensure_ascii=False,
    ).encode()
    out.append(
        '<a download="paired-evidence.json" href="data:application/json;base64,'
        + base64.b64encode(data).decode()
        + '">下载配对原始结果与审核</a><p><a href="inference.html">全部原始指标</a> · <a href="stages.html">训练与导出阶段</a> · <a href="README.md">实验说明与证据索引</a></p></section></main><script>const links=[...document.querySelectorAll(".rail a")].filter(a=>a.hash!=="#top");function nav(){let id="summary";for(const a of links){const s=document.querySelector(a.hash);if(s&&s.getBoundingClientRect().top<=150)id=s.id}for(const a of links)a.classList.toggle("active",a.hash==="#"+id)}addEventListener("scroll",nav,{passive:true});nav();</script></body></html>'
    )
    return "\n".join(out).replace("四组配对", f"{len(results)}组配对")
