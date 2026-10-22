# 当前模型与证据

只展示本次skill重选后的方案，旧模型与历史数据见[归档说明](../../archives/README.md)。

| 模块 | 当前模型 / 精度 | 框架与后端 | 证据与判断 |
| --- | --- | --- | --- |
| ASR | Streaming Zipformer zh14M，混合INT8；同源FP32对照 | sherpa-onnx1.13.8 / ONNX Runtime1.28.2，CPU Execution Provider | [3条有声材料对照](experiments/rk3566/2026-10-22-asr-three-samples-v1/README.md)：指令用户确认；同时查看公开语音的实际转写及CER，不只看速度 |
| LLM初筛 | 官方Qwen2.5-0.5B-Instruct Q4_K_M GGUF | llama.cpp b6500 / GGML CPU，OpenMP | [通用初筛](experiments/rk3566/2026-10-22-voice-screening-v2-r1/README.md)；[fc/res兼容路径诊断](experiments/rk3566/2026-10-22-qwen-business-fit-v1/README.md)未通过，不能代表原生tool_calls |
| LLM原生试点 | 官方Qwen3-0.6B，596049920唯一参数；选定LoRA→Q4_K_M，396704704bytes | Mac MLX-LM0.32.2/Metal训练；llama.cpp e3797b1，Mac Metal和板端ARM CPU | [微调验证](experiments/mac/2026-10-22-qwen-selected9-adaptation-v1/README.md) · [同权重量化](experiments/mac/2026-10-22-qwen-selected-precision-v1/README.md)；Q4验证工具格式36/36、人设审核18/18、工具精确30/36。板端[最小试点](experiments/rk3566/2026-10-22-qwen-pilot32-board-v1/README.md)已执行；最终权重独立回归待完成 |
| TTS | MeloTTS zh_en FP32 ONNX | sherpa-onnx1.13.8 / ONNX Runtime1.28.2，CPU Execution Provider | [本轮4文本](experiments/rk3566/2026-10-22-voice-screening-v2-r1/README.md)：音频有效但整句等待长，尚未试听评审 |

ASR混合INT8的decoder仍是FP32；文件精度不能等同整个执行图精度。FP16本轮未准备、未测试，不填估计值。

## 怎样比较

同模型不同精度要固定输入、运行库、参数及场景；吞吐和实时送入分开。显示实际输入/输出、速度、质量检查、CPU容量占比、PSS MiB与实际内存比例；结论同时引用资源。更换模型/训练/精度后是部署方案对照，不能把差异单独归因某一种因素。

每模块轻量展示3条有意义用例，额外材料保留证据；样本数、进程轮次、资源窗口和是否试听要明确。当前各轮原始记录及哈希不变。
