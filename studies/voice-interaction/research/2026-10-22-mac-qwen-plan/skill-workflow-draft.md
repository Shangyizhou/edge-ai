# 模型实验工作流：候选技能与输入输出契约

日期：2026-10-22。状态：用户已确认6张实施工单并授权implement-spec，主集成PR为[#15](https://github.com/Shangyizhou/edge-ai/pull/15)。工作流设计已进入实现；具体完成情况以工单验收和新实验记录为准，不能将此设计稿视为技能已安装或模型已达标。

## 责任划分

| 技能 | 状态 | 输入 | 输出 | 完成边界 |
| --- | --- | --- | --- | --- |
| edge-model-selection | 现有，扩展实测报告适配 | 需求、候选/设备身份；或下游实测与制品谱系 | 候选方案/受控实验计划；或分层比较与已认可样式HTML | 给出有证据的判断；渲染不执行训练或推理 |
| edge-model-prepare | 现有，复用其request/checks/readiness契约 | 指定模型制品与运行库、设备、最小任务及benchmark配置 | 资产/运行库manifest、真实最小推理、readiness与可执行交接 | 下载、加载、真实推理和正式评测就绪分别记录 |
| edge-model-finetune | 已实现并安装，真实闭环实测完成 | 基座身份、工具Schema、角色事实/目标、数据或数据生成约束、提示版本、训练配置/资源预算 | 分组数据与覆盖、训练原始记录/资源、adapter及manifest、可复现训练结果 | 证明本次训练执行及adapter可加载，不代替独立能力验收 |
| edge-model-export | 已实现并安装，真实闭环实测完成 | 基座+adapter或已合并权重、明确转换/量化目标、转换环境、验证输入 | 合并/转换/量化制品谱系、每步成本与hash、输出制品就绪交接 | 来源→输出可追溯；转换成功与真实推理/质量通过分开 |
| edge-model-benchmark | 已实现并安装，真实闭环实测完成 | 已准备候选、冻结suite、目标设备、解码与采样协议、可选对照计划 | 原始输入输出、分层能力指标、阶段事件、实际资源和结果manifest | 执行真实实验并保留失败；报告与最终选择交给selection |

不为Qwen、某个人设、单个量化格式或某一张HTML各建一个skill。通用技能规定输入输出与不变量，模型/平台专属适配器、角色事实和真实结果留在实验项目。首轮适配范围明确为Qwen3/MLX-LM与llama.cpp，不能凭契约泛化为所有模型已支持。

## 可组合的流程

研究/候选（selection）→资产与最小推理（prepare）→未微调基线（benchmark）→数据和LoRA（finetune）→adapter能力验证（benchmark）→合并/转换/量化（export）→输出候选就绪（prepare）→同权重比较与板端实测（benchmark）→选择与HTML（selection）。

这是允许跳入的工作流，不是每次必须从头执行的固定长链。已有有效adapter可以直接export，已有实际制品可以prepare→benchmark，已有完整实测可以直接生成报告。根据请求范围执行，不因调用一个skill自动扩大到训练、量化、真实设备动作或公开发布。

每一项都是独立实用技能，可单独使用；在各个纵向工单中用真实样例验证其交接，而不是先写完3个空技能再做实验。

## 当前实现与设计口径

三个新增技能已通过#9/#10真实实验交接并安装；维护来源为[personal-skills PR #3](https://github.com/Shangyizhou/personal-skills/pull/3)。以下保留工作流设计意图，实际字段/命令以该来源的各技能references/contract.md及项目tools/qwen_lifecycle说明为准，避免把原设计字段名误当作执行接口。

## 共同交接约定

每份请求/结果声明schema版本和run_id，引用输入文件实际hash。制品以artifact_id、lineage、外置location、bytes、sha256和模型/runtime/设备身份表示。证据以ID引用原始输入、配置、日志、阶段事件、输出和采样记录。引用不等于已验证内容，接收方按需要检查实际资产。

状态至少区分未执行、执行完成/失败/部分完成；另行表示加载、原生解析、Schema和质量判定。缺失值为null并说明原因；模型退出0不等于满足能力目标。保持请求与原始证据只读，新结果写入新run，避免渲染改变测量。

能力测试集与角色事实单独版本化，可在不同候选中复用。实际数据与测试期望不是skill内的固定业务知识。最终测试不得用于调参。

## finetune：建议契约

已实现请求schema：edge-model-finetune/request-v1。

必要输入：
- base_artifact：基座revision、模型/hash、tokenizer/template身份及实际位置。
- objective：tool_calls、persona或两者；角色事实ref、选定tools_ref及输入/输出契约。
- dataset：已有train/valid引用，或明确的数据构造范围；分组切分与最终测试隔离策略。
- prompt_variants：精简/完整system身份，动态状态/上下文来源。
- train_config与budget：框架及版本、LoRA/QLoRA、层/rank、长度/batch/优化器参数、步数和资源范围。
- evidence_output：本run的外置资产与证据输出位置。

已实现结果schema：edge-model-finetune/result-v1。

输出包括数据来源与切分manifest、完整token分布/mask核查、训练配置/环境、adapter引用、steps/tokens/训练与验证loss时间序列、训练tokens/s和明确定义的时间窗、CPU/内存/Metal可用指标、swap/压力、耗时与状态。生成train-run离线阶段视图的数据；不以训练loss替代原生工具/角色测试。

## export：建议契约

已实现请求schema：edge-model-export/request-v1。

输入包括source_artifact/base与adapter引用、明确operations（merge/convert/quantize及顺序）、目标format/precision、固定转换工具与设备、输出位置和可重复smoke输入。可从中间制品开始，输出模型量化候选由请求决定。

已实现结果schema：edge-model-export/result-v1。

输出包括逐步stage输入/输出artifact_id与hash、文件bytes与总大小口径、工具版本/命令、耗时/采样峰值内存/CPU、状态和失败信息。每个输出候选提供prepare交接；调用prepare或交付其所需检查材料证明实际加载/最小推理，不重复定义一套相冲突的readiness等级。

质量和资源比较由benchmark继续完成。merge/convert/quantize每一步分别显示成本与下游质量，不把跨运行时差异都叫量化损失。

## benchmark：建议契约

已实现请求schema：edge-model-benchmark/request-v1。

输入包括actual_candidate与prepare就绪/原始smoke引用、suite_ref、system/tools/persona身份、runtime/backend/device、context/KV/线程/解码、冷热/缓存策略、执行轮次、资源采样与测量口径、对照组身份。测试输入允许固定响应fixture与真实模型两种来源，但必须分开标识，fixture通过不晋升模型状态。

已实现结果schema：edge-model-benchmark/result-v1。

输出包括逐例原始生成/解析调用/参数及Schema判定、角色事实检查与审核者、TTFT/完整有效调用等待、input/output tokens、prefill/decode事件与各自tokens/s、加载/空闲/推理窗口资源、失败/截断及有效样本分母。能力结果和推理资源独立归组，CPU/PSS/RSS/MLX内存字段各有明确平台口径。

结果经显式适配器进入当前报告数据视图及已有决策契约；不要把这个拟议schema称为现有selection/readiness/benchmark契约的原生格式。需要复用现有指标模块时保留其字段语义和未知值处理。

## 报告所有权与可重现交付

selection保留报告呈现规范和数据视图适配入口。新增训练曲线、制品转换链和量化表的实测视图，延续已认可的结论/资源、指标解释、真实输入输出、每节高亮发现和固定导航；当前模板不是已实现的训练报告生成器，需要通过首个真实Qwen基线/训练实验扩展验证。

阶段执行产生证据，报告消费证据；重渲染不能启动模型。每次结果可单独生成阶段HTML，累计结果可生成生命周期汇总HTML。同一数字可追到原始实验和采样窗口。

技能代码和数据无关的模板进入personal-skills的维护来源；Qwen训练样本、角色配置、实验结果留edge-ai或外置证据存储。实施时先检查该技能仓库的AGENTS和维护约定，再更新并安装到当前主机可发现位置。已安装副本不作为另一个独立维护来源，不自动推送或覆盖未提交修改。

新增技能需验证发现描述、必需/可选输入、缺失/失败交接、可恢复中间阶段和至少一个真实首轮样例；可复现脚本验证实际行为。人造数值仅能作为明确synthetic的契约fixture，不能进入实测HTML结论。

