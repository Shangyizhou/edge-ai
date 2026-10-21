# Qwen / llama.cpp CPU 部署

## 已有模型与程序

模型是旧robot项目的微调Qwen，而非另外下载的基础模型：

- `/home/orangepi/models/qwen3/qwen3-robot-bf16.gguf`
- `/home/orangepi/models/qwen3/qwen3-robot-q8_0.gguf`
- `/home/orangepi/build/llama.cpp-qwen3-22cd/bin/llama-server`
- 同目录`llama-quantize`与`llama-bench`。

已有可执行文件按报告manifest中的实际hash固定；本轮没有重新编译llama.cpp。权重和旧构建目录在源码外，新机器需先取得同源权重和兼容aarch64程序；这里不把文件名当作充分身份验证，也不假称已经验证从空环境重建。

## API 与短矩阵

worker启动本机临时端口的常驻`llama-server`，通过`/completion` SSE调用，保留完整请求、首内容token时间、逐块输出、最终timings/回复与停止原因。旧模板为`Human: ...<|im_end|>\nAssistant:`，不套用新模型chat模板，不执行回复中的函数。

CPU `-ngl 0`、禁用flash attention与warmup、无prompt缓存复用。seed42/temperature0.7/top_p0.8/top_k20/min_p0固定。基线context1024、batch128、microbatch64、f16 K/V cache，测1/2/4线程。

```sh
python3 tools/edge_benchmark/benchmark.py run \
  tools/edge_benchmark/qwen-working-profiles.json \
  .local/runs/qwen-profiles-new
```

## 同源量化与已验证修复

`quantize.json`以旧BF16直接生成Q8_0/Q5_K_M/Q4_K_M，输出位于缓存`assets/qwen3-robot-derived-*.gguf`。实际准备成功记录仍在外置`runs/quantize-02`，准备不算推理耗时。重新生成的Q8与原Q8 SHA-256完全相同：`27dc23f5d549e8e4c11defbafcbb8e405db995ef82e32a3cc2fa0b56b6c5f615`。

当前ARM运行库的Q4默认CPU_REPACK加载发生`stack smashing detected`；固定模型和提示仅加`--no-repack`后完成。可运行配置显式设`"repack": false`，原失败没有改成成功或删除。Q5/Q8无需该绕行方式。更小量化在本机并未更快，见报告中的TTFT、token/s与PSS对照。

BF16短提示TTFT约22.23秒、90秒实验预算内未完整结束，保留部分SSE流，不因超时把输出补成成功。context2048的实验只用正常短提示，不能推断填满长历史后的性能或效果。采样参数固定，没有用少量文本替代正式质量评测。

旧llama.cpp/GGUF没有RK3566 RKNN直接开关，本次Qwen均CPU；未以RKLLM其他芯片支持冒充本板可用。[官方依据、PDF对照和完整研究](../../research/llm.md)。
