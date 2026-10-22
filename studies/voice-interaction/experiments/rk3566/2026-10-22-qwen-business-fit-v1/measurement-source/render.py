"""Render actual business-fit observations without running models."""
import base64
import hashlib
import html
import json
from pathlib import Path
import re
import statistics

EXP=Path('/home/orangepi/code/edge-ai/studies/voice-interaction/experiments/rk3566/2026-10-22-qwen-business-fit-v1')
OUT=Path('/tmp/qwen-business-fit');OUT.mkdir(exist_ok=True)
h=lambda x:html.escape(str(x),quote=True)
def f(x):return '未测' if x is None else f'{x:.2f}'
def table(headers,rows):return '<div class="scroll"><table'+(' class="deployment-table"' if headers[0]=='部署方案' else '')+'><thead><tr>'+''.join('<th>'+h(x)+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+h(x)+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table></div>'
def note(title,text):return '<aside class="finding"><strong>'+h(title)+'</strong><p>'+h(text)+'</p></aside>'
def downloadable(path,label):
 payload=base64.b64encode(path.read_bytes()).decode()
 return '<a download="'+h(path.name)+'" href="data:application/json;base64,'+payload+'">'+h(label)+'</a>'
result=json.loads((EXP/'assessment.json').read_text());cases=result['cases'];tokens=result['token_counts']
full=[x['prompt_tokens'] for x in tokens if x['scope']=='full' and x['template']=='official-chatml'];subset=[x['prompt_tokens'] for x in tokens if x['scope']=='subset' and x['template']=='official-chatml']
passed=sum(c.get('case_pass',False) for c in cases)
reviews={r['id']:r for r in json.loads((EXP/'response-review.json').read_text())['samples']}
resources=[c['resources'] for c in cases]
cpu=sum(r['cpu_capacity_percent']['value']*r['duration_seconds'] for r in resources)/sum(r['duration_seconds'] for r in resources)
pss=max(r['peak_pss_mib']['value'] for r in resources);ram=max(r['ram_percent']['value'] for r in resources)
css=re.search(r'<style>(.*?)</style>',Path('/home/orangepi/.codex/skills/edge-model-selection/assets/benchmark-report.html').read_text(),re.S).group(1)
css+='\n.deployment-table td{white-space:pre-line}'
nav=[('summary','结论与部署'),('contract','项目真实契约'),('cases','3条实际业务测试'),('resources','速度与资源'),('next','下一步'),('evidence','原始证据')]
out=['<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Qwen 能否理解机器人业务？</title><style>'+css+'</style></head><body><nav class="rail"><strong>本页导航</strong>'+''.join('<a href="#'+i+'">'+t+'</a>' for i,t in nav)+'<small>真实板端测试<br>未执行机器人动作</small></nav><main><header><span class="badge">业务适配验证 · 独立实验</span><h1>Qwen 能否理解 ros-robot 的业务？</h1><p class="muted">官方 Qwen2.5-0.5B-Instruct Q4_K_M · RK3566 CPU · 2026-10-22</p></header>']
out.append('<section id="summary"><div class="eyebrow">先看结论</div><h2>当前 Qwen＋prompt 尚不适合直接接管业务动作</h2><p class="lead">完整 60 个工具的 prompt 已超过当前上下文预算；缩到 6 个真实工具后，本次 3 条业务测试完成并匹配预期 '+str(passed)+' 条。</p><p>这次检查的是实际业务函数选择、参数和否定意图，不是普通聊天或泛化“会输出 JSON”。完整目录没有送入生成，避免截断工具后伪称全量通过。</p>')
out.append(table(['部署方案','当前判断','CPU / 整机4核','峰值PSS / 实际内存'],[['Qwen2.5-0.5B-Instruct\nQ4_K_M（GGUF）\nllama.cpp b6500 / GGML CPU OpenMP\n线程2 / context2048 / KV F16','完整60工具：上下文不够\n6工具诊断小集：'+str(passed)+'/3匹配预期',f(cpu)+'%',f(pss)+' MiB / '+f(ram)+'%']]))
out.append('<p class="foot">CPU 为 3 次请求正式窗口按时长加权的进程树占整机容量均值；PSS 为这些窗口内每200ms采样峰值。并非完整60工具的资源开销，也不是原ROS C++推理节点的实测。</p></section>')
out.append('<section id="contract"><div class="eyebrow">项目核查</div><h2>项目实际需要的是哪种 function call？</h2>')
out.append(table(['层次','实际实现','与当前模型的关系'],[['在线路径','自然中文 + 原生 tool_calls；系统提示包含否定、缺参澄清、动作边界和状态查询规则。','不是打印一段JSON就会执行。'],['本地路径','LocalModel._prompt 构造 {"fc": ["函数(参数)"], "res": "回复"}；完整输出经解析器与ActionRegistry校验，再由另一个模块执行。','本次只走解析和参数校验，零动作执行。'],['模板与模型','本地现有 System/Human/Assistant 文本外壳为项目另一份训练模型保留；offline.json指向 qwen3-robot-q8_0.gguf。','不能把该模型的验证套用到官方Qwen2.5。本次明确适配官方ChatML，保留本地system内容与JSON grammar。'],['业务目录','当前注册表共60个业务工具：头部、导航、音乐、音量、WiFi、摄像头、融合与跟随。','工具存在只证明应用能校验/处理，不证明0.5B模型能正确选取。'],['策略覆盖','在线系统提示详细区分 enable_tracking 与 start_following；本地_prompt只有格式和通用工具限制，并不加载该完整在线提示。','详细业务约束需有明确离线表达；不能默认在线行为规则已经传给本地模型。']]))
out.append('<h3>先检查能不能装进上下文</h3>'+table(['目录 / 同3条输入','实际token数','当前2048上下文，另留128输出','项目4096示例，另留512输出'],[['完整60工具',str(min(full))+'–'+str(max(full)),'不够','不够'],['诊断6工具',str(min(subset))+'–'+str(max(subset)),'足够','足够']]))
out.append('<div class="method"><strong>这次怎样测：</strong>6个工具均直接来自当前项目Schema：volume_set、play_music、enable_lidar、disable_lidar、enable_tracking、start_following。保留真实工具名、说明和参数Schema，只过滤目录；不重写参数、不对选取结果作设备调用。模型使用官方ChatML，greedy、seed42、关闭提示缓存、最多128输出token；fc-first JSON语法来自项目C++原文。<br><strong>怎样读：</strong>语法有效只说明能解析；参数可绑定只说明注册表接受；“意图匹配”才检查函数名、顺序与参数是否符合预先冻结的本条例子。语法约束不保证理解业务。</div></section>')
out.append('<section id="cases"><div class="eyebrow">输入与实际输出</div><h2>3条真实业务测试 · 不隐藏失败</h2>')
for i,c in enumerate(cases):
 out.append('<article class="sample"><div class="sample-head"><span class="number">样例 '+str(i+1)+'</span><h4>'+h(c['id'])+'</h4><span class="badge">'+('匹配预期' if c.get('intent_pass') and c.get('status')=='complete' else '未通过完整检查')+'</span></div><small>用户输入</small><div class="output">'+h(c['input'])+'</div><small>事先冻结的预期函数（空数组表示不执行）</small><pre>'+h(json.dumps(c['expected'],ensure_ascii=False,indent=2))+'</pre><small>模型实际原文</small><div class="output">'+h(c.get('raw',''))+'</div><div class="stats"><span>首内容 '+f(c.get('ttft_s'))+'s</span><span>完整输出 '+f(c.get('total_s'))+'s</span></div><p>JSON语法 / 调用协议 / 参数绑定：'+h(str(c.get('json_valid')))+' / '+h(str(c.get('protocol_valid')))+' / '+h(str(c.get('registry_valid','未通过或未评估')))+'</p>')
 out.append(note('本条业务检查',reviews[c['id']]['reason']))
 if c.get('error'):out.append('<p class="warning">'+h(c['error'])+'</p>')
 out.append('</article>')
out.append(note('本模块发现 · '+str(passed)+'/3完成并匹配预期','检查的是这个6工具目录、这3条固定输入下的输出与Schema绑定。未测试全部60工具的选择、缺参澄清、对话记忆、设备回执或完整交互；也未证明任何动作真实执行或成功。'))
out.append('</section><section id="resources"><div class="eyebrow">请求等待与资源</div><h2>理解业务的代价，也要看在板子上等多久</h2>')
out.append(table(['样例','首内容等待','完整输出等待','CPU / 整机4核','峰值PSS'],[[c['id'],f(c.get('ttft_s'))+'s',f(c.get('total_s'))+'s',f(c['resources']['cpu_capacity_percent']['value'])+'%',f(c['resources']['peak_pss_mib']['value'])+' MiB'] for c in cases]))
out.append('<p class="warning">项目offline.json的provider_timeout为60秒。本次为获取完整诊断输出放宽到210秒；三个首内容等待均约119秒，超过该示例预算。此结果不是原ROS C++节点的超时实测。</p><p class="foot">首内容从HTTP请求开始到首个非空响应片段，含prompt处理；完整输出到服务流结束，非纯解码速度。加载、预热和3秒待机不计正式资源窗口。一次进程内3条输入，不是3轮复测；没有完整目录的生成性能测量。</p></section><section id="next"><div class="eyebrow">下一步</div><h2>先确定业务范围，再决定怎样接入</h2>')
out.append(table(['方向','要解决什么','通过依据'],[['限制当前支持的业务能力','选择固定且公开的工具子集；不在范围内的请求须澄清或拒绝。','同一目录下核对真实输出，覆盖否定、缺参、顺序、重复和状态查询。'],['若要支持完整60工具','单独研究目录压缩、路由或更大上下文，保留业务规则和参数校验。','全目录/路由正确性、完整prompt预算、等待与资源重新实测，不能沿用小目录结果。'],['接回ROS Agent之前','显式适配官方模型模板与离线业务约束，经过现有LocalModel解析与Registry整批验证。','离线回归通过后才做模拟接入，硬件动作保持dry-run。']]))
out.append('</section><section id="evidence"><div class="eyebrow">原始证据</div><h2>源码身份、请求与模型原文</h2><p>ros-robot源为本机干净工作区 commit '+h(json.loads((EXP/'source-manifest.json').read_text())['commit'])+'。生产项目未修改。快照保存在独立实验中。</p><p>'+downloadable(EXP/'response-review.json','逐条业务评审')+' · '+downloadable(EXP/'decision.json','当前决策')+' · '+downloadable(EXP/'assessment.json','下载分层评估JSON')+' · '+downloadable(EXP/'results.json','原始测量JSON')+' · '+downloadable(EXP/'tools-full.json','60工具Schema')+' · '+downloadable(EXP/'tools-subset.json','本轮6工具Schema')+' · '+downloadable(EXP/'source-manifest.json','源码与身份清单')+'</p><details><summary>本次执行配置</summary><pre>'+h((EXP/'execution-plan.json').read_text())+'</pre></details><p class="foot">报告包含模型实测原文，未隐藏失败。解析、Schema绑定与语义意图检查是三个独立层次；不是产品适配认证。</p></section></main>')
js='''const links=[...document.querySelectorAll('.rail a')];const sections=links.map(a=>document.querySelector(a.getAttribute('href')));function updateNav(){let active=sections[0];for(const s of sections){if(s.getBoundingClientRect().top<=150)active=s;}for(const a of links)a.classList.toggle('active',a.getAttribute('href')==='#'+active.id);}addEventListener('scroll',updateNav,{passive:true});updateNav();'''
out.append('<script>'+js+'</script></body></html>')
(OUT/'report.html').write_text('\n'.join(out));(OUT/'report-mac.html').write_text('\n'.join(out))
print(OUT/'report-mac.html')
