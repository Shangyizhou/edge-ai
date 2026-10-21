# YOLOv6 目标快照

输入固定640×352 RGB、30fps。

[实测结论](results.md) · [静态报告](report.html) · [完整指标](summary.json) · [准备来源](preparation/preparation.json)

根目录11个目标配置；diagnostics/input-matrix另存24个旧输入诊断配置，未混入目标结论。权重、图片、音频与构建产物在外置缓存。

```sh
python3 tools/edge_benchmark/benchmark.py report studies/object-detection/experiments/rk3566/2026-10-21-yolo
```
