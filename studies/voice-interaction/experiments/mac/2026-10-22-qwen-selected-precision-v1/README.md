# 选定 Qwen3 LoRA：合并与同权重精度验证

本实验回答：选定768微步v3 adapter合并后是否保留输出，F16/Q4/Q5是否维持质量，以及准备哪个同基座制品给#14。实际执行范围为Mac M5/16GB、Metal、冻结60条验证输入（36工具/18人设/6聊天）；最终120和额外12挑战均未读取、未推理、未用于选择。无训练、板端更改、生产集成或设备动作。

[离线主HTML](report.html)展示全部60输入的7条件配对输出、阶段成本及解释；[机器可读汇总](comparison-summary.json)、[选择](selection.json)、[完整角色上下文审核](persona-review.json)、[所有工具失败](tool-failures.json)可核对原始结果。[原生指标新视图](inference-current-view.html)只重新渲染已有证据；原执行HTML和测量源码保留。

## 当前结论

| 条件 | 原生 / JSON / Schema / Registry（工具n36） | 精确工具 | 角色上下文（n18） | 聊天n6 |
|---|---|---|---|---|
| MLX adapter BF16+F32 LoRA | 36/36，各项相同 |33|18|6|
| MLX merged BF16 |36/36，各项相同|33|18|6|
| llama F16 |36/36，各项相同|33|18|6|
| llama Q4_K_M |36/36，各项相同|30|18|6|
| llama Q5_K_M |36/36，各项相同|31|16|6|
| llama Q8_0 |36/36，各项相同|33|18|6|
| 同基座未微调matched Q4 routing |16/36，各项相同|15|3|6|

MLX adapter/merged的60条原文完全相同：[回归结果](merge-regression.json)。F16和Q8仍有valid_022跟随意图错误、valid_029/032歌曲反斜杠遗漏，不是完美语义质量。Q4新增/改变跟随和转义错误；Q5的valid_042/049写成“我是小沫，用户创造者”，颠倒人设创造归属。自动关键词把Q5判18/18，完整上下文应16/18。所有角色结论为assistant Codex逐条审核，无人工验收；固定事实回复的重复不代表自然对话风格合格。

不要把routing提示下基座退化当成一般微调提升。此前同原始短提示MLX基座已33/36精确工具、人设1/18；v3原始短提示32/36、人设17/18。本实验选定routing组合工具仍33/36、人设18/18。该反事实的[完整原结果](baseline-originalshort-reference.json)和[前序解释](../2026-10-22-qwen-selected9-adaptation-v1/README.md)均保留。未微调模型在当前llama grammar组合的16/36原生，不能直接与MLX routing基座0/36归因量化。

## 选择与资源取舍

#14必须运行同基座未微调Q4与选定微调Q4作为同精度主对照；Q4文件396704704bytes，保留其6条验证语义失败，不把格式通过写成语义达标。Q5并未同时改善语义和人设，故不作为推荐备选。

在实际诊断Q4/Q5损失后，从同一F16增加Q8_0；它恢复F16的33/36工具精确目标和18/18上下文人设，作为可选质量候选。Q8文件639446976bytes，比Q4多242742272bytes；Mac单轮60例中位decode115.34→86.05tok/s、完整响应0.481→0.516s，采样server RSS1433.08→1663.81MiB。Q4更小不自动等于板端更快。Mac数值不外推RK3566内存/等待；板端是否加入Q8由#14磁盘与资源检查决定，无需完整精度矩阵。

## 来源链与匹配基座

官方Qwen3-0.6B revision `c1899de289a04d12100db370d81485cdf75e47ca`，unique参数596049920。选定adapter SHA256 `3f9a8e9d7d823781497bcc24a468e2618fb39aed65735a27974b493cbf9bfbfc`；前序合并/F16/Q4来源和资源由[runs/selected9-768-v3-export-v1/results.json](runs/selected9-768-v3-export-v1/results.json)承接。F16 SHA256 `e5ab9acb7cd47b495e2c337a57be2a0b162754d8adcbba3b21ec183c89012f2a`。Q4/Q5/Q8都从此同一F16分别生成；不是Q4重转换Q5。每一步的命令、输入ID、输出bytes/hash、退出和资源在各export结果、log和resources中。

首次未微调导出保留HF中重复的lm_head，与fused HF不同，产生484220224bytes Q4和311张量；其真实60例结果（17原生/16精确/角色3）和成本保留在`runs/precision13-baseq4-validation`及`runs/precision13-export`，作为序列化诊断，不用于#14匹配基座。

