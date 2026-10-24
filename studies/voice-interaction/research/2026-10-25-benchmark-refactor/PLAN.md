# Benchmark 固定代码流程：Qwen 与 ASR 最小重构方案

日期：2026-10-25。状态：讨论稿，未实施。只分析源码、编写方案；不训练、不推理、不访问设备、不上传、不修改历史实验。

## 1. 固定决策

保留现有模型执行器和评分代码，在 `tools/edge_benchmark/` 增加统一入口及两个任务适配器。用户只提供需求，LLM 按模板准备配置和测试说明；用户确认后由固定代码执行。配置准备不会自动启动测试。MLflow 负责记录与查看，不负责模型调度。首版不引入插件发现、调度服务、自动搜索、工作流框架或新网页。

首版支持 Qwen 原生调用与已有 sherpa ASR 执行路径，不承诺任意 LLM/ASR 通用兼容。TTS 后续有实际需求时增加对应适配器。

GitHub 一个代码仓库；HF 现有模型、数据集仓库保持；MLflow 继续作为日常入口。旧 HTML 留档，新测试默认不生成 HTML。原始证据仍以本地冻结文件为准，MLflow 是索引与展示副本，遵守既有 catalog ADR。

## 2. 已有实现与缺口

| 位置 | 可复用能力 | 本轮处理 |
| --- | --- | --- |
| `tools/qwen_lifecycle/benchmark.py` | MLX/HTTP 推理、逐例保存、协议校验与资源采样 | 保留执行核心，不复制 |
| `tools/qwen_lifecycle/server_lifecycle.py` | 自有服务生命周期、预检、实际服务进程监控 | 保留；报告渲染改为显式可选 |
| `tools/qwen_lifecycle/protocol.py` | 原生调用、JSON/Schema/Registry 纯校验 | 保留；不执行工具 |
| `tools/edge_workflow/qwen_adapter.py` | 新制品冒烟后执行正式测试 | 抽离对 HTML 文件存在的依赖，不强制重复冒烟 |
| `tools/edge_workflow/asr_adapter.py` | 现有 sherpa ASR 执行与 CER 汇总 | 修正状态/分母、报告耦合，作为首个 ASR 适配器 |
| `tools/edge_benchmark/asr_suite.py` | ASR 候选与复测矩阵 | 复用配置展开，不另写矩阵引擎 |
| `tools/edge_workflow/collect_asr.py` | 按实际推理窗口汇总资源 | 复用；不得把加载/空闲混入推理资源 |
| `tools/experiment_tracking/` | 历史导入、catalog 与 MLflow 绑定 | 增加面向新结果的幂等登记；旧导入不作为执行入口 |

GitHub main、本地训练改动、PR #20 属不同状态；实现前在干净分支确认依赖，只合入必要代码，不批量提交私有数据或整个脏工作区。MLflow 库不放入板端模型环境：模型子进程负责执行，Mac 控制端读取事件并登记。板端执行与 SSH 调度不在首版自动化范围。

## 3. 用户可见流程

1. 用户提出测试目的、模型位置、设备和预算；缺失资产路径或独立参考文本时明确列出，不能臆造。
2. LLM 阅读当前执行器能力，必要时调研模型/运行时要求，生成 `request.json`；已有题集复用，新增题集给用户审核。不存在的后端报不支持，不临时生成并直接运行陌生代码。
3. `plan` 只校验、展开配置，输出候选数、题数、预计请求上限、计时口径、资产缺口与输出位置；不加载模型、不下载权重、不 SSH、不启动服务。
4. 用户确认可读方案后，单独运行 `run`。顺序执行候选，遵守总预算及逐例超时。
5. 原始输出先落盘，MLflow 同步参数、逐例表、摘要和证据引用；用户看 MLflow，无须查看配置细节。
6. 人工/LLM 写短结论，模型卡仅在选定交付时更新；发布、部署不随 bench 自动发生。

建议命令接口（均为拟新增，不是当前可用命令）：

```sh
python -m tools.edge_benchmark plan request.json --output NEW_PLAN_DIR
python -m tools.edge_benchmark run NEW_PLAN_DIR/plan.json --output NEW_RUN_DIR
python -m tools.edge_benchmark sync NEW_RUN_DIR
```

`plan` 冻结实际配置及输入哈希；`run` 重新核对，不一致则拒绝启动。首次执行前检查模型/运行时身份并记录。计划阶段不声称已测兼容。`sync` 只重放已保存记录，不运行模型。

## 4. 配置：共用少量字段，任务参数各自保留

使用 JSON，与现有接口一致，不增加 YAML 解析依赖。两个经过审核的模板，不创建巨型跨任务 schema。共同字段：schema、name、task、device、candidates、suite、budget；MLflow URI 从环境/本机配置读取，不写入公共实验模板。内部以 task 显式选择两个 adapter，不允许配置任意模块路径或 shell 命令。

