# 当前机器人接入边界

本轮已实际完成 Qwen3-0.6B 的数据冻结、Mac LoRA训练、合并/GGUF转换、同权重量化验证，以及未训练/微调Q4在Mac与RK3566的完整独立回归。已测边界止于 **原生回复 → JSON/Schema → Registry整批纯校验**，没有进入执行器、设备handler或ROS动作。完整语音交互、视觉共跑和长期稳定仍未验收。

```text
Mac：冻结训练/验证数据 → LoRA → 合并 → F16 GGUF → Q4/Q5/Q8验证
                                                     ↓ 预选Q4
Mac / RK3566：冻结132输入 → 实际模型推理 → 原生tool_calls解析
                                      → 严格参数JSON / 当前Schema
                                      → ActionRegistry整批纯校验【本轮止于此】
```

[最终生命周期报告](experiments/final/2026-10-22-qwen-final132-v1/report.html)保留四组共528次最终请求，原120与补充12多调用分别统计。微调Q4在两平台的84个期望工具请求均通过原生/JSON/Schema/Registry；完整计划语义分别73/84、72/84。角色上下文审核均21/36，各有10条角色请求误调用工具，普通聊天均12/12无调用。工具格式试点通过不能替代人设、业务动作或完整产品接受；最终失败不用于本轮重新训练、改提示或更换精度。

生产实现继续由板端 `/home/orangepi/code/ros-robot` 维护。本仓库的来源为已冻结的`23ef814cfb0a8c174b42b288454c30d5498e88d0`源码/Schema快照；实验快照是证据，不是新的生产实现。没有修改旧C++/fc-res路径，也没有放宽现有JSON/Schema/整批拒绝边界。

后续接入仍需提供本轮9工具目录与实际Schema、精简路由system、用户输入和必要会话；权限、设备状态和执行回执继续由应用动态提供。固定角色事实不能代替当前设备知识，模型调用不等于执行成功。原生调用的数量、顺序、重复和转义必须保留，普通content里的JSON不能冒充调用。

生产Provider/Executor适配、业务否定与澄清、执行前置条件、真实回执和失败恢复属于后续应用工作，不升级为本轮原生格式试点的前置门槛。下一轮角色与语义改进需要新的开发来源和新的独立封存集；之后再分别验证模拟接入、ASR→LLM→TTS→播放/恢复监听，以及ROS/视觉共跑和资源竞争。本轮不授权真实运动。

[复现与五技能交接](experiments/final/2026-10-22-qwen-final132-v1/reproduce.md) · [后续原生接入契约](experiments/final/2026-10-22-qwen-final132-v1/integration-contract.md) · [质量门槛与资源阈值来源](experiments/final/2026-10-22-qwen-final132-v1/gates.json) · [当前推进计划](plan.md)。本轮未发布Pages；新Qwen实验默认不进入静态导出，公开发布需单独操作。
