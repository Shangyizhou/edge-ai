# RK3566 Zipformer INT8 PTQ：部分可运行，当前候选不采用

日期：2026-10-21。对应 [Issue #2](https://github.com/Shangyizhou/edge-ai/issues/2)。这是有界转换与功能探索，不是完成的性能复测。结构化入口：[阶段状态](status.json)、[识别输出及质量](functional-results.json)、[静态页面](report.html)。

## 结论

**实际生成了 INT8 joiner，并在 RK3566 NPU 上执行成功；尚未得到完整 INT8 ASR，当前混合精度候选识别质量明显退化，不能推荐部署。** encoder 的浮点控制和 INT8 尝试均在本轮编译预算内超时，不能据此宣称不支持。decoder 本轮未转换。

| 项目 | 未量化 joiner 控制 | INT8 joiner 候选 |
| --- | --- | --- |
| 来源与转换器 | 同一浮点 ONNX，RKNN Toolkit2 2.5.0 | 相同 |
| joiner 文件 | 6,461,782 B（6.16 MiB） | 3,285,117 B（3.13 MiB），减少49.16% |
| 上板运行 | 成功 | 成功；Add/Tanh/Conv 为 INT8 NPU |
| 两条独立 FLEURS 的 CER | 18/66 = 27.27% | 58/66 = 87.88% |
| 命令功能检查 | 机器人请让底盘上前移动二十厘米 | 机器人请让底盘 |
| 质量门槛 | 仅为小样本控制，不代表通用准确率 | 未通过，停止性能复测 |

完整识别的 encoder/decoder 均保持原历史 FP16，只替换 joiner。这里的文件缩小只属于 joiner，不是整个模型或内存减半。CPU 动态 INT8 与本次 RKNN 静态 W8A8 也不自动等价；[同精度主基线 #1](https://github.com/Shangyizhou/edge-ai/issues/1) 仍未完成。

## 实际做了什么

1. 在 Git 外新建 Python3.8 转换环境，保留原模型和私有运行库。RKNN 2.3.2 固定依赖 onnxoptimizer0.2.7 源码构建触及480秒预算；改用正式2.5.0 ARM64 wheel及其依赖，未删改旧版依赖。固定环境见 [freeze](environment-freeze.txt)、[资产身份](assets.json)。
2. 从同源 checkpoint（SHA256 `d3285a7cf654abcdb3ee83f364a4378cdd1e691b29ae9ee2b6119202b2bd8a3e`）及 icefall `1c388ad9be94c0ee9de76f7a6ed45b1cff677d13` 导出三个浮点 ONNX。第一次导出触发主机可用内存保护；第二次成功，未改变用户其他进程。
3. 用已有 `official0` 和 `command` 音频捕获真实 fbank、token context 和逐块反馈状态，各组件16组输入，共624个张量。保留 int64 计数/token。encoder 实际 T=71、步长64，不套用其他模型尺寸。[清单](calibration-manifest.json)记录顺序、shape、dtype及hash；[校验](capture-validation.json)核对所有文件，并验证下一步全部35个状态与前一步输出严格相等。校准只采每条前8块、joiner每块一个帧，覆盖很小，不能视为代表性校准。
4. 浮点 encoder 优化等级3编译在480秒超时；INT8 encoder 等级0在360秒超时，两者仍在图优化阶段，无产物。原始日志分别见 [float](stages/float-encoder/stdout.log)、[INT8](stages/int8-encoder-opt0/stdout.log)，编译错误/进度也见各目录 stderr.log。
5. joiner 浮点和 INT8 构建均返回成功，构建约14.36/19.84秒。INT8 使用该SDK默认 `w8a8 / normal / channel`、优化等级3；[默认参数](rknn25-config-defaults.json)和[构建证据](int8-joiner-build.json)保留。编译器提示模型输入/输出改为INT8；不能只根据构建选项推断实际执行精度。
6. 独立组件探针及完整ASR对照定位运行库兼容边界，最后用原已验证的私有 runtime2.2.0 完成三条音频功能检查。未修改系统运行库或驱动、生产ROS节点。

## 实际执行精度与接口

[零输入层报告](stages/probe-int8-joiner-profile22/stdout.log)显示 Add、Tanh、Conv 均为 INT8 NPU；输入/输出操作及最终 reshape 有CPU处理，不能称全算子全NPU。两个输入为非对称量化，scale约0.0194824/0.0142165，zero-point为2/-9。该报告只验证执行与精度，不将其中微秒计时当作实际音频吞吐。

已检查 [Sherpa v1.13.8 RKNN 实现](https://github.com/k2-fsa/sherpa-onnx/blob/v1.13.8/sherpa-onnx/csrc/rknn/online-zipformer-transducer-model-rknn.cc)：RunJoiner 声明 float32 输入并请求 `want_float=1` 输出，而非直接把INT8字节当浮点。源码层面存在运行库转换路径，但尚未逐层核对真实输入输出误差，不能据此排除全部接口或量化参数问题。与此同时，该版本 encoder 的状态类型分支只接受 FP16/int64；即使后续量化encoder成功，也需检查是否必须保留浮点状态接口或修改适配器。

**本次只能确认量化候选导致可观察的输出退化，尚未定位精确误差层或唯一原因。** 小校准覆盖、量化策略、输出logit精度等都需进一步证据，不能将退化说成上游关闭量化的原始原因。

## 运行库与失败记录

| 条件 | 观察 | 判断边界 |
| --- | --- | --- |
| runtime2.5.0，独立joiner，不开profiling | float/INT8均运行成功 | 仅证明独立组件可执行 |
| runtime2.5.0，独立joiner，开profiling | 两者SIGSEGV；gdb落在rknn_run | 不是仅查询报告失败，也不是INT8独有 |
| runtime2.5.0，完整ASR | 新float/INT8 joiner及完全未改动旧FP16模型均SIGSEGV | gdb：flags=0，崩溃在encoder rknn_run；不能归咎新量化joiner |
| runtime2.2.0，完整ASR | float控制和INT8 joiner候选均完成三条回放 | 支持当前有限功能结论，不证明全部2.5产物兼容 |

驱动保持0.9.6。gdb阶段的 `status=ok` 表示调试器命令正常退出，其被调试推理实际SIGSEGV，不能计为成功推理。最初旧encoder探针20秒超时来自未优化逐字节读文件，改为批量读取并O2后正常；保留初版源码和失败记录，不把辅助工具缺陷写成模型故障。

## 质量与资源数据如何读

两条 FLEURS 未用于校准，合计66个归一化参考字符，参考转写、音频hash和输出均见功能JSON。命令参与了校准且只有历史模型共识参考，不计入CER。三条音频均为一次非实时供音的功能回放；INT8候选其中两条发生更早端点，属于实际识别退化表现。

float/INT8 joiner 两个功能进程树峰值PSS约204.84/201.81 MiB，保留在原始结果中。它们是单次功能探针，尚无重复、受控资源复测，**不报告提速倍数或内存优化收益**。PSS衡量进程树分摊的主机驻留内存，不是NPU独立内存统计。

## 下一步建议

先保留现有可用FP16部署。继续INT8时，优先用真实 joiner 输入做浮点/量化输出与逐层误差对照，再扩大少量校准帧及实际token覆盖，按误差决定敏感层保留浮点；暂不做大量参数穷举。encoder转换宜迁至资源更充足的主机构建，并独立处理流式状态接口兼容。复杂度高于改一个开关，当前没有收益证据支持替换部署。

公平后端对照可并行考虑同源未量化ONNX与已验证FP16 RKNN的精度核验；必须披露FP32/FP16差异，不能直接冠以同精度主基线。

所有阶段配置、资源采样和原始输出见 `stages/`；实际执行命令见 `commands/`，只生成而未执行的计划没有纳入阶段结果。源码快照随阶段保留；模型、SDK、音频、NPY及二进制仍位于Git外，绝对路径为本设备实例配置。证据hash见 [清单](evidence-sha256.json)。
