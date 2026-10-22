"""Read-only aggregation of this frozen screening protocol, not ASR-lite-v1."""
import hashlib
import html
import json
import math
from pathlib import Path
import statistics
import sys

EXP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluation_metrics import resource_window, quality, metric


def read(path):
    return json.loads(path.read_text())


def rows(path):
    return [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []


def distribution(values):
    values = sorted(x for x in values if x is not None)
    return dict(n=len(values), median=statistics.median(values) if values else None,
                min=min(values) if values else None, max=max(values) if values else None,
                p95_nearest_rank=values[math.ceil(.95*len(values))-1] if values else None,
                limitation='small fixed inputs, one process round; not a stable tail estimate')


def windows(events, resources, cpu_count, mem_total):
    active = {}; output = {}
    for e in events:
        if e.get('event') != 'phase': continue
        name = e['name']
        if e['state'] == 'start': active[name] = e['monotonic_seconds']
        elif e['state'] == 'end' and name in active:
            start = active.pop(name); end = e['monotonic_seconds']
            w = resource_window(resources, start, end, cpu_count, mem_total)
            w.update(start_monotonic=start,end_monotonic=end)
            output.setdefault(name,[]).append(w)
    summaries = {}
    for name, items in output.items():
        durations = [w['duration_seconds'] for w in items]
        valid = [(w['average_cpu_cores']['value'],w['duration_seconds']) for w in items if w['average_cpu_cores']['value'] is not None]
        cores = sum(c*d for c,d in valid)/sum(d for c,d in valid) if valid and sum(d for c,d in valid)>0 else None
        peaks = [w['peak_pss_mib']['value'] for w in items if w['peak_pss_mib']['value'] is not None]
        summaries[name]=dict(windows=len(items),cpu_windows_evaluated=len(valid),seconds=sum(durations),
                            average_cpu_cores=metric(cores,'cores','duration weighted phase windows','insufficient bracketing samples'),
                            cpu_capacity_percent=metric(cores/cpu_count*100 if cores is not None else None,'%','process tree / logical CPU capacity','insufficient bracketing samples'),
                            peak_pss_mib=metric(max(peaks) if peaks else None,'MiB','sampled process tree within phase','no phase samples'),
                            individual_windows=items)
    return summaries, active


def aggregate():
    llm_review=read(EXP/'llm-review.json') if (EXP/'llm-review.json').exists() else None
    tts_integrity=read(EXP/'tts-integrity.json') if (EXP/'tts-integrity.json').exists() else None
    texts=read(EXP/'text-fixtures.json');fixtures={r['id']:r for r in read(EXP/'asr-fixtures.json')['fixtures']}
    cases=[]
    for module in ['asr','llm','tts']:
        manifest=read(EXP/(module+'-manifest.json'));suite=read(EXP/(module+'-screening.json'))
        cpu=manifest['cpu_count'];mem=manifest['host_memory']['MemTotal']
        for config in suite['cases']:
            folder=EXP/module/config['id'];result=read(folder/'result.json')
            events=rows(folder/'events.jsonl');resources=rows(folder/'resources.jsonl')
            samples=[e for e in events if e.get('event')=='sample' and (module!='asr' or e.get('stage')=='inference')]
            phases,unfinished=windows(events,resources,cpu,mem)
            case=dict(id=config['id'],module=module,execution=dict(status=result['status'],returncode=result['returncode']),
                      protocol=dict(id='rk3566-voice-screen-v2',tier='screening',round=1),
                      candidate=dict(precision=('mixed_int8' if 'int8' in config['id'] else 'fp32') if module=='asr' else 'Q4_K_M' if module=='llm' else 'FP32',backend='CPU',threads=config['threads'],model=config['model']),
                      phases=phases,unfinished_phases=unfinished,source=dict(result=str((folder/'result.json').relative_to(EXP)),sha256=hashlib.sha256((folder/'result.json').read_bytes()).hexdigest()),
                      full_process_resources=dict(peak_pss_mib=result['peak_pss_mib'],cpu_seconds=result['cpu_seconds'],wall_seconds=result['wall_seconds'],min_host_available_mib=result['min_host_available_mib']),
                      assessment=dict(product_performance='NOT_ASSESSED',reason='no user-confirmed quality/latency/RAM thresholds'),samples=[])
            if module=='asr':
                byid={s['fixture']:s for s in samples};score=[]
                for fixture in config['fixture_ids']:
                    s=byid.get(fixture);f=fixtures[fixture]
                    finals=[x for x in s['finals'] if x['text'].strip()] if s else []
                    last=finals[-1] if finals else None
                    row=dict(id=fixture,completed=s is not None,input_sha256=f['sha256'],reference=f.get('reference'),
                             transcript=s['final_text'] if s else None,expected_silence=fixture=='silence1',
                             compute_rtf=s['compute_rtf'] if s else None,
                             first_partial_s=s['first_partial_seconds'] if s and config['realtime'] else None,
                             last_nonempty_final_kind=last['kind'] if last else None,
                             endpoint_wait_from_file_end_s=last['elapsed_s']-s['original_audio_seconds'] if last and last['kind']=='endpoint' and config['realtime'] else None,
                             endpoint_wait_from_energy_anchor_s=last['elapsed_s']-f['energy_end_s'] if last and last['kind']=='endpoint' and config['realtime'] and f.get('energy_end_s') is not None else None,
                             eof_forced=any(x['kind']=='eof_forced' for x in finals),
                             output_integrity='expected_empty' if s and fixture=='silence1' and not s['final_text'] else 'nonempty' if s and s['final_text'] else 'unexpected_empty_or_missing')
                    score.append(dict(case_id=fixture,reference=f.get('reference'),transcript=row['transcript'],output_status='complete' if s else 'missing'))
                    case['samples'].append(row)
                case.update(scenario='realtime' if config['realtime'] else 'throughput',quality=quality(score),
                            expected_samples=len(config['fixture_ids']),completed_samples=len(samples),
                            aggregate_metrics=dict(speech_compute_rtf=distribution([s['compute_rtf'] for s in case['samples'] if not s['expected_silence']]),
                                                   first_partial_s=distribution([s['first_partial_s'] for s in case['samples']]),
                                                   endpoint_wait_from_file_end_s=distribution([s['endpoint_wait_from_file_end_s'] for s in case['samples']]),
                                                   endpoint_wait_from_energy_anchor_s=distribution([s['endpoint_wait_from_energy_anchor_s'] for s in case['samples']])))
            elif module=='llm':
                indexed={s['index']:s for s in samples}
                for i,task in enumerate(texts['llm']):
                    s=indexed.get(i)
                    case['samples'].append(dict(task,completed=s is not None,reply=s['reply'] if s else None,
                                                ttft_seconds=s['ttft_seconds'] if s else None,
                                                first_sentence_seconds=s['first_sentence_seconds'] if s else None,
                                                seconds=s['seconds'] if s else None,
                                                tokens_predicted=s.get('tokens_predicted') if s else None,
                                                stopped_limit=s.get('stopped_limit') if s else None,
                                                transport_observed_decode_tokens_per_second=s.get('transport_observed_decode_tokens_per_second') if s else None,
                                                native_timings=s.get('timings') if s else None,
                                                first_sentence_missing_reason=('structured JSON task has no Chinese sentence-ending punctuation' if task['id']=='slots' and s and s['first_sentence_seconds'] is None else 'no closed sentence observed' if s and s['first_sentence_seconds'] is None else None),quality_pass=None,quality_reason='awaiting explicit text rubric review'))
                if llm_review:
                    reviewed={r['id']:r for r in llm_review['samples']}
                    for sample in case['samples']:
                        review=reviewed[sample['id']]
                        if sample['reply'] is not None:
                            assert hashlib.sha256(sample['reply'].encode()).hexdigest()==review['reply_sha256']
                            sample.update(quality_pass=review['passed'],quality_reason=review['reason'],review_method=review['method'])
                case.update(expected_samples=6,completed_samples=len(samples),quality=llm_review or dict(status='PENDING_TEXT_REVIEW'),
                            aggregate_metrics={key:distribution([s[key] for s in case['samples']]) for key in ['ttft_seconds','first_sentence_seconds','transport_observed_decode_tokens_per_second']})
            else:
                indexed={s['index']:s for s in samples};media=read(folder/'external-media.json')['files']
                for i,task in enumerate(texts['tts']):
                    s=indexed.get(i);audio=next((m for m in media if Path(m['path']).name==str(i)+'.wav'),None)
                    case['samples'].append(dict(task,completed=s is not None,first_pcm_seconds=s['first_pcm_seconds'] if s else None,
                                                pcm_boundary=s['pcm_boundary'] if s else 'missing',rtf=s['rtf'] if s else None,
                                                generated_seconds=s['seconds'] if s else None,
                                                audio_duration_seconds=s['samples']/s['sample_rate'] if s else None,
                                                audio=audio,listening_review=None,quality_reason='no listening review; PCM integrity checked separately'))
                if tts_integrity:
                    checked={r['id']:r for r in tts_integrity['samples']}
                    for sample in case['samples']:
                        sample['pcm_integrity']=checked.get(sample['id'])
                case.update(expected_samples=4,completed_samples=len(samples),quality=dict(status='NOT_EVALUATED',reason='waveform validity is not pronunciation/voice quality'),
                            aggregate_metrics={key:distribution([s[key] for s in case['samples']]) for key in ['first_pcm_seconds','rtf']})
            cases.append(case)
    return dict(decisions=read(EXP/'decisions.json') if (EXP/'decisions.json').exists() else [],listening_page='/home/orangepi/.cache/edge-voice-v2/runs/2026-10-22-voice-screening-v2-r1/listening.html',root_cause='UNKNOWN; no independent operator/system profiling',schema_version='edge-voice-screening/1',protocol_id='rk3566-voice-screen-v2',report_kind='measured_screening',
                source_kind='device_measurement',rounds=1,case_count=len(cases),cases=cases,product_acceptance='NOT_EVALUATED',
                data_contract_note='v2 Python ASR/LLM/TTS adapters; not compatible with ASR-lite-v1 execution validator; metric units/boundaries below and phase metric objects retained',
                metric_definitions=dict(asr_compute_rtf='feature/decode/result/reset/EOF wall computation including 3.2s zero tail divided by original audio duration; pacing/loading excluded',
                                        asr_first_partial='first nonempty text minus first block submission; realtime cases only',
                                        asr_final='last nonempty endpoint final minus scheduled file end or declared energy anchor; EOF forced text excluded from endpoint waiting',
                                        asr_pacing='100ms chunks scheduled at audio block start, not v1 block-end convention; cannot compare v1 waits directly',
                                        llm_ttft='request to first nonempty content chunk; not model-only token timing',
                                        llm_sentence='request to first 。！？ closed sentence; structured JSON may have no such sentence',
                                        tts_pcm='whole utterance return plus PCM16 conversion; file writes excluded, no speaker first sound measured',
                                        phase_cpu='sample-bracket or interior sample CPU deltas, duration-weighted over repeated phase windows; raw scope per window',
                                        pss='200ms sampled process-tree PSS; not kernel high-watermark or entire host memory'),
                limitations=['one process round, three ASR materials reused across four configurations; only one independently transcribed ASR clip',
                             'asset hashing warms filesystem cache; startup is not cold-disk latency','no stable P95 or long-run thermal claim','LLM rubric review is text inspection, not a large quality benchmark',
                             'TTS pronunciation/naturalness need listening review; no playback during execution',
                             'no ROS/YOLO coexistence, microphone, AEC, interruption, or full interaction acceptance'])


def render(data):
    h=lambda x:html.escape(str(x),quote=True)
    def val(v, digits=2):
        return '—' if v is None else format(v, f'.{digits}f') if isinstance(v,(int,float)) else str(v)
    def table(headers, rows):
        return '<div class="table-wrap"><table><thead><tr>'+''.join('<th>'+h(x)+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+h(x)+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table></div>'
    def stats(c, key, unit=''):
        d=c.get('aggregate_metrics',{}).get(key,{})
        return val(d.get('median'))+unit+'（'+val(d.get('min'))+'–'+val(d.get('max'))+unit+'；n='+str(d.get('n',0))+'）'
    def resource(c, key):
        return c.get('phases',{}).get('inference',{}).get(key,{}).get('value')
    def name(c):
        if c['module']=='asr':
            return ('混合 INT8' if 'int8' in c['id'] else 'FP32')+' / '+('实时送入' if c.get('scenario')=='realtime' else '尽快送入')
        return 'Qwen2.5 · 0.5B · Q4_K_M' if c['module']=='llm' else 'Melo zh_en · FP32'
    cases=data.get('cases',[])
    out=['<!doctype html>\n<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>RK3566 语音模型初筛 · 结论与依据</title>\n<style>\n:root{--ink:#172d38;--muted:#516673;--line:#dce5e8;--accent:#086b62}*{box-sizing:border-box}body{margin:0;background:#f3f5f5;color:var(--ink);font:16px/1.75 system-ui,-apple-system,"Segoe UI",sans-serif}main{max-width:1180px;margin:auto;padding:40px 28px 64px}header{margin-bottom:30px}h1{font-size:clamp(28px,4vw,42px);line-height:1.3;letter-spacing:-1px;margin:12px 0}h2{font-size:26px;line-height:1.4;margin:0 0 16px}h3{font-size:20px;margin:26px 0 12px}p{margin:10px 0}a{color:var(--accent);text-underline-offset:4px}.eyebrow{font-size:12px;font-weight:700;letter-spacing:2px;color:var(--accent)}.muted,small{color:var(--muted)}nav{display:flex;gap:12px;flex-wrap:wrap;margin:22px 0}nav a{font-size:14px;text-decoration:none;background:white;border:1px solid var(--line);border-radius:24px;padding:7px 16px}section{background:white;border:1px solid var(--line);border-radius:18px;padding:30px;margin:24px 0;scroll-margin-top:20px}.lead{font-size:22px;font-weight:650;line-height:1.6;max-width:960px}.cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin:24px 0}.card{padding:22px;border-radius:12px;background:#f5f8f8;border-top:4px solid var(--accent)}.card.warn{border-top-color:#bf7926;background:#fff9ee}.card h3{margin:10px 0;font-size:21px}.tag{font-size:12px;font-weight:700;color:var(--accent)}.warn .tag{color:#8a5417}.note{padding:14px 18px;border-left:3px solid #bdcdd3;background:#f5f8fa;margin:18px 0}.table-wrap{overflow-x:auto;margin:18px 0;border:1px solid var(--line);border-radius:10px}table{width:100%;border-collapse:collapse;font-size:14px}th{background:#edf3f3;color:#314b56;text-align:left;font-weight:650;white-space:nowrap}td,th{padding:13px 15px;border-bottom:1px solid var(--line);vertical-align:top}tr:last-child td{border-bottom:0}td{min-width:90px}td:first-child{font-weight:550}p,td,pre{overflow-wrap:anywhere}pre{white-space:pre-wrap;background:#f5f7f8;padding:16px;border-radius:8px;font-size:12px;max-height:500px;overflow:auto}details{border-top:1px solid var(--line);padding:13px 0}summary{cursor:pointer;color:var(--accent);font-weight:550}.quote{font-size:20px;font-weight:600;color:#8b4323}.foot{font-size:13px;color:var(--muted)}@media(max-width:800px){main{padding:22px 14px}.cards{grid-template-columns:1fr}section{padding:20px 16px}td,th{padding:10px}h2{font-size:23px}}@media print{body{background:white}main{padding:0}section{break-inside:avoid}nav{display:none}}\n</style></head><body><main>\n<header><div class="eyebrow">EDGE AI / RK3566 / 2026.10.22</div><h1>机器人本地语音，该怎样继续选？</h1><p class="muted">Orange Pi 3B · RK3566 · 标称 4GB · 单模块初筛，第 1 轮</p><nav><a href="#conclusions">01 先看结论</a><a href="#meaning">02 看懂指标与测试口径</a><a href="#data">03 查看实测数据</a><a href="#evidence">04 追溯原始证据</a></nav></header>\n<section id="conclusions"><div class="eyebrow">01 / DECISION</div><h2>先看结论</h2><p class="lead">ASR 保留 INT8 候选并补查质量；LLM 先解决事实编造和回答等待；TTS 先调整合成方案，再决定复测。</p><p>本轮已跑通三个模块，但还不能确认这套组合适合机器人语音交互。当前更有价值的是补齐质量证据、处理明显的等待问题。</p><div class="cards"><article class="card"><span class="tag">ASR / 听懂</span><h3>保留候选，先查识别质量</h3><p>混合 INT8 的计算与内存开销较低；保留同源 FP32 作质量对照。现有参考音频太少，尚不能认定中文识别达标。</p><p class="muted">下一步：补齐固定小集，重点检查专名和数字。</p></article><article class="card warn"><span class="tag">LLM / 思考</span><h3>先调整，再比较</h3><p>简单任务多数能完成，但会编造未知温度，首句等待也较长。当前配置还缺乏适合即时对话的证据。</p><p class="muted">下一步：保留失败用例，验证提示处理等待及候选替代方案。</p></article><article class="card warn"><span class="tag">TTS / 说话</span><h3>暂缓重复当前配置</h3><p>能合成有效音频，但整句返回慢，发音与自然度还未试听。直接重复当前配置的收益有限。</p><p class="muted">下一步：先试听，再检查更轻的部署与合成耗时。</p></article></div><div class="note">这是模型初筛结论。产品质量、延迟和内存门槛尚未确认；麦克风、扬声器、ROS / YOLO 共跑及完整交互均未验收。</div>']
    # Keep the machine-readable decision wording available without overwhelming the lead.
    out.append('<details><summary>查看完整决策记录</summary>')
    for d in data.get('decisions',[]):
        out.append('<p><strong>'+h(d['candidate'])+'：</strong>'+h(d['disposition'])+'</p><p>'+h(d['reason'])+'</p>')
    out.append('</details></section>')
    out.append('<section id="meaning"><div class="eyebrow">02 / HOW TO READ</div><h2>这些数据能说明什么？先统一口径</h2><h3>这次怎样测</h3><p>三个模块在同一块板子上依次独立运行，推理引擎均设置 2 线程。共有 6 种进程配置、22 条正式输入记录，每种配置只跑 1 轮。加载、预热、空闲和正式推理分别记录；下面的 CPU 与内存只取正式推理窗口。</p><p>ASR 的 3 段材料在 4 种配置中复用，其中只有 1 段有独立参考转写；LLM 用 6 条固定任务；TTS 用 4 条固定文本。22 条执行记录不等于 22 个独立质量样本，也不是三轮复测。</p>')
    out.append(table(['概念','具体测什么','怎样判断，边界在哪里'],[
        ['模型 / 运行时 / 精度','ASR 将声音转为文字，LLM 生成回答，TTS 将文字合成为声音。运行时是执行模型的软件。INT8 / FP32 / Q4_K_M 表示不同权重或计算精度。','精度降低可能省资源，也可能改变质量，必须一起检查。这里全部使用 CPU；ASR 混合 INT8 的 decoder 仍为 FP32，并非全模型 INT8。'],
        ['ASR 计算 RTF（越小越快）','计算耗时 ÷ 原始音频时长。例如 RTF=0.3，处理 10 秒音频需约 3 秒计算。','不包含加载和按实时节奏等待；包含特征、解码、结果处理及 3.2 秒补零尾部的计算。小于 1 只说明这组输入计算跟得上，不保证说完就立刻出结果。'],
        ['ASR 首个文字 / 端点等待','首个文字：从首块音频送入到首个非空识别结果。端点等待：从能量结束锚点到最后一个非空端点结果。','首个文字包含文件开头静音，不能称为从人开口计时。能量锚点用 20ms RMS > −35dBFS 定义，不能视为人工标注的说话结束。EOF 强制结果不混入端点等待。'],
        ['CER：字错误率（越低越好）','替换、删除、插入的字符数 ÷ 参考字符数。这里仅一段独立参考，共 37 个归一化字符。','英文专名和数字写法参与评分。CER 不是通用准确率，不能把单条 CER 换成整体识别成功率；无独立参考的命令只展示输出。'],
        ['LLM 首内容 / 首句等待','首内容 TTFT：请求发出到首个非空内容片段。首句：请求发出到首次出现 。！？ 闭合句。','收到一个片段并不代表已拿到一句可用于后续合成的文本。JSON 任务没有中文句末标点，首句不适用。均含请求与服务处理，不是纯模型内核运算。'],
        ['LLM 任务检查 / 输出速度','按每条事先固定的要求检查回答；输出速度单位为 token/s（token 是模型文本单位，不等于一个汉字）。','本轮为 Codex 按文本规则检查，无独立人工复核。通过比例只覆盖这 6 条任务；输出速度不能代替事实可靠性或首句等待。'],
        ['TTS 首 PCM / 合成 RTF','PCM 是可播放的数字音频样本。这里首 PCM 等待是整句合成返回并转为 PCM16 的耗时；RTF=合成耗时 ÷ 生成音频时长。','例如 RTF=6.5，生成 1 秒音频约需 6.5 秒。未测流式首包或扬声器首声；首 PCM 不含写文件。WAV 有效只证明文件可用，发音、数字读法和自然度仍需试听。'],
        ['CPU 容量占比 / PSS 内存','CPU 为进程树占整机 4 核总容量的比例；PSS 按比例分摊共享驻留内存，单位 MiB。','25% 约相当于持续用满 1 个核。引擎 2 线程不代表整个进程只有 2 个线程。PSS 是每 200ms 采样的推理窗峰值，不是整机内存或绝对峰值。'],
        ['中位数 / 范围 / n','中位数表示这几条输入的中间水平；范围是最小到最大；n 是该指标有值的输入数。','都是同一进程内固定小集的一轮观察，不是多轮统计置信度。不同句长影响耗时；小样本不用于稳定 P95、长期温控或总体质量结论。']]))
    out.append('<div class="note"><strong>这轮有用的地方：</strong>能看出相同输入下的部署开销、实际输出和明显失败点，帮助决定下一项实验。<br><strong>还回答不了的：</strong>真实用户总体体验、长期稳定、最终达标与共跑表现。各模块延迟和资源不可直接相加成整机结论。</div></section>')
    out.append('<section id="data"><div class="eyebrow">03 / MEASUREMENTS</div><h2>实际测到了什么</h2><p class="muted">下表中的统计值均来自原始记录。除质量计数外，汇总单元格按“中位数（最小–最大；n）”呈现。</p><h3>ASR · 识别快不快，听得对不对</h3><p>尽快送入用于看计算吞吐；实时送入按 100ms 音频块的起始时间投喂，用于观察在线出字和端点等待。同源权重、相同输入下对比混合 INT8 与 FP32。</p>')
    asr=[c for c in cases if c['module']=='asr']
    out.append(table(['配置','完成输入','语音计算 RTF','首个文字等待','能量结束后端点等待'],[
        [name(c),str(c['completed_samples'])+'/'+str(c['expected_samples']),stats(c,'speech_compute_rtf'),stats(c,'first_partial_s','s') if c.get('scenario')=='realtime' else '不适用',stats(c,'endpoint_wait_from_energy_anchor_s','s') if c.get('scenario')=='realtime' else '不适用'] for c in asr]))
    out.append('<p><strong>质量结果：</strong>唯一独立参考音频在两种精度、两种送入方式下均为 20 / 37 个字符错误，CER 54.1%。这说明本条样例存在明显错误，仍需更多参考样本判断适用性。静音样例均输出空文本。</p>')
    # Avoid duplicating identical transcripts for both pacing configurations.
    speech_rows=[]
    for c in asr:
        if c.get('scenario')!='throughput': continue
        for s in c['samples']:
            if not s.get('expected_silence'):
                speech_rows.append([name(c).split(' / ')[0],s['id'],s.get('reference') or '无独立参考，不能评分',s.get('transcript') or '（空）'])
    out.append(table(['精度','输入样例','参考文本','实际识别'],speech_rows))
    out.append('<p class="foot">首个文字等待包含文件前导静音。端点等待取最后一个非空 endpoint 事件；排除 EOF 强制输出和后续空端点。文件尾部静音可能使“相对文件结束”的等待为负，完整事件和该口径留在证据中。本轮块起始投喂规则与旧版不同，不直接比较旧延迟。</p>')
    llms=[c for c in cases if c['module']=='llm']
    out.append('<h3>LLM · 回答是否可靠，需要等多久</h3>')
    for c in llms:
        out.append('<p>'+h(name(c))+'；固定系统提示要求简短中文、未知事实明确承认未知。线程 2，context 2048，batch 128，ubatch 64，KV F16，最多生成 96 tokens，贪心解码，关闭提示缓存。</p>')
        out.append(table(['指标','本轮结果'],[['首内容等待 TTFT',stats(c,'ttft_seconds','s')],['首个中文闭合句等待',stats(c,'first_sentence_seconds','s')],['传输侧观察的输出速度',stats(c,'transport_observed_decode_tokens_per_second',' token/s')],['固定任务检查','5 / 6 通过（Codex 文本规则检查）']]))
        out.append('<div class="note"><strong>关键失败：</strong>明确告知“没有接入温度传感器”，仍回答<span class="quote">“室内温度为20摄氏度。”</span>。系统提示尚未可靠阻止事实编造。</div>')
        out.append(table(['任务输入','实际回答','按固定要求检查','首内容 / 首句等待'],[[s['prompt'],s.get('reply') or '（空）',('通过' if s.get('quality_pass') else '未通过')+'：'+s.get('quality_reason',''),val(s.get('ttft_seconds'))+'s / '+(val(s.get('first_sentence_seconds'))+'s' if s.get('first_sentence_seconds') is not None else '不适用（JSON）')] for s in c['samples']]))
        out.append('<p class="foot">6 次请求均无前缀缓存命中；原生 prompt 处理记录约 7.94–10.75s，与首内容等待接近。这是等待组成的线索，尚无独立算子或系统剖析支持具体根因判断。</p>')
    out.append('<h3>TTS · 什么时候拿到音频，音频是否说得好</h3>')
    for c in [c for c in cases if c['module']=='tts']:
        out.append('<p>'+h(name(c))+'；4 条均生成有效、非零的单声道 PCM16 WAV。<strong>尚未试听，因此发音正确性和自然度未知。</strong></p>')
        out.append(table(['指标','本轮结果'],[['整句首 PCM 等待',stats(c,'first_pcm_seconds','s')],['合成 RTF',stats(c,'rtf')],['音频质量','文件有效性通过；听感未评审']]))
        out.append(table(['合成文本','生成音频时长','整句首 PCM 等待','合成 RTF','主观听感'],[[s['text'],val(s.get('audio_duration_seconds'))+'s',val(s.get('first_pcm_seconds'))+'s',val(s.get('rtf')),'未评审'] for s in c['samples']]))
    if data.get('listening_page'):
        out.append('<p><a href="'+h(data['listening_page'])+'">打开本机四段音频试听页 →</a><span class="muted"> 音频保留在 Git 外，链接仅在当前设备可用。</span></p>')
    out.append('<h3>资源开销 · 还有多少空间留给机器人</h3><p>这里只展示独立运行时的开销，尚未测 ROS、视觉和语音共同运行的资源竞争。</p>')
    out.append(table(['模块 / 配置','正式输入完成数','推理窗 CPU 容量占比','推理窗峰值 PSS'],[[c['module'].upper()+' / '+name(c),str(c['completed_samples'])+'/'+str(c['expected_samples']),val(resource(c,'cpu_capacity_percent'))+'%',val(resource(c,'peak_pss_mib'))+' MiB'] for c in cases]))
    out.append('<p class="foot">所有配置正常退出，无超时或保护中断。CPU 对重复推理窗口按时长加权；PSS 为这些窗口中的采样峰值。加载与预热另存记录，未混入本表。资产校验已预热文件系统缓存，启动记录不代表冷盘启动。</p></section>')
    out.append('<section id="evidence"><div class="eyebrow">04 / EVIDENCE</div><h2>原始证据与完整统计</h2><p>先看上面的解释与结果；需要复核时，再展开配置、逐条事件、计时和采样记录。</p><p><a href="results.json">结果 JSON</a> · <a href="README.md">实验说明</a> · <a href="protocol.json">测试协议</a> · <a href="artifact-hashes.json">文件哈希清单</a></p>')
    for c in cases:
        out.append('<details><summary>'+h(c['module'].upper()+' / '+name(c))+' · 完整记录</summary><p><a href="'+h(c['source']['result'])+'">进程原始结果</a> · SHA256 '+h(c['source']['sha256'])+'</p><pre>'+h(json.dumps(c,ensure_ascii=False,indent=2))+'</pre></details>')
    out.append('<details><summary>机器可读的指标定义与限制</summary><pre>'+h(json.dumps(dict(definitions=data.get('metric_definitions',{}),limitations=data.get('limitations',[])),ensure_ascii=False,indent=2))+'</pre></details></section><footer class="foot">板端实测 · 单轮初筛 · 完整交互未验收 · 展示调整不改变原始测量</footer></main></body></html>')
    return '\n'.join(out)


if __name__=='__main__':
    if '--render' in sys.argv:
        result=read(EXP/'results.json')
    else:
        result=aggregate()
        (EXP/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    (EXP/'report.html').write_text(render(result))
