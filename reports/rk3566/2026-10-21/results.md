> 本文来自原ros-robot实验，原分支/路径用于追溯；当前维护仓库为edge-ai。Git快照省略音频，完整原件仍在外置缓存。

# RK3566 首轮短测试记录（2026-10-21 UTC）

本轮已把旧 ASR、SummerTTS、旧微调 Qwen 跑通，并完成非小雅 TTS 候选、同源量化、线程和共存对照。NPU 使用同源 ASR 官方历史 compiler2.2.0 产物实际解码通过。全部为文件推理，模型返回的函数名只作为字符串保存，没有执行动作、录音或播放。

交付分支：`codex/edge-inference-benchmark-research-20261021`。源码在独立工作树 `/home/orangepi/code/ros-robot-edge-benchmark`。原集成分支暂停且保持原状。

## 报告与复测

- HTML：`/home/orangepi/.cache/ros-robot-edge-benchmark/runs/comparison-20261021/report.html`。
- 同目录保留案例 JSON、200ms 资源记录、原始引擎日志、音频、流式回复和各来源 manifest；复制整个目录可以搬运报告。
- 实验入口与配置说明：[README](../../../tools/edge_benchmark/README.md)。`run CONFIG NEW_OUTPUT` 运行，`report OUTPUT` 从保存结果重建，`combine NEW_OUTPUT SOURCE...` 汇总已有实验。
- 研究依据：[ASR/TTS/NPU 官方资料](../../../docs/research/rk3566/research-speech.md)、[llama/Qwen/PDF 对照](../../../docs/research/rk3566/research-llm.md)。附件是部署经验参考，其中其他机器性能没有当作本板结果。

## 已测参数与口径

ASR 固定旧 streaming Zipformer，CPU 1/2/4线程、greedy/beam4、100ms输入块、真实节奏回放，以及 native CLI CPU/RKNN 对照。TTS 固定正常语速，Summer与sherpa huayan测1/2/4线程，Piper使用其原生默认线程池；另测中文VITS、Melo ONNX。Qwen固定旧模板和seed42、temperature0.7、top_p0.8、top_k20，测BF16/Q8_0/Q5_K_M/Q4_K_M、1/2/4线程、context1024/2048、batch128/256、microbatch64/128、K cache f16/q8_0（V保持f16）。未穷举采样参数，也未填满2048上下文。

代表指标是ASR计算RTF、流式首个partial、TTS整句PCM就绪/RTF、LLM预填充吞吐、生成token/s、TTFT和完成耗时，以及进程树RSS/PSS、CPU核秒、swap、主机可用内存、温度与频率。初始化单独记录，但适配器范围不同，不能把所有加载时间当同口径冷启动排名。少量样本没有稳定p95、CER/WER或MOS结论。

## 三基线结果

下表线程组使用相同的组内输入顺序；PSS是整个案例采样峰值，CPU百分比以100%为一核。RTF低于1表示该样本计算快于音频时长。

| 配置 | 逐例RTF / 生成速度 | 峰值PSS MiB |
| --- | --- | ---: |
| ASR CPU 1线程 | 0.452 / 0.503 | 167.5 |
| ASR CPU 2线程 | 0.342 / 0.349 | 157.2 |
| ASR CPU 4线程 | 0.795 / 0.762 | 171.2 |
| Summer 1线程 | 1.150 / 1.310 | 587.4 |
| Summer 2线程 | 0.976 / 0.851 | 592.2 |
| Summer 4线程 | 1.404 / 1.034 | 602.4 |
| Qwen Q8 1线程 | 4.08 / 4.02 token/s | 983.2 |
| Qwen Q8 2线程 | 5.32 / 5.84 token/s | 987.4 |
| Qwen Q8 4线程 | 1.34 / 1.53 token/s | 1006.6 |

Q8两线程TTFT为1.21/1.87秒，实际输入21/35tokens。增加到四线程在这些例子里反而变慢；当前板子可先采用两线程作为复测起点。没有用单次筛查证明降频或线程竞争的唯一根因。

