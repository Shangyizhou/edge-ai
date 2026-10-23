# 数据与任务化工作流：Qwen Mac 技术试点

日期：2026-10-23。对应 [#16](https://github.com/Shangyizhou/edge-ai/issues/16)。执行用户已确认的[适配计划](../../../research/2026-10-23-data-workflow/implementation-plan.md)，不是替换前一轮主模型。

## 结果与入口

[分环节总报告](workflow-overview/report.html) · [数据准备](data-review-examples/report.html) · [评测准备](evaluation-review/report.html) · [推理就绪](readiness-review/report.html) · [训练曲线](training-report/report.html) · [导出](export-report/report.html) · [Mac对比与全部案例](comparison-reviewed/report.html) · [板端两任务](../../../experiments/rk3566/2026-10-23-workflow-validation-v1/comparison/report.html)。

60训练、18验证、24开发诊断、24预留最终，均为来源分组的合成技术样本，不是自然用户分布。Train数据-only模式不自动执行训练；冻结数据后，训练适配器对完整样本实际执行非思考模板、长度和监督mask预检。最大926 tokens，无截断。

32微步、累积8，即4次优化器更新，实际全阶段约49.31秒，MLX峰分配约2.73GB，不等于RSS。只有一个技术adapter，不作参数搜索或主候选晋升。24例开发集中，工具原生/Schema从9/12到11/12，工具及参数完全匹配从8/12到9/12，角色自动规则均1/8、聊天均4/4。角色自动规则不是完整语义审核，不能把无关键字要求的未知事实例视作角色已学会。

合并、F16转换和Q4量化均完成；12例转换子集在merged/F16/Q4的分项计数相同，但有失败，也不证明逐字输出相同或量化无损。MLX与llama.cpp有不同原生解析/约束和计数边界，不能单因素归因。Mac直接转换回归之外，另有Q4独立冒烟后正式12例验证新制品交接。

## 数据、身份与失败

- `historical-replay.json` 使用真正选定v3训练的train/valid字节身份，而非误用原始v1数据清单；计数为300/60。`historical-input-hashes.json` 记载1917个旧文件，全部原字节保持。
- `data-isolation-audit.json` 是独立检查器结果，仅证实声明组及归一化完全重复检查；不证明全部语义近重复、基座预训练污染或访问隔离。
- `registry-source-check.json` 只读确认板端ros-robot仍为原冻结提交，工作区干净；调用止于纯Registry校验，不执行处理器。
- 模型/adapter/GGUF与预留最终数据在 `/Users/syz/.local/share/edge-ai/workflow-20261023/`。最终24例未被用于调参或执行测评；同一代理/共享目录不称盲测。
- 导出文件名沿用旧请求惯例，但根目录与实际源adapter是本轮新32微步制品。准确谱系以本轮request/results和hash为准，不能将文件名中的768误认为训练步数。
- `train32/`、`export/` 是小型文本证据副本，不含权重；`source/`保存实际试点生成/适配代码快照。维护源码在 tools/edge_workflow，后续仅格式化/兼容修订不改历史证据。
- `training-proposal.json`、`training-guard.json`、`export-guard.json` 保留配置、预算和实际资源保护。没有自动延长训练或清理旧模型。

## 判断与限制

技术链路完成，模型能力仍不足。保留旧主候选，不开启新最终测试集；实际机器人集成、ROS/视觉/语音共跑、硬件动作与生产验收未进行。此前已观察最终132例仍只作为历史/回归。

HTML核心页面离线，证据与阶段链接按本机位置组织；未声称整个跨目录证据可作为单文件搬迁。静态/链接/交互脚本检查与浏览器视觉检查分开，浏览器视觉本轮未验证。代码和结果本地交付，未推送Git或发布网站。
