# RK3566 首选语音模型：补齐最小真实推理

日期：2026-10-22（Asia/Shanghai）。调用 `edge-model-prepare`，承接此前资产、运行库与加载检查。本轮是新的板端最小功能实验，不采用旧本地测速或识别结果作选型依据。

## 结论

**三个基线候选均为READY_FOR_BENCHMARK。** 资产、运行库、最小真实推理与配置交接四个准备门均有证据；产品验收为NOT_EVALUATED。这次只补完整准备阶段，不是单模块初筛、三轮复测或完整交互验收。

[就绪HTML](readiness/report.html) · [就绪JSON](readiness/readiness.json) · [请求](request.json) · [逐门检查](checks.json) · [运行manifest](manifest.json) · [文件哈希](artifact-hashes.json)

| 部署 | 本轮输入及实际输出 | 最小检查范围 |
| --- | --- | --- |
| ASR zh14M混合INT8 | 固定FLEURS普通话非静音音频，输出“高特四零三路公交汽车定期发车前往心特拉在罗凯角停靠” | [原始转写](asr-smoke/asr-output.json)、[检查记录](asr-smoke/inference-record.json)；能解码并生成中文，不宣称CER达标 |
| ASR同包FP32对照 | 同一固定音频，实际输出保留在[原始转写](asr-fp32-smoke/asr-output.json) | [检查记录](asr-fp32-smoke/inference-record.json)；覆盖原测试配置使用的第二种精度，不作后端或速度对比 |
| Qwen2.5-0.5B-Instruct Q4_K_M | “请只回复：你好。” → “你好。”，实际生成3 token | [完整请求](llm-smoke/request.json)、[完整响应](llm-smoke/response.json)、[检查记录](llm-smoke/inference-record.json) |
| Melo zh_en FP32 | “你好，我是机器人。” → 68842个44.1kHz样本，约1.56秒音频 | [检查记录](tts-smoke/inference-record.json)；有限、非零且PCM16 WAV可读，未播放或听感验收 |

ASR参考句含“Scotturb 403”“辛特拉”“罗卡角”，当前输出存在专名、数字形式等差异；这些需要正式小集质量检查，不能由非空转写推导准确率合格。两种精度均只识别一个样本。

## 冻结与执行边界

复用已核验的现成资产和运行程序，没有下载、编译或切换模型/后端。CPU2线程，sherpa-onnx1.13.8/实际ORT1.28.2；LLM为独立llama.cpp b6500 CPU，context2048，KV f16，greedy。配置和运行库身份见[资产](assets-manifest.json)、[运行库](runtime-manifest.json)及本轮[112文件检查](preflight.json)。

ASR按100ms块快速送入、尾静音3.2s、EOF完成，不等待真实语音节奏，不验证端点重置、连续监听或实时性。LLM只有一个completion请求，无隐式预热，16个新token上限；继承配置中screening的96-token字段并未用于本轮，实际请求以request.json和smoke.py为准。TTS整句返回后写PCM/WAV，不验证首块增量或扬声器首音。

初始[计划](plan.json)为三模块各一个样例、进程级各180s、合计540s预算；为原配置的FP32对照在执行前增加了[独立补充计划](control-plan.json)，额外上限180s，全部总上限720s。顺序执行，无重复/预热，无性能采样比较。外层复用进程树采样和600MiB MemAvailable保护，退出/超时保留原始事实。result.json中的wall时间包括Python、运行库、模型加载和输入输出；不是纯推理时延或用户交互等待，不在本报告排名。

每个目录保留实际命令、配置、输入身份、stdout/stderr、结果与资源记录；[测量源码快照](measurement-source/smoke.py)及调用编排一并保留。输入录音、模型和生成PCM/WAV均在Git外；[音频位置与哈希](tts-smoke/external-media.json)可用于本机查看，未复制音频入仓库。

## 下一步

将readiness.json中的benchmark_handoff交给正式单模块筛选：ASR INT8/FP32同源对照与质量小集、LLM6条任务、TTS4条文本；固定计时边界与分阶段资源采样。入围后再做三轮复测，之后才进入ROS/YOLO共跑。此轮没有更改原始历史报告或个人skill里的历史LOADED_ONLY示例；它们仍代表各自当时的证据。