下列是说明配置形态的模板；尖括号均为待绑定值，`plan` 必须拒绝未替换占位符。模型 ID 对应现有 catalog；实际运行所需本机路径在执行计划中解析，不提交到公开仓库。

### Qwen：比较同源 F16 与 Q4 的指令调用能力

需求：同一 Mac、同一 llama.cpp、同一题集，比较已有 F16/Q4，不训练、不执行工具。

```json
{
  "schema": "edge-benchmark/request-v1",
  "name": "qwen-f16-q4-regression",
  "task": "qwen_tool_calls",
  "device": "mac-local",
  "candidates": [
    {"id": "f16", "model_ref": "<catalog-f16-id>"},
    {"id": "q4", "model_ref": "<catalog-q4-id>"}
  ],
  "suite": {"path": "<reviewed-suite.json>", "sha256": "<digest>"},
  "budget": {"total_seconds": 1800, "case_timeout_seconds": 180},
  "qwen": {
    "runtime_ref": "<pinned-llama-runtime>",
    "threads": 2,
    "context_length": 2048,
    "temperature": 0,
    "max_new_tokens": 256,
    "cache_prompt": false
  }
}
```

运行时模板还必须绑定实际二进制版本与启动参数、tokenizer/template、SystemPrompt、工具 Schema、KV 精度及服务器资源身份。不能借 temperature=0 声称所有后端完全可重复。控制端将模板展开为已有 Qwen 请求，不重写实际生成。

指标：原生格式/JSON/Schema/Registry 分层结果；完整工具计划匹配、应该不调用时误调用；分组正确数/分母；逐例响应完整耗时。存在真实原生 token 事件时才提供 TTFT/prefill/decode，缺失不估算。资源记录服务进程 RSS（Mac）或 PSS（Linux），注明采样间隔。Q4 与 F16 必须关联同一高精度来源，MLX 与 llama.cpp 的差异不得解释为纯量化效应。

当前旧 suite 有整套共享工具目录，而部分新数据逐例缺工具；首版必须覆盖“每例实际 tools”及其哈希，否则应拒绝该题集，不悄悄回退到完整目录。人设/解释语义不能以关键词评分冒充上下文审核：首版保留待审标记或已有明确评分版本，不新增隐式 LLM 评委。

失败和截断保留在请求分母；期望无调用的分母单列。冒烟只证明可执行，不能计入正式得分。

### ASR：比较两套已有精度的转写质量与资源

需求：同设备、同材料、相同解码与输入节奏，比较已有 FP32/INT8 文件。若实际后端不同，标为部署方案对照。

```json
{
  "schema": "edge-benchmark/request-v1",
  "name": "zipformer-fp32-int8",
  "task": "asr_transcription",
  "device": "<execution-device>",
  "candidates": [
    {"id": "fp32", "model_ref": "<asr-fp32-assets>"},
    {"id": "int8", "model_ref": "<asr-int8-assets>"}
  ],
  "suite": {"path": "<audio-and-reference-manifest.json>", "sha256": "<digest>"},
  "budget": {"total_seconds": 1200, "case_timeout_seconds": 120},
  "asr": {
    "runtime_ref": "<pinned-sherpa-runtime>",
    "threads": 2,
    "realtime": true,
    "chunk_ms": 100,
    "tail_seconds": 3.2,
    "normalization_ref": "<existing-normalization-version>"
  }
}
```

音频清单必须包括实际文件哈希、时长、格式、参考文本及参考来源；运行前验证执行器所需单声道16k输入。修改音频预处理另产出文件并记录，不覆盖原录音。CER 用总编辑距离/总参考字符数，不平均逐句百分比；缺独立参考样本不进入 CER，单列无参考数。保存逐例原文、参考、错误数、完成状态。

性能保留 compute_rtf；100ms节奏等待、加载、首轮、预热、尾部计算分别说明，不能把 compute RTF 当真实用户等待。CPU/PSS 按实际推理窗口汇总。失败样本单列完成率与 CER 覆盖，不能因 CER 排除失败而宣称整体更准确。缺失模型文件时 `plan` 报缺口，不擅自替换 NPU/CPU 资产或假称测试已就绪。

## 5. MLflow：简单列表，少量关联

同一任务和冻结协议的候选进入同一 Experiment，例如 `edge-ai/qwen-tool-calls` 和 `edge-ai/asr-transcription`。不按每个参数值新建 Experiment；同名指标在不同协议下仍须筛选协议才能比较。

每个候选的一次正式执行对应一个 Run；首版不新增多层父子树。通过 comparison_id 连接同组候选，通过稳定 model_id、dataset_id、protocol_id 连接来源；检查点评测通过 training_id/checkpoint 标识关联，不再造第二套身份。

