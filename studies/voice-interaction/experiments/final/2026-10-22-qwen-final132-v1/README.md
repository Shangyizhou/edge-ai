# Qwen3 最终独立回归与生命周期报告

本轮完成状态以[门槛与来源](gates.json)、[最终分组汇总](final-summary.json)和[生命周期HTML](report.html)为准。范围为两个Q4模型×Mac/RK3566×132样本，止于原生调用与Registry纯校验；未修改生产代码、执行设备动作或发布Pages。

## 预注册范围与身份

- 官方Qwen3-0.6B revision `c1899de289a04d12100db370d81485cdf75e47ca`，真实独立参数596049920；选定v3 rank8/后8层q/v adapter，300训练/60验证，最终数据不用于再训练或选择。
- 主Q4对照在最终输入打开前[预注册](../../../research/2026-10-22-mac-qwen-plan/final-evaluation-plan.json)。未训练模型用`matched-base-dedup-v2` SHA `613697c3c0970385bc9e34a926fa30f39b37ae4471ca397a15666cebbff1d7ab`；微调Q4 SHA `6f173f8a0c51b56c558ed47559a57a78b5c036391b63f9b8ed0731d54cc4b2f5`。两者310张量同布局，去重不是LoRA压缩。
- 原120封存SHA `12ecc86b2bde791728312d8660ea66af26fd8e51477803bb52f0d7cb760de3a5`；独立补充12多调用SHA `22f20895471afba0887f641acf1229e9b87dfa371540818cc9bf66171d59e7eb`。各132由72单工具+36角色+12聊天+12多调用组成，共84工具请求、100个目标调用。分别报告120与12，未裁样本。
- [精确启动冻结](launch-freeze.json)在首个最终生成前提交`c2282fd`；两个板端Q4先用已知validation首例完成真实准备冒烟，各1/1原生/JSON/Schema/Registry通过，max256完整预算通过。runtime固定llama.cpp `e3797b184d428c7a019362612b76971f60af6670`。
- Mac：M5/Metal、8192 context/f16 K+V/cacheoff/4线程/b512/ub512/max256/temp0；板端：RK3566 ARM CPU、2048 context/q8 K+V/cacheon/2线程/b512/ub128/no-repack/mmap/fitoff/faon/max256/temp0。同一平台base→selected串行；平台间配置不同，不能作纯硬件加速归因。

## 关键结论与未满足项

| 部署 / Q4 | 原生=JSON=Schema=Registry /84 | 精确 原72 / 补12 / 合84 | 上下文角色 /36（误调用） | 聊天 /12 | CPU整机容量 | 采样峰值 / 实际RAM | 有效工具P50/P95秒 (n) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| final14-mac-base | 27 | 15 / 4 / 19 | 5（0） | 12 | 6.64% | RSS 1400.45MiB / 8.55% | 0.658/1.015 (27) |
| final14-mac-selected | 84 | 67 / 6 / 73 | 21（10） | 12 | 5.90% | RSS 1413.58MiB / 8.63% | 0.598/0.913 (84) |
| final14-board-base | 26 | 15 / 4 / 19 | 6（0） | 12 | 48.43% | PSS 566.18MiB / 14.43% | 13.214/28.352 (26) |
| final14-board-selected | 84 | 65 / 7 / 72 | 21（10） | 12 | 46.04% | PSS 600.30MiB / 15.30% | 11.571/27.331 (84) |

CPU为逐例推理/纯校验等待窗的server树；上述内存与加载窗合并最大采样值相同。有效工具延迟只取期望工具请求中实际完整通过原生/JSON/Schema/Registry的子集，排除所有persona误调用；不要求该调用语义精确。

| 部署 | full / 实际prefill / output 中位tokens（全部132） | 原生prefill / decode 中位tok/s | 新KV冷首例 TTFT / 完整响应 / 有效工具 秒 |
| --- | --- | --- | --- |
| final14-mac-base | 920.0 / 920.0 / 16.0 | 2840.254 / 111.116 | 0.217 / 0.288 / 无有效结果 |
| final14-mac-selected | 920.0 / 920.0 / 16.0 | 3438.238 / 123.445 | 0.236 / 0.280 / 0.476 |
| final14-board-base | 920.0 / 18.0 / 16.5 | 3.930 / 2.668 | 166.224 / 169.595 / 无有效结果 |
| final14-board-selected | 920.0 / 18.0 / 16.0 | 3.917 / 2.651 | 169.759 / 172.400 / 174.273 |

