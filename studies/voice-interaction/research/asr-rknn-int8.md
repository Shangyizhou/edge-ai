# 旧 Zipformer 的 RKNN INT8 量化调查

日期：2026-10-21。范围：现有 small bilingual zh/en 2023-02-16、`pruned_transducer_stateless7_streaming` 路线、RK3566。本文是一次源码调查，**不表示已成功转换、上板或得到性能结果**。

## 目前能确认什么

可以尝试 RKNN 静态训练后量化（PTQ），但不是把已有 RKNN 文件改成 INT8。应从同一 checkpoint 的浮点 ONNX 开始，分别构建未量化控制组和量化候选，保留独立目录、hash、构建参数和日志。

固定的 [icefall 导出源码（1c388ad）](https://github.com/k2-fsa/icefall/blob/1c388ad9be94c0ee9de76f7a6ed45b1cff677d13/egs/librispeech/ASR/pruned_transducer_stateless7_streaming/export_rknn.py) 对 encoder、decoder、joiner 都调用同一 `init_model()`，其中为 `build(do_quantization=False)`，没有校准集参数。encoder 还通过 `custom_string` 保存流式模型元数据；修改量化路径时必须保留。**这份源码没有解释为什么关闭量化，也没有证明打开后一定可用。** 不能把原因自行写成准确率问题或算子不支持。

[RKNN Toolkit2 v2.2.0 的官方多输入示例](https://github.com/airockchip/rknn-toolkit2/blob/v2.2.0/rknn-toolkit2/examples/functions/multi_input/test.py) 在 RK3566 上使用 `build(do_quantization=True, dataset='./dataset.txt')`。[对应 dataset.txt](https://github.com/airockchip/rknn-toolkit2/blob/v2.2.0/rknn-toolkit2/examples/functions/multi_input/dataset.txt) 每行以空格分隔各输入文件，包含多个 `.npy`。因此 ASR 校准需要模型实际输入张量，不能把 WAV 路径当作 encoder 的输入文件。

## 校准必须保持流式状态

[旧 ONNX 参考推理实现](https://github.com/k2-fsa/icefall/blob/1c388ad9be94c0ee9de76f7a6ed45b1cff677d13/egs/librispeech/ASR/pruned_transducer_stateless7_streaming/onnx_pretrained.py) 初始化 `cached_len` 为 int64，其余缓存为浮点；输入除了 `x`，还有 `cached_len/avg/key/val/val2/conv1/conv2` 各 encoder stage 的状态。每次 encoder 执行后，输出状态会反馈到下一块。decoder 输入是 int64 token context；joiner 接收 encoder 和 decoder 的实际浮点输出。特征提取为 16kHz、80 维 fbank、dither=0、snip_edges=False、high_freq=-400；具体窗口长度和步长从目标 ONNX 元数据读取，不照抄其他模型示例。

以下是据此形成的实施方案：

1. 用**待转换的原始浮点 ONNX**顺序解码少量固定校准录音。每段开始重置状态，段内持续反馈状态。
2. 在每次 encoder/decoder/joiner 调用前，按 `session.get_inputs()` 的真实顺序、shape、dtype 保存输入 `.npy`；同时记录 input name → 文件映射、源音频和 chunk 索引。
3. encoder 每行是特征及全部旧状态，不是输出状态；decoder 行保存真实 token context，joiner 行保存同一步真实 encoder/decoder 投影。
4. 保留起始零状态、运行中非零状态、语音和静音；不以全部随机数据或全部零状态代替校准。录音无需人工转写，参考识别只用于检查流程。
5. `.npy` 路径避免空格；清单与缓存留在 Git 外，仓库保存来源、hash、shape/dtype 清单和生成脚本。

以上捕获方案来自模型数据流推导，不是上游已经提供的 ASR INT8 校准教程。RKNN 是否接受该版本模型的全部整数输入、状态和算子，仍需实际构建验证；遇到 dtype 错误不能为了通过编译静默把 token 或计数状态改成 INT8。

## 为什么 CPU INT8 不会自动成为公平控制组

[旧中文 ONNX 导出代码](https://github.com/k2-fsa/icefall/blob/1c388ad9be94c0ee9de76f7a6ed45b1cff677d13/egs/librispeech/ASR/pruned_transducer_stateless7_streaming/export-onnx-zh.py) 使用 ONNX Runtime 的 `quantize_dynamic`、`QInt8` 权重量化；encoder/joiner 选择 MatMul，decoder 选择 MatMul 和 Gather。实际既有 CPU 部署又只用了其中部分量化产物，需要逐文件记录，不能只写“INT8”。

[ONNX Runtime 官方说明](https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html) 区分运行时计算激活量化参数的动态量化与使用校准数据确定参数的静态量化。RKNN PTQ 与这套 CPU 动态量化在算子覆盖、量化参数、激活处理和浮点残留上可能不同。两边都标 INT8 仍只能先称为“INT8 部署方案比较”，不能直接将结果当作纯后端加速。需要核验实际编译层及运行精度，才能明确受控程度。

## 尝试顺序与退出条件

- 先用同一 ONNX、同版 toolkit、相同 target 和 runtime 构建未量化 RKNN 控制组。若它也失败，应先判断图/编译器/运行库问题，不归咎 INT8。
- 再尝试 encoder INT8，decoder/joiner 先保留未量化控制版本；这必须命名为混合精度候选。之后按结果再尝试其余模块，不承诺所有层都能 INT8。
- 每次构建保存版本、量化配置、校准张量 hash、编译警告及实际层精度；先加载和单样本，再做现有小语料功能/有限质量检查，最后才测资源。
- 若默认 PTQ 明显失真，优先定位误差层；[RKNN v2.2.0 混合量化官方示例](https://github.com/airockchip/rknn-toolkit2/blob/v2.2.0/rknn-toolkit2/examples/functions/hybrid_quant/README.md) 提供分层误差分析和混合精度路径，但这只是可选后续工具，不证明当前 Zipformer 已适配。
- 校准与有参考转写的评测尽量分开。小校准集可用于可行性探索，不能宣称覆盖真实机器人全部分布；失败日志也保留为新实验。

当前未知：INT8 编译能否成功、状态接口能否保持兼容、实际量化层覆盖、是否存在回退、文本变化和资源收益。这些均须由新的转换与上板证据回答。

## 转换环境的后续核查

RKNN 2.3.2 的 [ARM64 CP38 官方依赖表](https://github.com/airockchip/rknn-toolkit2/blob/v2.3.2/rknn-toolkit2/packages/arm64/arm64_requirements_cp38.txt) 固定 `onnxoptimizer==0.2.7`；该依赖在板端需要源码构建。本次依赖构建达到480秒预算后停止，保留日志，不将环境准备超时写成模型量化失败。

后续核实正式 [RKNN 2.5.0 ARM64 CP38 依赖表](https://github.com/airockchip/rknn-toolkit2/blob/v2.5.0/rknn-toolkit2/packages/arm64/arm64_requirements_cp38.txt) 已移除 `onnxoptimizer`，并提供对应 [官方 ARM64 CP38 wheel](https://github.com/airockchip/rknn-toolkit2/blob/v2.5.0/rknn-toolkit2/packages/arm64/rknn_toolkit2-2.5.0-cp38-cp38-manylinux_2_17_aarch64.manylinux2014_aarch64.whl)（38,961,358字节）。因此可建立**独立的2.5.0候选转换环境**，严格使用该版本wheel及配套依赖，不对2.3.2环境直接删依赖。

这条路线只解决转换工具环境的候选准备，尚不能证明现有Zipformer可转换为INT8、与板端runtime兼容或带来性能收益。编译器版本改变也必须在未量化控制组中验证，不能将新旧编译器差异混为量化效果。

## 实测状态补充

以上保留源码调查时的未知项。后续已执行[INT8 PTQ探索](../experiments/rk3566/2026-10-21-asr-int8-ptq/results.md)：joiner成功构建并有实际INT8 NPU层执行，但混合ASR候选质量明显退化；encoder转换预算内未完成，完整INT8路径尚不可用。不能将实际退化倒推为上游原先关闭量化的原因。