| MLflow 内容 | 来源 |
| --- | --- |
| Params | 完整实际配置的可筛选关键字段：runtime/precision/threads/context等 |
| Tags | task、comparison_id、稳定模型与数据身份、协议/评分版本、代码提交、数据用途、来源类型 |
| Metrics | 分子/分母、完成率、任务指标、延迟、资源；字段带单位；未知值不写0 |
| Artifacts | 实际配置、哈希清单、逐例表、评分口径、原始事件/日志或可恢复证据包 |
| Note | 改善、退步、限制与下一步，一小段即可 |

原始证据与 catalog 先成功写盘；MLflow 离线或上传失败时不重跑推理，保留待同步状态。运行结果与同步结果分开：completed/partial/failed/cancelled 与 pending/synced/error。校验不通过在执行前退出，不记为完成测量。总预算耗尽保留未运行项；CLI 对不完整执行返回非零退出码。

幂等同步以稳定执行 ID＋内容哈希找绑定：重复同步不建第二条 Run，不追加重复曲线/逐例表；同 ID 不同内容拒绝静默覆盖。执行中终止、连接断开须保留已知事实，只有确认退出才能标完成。MLflow 中断后的状态恢复由 sync 修正，不自行推断模型结果。

逐例文本可能敏感，沿用本机 loopback MLflow；不把原始音频、封存测试答案或权重自动上传。HF/GitHub 发布单独处理。备份范围包括未同步结果、catalog、绑定、MLflow数据库和附件。

## 6. 最少代码变化

目标新增/修改位置（方案，不代表文件已创建）：

```text
tools/edge_benchmark/
├── __main__.py         plan / run / sync 三个命令
├── experiment.py       配置校验、顺序执行、预算与结果清单
├── task_adapters.py    显式分派 Qwen / ASR，复用现有执行器
└── configs/            qwen 与 asr 两份 JSON 模板

tools/experiment_tracking/
└── record_execution.py 保存结果与现有 catalog/MLflow 关联
```

首版几个普通函数和必要的小型记录类型即可，不建继承树。共用执行状态、身份、资源单位和证据引用；任务评分保持独立。既有外部 request/result 合约与历史接口保留兼容入口，不递归扫 experiments 重评分。ASR 本机/板端执行用显式环境，不强行同一 Python 环境加载 MLX、sherpa 和 MLflow。

读取请求、校验、模型执行、评分、写盘、同步按业务步骤分开；MLflow SDK只在控制端同步边界引入。捕获特定外部 I/O 错误，验证或评分程序错误不能伪装成模型失败。主要流程中文 docstring/关键阶段注释，公开接口类型标注。Python 兼容性按实际边界声明；现有 Ruff target 为 py38，不直接使用更高版本语法。新增模块有意扩入 Ruff scope，遵守 `~/python-style.md`，格式、lint和行为检查均需通过。

## 7. 实施顺序与验收

1. **整理入口与脱离 Skill**：找到备份脚本中的必要校验逻辑并按许可证/依赖迁入；README 无失效的用户目录命令。两个任务 plan 可离线校验，未知字段、占位符、缺资产、预算无效、题集哈希变化均拒绝。无模型导入副作用。
2. **执行与记录分离**：Qwen/ASR 复用原执行器，报告默认关闭，保留原始文件；候选顺序执行，共享总预算且逐例超时能实际传递；打断只清理自己拥有的进程。
3. **接入 MLflow**：新执行记录及逐例自动登记；离线落盘、稍后同步、重复同步不增记录；不影响旧导入和原有表格。
4. **合成证据验收**：以测试替身验证派发/评分边界、每例缺工具、失败分母、ASR参考覆盖、部分执行、同步中断与幂等；所有测试记录显式 synthetic，不能显示为真实模型测量。不下载或加载任何模型。
5. **后续单独授权真实冒烟**：Qwen已有模型少量样本、ASR匹配资产少量录音验证新入口；本方案不执行。不能在未跑真实模型时宣布实际测量已通过。

这次验收交付目标是两份模板、统一命令、代码说明和离线测试，不要求训练、量化、上板、远端上传、发布模型或设计新 HTML。

## 8. 与训练、扩展的关系

首版只把 bench 做稳定。后续训练每保存一个指定检查点，交付既有 model_id、来源 training_id 和模板给同一 bench；训练损失继续归训练 Run，生成质量归评测 Run。禁止训练执行上下文自动读取封存测试，正式测试另行触发。

新 TTS 任务只在出现需求时增加一个明确 task 分派和结果映射，复用预算/写盘/同步。首版不提前建设 TTS、分布式搜索、定时队列、HF 自动发布、泛化工作流编排。