板端微调Q4首例full/evaluated/cached=918/918/0，完整有效调用174.273秒，不能用11.571秒P50承诺冷启动。后续缓存命中按真实native字段保留，暖前缀请求内容/输出长度仍不同。板端两组实际采样间隔中位269.778/265.405ms（200ms等待加采样开销），最高thermal zone分别53.75/55.00°C；整机swap-in逐例窗合计12/8KiB、swap-out均0。Mac同窗整机swap-in约578.0/804.7MB，是系统全局计数，无法归因模型；不作内存压力稳定性或共跑结论。


Mac微调Q4的84请求全部原生/JSON/Schema/Registry接收，精确完整计划73/84（原72单工具67/72，补充多调用6/12）。模型实际给97个调用，目标共100个；精确指标按完整请求计分，不把它说成逐调用正确率。

Mac上下文角色审核21/36，较同提示未训练Q4的5/36提升，但未达到预定全通过。微调模型姓名5/6、角色用途1/6、创作者4/6、自我介绍0/6、未知履历6/6、角色/基座来源5/6；10个角色请求误调用工具，普通聊天12/12无调用。关键词辅助分23/36不是人设接受率。

验证阶段同Q4人设18/18未保持到独立表达：合成训练表达覆盖有限、多轮验证选择的过拟合是可能解释，不能把本轮差距唯一归因量化。下一轮要用新的真实来源开发数据和新的封存集；本轮失败不回流调参再冒充独立成绩。Q8只是已测Mac量化损失参照，未因最终失败换成Q8或增加板端Q8矩阵。

角色规范事实回复并不等于丰富风格、自然度或人工接受；工具格式通过不等于意图、调用顺序、转义、前置业务条件或设备动作正确。完整生产/语音/共跑/长期稳定验收仍未完成。板端与完整指标以最终汇总表为准。

## 证据与口径

[原始计数与资源审计](resource-audit.json)区分full prompt usage、实际evaluated prefill、cached、output、native解码`n_gen−1`步数，保留TTFT和完整有效调用P50/P95及n。有效工具等待为请求→完整原生JSON/Schema/Registry，不以快速失败充成功；精确意图另计。P95是单轮最近秩经验数，不是稳定尾延迟。

采样对象为真实模型server PID及递归子进程；CPU占整机逻辑核容量，窗口含等待纯Registry，但client/Registry进程CPU不在server树。Linux用PSS、Mac用RSS，不相加MLX分配；加载、推理/纯校验窗分开。200ms是等待间隔，实际采样开销和thermal详见审计。整机余量/swap是同时观测，不能归因模型或宣称共跑达标。没有已确认产品等待/内存阈值；PSS≤1.3GiB、余量≥512MiB只是历史研究建议。

“冷首例”指新server的空KV/前缀，不是受控OS文件页缓存冷启动。缓存减少前缀计算量，不等于模型吞吐倍增。Mac初次后台启动中断的3个case和原始目录完整保留，随后相同冻结配置完整重启132；canonical共528次，与附加中断3次/板端devsmoke2次分列。

[逐项角色审核](persona-review.json)为Codex assistant，非人工验收；[冻结请求及原始引用静态证明](handoff-static-proof.json)核对实际hash。主比较读取每次原始`benchmark/results.json`；旧Mac launcher顶层引用缺少`benchmark/`前缀的原件保留，`derived-handoff.json`带原件SHA只重定位引用，不是新测量。

主HTML及JSON内嵌本轮原始证据ZIP，核心阅读离线；历史阶段完整raw仍在原实验伴随目录，不声称递归内嵌全部历史。浏览器文件预览策略拒绝，未使用HTTP、其他浏览器或Playwright规避。静态锚点/链接/转义/响应式CSS检查与实际桌面/手机视觉验收分列，后者仍UNVERIFIED。

[复现与五技能交接](reproduce.md) · [后续原生接入契约](integration-contract.md) · [逐文件manifest](manifest.json) · [静态验证](static-qa.json)。权重、build、venv与旧模型均在Git外并保留。

根集成已通过`ae5b10de2a12057cc0405dacab26730c70429c10`为新的Qwen实验前缀增加静态站点导出排除规则；本轮未发布Pages，这些数据默认不进入公开静态导出。公开发布需要单独操作。
