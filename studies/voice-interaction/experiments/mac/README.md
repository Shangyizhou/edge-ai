# Mac 模型实验

- [2026-10-22 Qwen3 原生调用与角色未微调基线](2026-10-22-qwen-native-baseline-v1/README.md)：
  官方0.6B / BF16 / MLX-LM Metal，完整/精简system各14条开发样例；真实Registry纯校验，
  无设备执行、训练或板端效果。后续LoRA对照应保持独立测试隔离。

- [最小LoRA与导出闭环](2026-10-22-qwen-lora-export-pilot-v1/README.md)：32微步、合并/F16/Q4和逐制品真实冒烟，保留转换失败。
- [关键工具与人设适配](2026-10-22-qwen-selected9-adaptation-v1/README.md)：300训练/60验证及完整/精简提示，选定v3，最终集封存。
- [合并与同权重量化对照](2026-10-22-qwen-selected-precision-v1/README.md)：adapter/merged原文一致；F16/Q4/Q5/Q8真实对照，区分格式、语义与人设损失。

- [最终跨设备独立集](../final/2026-10-22-qwen-final132-v1/README.md)：Mac与板端各两组132条；原生格式通过，人设保持仅部分达成，完整原始输出与资源单列。