ASR按实际音频节奏回放时，第一个partial对应音频1.1秒、墙钟约1.21秒；计算RTF约0.670。首次端点在文件结束前出现，因为录音本身有句间停顿，不能称真人末音到最终结果的延迟。一个早期8秒C270历史录音在CPU/NPU均得到空文本，保留为失败/空识别观察，不把它计作正确识别；另补历史有效语音对照，见原始输出。

## TTS 相同文本对照

| 部署 | 中句RTF | 长句RTF | 峰值PSS MiB |
| --- | ---: | ---: | ---: |
| Summer 2线程（matched） | 0.803 | 0.797 | 546.0 |
| sherpa huayan 1线程 | 1.339 | 1.306 | 258.6 |
| sherpa huayan 2线程 | 0.782 | 0.794 | 249.7 |
| sherpa huayan 4线程 | 0.662 | 0.662 | 255.9 |
| Piper huayan 默认线程 | 0.671 | 0.659 | 313.0 |
| sherpa 中文VITS 4线程 | 3.772 | 未测 | 246.6 |
| sherpa Melo 4线程 | 5.085 | 未测 | 376.7 |

Piper与sherpa的huayan模型计算图/张量hash相同，但文本前端和ORT版本不同（1.14.1与1.28.2），不把差异归结为纯引擎速度。Piper不能标成单线程。Summer数字/文本前端与其他模型不同，音频长度也不同，因此报告同时保存耗时和真实音频供复核。

对本轮正常输入，huayan部署比所选中文VITS/Melo更适合继续研究交互时延；Summer仍可作为完整旧基线保留。音质、数字读法、中文准确性需要结合WAV评判，速度不替代试听。VITS两线程那一项被整个180秒套件剩余预算截断（约8.9秒），并非给足独立超时后失败；后续更低线程项未执行，未填造读数。

## 同源量化与运行库现象

从旧BF16重新生成的Q8 SHA-256与现有Q8完全相同：`27dc23f5d549e8e4c11defbafcbb8e405db995ef82e32a3cc2fa0b56b6c5f615`。Q5/Q4也直接由同一BF16与同一quantizer生成，严格同源对照成立。量化准备耗时另记，不计作推理耗时。

同一35token提示、两线程、context1024/batch128/microbatch64/f16 KV：Q8重复例约6.01token/s、TTFT1.85秒、PSS986.3MiB；Q5约3.31token/s、TTFT5.85秒、PSS603.8MiB；Q4关闭repack约3.61token/s、TTFT4.80秒、PSS557.3MiB。更小的量化没有在本机自动换来更高速度；可分别作为速度优先和内存优先候选，最终还需效果评判。

Q4原生默认重打包加载触发`stack smashing detected`，多配置均在请求前失败；固定模型和输入，仅增加`--no-repack`便完成请求。后续batch/context/KV对照沿用该可复核绕行方式，不宣称已修复底层库。原始失败日志保留。

BF16长提示60秒未完成，原worker只在完成时保存流，因此不能从缺失sample推断没有生成token。补测短12token提示时，TTFT约22.23秒、PSS1363.4MiB，到90秒预算仍未完整结束；新的逐块流日志保存了已生成内容。按用户要求限制实验时长，没有无限等待或把部分输出记作成功完成。

Q4的回复里出现“确保机器人处于低电量状态”等语义问题；原文已保存。这是后续效果评判的重要样例，本轮没有因该现象暂停其他实验或执行其返回动作。

## NPU 实际结果

当前公开compiler2.1产物在本板driver0.9.6上encoder op42失败，替换runtime2.1/2.2/2.3.2/2.5均未解决；历史compiler2.3产物也失败。最终采用官方2025-03-19同源compiler2.2.0产物+私有runtime2.2.0，完整ASR通过，系统库与内核未改动。具体模型来源、hash和失败链见research-speech最后一节。

