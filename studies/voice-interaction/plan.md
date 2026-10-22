# 当前推进计划

目标、阶段和结论以[主题首页](README.md)为准；本页只列当前skill流程及下一步。

| 阶段 | 状态 | 证据 / 完成条件 |
| --- | --- | --- |
| 选型与协议 | 已完成本轮资料筛选和初筛设计 | [选型](research/2026-10-22-local-stack/README.md) · [冻结用例](research/2026-10-22-preparation-v2/README.md) |
| 准备与最小推理 | 已实际执行，不只检查下载/加载 | [实际就绪](experiments/rk3566/2026-10-22-preparation-smoke-v1/README.md) |
| 单模块小集 | 已执行，保留失败和质量边界 | [本轮初筛](experiments/rk3566/2026-10-22-voice-screening-v2-r1/README.md) · [3条ASR](experiments/rk3566/2026-10-22-asr-three-samples-v1/README.md) |
| Qwen3业务适配 | 方案已讨论，未训练 | [原生工具LoRA与Mac规划](research/2026-10-22-qwen-adaptation/README.md) |
| 整链路与共跑 | 尚未验收 | [接入边界](integration.md) |

下一交付是Mac训练包，不迁移板子ROS工作区。先冻结当前ros-robot原生tool_calls、工具Schema与数据划分，再验证Mac训练环境、完整样本token预算和最小训练步；工具目录继续传递。训练后分别比较业务正确率、输入长度、板端等待、CPU和内存，不只看训练loss。

没有已确认的产品质量、等待和内存门槛。实际动作执行、长期稳定和共跑需独立验收，不能由旧实验或本轮单模块结果代替。
