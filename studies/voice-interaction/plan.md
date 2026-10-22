# 当前推进计划

目标、阶段和结论以[主题首页](README.md)为准；本页只列当前skill流程及下一步。

| 阶段 | 状态 | 证据 / 完成条件 |
| --- | --- | --- |
| 选型与协议 | 已完成本轮资料筛选和初筛设计 | [选型](research/2026-10-22-local-stack/README.md) · [冻结用例](research/2026-10-22-preparation-v2/README.md) |
| 准备与最小推理 | 已实际执行，不只检查下载/加载 | [实际就绪](experiments/rk3566/2026-10-22-preparation-smoke-v1/README.md) |
| 单模块小集 | 已执行，保留失败和质量边界 | [本轮初筛](experiments/rk3566/2026-10-22-voice-screening-v2-r1/README.md) · [3条ASR](experiments/rk3566/2026-10-22-asr-three-samples-v1/README.md) |
| Qwen3业务适配 | 六张工单实现与实测完成；独立原生格式通过，人设部分未达目标 | [集成PR #15](https://github.com/Shangyizhou/edge-ai/pull/15) · [Mac基线](experiments/mac/2026-10-22-qwen-native-baseline-v1/README.md) · [LoRA试点](experiments/mac/2026-10-22-qwen-lora-export-pilot-v1/README.md) |
| 整链路与共跑 | 尚未验收 | [接入边界](integration.md) |

Mac关键工具训练与同权重量化包已实际交付；板端缓存/KV试点、独立最终回归和生命周期HTML已交付；下一轮改善人设需要新数据与新封存集。Agent原生tool_calls、选定Schema、精简SystemPrompt、数据划分与完整样本预算已冻结；推理继续传选定目录。首轮独立验证原生解析、JSON和Schema，模型调通后再改旧项目代码，业务流程后续适配。不要求先覆盖全60工具；部署另测板端等待、CPU和内存。

没有已确认的产品质量、等待和内存门槛。实际动作执行、长期稳定和共跑需独立验收，不能由旧实验或本轮单模块结果代替。