同一官方1.13.8 native CLI、同录音、相同0.8秒尾静音：CPU两线程RTF0.29/0.32、PSS143.0MiB、整组CPU32.27核秒、墙钟21.30秒；NPU一线程RTF0.34/0.37、PSS213.4MiB、CPU7.52核秒、墙钟9.84秒。解码本身没有更快，但NPU组加载更快且节省CPU；CPU混合int8与RKNN浮点部署精度不同，不能视作完全同精度硬件竞速。NPU设备内存可能不完全体现在进程PSS。

Summer旧Eigen后端、当前llama.cpp/GGUF没有RK3566 RKNN直接开关；官方RKLLM支持列表也没有RK3566。因此本轮实际跑通的NPU路径是ASR，不把Summer或Qwen冒充NPU推理。

## 共存与建议

ASR一线程已加载后保持空闲，Summer两线程与Qwen Q8两线程由同一gate触发，真实重叠约12.06秒。整棵树峰值PSS1547.0MiB、主机最小可用848.1MiB、没有采样到swap。Summer同一句从单独RTF0.803变为1.571；Qwen约4.19token/s、TTFT2.75秒。模型能同时驻留不等于并发后仍满足交互速度，优先考虑错开LLM/TTS计算或分句调度，再做真实整链路验证。

可作为后续复测的三档起点：旧能力基线ASR CPU2/Summer2/Q8-2；CPU留量方案ASR NPU/huayan4/Q8-2并错开重计算；内存留量方案ASR NPU/huayan2/Q5或Q4-no-repack-2。后两档整体组合未执行，不能宣称是已验证整机配置。视觉和ROS业务负载尚未纳入，既有完整60工具约5663token压力实验也没有重复。

## 验证与保留边界

超时/子进程回收/结果保留/HTML转义的公开接口测试通过；Ruff格式与检查通过。结果表和图只使用已存事实，同输入图与native/共存表分开。资产、录音、生成输出、转换依赖均在源码外。准备构建、下载、失败诊断与推理矩阵分别保留，未开展四小时穷举或稳定性长测。最终交付记录补充总时长与最后配置数据见下。

补测有效历史真人语音约5.9秒，CPU/NPU均识别为“机器人请让底盘上前移动二十厘米”，仅保存字符串。CPU两线程RTF0.31、PSS131.2MiB、14.44核秒；NPU RTF0.32、PSS212.4MiB、2.82核秒。与官方10秒语音共同说明NPU完整识别路径可用，仍不构成准确率数据集。

Q4关闭repack后的35token同提示配置结果：

| context / batch / microbatch / K,V cache | TTFT s | token/s | PSS MiB | 结束 |
| --- | ---: | ---: | ---: | --- |
| 1024 / 128 / 64 / f16,f16 | 4.80 | 3.61 | 557.3 | EOS,44tokens |
| 1024 / 256 / 128 / f16,f16 | 5.03 | 2.48 | 577.9 | EOS,44tokens |
| 2048 / 256 / 128 / f16,f16 | 6.02 | 3.25 | 691.6 | EOS,44tokens |
| 2048 / 256 / 128 / q8_0,f16 | 5.84 | 2.08 | 616.8 | EOS,58tokens |

此处KV量化节约采样PSS约75MiB，但回复token数/文本改变，不能直接把总请求耗时差全部归因于单token推理。batch与microbatch第一对同时变化，属于配置对照，不是分别证明两个参数的独立因果；少量样本也有频率/缓存和系统调度波动。先保留小batch/context作为短交互起点。

总报告汇集11组、38个配置案例；实际累计案例墙钟 **956.1秒（15.9分钟，含模型加载、超时与失败）**，未含下载、编译、量化准备及非性能功能诊断。首次三基线套件约4分50秒，后续小矩阵与定位失败补测使累计超过原约10分钟目标。未进行四小时持续推理。量化准备两次尝试的失败/完成记录分别在`quantize-01`/`quantize-02`，没有混入推理速度图。
