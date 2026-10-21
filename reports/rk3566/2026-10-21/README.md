# RK3566 · 2026-10-21 冻结结果

[结论](results.md) · [静态报告](report.html) · [迁移来源](migration-provenance.json)

11组38配置，累计案例墙钟956.1秒。JSON/JSONL/log保留原始数值、输入/输出文本、配置和资源；来源manifest与逐文件hash用于追溯。`notes.json`是人工解释，独立于原始结果。

为避免上传录音、合成音频和大资产，快照省略WAV/PCM并重新生成HTML，不包含播放控件。完整原件在本机外置`/home/orangepi/.cache/ros-robot-edge-benchmark/runs/comparison-20261021`，音频和权重没有删除。

```sh
python3 tools/edge_benchmark/benchmark.py report reports/rk3566/2026-10-21
```

必须在仓库根目录执行。重建页面不重跑模型、不修改历史JSON。原始测量时使用的代码hash与当前迁移提交不同，来源hash仍保留，不为匹配新路径而重写。各配置顶层id保持原样，包括早期失败、预算截断和后续修复对照。
