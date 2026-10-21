# 语音交互模型调研与性能测试

研究在RK3566上组合ASR、TTS和本地LLM的可行性、性能与部署方法。现有材料覆盖模型对照、流式识别和生产ROS ASR接入；完整四进程与声卡体验尚未验收。

| 想了解什么 | 阅读入口 |
| --- | --- |
| ASR、TTS、Qwen首轮性能和限制 | [基线结果](experiments/rk3566/2026-10-21-baseline/results.md) |
| 常驻ASR、端点参数、实时输入与YOLO竞争 | [流式ASR结果](experiments/rk3566/2026-10-21-streaming-asr/results.md) |
| 生产ROS ASR的NPU接入、暂停恢复和共跑 | [ROS节点验证](experiments/rk3566/2026-10-21-ros-asr/results.md) |
| 实验顺序和各轮作用 | [实验索引](experiments/rk3566/README.md) |
| 怎样部署和复测 | [RK3566入口](platforms/rk3566/README.md) |
| 选型依据和测试口径 | [调研索引](research/README.md) |
| 原始任务与讨论 | [范围](history/2026-10-21/spec.md) · [问题记录](history/2026-10-21/questions.md) |

最近结果优先看ROS节点验证；各轮报告只代表其注明的模型、设备和测量条件。连续流后段文字变化仍保留为限制，不能将新流样本一致性解释成准确率。

YOLO独立性能和部署归入[目标检测主题](../object-detection/README.md)。语音主题保留ASR主导的共跑实验，目标检测主题保留视觉主导的对照，证据不重复复制。共用工具见[benchmark说明](../../tools/edge_benchmark/README.md)。
