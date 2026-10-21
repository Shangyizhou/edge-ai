# 目标检测模型调研与性能测试

当前覆盖RK3566上ros-robot YOLOv6的CPU候选/NPU对照，输入为上游缩放后的640×352、目标30fps，以及与ASR共享NPU时的表现。

| 想了解什么 | 阅读入口 |
| --- | --- |
| 性能、丢帧、CPU对照和ASR竞争 | [实验结论](experiments/rk3566/2026-10-21-yolo/results.md) · [图表](experiments/rk3566/2026-10-21-yolo/report.html) |
| 参数、模型来源与runtime兼容 | [YOLO调研](research/yolo.md) |
| 如何部署和复测 | [RK3566部署](platforms/rk3566/deployment.md) |
| 实验归档 | [实验索引](experiments/rk3566/README.md) |

后续生产ROS ASR与YOLO同步回放的原始证据由[语音交互主题](../voice-interaction/experiments/rk3566/2026-10-21-ros-asr/results.md)保存。共用工具见[benchmark说明](../../tools/edge_benchmark/README.md)。
