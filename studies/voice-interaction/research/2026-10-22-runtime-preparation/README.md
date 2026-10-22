# 首选模型与测试运行环境准备

日期：2026-10-22。本轮承接[第1步协议](../2026-10-22-preparation-v2/README.md)，只准备资产、运行库和执行配置，并检查模型加载；不做正式单模块筛选、三轮复测或交互验收。

当前状态：**READY_FOR_SCREENING**。ASR INT8/FP32、Melo模型构造及Qwen健康接口加载检查通过；18项工具测试通过。最终资产/运行库哈希和三份配置检查通过，详见[就绪报告](readiness.html)。这仅表示可开始初筛，不是推理性能或交互验收。

## 交付

| 模块 | 固定部署组合 | 准备检查 |
| --- | --- | --- |
| ASR | Zipformer中文14M，官方revision `204ad334e2e683fd295359930cc16fc0432a23ac`，CPU混合INT8及FP32 | 5个权重文件及tokens已补齐；LFS SHA256已核对；两套模型构造成功 |
| LLM | Qwen2.5-0.5B-Instruct官方Q4_K_M，revision `9217f5db79a29953eb74d5343926648285ec7e67` | 权重SHA256匹配发布值；独立编译llama.cpp b6500 CPU |
| TTS | Melo zh_en官方转换revision `a0d5c6a264c0ef92d70d8661d8cc502d79627cd6`，CPU FP32 | 复用现有模型/词典/FST，逐项比对上游LFS SHA256或Git blob；模型构造成功 |

权重位于 `/home/orangepi/models/edge-voice-v2/`；Melo保持原外置路径。没有替换私有Qwen、旧bilingual模型或系统NPU库。未补下载备选模型。

[资产清单](assets-manifest.json)记录URL/revision/路径/hash。许可依据：Qwen与ASR发布者模型卡Apache-2.0，Melo上游模型卡MIT；Melo已有MIT文本。部分模型仓未单独提供LICENSE文件，保留模型卡及来源，不把代码许可自动当权重许可。

## 实际环境

ASR/TTS复用已核验的外置Python环境 `/home/orangepi/venvs/sherpa-onnx`，sherpa-onnx1.13.8，实际加载ORT1.28.2；不依据pip列表猜测加载库。[加载检查](sherpa-load-check.json)保留成功构造范围与库hash，未调用识别解码或TTS生成。

LLM源码为llama.cpp b6500 commit `a7a98e0fffed794396b3fbad4dcdbbc184963645`；CPU `armv8-a`、OpenMP、Release、GPU层0。归档构建的version字符串可能没有Git标识，以下载归档hash、固定commit、编译配置和最终binary hash共同确定身份。运行库与构建信息见`runtime-manifest.json`，最终就绪状态以`readiness.json`为准。

## 可执行配置与命令

三个配置均由现有 `benchmark.py run` 入口执行，不再是纯设计JSON。ASR首轮含INT8/FP32 × 非实时/实时四组，固定3条素材；LLM6条任务，TTS4条文本。输入资产hash清单见[asr-fixtures.json](asr-fixtures.json)，文本及判定rubric沿用上一轮`text-fixtures.json`。

先在仓库根目录做检查：

```bash
python3 tools/edge_benchmark/voice_preflight.py \
  studies/voice-interaction/research/2026-10-22-runtime-preparation
```

检查通过后，以下为**后续正式初筛命令，此次未执行**。OUTPUT必须为新目录，JSON配置里的资产路径绑定当前板子。

```bash
python3 tools/edge_benchmark/benchmark.py run \
  studies/voice-interaction/research/2026-10-22-runtime-preparation/asr-screening.json \
  /home/orangepi/.cache/edge-voice-v2/runs/asr-screening-01
python3 tools/edge_benchmark/benchmark.py run \
  studies/voice-interaction/research/2026-10-22-runtime-preparation/llm-screening.json \
  /home/orangepi/.cache/edge-voice-v2/runs/llm-screening-01
python3 tools/edge_benchmark/benchmark.py run \
  studies/voice-interaction/research/2026-10-22-runtime-preparation/tts-screening.json \
  /home/orangepi/.cache/edge-voice-v2/runs/tts-screening-01
```

各模块预算600s，三模块串行上限合计1800s；ASR子组90s。LLM/TTS多文本共用常驻进程，单输入设90s截止，模块进程另有600s硬预算。Python信号在原生调用返回Python后处理，非流式TTS原生阻塞仍由模块硬预算兜底，不能声称90s原生抢占。MemAvailable低于600MiB停止本轮拥有的进程组。

## 适配与指标边界

- 新ASR适配器显式接收encoder/decoder/joiner路径，支持FP32对照；100ms绝对时间回放，不重置落后时钟，尾静音3.2s，记录partial、endpoint及EOF强制结果。旧模型共识转写已排除。
- LLM使用Qwen2.5的无工具ChatML格式（固定system/user/assistant头），greedy、固定上下文、无prompt复用；记录首非空content和首个中文句末标点闭合的可播短句。
- Melo使用完整句generate返回，首PCM明确是整句返回并转PCM16后的边界，不宣称真正增量合成；生成WAV仅用于离线听检，不播放。
- 三者分别记录加载、首请求、预热、3秒待机、推理阶段。资源每200ms采样进程树PSS/RSS及CPU；原始日志、JSON事件和资源事实独立保留。

现有通用HTML报告只提供基础查看；ASR适配器另外生成quality.json逐条及加权CER（仅独立参考）；LLM rubric和TTS听检需在正式初筛后补充，不把正常退出当质量通过。LLM原生token时序来自完整SSE trace，不能把HTTP块数当token数。当前没有新的速度/内存性能结论，完整语音交互仍为INSUFFICIENT_EVIDENCE。

## 清理与保留

按用户授权清理了pip可重新下载的HTTP缓存、uv不可达缓存；本轮构建完成后仅保留运行所需产物及可复现清单，移除临时压缩包和编译中间文件。具体释放量见`cleanup.json`。历史实验日志、原始记录、旧项目生产源及私有权重不删除。
