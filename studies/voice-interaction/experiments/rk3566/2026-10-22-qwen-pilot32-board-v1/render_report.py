"""Regenerate derived pilot views from immutable measurements; no models."""
import hashlib
import html
import importlib.util
import io
import json
from pathlib import Path
import statistics
import zipfile

ROOT = Path(__file__).resolve().parent
LABELS = ['f16-e379-v2', 'q8-e379-v2', 'cache-false-v2', 'cache-true-v2', 'cache-q8-true-v1']

def read(path):
    return json.loads((ROOT / path).read_text())

def write(path, value):
    (ROOT / path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def summarize(result, label):
    rows = [c['resources'] for c in result['cases']]
    peak = max(r['peak_pss_bytes'] for r in rows)
    wall = sum(r['wall_seconds'] for r in rows)
    events = [read('runs/' + label + '/benchmark/events/' + c['id'] + '.json')['resources'] for c in result['cases']]
    intervals = [b['monotonic_seconds']-a['monotonic_seconds'] for samples in events for a,b in zip(samples,samples[1:])]
    temperatures = [value for samples in events for s in samples for value in s.get('thermal_zone_celsius',{}).values()]
    return {'run_id':result['run_id'], 'kv':result['candidate']['kv_type'], 'summary':result['summary'],
        'cpu_capacity_percent':sum(r['cpu_seconds'] for r in rows)/wall/4*100,
        'peak_pss_mib':peak/2**20, 'peak_pss_memtotal_percent':peak/rows[0]['host_mem_total_bytes']*100,
        'minimum_host_available_mib':min(r['minimum_host_mem_available_bytes'] for r in rows)/2**20,
        'host_swap_in_delta_bytes_sum_windows':sum(r['host_swap_in_delta_bytes'] for r in rows),
        'host_swap_out_delta_bytes_sum_windows':sum(r['host_swap_out_delta_bytes'] for r in rows),
        'median_actual_sample_interval_seconds':statistics.median(intervals),
        'maximum_observed_thermal_zone_celsius':max(temperatures) if temperatures else None,
        'prefill_tps_median':statistics.median(c['generation']['prefill_tokens_per_second'] for c in result['cases']),
        'decode_tps_median':statistics.median(c['generation']['decode_tokens_per_second'] for c in result['cases']),
        'health_ready_seconds':read('runs/' + label + '/server-load.json')['health_ready_seconds']}

def main():
    results = [read('runs/' + name + '/results.json') for name in LABELS]
    raw_before = {str(p.relative_to(ROOT)):digest(p) for p in (ROOT/'runs').rglob('*.json')}
    summaries = [summarize(r,label) for r,label in zip(results,LABELS)]
    cache_rows = []
    for label,result in zip(LABELS[2:],results[2:]):
        for case in result['cases']:
            g = case['generation']
            cache_rows.append({'group':label,'id':case['id'],'full_input_tokens':g['prompt_tokens'],
                'evaluated_prefill_tokens':g['evaluated_prefill_tokens'],
                'native_cached_tokens':g['native_usage']['prompt_tokens_details']['cached_tokens'],
                'output_tokens':g['output_tokens'], 'generation_steps':g['native_timings']['predicted_n']-1,
                'prefill_seconds':g['prefill_seconds'],'decode_seconds':g['decode_seconds'],
                'first_content_seconds':g['ttft_seconds'],'http_seconds':g['wall_seconds'],
                'valid_call_seconds':case['valid_call_seconds'],
                'expected_behavior':case['assessment']['expected_behavior']})
    write('analysis.json',{'source':'derived from saved native usage/timings and raw samples',
        'generation_steps_source':'runtime-counter-source.json; e379 n_gen_steps=n_gen-1',
        'runs':summaries,'cache_cases':cache_rows,'inference_executions':sum(len(r['cases']) for r in results),
        'scope':'development only; no sealed final test, hardware action or production integration'})
    table = '| 组 | CPU/4核容量 | 峰PSS MiB / 实际RAM | prefill中位 tok/s | decode中位 tok/s | 工具预期 | 人设规则 |\n|---|---:|---:|---:|---:|---:|---:|\n'
    for label,s in zip(LABELS,summaries):
        q=s['summary'];table+=f"| {label} | {s['cpu_capacity_percent']:.2f}% | {s['peak_pss_mib']:.2f} / {s['peak_pss_memtotal_percent']:.2f}% | {s['prefill_tps_median']:.3f} | {s['decode_tps_median']:.3f} | {q['tool_expected_behavior']}/{q['tool_samples']} | {q['persona_valid']}/{q['persona_samples']} |\n"
    cache_table='| 组 / 例 | 完整输入 | 实际prefill | 原生cached | 输出 / decode步数 | 首内容 s | HTTP s | 完整有效调用 s |\n|---|---:|---:|---:|---:|---:|---:|---:|\n'
    for c in cache_rows:
        cache_table+=f"| {c['group']} / {c['id']} | {c['full_input_tokens']} | {c['evaluated_prefill_tokens']} | {c['native_cached_tokens']} | {c['output_tokens']} / {c['generation_steps']} | {c['first_content_seconds']:.3f} | {c['http_seconds']:.3f} | {c['valid_call_seconds']:.3f} |\n"
    text='''# Qwen3 最小 LoRA Q4 · RK3566 独立验证

工单 #12。沿用 #10 的32微步/4次优化器更新试点 Q4_K_M，只验证独立部署、原生工具 intake 和 Linux 采集。[离线阶段 HTML](report.html) · [KV准备交付](prepare/report.html) · [缓存组合准备](prepare-cache/report.html) · [派生指标](analysis.json)。

本轮5个独立服务轮次、23次开发推理：两组各7例（3工具、3人设、1聊天），三组各3次 volume_set 缓存对照。共8条不同用户输入，重复执行不当成独立材料。九工具目录已原样传入，实际调用只覆盖 start_camera、volume_set、play_music 三种；其余六种不据此宣称通过。没有读取 sealed final，更未执行处理器、旧 C++、ROS 或硬件动作。

## 当前结论

同一试点Q4在两种KV均可原生生成并经JSON/原始Schema/同源Registry接收。短组工具均3/3、聊天均1/1；人设 f16 为0/3，q8_0 为1/3。f16姓名输出“小安”，q8_0输出“小沫”；Mac同Q4为1/3。固定规则结果保留，不能将试点人设推广为稳定能力。

'''+table+'''
缓存组prefill中位数来自不同实际评估量，不能据此跨模式排名模型速度。三组九目录对照的9次调用均与预期参数一致。缓存减少重复前缀计算的等待，不能解释成模型吞吐增加十倍；完整输入、实际prefill与原生cached计数分别保留。

'''+cache_table+'''
建议 #14 从有真实准备证据的 q8_0 KV + cache_prompt=true 组合冻结配置，在新 selected 制品上先完成独立加载/开发冒烟，再完整执行全部132条 final；不得删样本。q8缓存冷首例比f16更慢，暖/变更前缀更快；不要只拿重复请求预算全部final，更不能根据这几例宣称P95。GGML_CPU_REPACK=OFF 是保守构建，不代表RK3566最优速度或硬件上限。

## 身份、准备与失败

- 设备为 Rockchip RK3566 OPi3B、4个Cortex-A55、Ubuntu20.04 / Linux5.10.160、glibc2.31、ondemand；实际MemTotal4017020KiB（4113428480字节）。[复核](device-before.txt)、[OS/ABI](os-abi.txt)、[结束状态](device-after.txt)。旧模型、旧运行库、生产源码均保留。
- GGUF 396704704字节，SHA256 `8a1e5584a9f8ee04b1e54afad217f2dbb6f4e31ab0a1d8832d8faadda92e7a9b`。[Mac导出来源](../../mac/2026-10-22-qwen-lora-export-pilot-v1/README.md)、[base清单](base-artifact-manifest.json)。权重、源码SDK、构建和隔离venv在仓库外。
- 先复用22cd28d：默认direct I/O/repack配置加载时SIGABRT；关闭repack并改mmap后health ready，但原始Schema的 `\\S` 在工具grammar转换时HTTP400。[诊断顺序](attempts.json)、[原失败](failed-runs/)。一次端口探测TIME_WAIT失败也保留并修复，未启动模型。
- 独立构建同Mac的 `e3797b184d428c7a019362612b76971f60af6670`，GCC9.4.0、CPU native、REPACK OFF、OpenMP、无GPU；系统CMake3.16嵌套UI脚本失败，隔离venv CMake4.4.4修复。[构建配方](build-recipe.json)、[成功日志](build-e379-v2.log)、[首构建失败](build-e379-cmake316-failed.log)。官方ARM发布工作流与板端ABI的选择依据见配方，未声称所有预编译包不兼容。
- 新版已移除 `--mmap`，需 `--load-mode mmap`。首次四组均参数退出，原失败目录和queue退出记录保留；随后新request、新run目录重跑。
- e379接受原Schema，但明确警告不支持该非锚定pattern、grammar接受任意字符串。原Schema没有改写，JSON Schema和Registry后置纯校验仍严格执行。[计数来源与SHA](runtime-counter-source.json)、[九Schema一致性](board-schema-check.json)、[业务快照](business-source/registry_validate.py)。

## 测量口径与复跑

服务仅绑定127.0.0.1，2线程、单槽、2048上下文、512 batch /128 microbatch、FA on、温度0、最大输出128。完整提示词加输出预算逐例检查；九目录883+128=1011tokens，未截断。f16/q8、cacheoff/on分组执行，顺序记录在queue JSON。

权重SHA校验在启动前顺序读取文件，页缓存可能已预热；加载窗为启动服务至health ready，排除哈希，不能称冷盘启动。推理资源窗覆盖请求到纯intake结束，但CPU/PSS监控实际模型服务进程树，不将HTTP客户端伪装成模型进程。CPU除以实际4核容量；PSS为采样峰而非kernel高水位，200ms是调度等待间隔，实际间隔包含采样成本并保留原始时间戳。整机可用内存、swap使用/换入/换出及可读thermal-zone保存在逐例events；swap计数属整机，不能归因单模型。

完整input来自native usage；实际prefill为timings.prompt_n；缓存数直接来自native字段，未用差值猜测。predicted_n是输出总数，decode原生速率按n_gen-1步数计算，首token来自prefill末logits。首内容含HTTP与原生解析器缓冲，完整有效调用另含JSON/Schema/纯Registry子进程启动和校验；两者均非完整机器人交互。

`python -m tools.qwen_lifecycle.board_run NEW_REQUEST NEW_OUTPUT` 是板端入口，亦可由edge-model-benchmark dispatcher调用。复制冻结请求时使用新run_id和新输出目录，按实际路径调整model/suite/validator；不要覆盖历史目录。完整隔离路径、argv、来源SHA和下游建议见 [handoff](handoff.md)。

Mac Q4对照沿用T10原结果与证据：同7开发输入/同权重，Metal、声明context8192、默认未量化KV；板端CPU/context2048/KV/FA等不同，是部署方案对照，不能当纯后端或量化归因。Mac RSS、MLX分配和Linux PSS不等价，不相加。采集时source保留在每组source/；本页新view采用独立冻结renderer802d872，未追溯改写measurement快照或旧HTML。

静态引用、转义、嵌入JSON/ZIP、源哈希和响应式CSS检查见 [QA](qa.json)。浏览器file://策略拒绝后未尝试替代预览，视觉交互未验证。准备通过只覆盖已注明的加载/开发边界，生产集成、完整目录和共跑验收均未完成。
'''
    (ROOT/'README.md').write_text(text)
    spec=importlib.util.spec_from_file_location('frozen_view',ROOT/'view-source/report.py')
    view=importlib.util.module_from_spec(spec);spec.loader.exec_module(view)
    bundle=io.BytesIO()
    with zipfile.ZipFile(bundle,'w',zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(ROOT.rglob('*')):
            if path.is_file() and path.suffix!='.html' and path.name not in ('evidence-manifest.json','qa.json') and '__pycache__' not in path.parts:
                archive.write(path,str(path.relative_to(ROOT)))
    rendered=view.render([read('mac-q4-results.json')]+results,bundle.getvalue())
    rendered=rendered.replace('<h1>Qwen：从未微调基线到部署制品</h1>','<h1>Qwen3试点 Q4 · RK3566板端阶段验证</h1>')
    note='<aside class="finding"><strong>本轮范围与关键控制</strong><p>同试点Q4；板端4核A55、实际RAM3.83GiB，2线程/context2048。23次开发执行，重复不当独立材料。旧库加载/Schema失败、新版CLI失败原样保留；e379 grammar不覆盖全部正则约束，原始Schema/Registry后置校验保持。</p><p>缓存跳过前缀计算，完整883tokens不变。原生decode速率按输出数减1的实际步数，首token来自prefill末logits；文件378.33MiB不能替代PSS。Mac与板端分组，非纯硬件加速归因。</p><p><a href="prepare/report.html">KV准备</a> · <a href="prepare-cache/report.html">q8缓存组合准备</a> · <a href="README.md">完整口径/失败/复跑</a></p></aside>'
    rendered=rendered.replace('<h2>原生调用、角色设定和硬件资源分别判断</h2>','<h2>原生调用、角色设定和硬件资源分别判断</h2>'+note,1)
    (ROOT/'report.html').write_text(rendered)
    assert raw_before=={str(p.relative_to(ROOT)):digest(p) for p in (ROOT/'runs').rglob('*.json')}, 'renderer changed raw evidence'

if __name__=='__main__':
    main()
