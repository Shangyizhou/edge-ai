# 当前skill流程实验索引

只列重新选型后实际新增的实验。原HTML、JSON、日志、配置、清单、哈希和测量源码保持原样；旧批次在[仓库外归档](../../../../archives/README.md)。

| 实验 | 回答什么 | 入口 |
| --- | --- | --- |
| 2026-10-22-preparation-smoke-v1 | 三模块是否实际完成最小推理 | [说明](2026-10-22-preparation-smoke-v1/README.md) · [就绪HTML](2026-10-22-preparation-smoke-v1/readiness/report.html) |
| 2026-10-22-voice-screening-v2-r1 | 一轮单模块性能、资源和固定小集输出 | [说明](2026-10-22-voice-screening-v2-r1/README.md) · [HTML](2026-10-22-voice-screening-v2-r1/report.html) · [JSON](2026-10-22-voice-screening-v2-r1/results.json) |
| 2026-10-22-asr-three-samples-v1 | 同3段有声材料、INT8/FP32与实时/吞吐对照 | [说明](2026-10-22-asr-three-samples-v1/README.md) · [JSON](2026-10-22-asr-three-samples-v1/results.json) |
| 2026-10-22-qwen-business-fit-v1 | ros-robot的fc/res兼容路径诊断，0/3；不代表当前原生tool_calls效果 | [原记录与边界](2026-10-22-qwen-business-fit-v1/README.md) · [分层复核](2026-10-22-qwen-business-fit-v1/assessment.json) |

| 2026-10-22-qwen-pilot32-board-v1 | 试点Q4原生推理、f16/q8 KV与前缀缓存，23次开发执行；不代表最终权重效果 | [说明](2026-10-22-qwen-pilot32-board-v1/README.md) · [离线HTML](2026-10-22-qwen-pilot32-board-v1/report.html) |

原生试点和[Mac完整微调/量化](../mac/README.md)已实际执行，当前进入独立最终回归。不同样本子集和计时口径不能拼成统一排名。
