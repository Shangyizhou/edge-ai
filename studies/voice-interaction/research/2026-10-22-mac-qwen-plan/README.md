# Mac Qwen 原生 tool_calls 微调计划

日期：2026-10-22。状态：设备与源码只读核查完成；未执行训练、模型转换、原生推理或机器人动作。用户最新澄清覆盖此前计划中“先适配旧C++”“必须覆盖全部60工具”“完整业务正确率作为首轮门槛”的设定。

执行范围与验收以[GitHub规格 #8](https://github.com/Shangyizhou/edge-ai/issues/8)为准，已标记ready-for-agent。用户已确认独立原生推理→Agent调用结构→Registry纯JSON/Schema校验的测试边界；本页保留研究依据和候选配置。

工单拆分时用户追加并确认了角色人设/背景/介绍评测、各阶段资源与效果数据、沿用已认可HTML以及按需新增可复用skill的要求；6张工单已发布，见[生命周期报告范围与工单索引](lifecycle-report-plan.md)和[技能输入输出设计](skill-workflow-draft.md)。父规格保持原样，尚未启动实验；当前入口为[基线工单#9](https://github.com/Shangyizhou/edge-ai/issues/9)。

## 用户确认的范围

- 目标是 Agent 原生 `tool_calls`。先在独立训练/推理环境调通，再改 ros-robot 旧代码；旧 C++ 节点及 fc/res 不构成首轮阻塞或训练目标。
- 首轮只选关键有用工具，不要求覆盖60工具。推理继续提供本轮选定工具的目录；未训练工具不属于首轮覆盖承诺。
- 首轮重点是原生调用可解析、参数 JSON 合法，并验证当前 JSON Schema 保护链可接收。业务策略、执行流程与生产适配后续由应用处理，不以完整业务验收阻塞格式试点。
- 固定 SystemPrompt 规则、调用习惯与重复示例尽量通过微调学习，推理时使用精简指令；工具Schema、设备当前状态和运行时上下文继续作为输入。

## 建议路线

官方 Qwen3-0.6B → Mac MLX-LM BF16基座LoRA → 合并 → llama.cpp Qwen3 GGUF → Q4_K_M板端候选。Q5_K_M作质量备选，Q8_0作量化损失参照；内存不足再评估MLX 4bit QLoRA。先独立验证原生模板与解析、JSON/Schema，再回板端测内存与延迟，最后适配生产代码。16GB适合首轮0.6B小工具组试点，实际峰值与耗时仍待最小训练步验证。

LLaMA-Factory不是LoRA必要条件，本机优先MLX-LM。训练依赖尚未安装验证。模型与生成输出放Git外。

## 已核实的环境

| 项目 | 只读检查结果 | 影响 |
| --- | --- | --- |
| Mac | MacBook Air，Apple M5，10 核 CPU、8 核 GPU、16GB 统一内存；可用磁盘约 58GiB | 合理预期可做 0.6B 小规模 LoRA；长序列峰值与持续吞吐待实际试跑 |
| 板端连接 | `ssh orangepi-ts` 成功；源码在 `~/code/ros-robot` | 后续用 SSH 采集与传输；不迁移整个 ROS 工作区 |
| 板端硬件 | Orange Pi 3B / RK3566，4× Cortex-A55，最高 1.8GHz；MemTotal 4,017,020KiB，约 3.83GiB | 部署目标是小模型 CPU 推理，不能把 NPU TOPS 当成已支持 LLM |
| 板端瞬时内存 | MemAvailable 2,947,848KiB，约 2.81GiB | 只是检查当时的快照，不能当成 ROS/视觉/语音共跑预算 |
| 板端磁盘 | 根分区 28G，已用约 97%，剩约 895MiB | 所有转换在 Mac 做，传输前重查空间；保留旧模型，不擅自删除 |
| ros-robot | 分支 `codex/offline-agent-integration-20261021`，commit `23ef814cfb0a8c174b42b288454c30d5498e88d0`，工作区干净 | 该板端实际源码是首轮协议来源，不能直接以远程 main 替代 |

硬件由 `system_profiler`、`df`、`/proc/meminfo`、`lscpu` 检查；不保存机器序列号和 UUID。工具执行记录在本次聊天；可复用字段及源码哈希见 [research.json](research.json)。

## SystemPrompt 如何学进模型

微调不是把一段system文本当成永久配置保存，而是用大量“输入→期望assistant输出”示例训练稳定行为。可以迁入训练的内容包括角色/语言风格、原生工具输出方式、常见工具选择与参数填写方式，以及用户希望固定保留的基本行为。不要只把原来的长prompt重复附在全部训练样本上，再假设推理时删除它仍然有效。

训练数据使用精简system、真实tools和正确assistant目标；少量完整/精简提示对照用验证集选择。推理可以先尝试“你是机器人助手。需要操作时使用提供的工具，否则正常回复。”之类短指令，再以验证结果确定是否还能省略。固定行为不保证训练后绝对遵守，可变工具目录与Schema继续由程序提供。

当前设备状态、当次可用能力、权限、用户输入、会话事实和执行结果不作为固定记忆写进权重。JSON Schema校验、工具白名单和执行控制继续留在应用边界；无需把全部业务分支先训练完。

## 原生输出契约

以Agent现有原生工具接口为目标。训练数据用 `messages + tools`，由固定的Qwen3官方工具模板序列化；推理用匹配模板/解析器获得真正的 `tool_calls`。Qwen3模型生成的工具标记内含JSON，服务层将它转成Agent接收的调用结构。这不同于在普通content里打印一个看起来像tool_calls的JSON，也不需要模型生成整段HTTP响应或随机调用ID。

示例目标：用户“播放夜曲”对应 `play_music`，参数对象 `{"song_name":"夜曲"}`；普通聊天允许无调用。先冻结工具名、参数对象、空参数、多调用和完整响应结束方式。旧fc/res grammar、旧模板、旧流式播报逻辑均留待模型调通后的项目适配阶段处理。

JSON可解析与JSON Schema通过分开统计：未知工具、缺字段或类型错误可能是合法JSON，仍应由Schema/注册表拒绝。此次只验证该接收边界有效，不扩展成完整业务效果或硬件验收。

## 首批工具与数据

先从实际高频能力中选一个小目录，具体名单尚待确定。可供选择的种子组：摄像头、融合、跟随及状态查询，或加入音乐/音量参数型工具；不是默认要求全部纳入。规模可从约8个工具起步，以实际用途为准。训练和首轮推理均可只提供选定目录，不强制附带其余工具。

数据来自当前ActionRegistry/Pydantic及已有原生调用示例。每条包含精简system、选定tools、user和正确assistant目标，避免按目标答案只展示唯一正确工具；目录应体现实际可用集合。

| 样本类别 | 首轮目的 |
| --- | --- |
| 单工具/口语改写 | 建立最常用输入与调用格式的对应 |
| 空参数/字符串/数字 | 输出正确参数对象、类型与转义 |
| 少量多调用 | 能解析多个独立原生调用，覆盖数组及结束方式 |
| 无工具回复 | 正常聊天不必强行输出调用 |
| 选定工具的边界 | 覆盖Schema要求的必填、可选、默认值与非法输出拒绝 |

试点建议300训练/60验证/120独立测试，可随首批工具规模缩小。按原始语义场景和改写来源分组切分，近似改写不能跨训练和测试。合成样本先作JSON/Schema校验，错误输出留作诊断，不作为正确监督答案。后续按真实失败补数据，不预先要求全60工具或数千条完整业务数据。

## Mac 训练与导出

1. 固定Qwen3-0.6B revision、tokenizer和chat template，检查tools传递、非思考模式和assistant监督mask。
2. 起始候选：BF16基座LoRA、batch 1、rank 8、后8层、梯度累积8、梯度检查点；学习率从1e-4附近用验证集筛选。均为未试跑参数。
3. 统计选定工具+精简system+用户输入+输出的完整token长度，2048为初始候选，需要时评估4096；按实际长度选择，不静默截断。全60工具的历史5700 tokens不作为本轮固定成本。
4. 先20–50步确认峰值内存、swap、吞吐和loss，必要时降低适配层/调整检查点，或评估QLoRA。建议进程先控制在约10GiB并观察整机压力，非用户确认门槛。
5. 先验证最小训练、adapter合并和Qwen3 GGUF转换闭环；不假定MLX自带GGUF exporter覆盖所有架构。保留最佳adapter与少量检查点。

MLX-LM当前ChatDataset的mask_prompt按末尾消息计算，首轮把每个监督目标整理成末尾assistant，核对实际mask，不能假定任意多轮都自动只监督assistant。QLoRA反量化不恢复原始高精度，需记录训练与导出路径。

## 香橙派精度与内存

| 候选 | 定位 |
| --- | --- |
| 同一合并权重Q4_K_M / llama.cpp / ARM CPU | 首选部署候选，验证原生解析和Schema通过率后测资源 |
| 同一权重Q5_K_M | Q4格式/参数表现不足时对照 |
| 同一权重Q8_0 | 量化损失参照；旧Q8模型不能代替新权重结果 |

权重精度、训练基座精度、KV cache精度分别选择。官方Qwen3-0.6B架构28层、8 KV heads、head_dim128；理论f16 KV为 `2×28×8×128×2×context_tokens` bytes：2048容量约224MiB、4096约448MiB、8192约896MiB；q8_0 KV粗估约减至53%，支持性和实际进程内存仍需验证。选定工具目录使短上下文更值得优先尝试，不必预设8192。

板端首轮2线程、单请求，固定context/KV/模板对比Q4/Q5/Q8，再单独比较KV精度。建议LLM进程树峰值PSS约≤1.3GiB、共跑最低MemAvailable≥512MiB，仅为待测预算。转换在Mac完成，传输前重查板端空间，不删除现有模型。

## 执行顺序与首轮验收

1. 选定关键工具，导出Schema与来源身份，冻结精简prompt和原生样本。
2. 独立环境验证模型原生输出→解析器→Agent调用结构，校验JSON及Schema，不调用设备。
3. 记录同一基座未微调的格式对照；完成小规模LoRA与独立测试。
4. 同一合并权重导出Q4/Q5/Q8，在Mac回归，再上板测内存和延迟。
5. 模型调通后改ros-robot旧代码接入；业务流程和完整系统验收后续开展。

首轮分别统计原生解析率、参数JSON可解析率、工具/Schema接收率，期望在冻结测试集上争取100%；记录样本数与逐条失败。工具选择/参数语义可作观察，不设完整业务95%或60工具覆盖前置门槛。量化前后用相同样本比较，记录prompt tokens、完整有效调用P50/P95、进程树PSS/CPU和整机余量。合法JSON不会由训练自动保证，Schema拒绝路径继续生效。

## 官方依据与证据边界

- [MLX-LM LoRA](https://github.com/ml-explore/mlx-lm/blob/72be8c955d9a0d3099bd01865af288e0e947c3fa/mlx_lm/LORA.md)、[Qwen3 实现](https://github.com/ml-explore/mlx-lm/blob/72be8c955d9a0d3099bd01865af288e0e947c3fa/mlx_lm/models/qwen3.py)、[数据加载器](https://github.com/ml-explore/mlx-lm/blob/72be8c955d9a0d3099bd01865af288e0e947c3fa/mlx_lm/tuner/datasets.py)。
- [Qwen3-0.6B 配置](https://huggingface.co/Qwen/Qwen3-0.6B/blob/c1899de289a04d12100db370d81485cdf75e47ca/config.json)、[官方工具协议说明](https://github.com/QwenLM/Qwen3/blob/main/docs/source/framework/function_call.md)。
- [llama.cpp 量化](https://github.com/ggml-org/llama.cpp/blob/e3797b184d428c7a019362612b76971f60af6670/tools/quantize/README.md)、[LLaMA-Factory](https://github.com/hiyouga/LlamaFactory/tree/c683e59edd8f893abc5e1403184a1d0644817d2a)。这些源码版本仅是调研快照，不代表板端已安装版本。
- [结构化方案](research.json) · [离线 HTML](report.html)。本轮不更新公开报告目录、不重新跑旧模型 Benchmark。硬件检查和源码发现不等同于训练可行性或新模型板端通过。
