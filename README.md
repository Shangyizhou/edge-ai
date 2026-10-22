# edge-ai · 当前 skill 流程

当前只展示2026-10-22按 `edge-model-selection`、`edge-model-prepare` 重新开展的机器人本地语音研究。旧语音、YOLO、量化/共跑实验及旧看板资料已[移至仓库外归档](archives/README.md)，不参与当前结论。

| 阶段 | 当前状态 | 入口 |
| --- | --- | --- |
| 选型 | 基于当前RK3566配置与官方资料重新筛选 | [候选与来源](studies/voice-interaction/research/2026-10-22-local-stack/README.md) |
| 准备 | 模型、运行库、输入冻结；最小真实推理通过 | [准备证据](studies/voice-interaction/experiments/rk3566/2026-10-22-preparation-smoke-v1/README.md) |
| 单模块验证 | ASR、LLM、TTS本轮记录保留；ASR补齐3条有声材料 | [当前结论](studies/voice-interaction/README.md) · [实验索引](studies/voice-interaction/experiments/rk3566/README.md) |
| 业务适配 | 原生tool_calls尚未验证；计划Qwen3业务LoRA | [当前方案与Mac配置](studies/voice-interaction/research/2026-10-22-qwen-adaptation/README.md) |
| 训练与整链路 | 尚未训练、整链路与共跑尚未验收 | [接入边界](studies/voice-interaction/integration.md) |

训练规划：MacBook Air M5 / 16GB统一内存 / 约70GB可用空间，由用户提供，尚未直接检查环境。计划先在Mac做Qwen3-0.6B LoRA/QLoRA小规模验证，板子负责推理验收；工具目录继续传递，不迁移整套ROS工作区。

## 阅读和工具

[主题首页](studies/voice-interaction/README.md) · [准备与推进](studies/voice-interaction/plan.md) · [模型与证据](studies/voice-interaction/models.md) · [研究方法](docs/methodology/README.md)。

网站由当前Markdown和本轮证据生成，构建说明见[网站工具](tools/research_site/README.md)。本地整理不会自动更新线上Pages；发布仍需单独提交、推送。

新测量另建实验，保留配置、日志、清单、哈希和源码快照；模型、音频、SDK、凭据和构建产物留在仓库外。实际生产实现维护在ros-robot，本站快照只作证据。归档没有删除模型或本轮仍在引用的外部素材。

工作与规格记录在[GitHub Issues](https://github.com/Shangyizhou/edge-ai/issues/7)。代理约定见[AGENTS.md](AGENTS.md)，术语见[GLOSSARY.md](GLOSSARY.md)。
