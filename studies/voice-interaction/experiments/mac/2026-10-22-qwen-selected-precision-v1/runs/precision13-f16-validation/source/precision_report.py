"""Read-only precision comparison; inference and review must already exist."""

import html
import json
from pathlib import Path

from .report import median, number, resources


def paired(results):
    """Reject mismatched inputs; deployment controls remain explicitly reported."""
    if not results:
        raise ValueError("no results")
    signatures = [[(c['id'], c['user'], c['expected'], c['messages'])
                   for c in r['cases']] for r in results]
    if any(s != signatures[0] for s in signatures[1:]):
        raise ValueError("unpaired inputs, targets or prompts")


def render(results, review, exports, decision):
    paired(results)
    reviews = {(x['run_id'], x['case_id']): x for x in review['cases']}
    for r in results:
        for c in r['cases']:
            if c['kind'] == 'persona' and (r['run_id'], c['id']) not in reviews:
                raise ValueError('missing contextual review')
    e = lambda x: html.escape(str(x))
    js = lambda x: e(json.dumps(x, ensure_ascii=False, indent=2))
    style = Path(__file__).with_name('report.css').read_text()
    out = ['<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>同权重精度验证</title><style>'+style+'</style><body><nav class="rail"><strong>同权重精度验证</strong><a href="#summary">选择</a><a href="#stages">转换链</a><a href="#quality">质量与资源</a><a href="#paired">60条配对</a><a href="#evidence">证据</a></nav><main><header><h1>选定 LoRA → 合并 → F16 / Q4 / Q5</h1><p>Mac M5 · 验证集 n=60 · 最终测试封存 · 无设备执行</p></header><section id="summary"><h2>选择与边界</h2><aside class="finding">'+e(decision['conclusion'])+'</aside><p>'+e(decision['baseline_warning'])+'</p><details><summary>配置选择依据</summary><pre>'+js(decision)+'</pre></details></section><section id="stages"><h2>转换链与阶段成本</h2><p>转换进程树 100ms 采样；wall 不含后续制品哈希。CPU占10逻辑核容量。RSS是采样峰值；短子进程可漏采。转换成功与实际推理、质量接受分别判断。</p>']
    for export in exports:
        out.append('<details><summary>'+e(export['run_id'])+'：阶段、来源、bytes/hash与资源</summary><pre>'+js(export)+'</pre></details>')
    out.append('<aside class="finding">Q4、Q5均从同一选定 F16 单独量化。高精度参照为 F16；Q8_0未测。基础模型转为F16/Q4用于后续板端配对；不是旧Qwen2.5制品。HF体积变化同时含 tied-weight 去重，不能当作纯量化压缩。</aside></section><section id="quality"><h2>质量、等待与实际内存</h2><p>同36工具/18角色/6聊天。原生、JSON、Schema与精确目标分别计数；角色为完整输出的assistant上下文审核，无人工验收。request→首content 与 request→完整响应为墙钟；成功有效工具等待另列原始记录。MLX原生prefill含首token；llama原生计数边界不同，因此跨运行时仅为部署组合对照。以下均60例中位数。CPU为推理+纯校验窗进程树占整机容量；RSS与MLX分配可能重叠，不相加。无GPU利用率、无Mac PSS。</p><div class="scroll"><table><tr><th>候选/运行时/格式</th><th>bytes</th><th>原生/JSON/Schema/精确 工具 /36</th><th>角色 /18</th><th>prefill/decode tok/s</th><th>TTFT/完整 s</th><th>CPU/RSS MiB/主机RAM%</th></tr>')
    for r in results:
        s=r['summary']; p=r['candidate']; res=resources(r['cases']); rev=[reviews[(r['run_id'],c['id'])] for c in r['cases'] if c['kind']=='persona']; mem=res['memory']; host=r['cases'][0].get('resources',{}).get('host_mem_total_bytes')
        vals=[r['run_id']+' · '+p['precision']+' / '+p['actual_runtime']['name']+' / '+p['backend'],r['artifacts']['total_bytes'],f"{s['native_calls']}/{s['json_valid']}/{s['schema_valid']}/{s['tool_expected_behavior']}",f"{sum(x['passed'] for x in rev)}/{len(rev)}",number(median(r['cases'],'prefill_tokens_per_second'))+' / '+number(median(r['cases'],'decode_tokens_per_second')),number(median(r['cases'],'ttft_seconds'))+' / '+number(median(r['cases'],'wall_seconds')),number(res['cpu'])+'% / '+number(mem)+' / '+number(mem*1048576/host*100 if mem and host else None)+'%']
        out.append('<tr>'+''.join('<td>'+e(v)+'</td>' for v in vals)+'</tr>')
    out.append('</table></div><aside class="finding">'+e(decision['quality_finding'])+'</aside></section><section id="paired"><h2>全部60条实际配对输出</h2><p>输入、预期、原生调用和原文可见，失败仍在分母。各案例的工具调用仅通过纯JSON/Schema/Registry校验，无Executor。</p>')
    for index, c in enumerate(results[0]['cases']):
        out.append('<article class="sample"><h3>'+e(c['id'])+' · '+e(c['kind'])+'</h3><p>'+e(c['user'])+'</p><pre>'+js(c['expected'])+'</pre>')
        for r in results:
            x=r['cases'][index]; rev=reviews.get((r['run_id'],c['id'])); g=x.get('generation',{}); a=x.get('assessment',{}); reply=a.get('reply',{})
            out.append('<h4>'+e(r['run_id'])+'</h4><pre>'+e(g.get('raw',x.get('error')))+'\n'+js(reply.get('tool_calls',[]))+'</pre><p>'+e((str(rev['passed'])+' · '+rev['reason']) if rev else '精确目标 '+str(a.get('expected_behavior')))+' · TTFT '+number(g.get('ttft_seconds'))+'s · 完整 '+number(g.get('wall_seconds'))+'s · 有效调用 '+number(x.get('valid_call_seconds'))+'s</p>')
        out.append('</article>')
    out.append('</section><section id="evidence"><h2>身份、配置与限制</h2><p>F16/Q4/Q5使用相同llama.cpp revision、Metal、8192 context、f16 K/V、4线程、512 batch、temp0、256输出tokens、无prompt cache。MLX adapter/merged是同运行时回归；MLX→GGUF还改变backend实现/模板/原生grammar，不能把差异全归因转换或量化。单轮合成验证不代表用户分布、稳定P95、板端速度或产品验收。浏览器视觉未验证：file策略禁止预览，未绕行。</p><aside class="finding">未读取最终120条或额外12条挑战；选择仅基于验证集。动态工具目录/权限/状态/执行回执仍由应用提供。</aside><p><a href="README.md">实验说明</a> · <a href="comparison-summary.json">比较JSON</a> · <a href="persona-review.json">完整角色审核</a> · <a href="preparation/report.html">准备handoff</a></p><details><summary>完整身份与配置</summary><pre>'+js([{'run_id':r['run_id'],'candidate':r['candidate'],'environment':r['environment']} for r in results])+'</pre></details></section></main><script>const links=[...document.querySelectorAll(".rail a")];function nav(){let id="summary";for(const a of links){if(document.querySelector(a.hash).getBoundingClientRect().top<150)id=a.hash.slice(1)}for(const a of links)a.classList.toggle("active",a.hash==="#"+id)}addEventListener("scroll",nav,{passive:true});nav();</script></body></html>')
    return '\n'.join(out)
