# 当前部署与训练交接

生产ROS源码继续在板子的ros-robot工作区维护，Mac建立独立训练目录，无需迁移整套ROS工程。

```text
qwen3-robot-training/
├── contracts/   # 当前工具Schema、业务规则和来源commit/hash
├── data/        # 训练、验证、独立测试集
├── configs/     # 训练与导出配置
├── scripts/     # 训练、评估、转换
└── outputs/     # 权重与适配器，不进Git
```

Mac配置由用户提供：MacBook Air M5、16GB统一内存、约70GB空闲。计划先验证MLX-LM与Qwen3-0.6B小规模LoRA/QLoRA；完整工具样本的token、内存、速度和磁盘需求需短跑测量，不能靠截断工具目录降低负载。目前没有训练包、训练任务或GPU租借。

训练目标是当前ros-robot原生tool_calls与独立业务函数，不使用旧模型fc/res字符串契约。工具目录继续在推理时提供；程序保持整批参数校验、顺序执行和真实回执。

本轮可用部署资产身份与命令见[运行准备](research/2026-10-22-runtime-preparation/README.md)及[最小真实推理](experiments/rk3566/2026-10-22-preparation-smoke-v1/README.md)。模型和音频留在仓库外，归档操作没有移动仍被本轮使用的资源。新组合未经验证不能直接替换生产配置。

[当前推进](plan.md) · [训练方案](research/2026-10-22-qwen-adaptation/README.md)。
