# 固定 Benchmark 流程

一个项目入口，两个已有任务。无需安装 Skill，无需新增网页。用户提出能力需求，LLM 准备配置和可读测试说明；用户确认后再执行。`plan` 不加载模型，`run` 会真实推理，`sync` 不会推理。

```text
需求 → 审核配置／材料 → plan → run → MLflow
                              本地结果先保存，失败可 sync
```

## 配置与命令

复制 `configs/qwen.example.json` 或 `configs/asr.example.json` 到新的实验配置目录，填写资产位置、题集 SHA256、模型身份及预算。示例是说明模板，不是测量数据；未替换占位符会拒绝运行。Qwen 示例包括逐例无工具目录，但不是可用作独立验收的真实题集。不要把已观察示例当成封存测试。

```sh
# 检查并冻结所有输入和执行源码，不启动模型、服务或 SSH
python -m tools.edge_benchmark plan request.json --output /path/to/new-plan

# 仅在确认测试方案后执行；每次使用新输出目录
export MLFLOW_TRACKING_URI=http://127.0.0.1:5001
python -m tools.edge_benchmark run /path/to/new-plan/plan.json --output /path/to/new-run

# 同步失败后补传，不重跑模型
python -m tools.edge_benchmark sync /path/to/new-run
```

运行入口需要控制端 psutil；同步还需 MLflow。可选安装文件为 `requirements-control.txt`（Python3.9+，匹配当前MLflow3.1.4）。模型环境通过每个候选的 `python` 指定，继续使用既有 MLX/llama.cpp 或 sherpa 环境，不在其中安装 MLflow。所有模型/资产必须已在执行主机上；首版没有下载、远端调度或 SSH。

JSON 配置共有任务、协议ID、题集、预算和候选列表；`data_use` 区分 development/regression/independent_test，默认 regression；模型参数留在候选 `request` 内。所有文件路径默认相对配置文件，题集内音频/工具文件相对题集文件。`suite.sha256` 是题集原文件哈希，plan 另冻结模型目录、二进制、Python、实际展开题集和执行源码。任一资产变化需要新计划。plan 不导入运行时，所以不能据此宣称动态库兼容或实际模型就绪。

`protocol_id` 必须在题集/评分/计时口径改变后更新。共用一个协议的候选才作直接比较。目录快照保留全部模型文件身份，运行记录保存执行源文件与实际包版本；大权重不复制进结果或 MLflow。

## Qwen

支持 MLX 本地环境和由本次拥有的 llama-server。HTTP 模式必须提供 `server`，不能用未明确监控身份的外部服务。MLX 模式不填 `server`。原生调用、JSON、Schema、Registry 纯校验继续使用 `qwen_lifecycle`；Registry validator 只使用已核查的纯校验程序，不能指定设备处理程序。未配置时 Registry 指标缺失，不能声称通过。

每条案例可用 `tools: []` 或独立目录覆盖共享工具，生成和上下文预检一致。题集保留 `user`、`expected`、可选 `source_group`；沿用现有 tool/chat/persona 期望形状。旧关键词人设判定不等于完整语义审核，相关结论必须另审。

不同精度比较须有同源制品身份。保持题集、实际 runtime、提示/工具、线程、上下文与缓存策略一致；否则只能解释为部署方案对照。MLflow 展示完整调用计数、误调用、分母、完成率、完成样本响应中位数和采样内存。TTFT/token吞吐等仍以原始逐例事件为准，不估算未知值。

## ASR

首版复用已有 **Linux streaming_asr 原生程序**及 `/proc` 资源采样，不支持在 Mac 执行，也不自动登录香橙派。可在有匹配资产的 Linux 主机准备和执行，再把整个结果目录复制回 Mac 进行 sync。

