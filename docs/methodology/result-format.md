# 评测结果格式 v1.0

SOP见[轻量评测流程](model-evaluation-sop.md)。机器可读契约为[evaluation-v1.schema.json](../../tools/edge_benchmark/schemas/evaluation-v1.schema.json)，实际测量仍保留在各实验的原始目录。

## 输入、执行和展示各做什么

`asr_suite.py` 将共享素材清单及候选部署声明展开为矩阵；`benchmark.py run` 顺序执行并保存原始事件、资源与资产 manifest；`evaluation.py export` 只读转换为 `results.json`；`evaluation.py report` 用静态模板重新渲染，不运行模型。运行时仅依赖 Python 标准库；ASR原生探针依赖外置SDK、模型和编译产物。

`validate` 检查格式版本、必要字段、重复身份、指标有限数值/缺失原因、质量覆盖/计数及比较约束。这是标准库实现的必要语义检查，不是完整的 JSON Schema 验证器；外部消费者可用标准 Draft 2020-12 验证器检查 schema。

## 一条记录的含义

一个 record 对应一次独立进程级运行。`id` 来自原始 `result.json` SHA-256 前16位；来源内容相同只导出一次，移动目录不改变身份。根节点含 `schema_version`、UTC生成时间、转换器/模板/schema哈希、记录列表和`summaries`逐轮汇总。中位数/范围先写入JSON；页面只渲染，校验会核对汇总与逐轮记录一致。

| 字段 | 意义 |
| --- | --- |
| protocol | 协议ID、throughput/realtime等场景、screening/qualification强度、轮次及legacy/versioned来源 |
| device / candidate | 实际CPU数和MemTotal、平台；候选模型、精度、框架、后端、线程等参数及资产hash |
| comparison | legacy/deployment/controlled_backend、人工命名组、条件摘要及比较键 |
| execution | 进程执行状态与返回码，正常退出不代表通过产品验收 |
| completeness | 预期样本数及缺失/空/EOF残留等不完整输出数；预期静音的空输出有效 |
| quality | 有可靠参考的样本覆盖、归一规则、字符错误数/CER及整句一致数；无参考为not_evaluated |
| assessment | 产品性能门槛尚未约定时为not_assessed，不能将RTF小于1自动当成整链路验收通过 |
| metrics / phases | 带单位、计时/资源范围、缺失原因的指标；显式阶段有时长、采样数和资源 |
| samples / evidence | 逐例输入hash、参考来源、识别文本与时间；原始结果相对路径及hash |

指标统一为 `{ "value": 数字或null, "unit": "MiB", "scope": "process_tree_sampled", "reason": null或缺失原因 }`。未知不得填0、NaN或由设备标称4GB推算。阶段中非指标的时长和采样数为普通数值。指标字段可以扩展，消费者应按名称读取。

## 比较键与推荐

比较键包含协议、场景、强度、设备/实际资源、固定输入hash和参考、预处理、文本归一、送音/尾静音/端点、启动预热策略及比较组。候选模型精度和线程等部署差异单独显示，不被隐藏。每种候选只在同键且同部署身份内汇总三轮中位数和范围；逐轮失败事实仍保留。

受控后端对照额外要求 `controls.model_lineage / precision / verification`，并检查精度与候选一致。工具验证声明和条件的一致性，不能自动证明权重谱系；研究者必须在verification中提供可核对的来源、转换及hash证据。证据不足就使用deployment。页面不自动报告纯硬件加速倍率。

旧记录缺少新版冻结条件时一律legacy、比较键null，不回填为edge-asr-lite-v1。即使出现在相邻历史面板，也只是方便查证，不意味着输入和口径可比。

## ASR v1 的固定边界

- 16kHz、单声道PCM16，相同文件hash；100ms块，按块末端的绝对到达时刻送入。非实时场景不等待。
- 规则1尾静音2.4秒、规则2为1.2秒、规则3为20秒，greedy_search。每条独立新stream，模型进程内只构造一次。
- 加载→首次2秒零输入探针→独立2秒零输入预热→3秒待机→全部用例推理。首次探针计的是静音计算，不是首个真实用户请求。没有清缓存，不称冷盘启动。
- 每条补3.2秒尾静音。计算RTF = 全部用例实际处理用时（含尾静音、结果检查及EOF drain）/原始音频时长（不含追加尾静音）；不包含按节奏睡眠、模型加载和独立预热。
- first_partial相对各文件回放开始；最终等待只在实时、存在非空端点且没有EOF残留时计入，相对固定20ms RMS>-35dBFS能量末端。不是人工末音标签。静音无锚点，不能算此延迟。
- 最大提交滞后/完成滞后仅用于实时块。非实时中的同名原始零值不被当作实时结果展示。
- 文本NFKC、casefold、去标点和空白；不把数字和汉字数字强行等价。CER按参考字符数加权，空/缺失输出计删除；仅dataset_transcript/manual_verified且有来源的参考参与评分。重复轮次不增加语料数量。

## 资源边界

资源采样约200ms一次，范围是worker及其存活子进程；共享页用PSS，RSS相加可能重复共享页。PSS/MemTotal表示这棵进程树的比例，并非整机所有进程的内存利用率。CPU容量占比 = 核秒/墙钟/逻辑CPU数×100。

阶段与资源共享主机单调钟。阶段CPU使用包围边界的样本差值，无法包围时可使用阶段内首末样本（scope明确为phase_interior_samples）；不足两点或计数下降时为null。近似窗口可能包含少量相邻阶段，短加载/首请求阶段受采样间隔影响更大。阶段内PSS峰值是采样峰值，不是内核高水位。全case CPU/峰值保留，不能混为活跃推理资源。

Swap为进程树读数；MemAvailable是受后台程序共同影响的主机读数。频率/温度见原始resources.jsonl；NPU频率不是忙碌率。目前NPU忙碌率、独占内存均未测。动态库映射只能证明加载了库；CPU进程也可能因SDK依赖映射RKNN库，需结合provider、模型资产及执行路径判断后端。

## 历史映射和分享

旧ASR Python、原生CLI、流式、ROS分别保留profile；RTF分母及重载成本不同，不混排。旧CLI已四舍五入的RTF保留其精度。历史MemTotal/分阶段边界未知就为空，不从今天的环境倒推。

ROS只读映射已有回放事件及summary中的能量相对端点，缺资源不推算。共跑记录保留组合进程树范围，不将组合PSS/CPU归为ASR单独占用。JSON链接原始结果，逐条专用事件仍由原始文件查阅。静态HTML为同一JSON的视图，无外部脚本；复制分享时保留相对目录结构，模型、SDK和音频仍留在外部缓存。
