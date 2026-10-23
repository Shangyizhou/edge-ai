"""Build portable lifecycle input/report from completed raw evidence; read-only."""
import base64,hashlib,io,json,pathlib,sys,zipfile
W=pathlib.Path('/tmp/edge-ai-ticket-14');E=W/'studies/voice-interaction/experiments/final/2026-10-22-qwen-final132-v1';P=pathlib.Path('/Users/syz/.local/share/edge-ai/qwen-lifecycle/ticket14');sys.path.insert(0,str(W))
from tools.qwen_lifecycle.final_report import render,summarize_final

def load(p):return json.loads(p.read_text())
def put(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
results=[load(E/'runs'/('final14-'+d+'-'+m)/'benchmark/results.json') for d in ['mac','board'] for m in ['base','selected']];suite=load(E/'final-suite.json');review=load(E/'persona-review.json');assert len(review['cases'])==144
summary=summarize_final(results,suite,review);put(E/'final-summary.json',summary)
by={r['run_id']:r['cohorts'][-1] for r in summary['runs']};ma=by['final14-mac-selected'];bo=by['final14-board-selected']
gates={'schema':'edge-ai/final-acceptance-boundary-v1','experiment_execution':'COMPLETE_528_REQUESTS' if all(len(r['cases'])==132 for r in results) else 'INCOMPLETE','primary_tuned_q4':{'native_json_schema_registry':'PASS' if all(g['format_gate']=='PASS' for g in [ma,bo]) else 'UNMET','persona_context_and_no_misroute':'PASS' if all(g['persona_gate']=='PASS' for g in [ma,bo]) else 'UNMET','ordinary_chat_no_call':'PASS' if all(g['chat_gate']=='PASS' for g in [ma,bo]) else 'UNMET'},'tool_exact_semantics':'OBSERVATION_ONLY; no95percent full-business threshold','resources':{'user_confirmed_product_thresholds':None,'research_suggestions_only':{'peak_llm_pss_bytes':int(1.3*1024**3),'co_running_minimum_available_bytes':512*1024**2},'product_gate':'UNKNOWN; no confirmed thresholds or co-running measurement'},'production_and_complete_interaction':'NOT_EVALUATED','human_persona_acceptance':'NOT_EVALUATED; Codex assistant review only','actual_desktop_mobile_visual':'UNVERIFIED; static checks only','next_experiment':'Fresh developer data and a fresh independent holdout; do not retune on final132.'};put(E/'gates.json',gates)
conclusion=f"微调Q4主候选由验证集预选，独立工具原生/JSON/Schema/Registry：Mac {ma['native_calls']}/{ma['json_valid']}/{ma['schema_valid']}/{ma['registry_valid']}，板端 {bo['native_calls']}/{bo['json_valid']}/{bo['schema_valid']}/{bo['registry_valid']}（各84请求）。完整计划语义分别 {ma['tool_expected_behavior']}/84、{bo['tool_expected_behavior']}/84。人设事实分别 {ma['contextual_persona_pass']}/36、{bo['contextual_persona_pass']}/36，误调用工具 {ma['persona_unintended_tool_requests']}/36、{bo['persona_unintended_tool_requests']}/36；角色门槛未全满足。普通聊天分别 {ma['chat_valid']}/12、{bo['chat_valid']}/12。当前结论是部分完成的格式/部署试点，保留全部失败，不宣称人设已稳定内化、动作正确或生产可用。"
limitations=[
 '验证人设18/18到Mac独立21/36，尤其角色用途1/6、自我介绍0/6，说明选定组合的表达泛化不足。300条合成训练与多轮验证选择的覆盖有限、选择过拟合是可能解释；没有实验把原因唯一归于Q4量化，T13同Q4验证曾18/18。下一轮须另采真实来源开发数据、保留本轮失败并建立新的独立封存集，不能用这次最终集调参后再报其为独立测试。',
 '普通chat12条无调用与persona36条误路由分别评判。角色答案采用规范固定事实，未验证丰富风格、自然度、长期一致性或人工接受。审核身份为Codex assistant；机械关键词分仅附录。',
 '9工具、合成分组表达与单轮设备测量；没有覆盖所有约60工具或未见业务意图。调用语义、次数、顺序、重复与转义是观察，JSON/Schema通过不能替代完整任务正确。',
 '同设备同配置仍只有一次顺序试验，输出内容/长度不同，主机负载和thermal可变；不能由等待差异宣称LoRA本身加速。',
 '同设备未训练/微调Q4使用同一冻结配置。Mac Metal8192/f16KV/cacheoff与RK3566 ARM CPU2048/q8KV/cacheon是不同部署组合，不作纯硬件/量化加速归因。Q8只在Mac验证测过，板端Q8最终质量和资源未知。',
 '板端为T12固定GCC9.4 Cortex-A55 CPU build、GGML_CPU_REPACK=OFF/OpenMP ON，无GPU/NPU执行；保守组合不是硬件最大能力或NPU兼容性证明。',
 'CPU与内存采样对象为实际模型server树；窗口含等待Registry纯校验，但Registry/client进程CPU不在该树。PSS/RSS是采样峰值，Mac RSS与MLX分配可重叠，不相加；GPU利用率、完整Mac压力指标未知。整机swap/余量与thermal只是同时观测，不能归因模型，也不证明共跑。',
 '“冷”是新server的空KV/前缀，不是OS文件页缓存冷启动。加载与推理分开；完整输入usage不等于实际prefill。native输出n_gen与解码n_gen−1步数分开保留，不强制重算吞吐。实际采样间隔包含200ms等待和采样开销，短终止边界也可更短。P95是单轮最近秩经验数，不是稳定尾延迟承诺。',
 '本轮未发布Pages。根集成ae5b10de为新Qwen实验前缀增加默认静态导出排除，公开发布仍需单独操作。',
 '没有用户已确认的产品延迟/内存门槛。历史PSS≤1.3GiB、共跑余量≥512MiB是研究建议，不能据单模型数值宣称产品达标。没有生产代码修改、Executor/设备handler/ROS动作、ASR/TTS整链路、视觉共跑或长期稳定验收。',
 '原始Mac首次后台启动中断的3个case完整保留；之后同冻结请求重新执行完整132。canonical共528次，附加中断3次与板端devsmoke2次另列，不挑选重试成绩。中断确切信号未知。',
 '旧Mac launcher顶层result含evidence相对路径前缀缺失，原件不改；本轮分析从不可变benchmark/results.json读取，derived-handoff.json只重定位引用并带原始SHA，不是新测量。维护版已修复未来handoff，执行源码快照未替换。',
 '核心HTML阅读、全部最终配对输出、上下文审核、阶段表与可下载JSON/本轮原始证据ZIP内嵌；历史阶段完整raw由仓库伴随目录链接提供，不声称递归内嵌全部历史。浏览器file预览被策略拒绝，未采用HTTP/其他浏览器/Playwright规避；实际桌面与手机视觉布局仍UNVERIFIED，只有静态锚点/链接/转义/响应式CSS核查。'
]
document={'schema':'edge-ai/qwen-lifecycle-final-view/v1','results':results,'suite':suite,'review':review,'stages':load(E/'stages.json'),'resource_audit':load(E/'resource-audit.json'),'freeze':{'launch':load(E/'launch-freeze.json'),'cohorts':load(E/'cohort-audit.json'),'handoffs':load(E/'handoff-static-proof.json'),'source':load(E/'source-identities.json')},'conclusion':conclusion,'acceptance_boundary':gates,'limitations':limitations,'links':[{'href':p,'label':label} for p,label in [('gates.json','各门槛与资源阈值来源'),('reproduce.md','复现与五技能交接'),('integration-contract.md','后续原生接入契约'),('resource-audit.json','原生计数/实际采样/thermal完整审计'),('preparation/output/report.html','真实开发冒烟准备报告'),('inference-report.html','selection机械规则辅助视图；人设结论以本主报告上下文审核为准'),('../../mac/2026-10-22-qwen-selected9-adaptation-v1/report.html','历史训练/提示受控验证及原始证据伴随目录'),('../../mac/2026-10-22-qwen-selected-precision-v1/report.html','历史合并/同权重量化及原始证据伴随目录'),('../../rk3566/2026-10-22-qwen-pilot32-board-v1/report.html','历史开发KV/缓存研究及原始证据伴随目录')]]}
# ZIP only immutable evidence/companion docs, not this final HTML/JSON (avoid recursion).
exclude={'report.html','lifecycle.json','manifest.json','static-qa.json','raw-evidence-manifest.json','inference-report.html'}
files=[p for p in sorted(E.rglob('*')) if p.is_file() and p.name not in exclude]
assert not any(p.suffix in ['.gguf','.safetensors','.wav','.mp4','.dylib','.so'] for p in files)
rawmanifest={'schema':'edge-ai/raw-evidence-manifest-v1','files':{str(p.relative_to(E)):{'sha256':sha(p),'bytes':p.stat().st_size} for p in files},'scope':'new final experiment evidence; immutable previous experiments referenced, not recursively copied'};put(E/'raw-evidence-manifest.json',rawmanifest)
archive=io.BytesIO()
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
 for p in files+[E/'raw-evidence-manifest.json']:z.write(p,str(p.relative_to(E)))
bundle=archive.getvalue();(P/'raw-evidence.zip').write_bytes(bundle);document['evidence_bundle_base64']=base64.b64encode(bundle).decode();document['evidence_bundle_sha256']=hashlib.sha256(bundle).hexdigest();put(E/'lifecycle.json',document)
rendered,again=render(document);assert again==summary;(E/'report.html').write_text(rendered);print(conclusion);print('rawZIP',len(bundle),'members',len(files)+1,'HTML',len(rendered.encode()))