随后在全新外置目录验证`tie_word_embeddings=true`、原始lm_head与embedding dtype和数值完全相同，删除重复存储的头；其余所有张量写出后逐项值和dtype验证完全一致，零训练/零张量运算。见[规范化证明](tied-normalization-proof.json)。[GGUF布局核对](precision13-gguf-layout.json)证明微调与matched基座均310张量，名称、量化类型、shape完全相同；tokenizer、模板与模型元数据一致。差异仅为license/languages/source-card等非执行元数据。matched Q4是396705024bytes；多320bytes为元数据差异，不能称LoRA压缩。

所有权重外置于`/Users/syz/.local/share/edge-ai/qwen-lifecycle/artifacts/`。选定制品在`selected9-768-v3/`，匹配基座在`matched-base-dedup-v2/`。禁止用首次`matched-base-v1/`替换匹配基座。精确路径和hash见`comparison-summary.json`各artifacts和`selection.json`。

## 测量口径与执行handoff

同MLX 0.32.2/MLX0.32.4、BF16基座、Metal、temp0/max256/context8192/prefill512、新样本cache进行adapter/merged回归。adapter的F32 LoRA residual会cast回输入dtype。同运行时输出相同只说明本60例，无数值全空间等价保证。

F16/Q4/Q5/Q8采用同一llama.cpp `e3797b184d428c7a019362612b76971f60af6670`、Metal、context8192、f16 K/V、4线程、batch/ubatch512、单slot、temp0/max256、非思考、native tool grammar，所有输入预先apply-template/tokenize预算检查，未截断。它们是同权重量化对照；MLX到GGUF还改变运行时、后端实现和grammar，只可称部署组合对照。[控制检查](controlled-comparison-audit.json)保存命令/生成/输入一致性及实际evaluated-prefill计数；cache_prompt=false仅是请求标志，不能自行证明无复用。

计时保留原生prefill/decode及request→首content、request→完整响应、成功完整调用等待。MLX原生prefill含首token，llama按native timings计数，不静默混合边界。无效调用没有成功等待。推理资源监控实际server PID，200ms进程树采样；CPU分母为10逻辑核容量，RSS为采样峰值。MLX分配与RSS可重叠不相加。转换资源100ms采样，wall不含制品哈希；短子进程可能漏采。系统swap/可用内存为整机状态，不是模型独占。无GPU利用率，无Mac PSS，不推算板端或共跑。

真实技能派发：`source/run13.py`派发MLX两次和F16/Q4/Q5/首次基座Q4各prepare+60；`source/run13q8.py`派发诊断后Q8 export+prepare+60；`source/run13matched.py`派发规范化+F16+Q4与matched prepare+60。export与benchmark均使用已安装技能wrapper及其真实结果校验；[准备handoff](preparation/output/readiness.json)通过readiness.py生成，7候选均READY_FOR_BENCHMARK。MLX最小推理证据复用完整run的首条实际case，不把health视为推理。资源/运行库/二进制身份在每个run及[库清单](precision13-runtime-libraries.json)，库清单注明rpath候选与实际加载证明的区别。

后续板端初始配置建议CPU/2线程/context2048/f16KV/单请求/同system和9工具，必须在#14重新预算检查和实际测量；#13只测Mac8192/4线程。动态Schema、权限、设备状态和执行回执仍由应用输入。

## 验证与限制

12项单元/接口测试及目标ruff检查通过；包括不配对输入/提示拒绝、缺角色上下文审核拒绝、loopback/model覆盖拒绝、精确绑定头规范化与不等头拒绝。最初本地venv无ruff；改用`uv tool run ruff`，初次样式告警已修复。打包脚本首轮缺PYTHONPATH报ModuleNotFoundError，补明确工作树路径后成功；非模型失败。模型转换/真实推理全部正常退出，所有语义与人设失败照常保留。原始执行源码未因后续格式化/渲染而替换。

浏览器视觉为UNVERIFIED：file预览策略禁止，无其他浏览器、HTTP或Playwright绕行。静态HTML引用验证及hash清单留存。未执行生产动作、未验收完整语音/机器人交互。输入是合成固定验证表达家族，非自然用户总体；一次运行不代表稳定P95或普遍质量。

新版intake的只读复核覆盖全部14个独立运行、486条实际记录（含首次重复头诊断及各最小推理），native/JSON/Schema/精确目标/关键词人设字段零变化；没有再次调用Registry或模型，没有覆写旧结果。见[intake复核](intake-readonly-reassessment.json)和[执行源码身份](measurement-source-identity.json)。新response_complete字段只用于后续新测量，不补写历史结果。Q5的完整上下文失败仍由独立审核记录覆盖。

`git diff --check`对新增维护代码通过；原生模型回答中的Markdown换行空格在派生HTML里形成trailing-whitespace提示，按原样保留，不为消除样式警告改写真实输出。工具/解释器hash及两套环境包版本另见[toolchain identity](toolchain-identity.json)；转换与训练环境保持分离。
