# Qwen业务适配：是否微调与旧模型身份核对

日期：2026-10-22。针对[业务调用实验](../../experiments/rk3566/2026-10-22-qwen-business-fit-v1/README.md)的后续解释。本次仅源码、GGUF元数据与官方文档核查，没有新推理、训练或硬件动作。

## 当前目标：以ros-robot原生业务工具协议为准

用户澄清：目标是当前ros-robot的原生 `tool_calls` 和独立业务函数Schema，不采用为旧模型保留的 `fc/res` 字符串兼容路径。上一轮3条失败只覆盖后者，不能作为当前原生工具协议0/3失败的证据。尚未分离模型、提示、协议和量化因素。

方向是评估官方Qwen3的业务SFT/LoRA：把固定业务映射、调用格式、否定、缺参澄清、顺序及动作边界学入权重，从而研究缩短system prompt和工具描述的效果。以项目ActionRegistry导出的Schema及Pydantic输入模型为数据权威，保持原生调用、整批校验、串行执行及回执语义，不恢复旧fc/res协议。

建议用同一Qwen3基座、同一量化和运行时，比较“未微调/LoRA × 完整/精简提示”四个组合。先用小组核心业务做验证，再扩大覆盖；3条例子仅是冒烟，独立测试材料不得进入训练。

训练数据可用原生assistant tool_calls和tools声明表达，由Qwen3正式工具模板序列化。模型生成的工具标记、服务端解析为API tool_calls、项目Registry参数绑定是不同层次；不能只训练整段HTTP响应JSON就假定现有传输适配完成。

用户随后确认：**推理时继续传递工具目录**。当前优化目标是内化固定业务行为、减少冗长system说明和重复调用示例，保留与项目一致的工具Schema及程序校验，不以完全省略工具目录为目标。现有Provider在tools为空时会设置tool_choice=none，这也说明模型输入优化与工具启用配置需要区分。

新工具、参数变更、当次权限、设备当前状态和执行是否成功不会由固定训练自动获得。业务正确率、prompt token减少和RK3566等待/资源收益均单独测量；微调不等同于速度优化。本轮没有执行训练、模型下载、原生推理或生产修改。

## 旧离线模型身份（直接读取本机GGUF）

文件 `/home/orangepi/models/qwen3/qwen3-robot-q8_0.gguf`：

- `general.architecture = qwen3`
- `general.name = Qwen3 Lora Merge`
- `general.finetune = lora-merge`
- `general.size_label = 596M`，与项目Qwen3-0.6B记录相符。
- 文件为Q8_0部署版本；另有BF16文件。元数据标记LoRA合并，不代替训练数据、日志或当前60工具覆盖率的验证。

当前对比文件是官方 `qwen2.5-0.5b-instruct-q4_k_m.gguf`，不是该业务权重。这里讨论旧项目的本地离线路径；旧云端LLMAgent另有qwen-plus默认值。没有采用历史速度/质量记录作为本轮模型推荐依据。

## 官方资料

- [Qwen2.5 function calling](https://qwen.readthedocs.io/en/v2.5/framework/function_call.html)：工具调用依赖对应的提示/工具模板；ChatML消息外壳与具体工具协议要区分。
- [Qwen3 function calling](https://github.com/QwenLM/Qwen3/blob/main/docs/source/framework/function_call.md)：官方工具调用集成说明，不保证项目旧微调模型或0.6B当前业务质量。
- [TRL SFT：工具调用训练](https://huggingface.co/docs/trl/sft_trainer#tool-calling-with-sft)：训练样例包括会话、工具调用/返回及工具Schema；支持SFT并不保证训练后的业务质量。

项目身份来源另见 `/home/orangepi/code/ros-robot/docs/offline-qwen-edge-validation-roadmap.md` 的模型归档与模板记录。

## LoRA用途和训练设备

LoRA冻结原有权重，只训练少量低秩更新，降低相对全量微调的训练参数、存储和内存需求。业务适配收益仍依赖训练数据；可维护不同任务的adapter，合并后再转换量化部署，合并不会增加原模型层数。它不保证通用推理提升或自动缩短同等输入的推理等待。

这里的基线只指同一Qwen3微调前的一次对照成绩，允许很低，不要求ros-robot原先已有好用模型，也不要求反复进行无收益的提示调参。

当前RK3566标称4GB、实际MemTotal约3.83GiB，不作为此次实用LoRA训练环境，负责部署与回归。训练可在有足够资源的开发机/Apple Silicon Mac（MLX路线）或租用GPU上完成；用户报告MacBook Air M5、16GB统一内存、约70GB可用存储；尚未直接检查Mac环境。建议以MLX-LM和Qwen3-0.6B开始本地LoRA/QLoRA小规模试跑，先不租GPU；这是可行性规划，不是已通过的训练测量。MLX-LM当前源码含Qwen3实现，LoRA文档支持训练与量化适配。GPU租用规格需根据基座、样本序列长度、batch与LoRA/量化设置估算和最小训练试跑确定，尚未租借或发生费用。

来源：[PEFT LoRA](https://huggingface.co/docs/peft/main/en/conceptual_guides/lora) · [MLX-LM LoRA训练](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/LORA.md)。

### Mac训练规划约束

16GB统一内存同时供系统和GPU使用。先验证依赖、原生工具训练数据序列化与少量训练步的实际峰值；记录完整样本token长度、batch、LoRA参数及是否使用梯度检查点。完整60工具提示本身已约5700 tokens，不能为了适配短序列上限而截掉工具目录或用户指令。可先做明确的小工具业务组验证，再用完整目录检验资源。70GB可用空间适合规划首轮0.6B实验，限制保存检查点数和重复模型副本；实际磁盘、耗时和训练质量均未测。

训练运行工具优先MLX-LM；TRL是可替代工具实现，不是业务数据/原生输出契约。最终合并导出、GGUF转换与量化后，在RK3566重新验收，不能用Mac结果代替板端效果。

当前支持依据：[MLX-LM Qwen3实现](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/models/qwen3.py)、[MLX-LM LoRA](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/LORA.md)、[官方Qwen3-0.6B](https://huggingface.co/Qwen/Qwen3-0.6B)。