当前 native CPU 路径固定使用 `encoder-epoch-99-avg-1.int8.onnx`、`decoder-epoch-99-avg-1.onnx`、`joiner-epoch-99-avg-1.int8.onnx`、`tokens.txt`；RKNN 路径使用 encoder/decoder/joiner.rknn 和 tokens.txt。缺文件在 plan 阶段退出，不改名、不拿其他编译版本替代。**这不是任意 FP32/INT8 通用加载器**；需要其他文件布局时先扩展明确的执行器并重新验证，不把示例标签当作真实精度。CPU与RKNN对比属于部署方案对照，不能直接归因纯量化。

清单 WAV 必须为单声道16k PCM16，包含有效能量末端、参考来源及内容。只有 `dataset_transcript` 或 `manual_verified` 且声明来源的完成转写进入 CER；同时展示总请求、完成数、参考覆盖。CER 按总错误字符/总参考字符计算，失败及缺参考不悄悄消失。保留原始转写，归一规则沿用 `evaluation_metrics`。

计算 RTF 排除加载和实时喂入等待，包含配置尾部计算；不能解释为用户端到端延迟。CPU/PSS 仅按正式推理窗口聚合。尾部与分块参数不同的成绩不混比。原始程序还有首轮/预热活动，不纳入正式样本分母，但占用总执行预算。

## 结果、失败与同步

```text
new-run/
├── plan.json / source/        冻结配置、资产身份与执行源码
├── 候选-input.json / 候选.log
├── 候选/                     原始案例、事件、资源和结果
├── execution.json            稳定执行ID、全部候选和状态
├── evidence.json             相对路径与内容哈希
└── sync.json                 单独的同步结果及 MLflow Run 绑定
```

所有候选顺序执行，共享总墙钟预算；逐例超时基于 Qwen 活动案例或 ASR 正式推理窗口。ASR 首轮/预热受总预算约束。超时或 Ctrl-C 停止本次跟踪的进程树，保留已完成结果及未运行候选；不自动重试、不停止既有服务。预算是停止触发点，另允许有限进程清理时间。

模型初始化失败、案例失败、未运行和同步失败分别保存。不完整执行返回非零退出码。整机断电或 SIGKILL 可能留下 `running` 记录：sync 拒绝将它推断为完成；先人工核查进程与原始证据，不重跑覆盖。被强制中断的 `.sync.lock` 只有确认无同步进程后才人工移除。单人顺序同步是支持边界，不提供多机器同时写同一记录的分布式锁。

MLflow URI 未设置时只保存本地，CLI 提示稍后 sync；同步失败保留结果并返回失败。每个候选一个 Run，通过 comparison_id、model_id、suite哈希、protocol_id关联。现有 catalog 不改身份、不被递归重建；新执行自身保存稳定ID和绑定，历史数据表不覆盖。封存测试、录音、权重和远端发布均不自动上传。

同执行ID及哈希的重复同步不增加 Run、指标点或逐例表行；同ID不同结果拒绝覆盖。仅同步本次结果目录中的文本证据。查看入口为 MLflow 的相应任务 Experiment；合成测试写入独立 `/synthetic` 分组，READY/FINISHED 不代表质量通过。

## 开发与维护

只扩展有实际需求的新任务。沿用普通函数和两个显式 Adapter，不增加插件扫描、调参框架或工作流服务。训练未来把检查点身份交给同一个 bench 即可，当前未改训练流程。

遵守 `~/python-style.md`：公开接口类型标注、中文 docstring，解析/校验、执行、评分和记录分开。新增文件扩入根 Ruff scope。控制入口按 Python3.8 兼容语法编写；MLflow同步环境需要Python3.9+。测试只使用替身和临时数据库：

```sh
python -m unittest tools.edge_benchmark.test_experiment -v
python -m unittest tools.experiment_tracking.test_record_execution -v
python -m unittest tools.qwen_lifecycle.test_lifecycle tools.qwen_lifecycle.test_server_lifecycle -v
```

有 MLflow 的隔离环境应实际运行同步测试；缺少它时显式跳过，不算同步验收。原生 ASR/真实模型冒烟须另行授权，本轮离线检查不能代替真实加载或板端验收。旧 CLI 和报告默认行为保留兼容，新统一入口不生成 HTML。
