# 当前推进计划

目标、阶段和结论以[主题首页](README.md)为准；本页只列当前skill流程及下一步。

| 阶段 | 状态 | 证据 / 完成条件 |
| --- | --- | --- |
| 选型与协议 | 已完成本轮资料筛选和初筛设计 | [选型](research/2026-10-22-local-stack/README.md) · [冻结用例](research/2026-10-22-preparation-v2/README.md) |
| 准备与最小推理 | 已实际执行，不只检查下载/加载 | [实际就绪](experiments/rk3566/2026-10-22-preparation-smoke-v1/README.md) |
| 单模块小集 | 已执行，保留失败和质量边界 | [本轮初筛](experiments/rk3566/2026-10-22-voice-screening-v2-r1/README.md) · [3条ASR](experiments/rk3566/2026-10-22-asr-three-samples-v1/README.md) |
| Qwen3业务适配 | 关键工具原生调用规格已发布，ready-for-agent；未训练 | [执行规格 #8](https://github.com/Shangyizhou/edge-ai/issues/8) · [数据、LoRA与量化执行计划](research/2026-10-22-mac-qwen-plan/README.md) |
| 整链路与共跑 | 尚未验收 | [接入边界](integration.md) |

下一交付是关键工具子集的Mac训练包。冻结Agent原生tool_calls、选定Schema、精简SystemPrompt与数据划分，验证完整样本token预算和最小训练步；推理继续传选定目录。首轮独立验证原生解析、JSON和Schema，模型调通后再改旧项目代码，业务流程后续适配。不要求先覆盖全60工具；部署另测板端等待、CPU和内存。

没有已确认的产品质量、等待和内存门槛。实际动作执行、长期稳定和共跑需独立验收，不能由旧实验或本轮单模块结果代替。
