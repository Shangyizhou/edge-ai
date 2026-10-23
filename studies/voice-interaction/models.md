# 当前模型与证据

只展示本次skill重选后的方案，旧模型与历史数据见[归档说明](../../archives/README.md)。

| 模块 | 当前模型 / 精度 | 框架与后端 | 证据与判断 |
| --- | --- | --- | --- |
| ASR | Streaming Zipformer zh14M，混合INT8；同源FP32对照 | sherpa-onnx1.13.8 / ONNX Runtime1.28.2，CPU Execution Provider | [3条有声材料对照](experiments/rk3566/2026-10-22-asr-three-samples-v1/README.md)：指令用户确认；同时查看公开语音的实际转写及CER，不只看速度 |
| LLM初筛 | 官方Qwen2.5-0.5B-Instruct Q4_K_M GGUF | llama.cpp b6500 / GGML CPU，OpenMP | [通用初筛](experiments/rk3566/2026-10-22-voice-screening-v2-r1/README.md)；[fc/res兼容路径诊断](experiments/rk3566/2026-10-22-qwen-business-fit-v1/README.md)未通过，不能代表原生tool_calls |
| LLM原生试点 | 官方Qwen3-0.6B，596049920唯一参数；选定LoRA→Q4_K_M，396704704bytes | Mac MLX-LM0.32.2/Metal训练；llama.cpp e3797b1，Mac Metal和板端ARM CPU | [微调验证](experiments/mac/2026-10-22-qwen-selected9-adaptation-v1/README.md) · [同权重量化](experiments/mac/2026-10-22-qwen-selected-precision-v1/README.md)；验证之外，[最终独立集](experiments/final/2026-10-22-qwen-final132-v1/README.md)Mac/板端各84/84工具格式通过、人设21/36；板端PSS600.30MiB、CPU46.04%四核容量，工具精确72/84。仅独立格式试点，角色内化及生产/共跑未验收 |
| TTS | MeloTTS zh_en FP32 ONNX | sherpa-onnx1.13.8 / ONNX Runtime1.28.2，CPU Execution Provider | [本轮4文本](experiments/rk3566/2026-10-22-voice-screening-v2-r1/README.md)：音频有效但整句等待长，尚未试听评审 |

ASR混合INT8的decoder仍是FP32；文件精度不能等同整个执行图精度。FP16本轮未准备、未测试，不填估计值。

## 怎样比较

同模型不同精度要固定输入、运行库、参数及场景；吞吐和实时送入分开。显示实际输入/输出、速度、质量检查、CPU容量占比、PSS MiB与实际内存比例；结论同时引用资源。更换模型/训练/精度后是部署方案对照，不能把差异单独归因某一种因素。

每模块轻量展示3条有意义用例，额外材料保留证据；样本数、进程轮次、资源窗口和是否试听要明确。当前各轮原始记录及哈希不变。


## 已上传的选定模型制品

正式768微步版本的MLX adapter和对应Q4已存入 [Hugging Face模型仓库](https://huggingface.co/Shangyizhou/xiaomo-qwen3-0.6b/tree/0bd09b627bb133b8a9f5a71cfeb8225a421d33ba)，固定文件URL与SHA256见 [发布清单](releases/selected9-768-v3.json)。仓库为Private；下载需要有权限的HF账号。基座从官方固定版本取回，Q4已经包含微调效果，无需叠加adapter。

```sh
hf auth login
hf download Shangyizhou/xiaomo-qwen3-0.6b \
  adapter/adapters.safetensors adapter/adapter_config.json \
  --revision 0bd09b627bb133b8a9f5a71cfeb8225a421d33ba --local-dir ./xiaomo-model
# 只部署Q4时，改为下载这一文件
hf download Shangyizhou/xiaomo-qwen3-0.6b \
  gguf/xiaomo-qwen3-0.6b-Q4_K_M.gguf \
  --revision 0bd09b627bb133b8a9f5a71cfeb8225a421d33ba --local-dir ./xiaomo-model
```

adapter为MLX原生格式；重新训练还需要实际数据及项目非思考模板/掩码预检，原配置内未使用的WikiSQL默认字段不是本轮训练来源。权重恢复不包含优化器状态。32微步工作流试跑权重未混入这个选定版本。
