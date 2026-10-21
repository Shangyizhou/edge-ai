# RK3566语音实验索引

想看当前建议，从[主题首页](../../README.md)开始；想理解数据如何影响选择，看[单模型对比](../../models.md)或[机器人验证](../../integration.md)。本页只按实验批次找原始证据。

按实验目的阅读；同日各批次的计时口径不同，不能直接把数值拼成统一排名。

| 实验 | 解决的问题 | 结果入口 |
| --- | --- | --- |
| 2026-10-21-asr-int8-ptq | 同源PTQ能否构建、上板和保持识别输出；部分成功、质量未通过 | [结论](2026-10-21-asr-int8-ptq/results.md) · [静态页](2026-10-21-asr-int8-ptq/report.html) |
| 2026-10-21-asr-lite-v1 | 统一SOP、6条小输入、CPU/NPU资源及三轮吞吐/实时复测 | [结论](2026-10-21-asr-lite-v1/results.md) · [新协议图表](2026-10-21-asr-lite-v1/evaluation/report.html) |
| 2026-10-21-baseline | ASR/TTS/Qwen路线、线程、量化与共存对照 | [结论](2026-10-21-baseline/results.md) · [图表](2026-10-21-baseline/report.html) |
| 2026-10-21-streaming-asr | 常驻模型、实时供音、端点扫描和YOLO共跑 | [结论](2026-10-21-streaming-asr/results.md) · [图表](2026-10-21-streaming-asr/report.html) |
| 2026-10-21-ros-asr | 生产C++ ROS节点NPU接入、流控制与实际YOLO共跑 | [结论](2026-10-21-ros-asr/results.md) |

目录内保留原始结果、日志、配置、manifest和测量时源码身份，失败记录同样保留。首次基线包含多个模型，整体迁移以保持原始实验关系。本轮未把案例重新拆入raw子目录，原有HTML相对链接和数据布局保持有效。

视觉主导的CPU/NPU和共跑对照见[目标检测实验](../../../object-detection/experiments/rk3566/README.md)。
