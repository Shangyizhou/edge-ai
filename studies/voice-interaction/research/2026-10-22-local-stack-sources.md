# RK3566 中文离线语音栈：官方来源核查

日期：2026-10-22。阶段：文献筛选，未运行模型。本次不采用历史板端实测的速度、质量或资源结论。阅读主题首页、roadmap、plan及平台部署说明，仅以其确认研究范围与设备背景。以下尺寸是发布文件大小，不是RSS、PSS或运行内存。

## 结论与证据边界

优先建立 CPU 基线：中文流式 Zipformer 14M + Melo 中文 ONNX + Qwen2.5 0.5B Q4_K_M。备用路线分别为 RK3566 专用 RKNN bilingual Zipformer、研究用途 Matcha Baker、Qwen3 0.6B Q8_0。这是待验证组合；中文远场质量、首段语音延迟、全链路CPU/内存及与视觉共跑均 UNKNOWN。

当前需求是本地机器人听说交互。并无用户确认的 CER、延迟、功耗、内存硬门槛；不能从模型可下载推导交互验收通过。

## ASR

- **CPU主候选**：`sherpa-onnx-streaming-zipformer-zh-14M-2023-02-23`。官方文档提供增量麦克风识别；FP32文件为 encoder/decoder/joiner `*-epoch-99-avg-1.onnx`。官方 INT8 示例实际使用 INT8 encoder、FP32 decoder、INT8 joiner，不能写全图INT8。三文件约21M+7.2M+1.7M；FP32约39M+7.2M+6.8M。HF revision `204ad334e2e683fd295359930cc16fc0432a23ac`，模型卡 Apache-2.0。冻结 sherpa-onnx v1.13.8 / ONNX Runtime CPU；ORT实际构建版本必须在执行前记录。中文单语言，不默认适合英文混说。[官方部署文档](https://k2-fsa.github.io/sherpa/onnx/pretrained_models/online-transducer/zipformer-transducer-models.html) · [发布者模型卡](https://huggingface.co/csukuangfj/sherpa-onnx-streaming-zipformer-zh-14M-2023-02-23)
- **NPU备选**：官方文档明确 RK3588 示例可以改用 RK3566 专用制品；不能把RK3588文件直接给RK3566。当前资产 `sherpa-onnx-rk3566-streaming-zipformer-bilingual-zh-en-2023-02-20.tar.bz2` 在release API的创建日期为2026-10-15，SHA256 `28e3f8949c93ef9cafbc7cb2ec7398f76730ff0309c7ed2d508e2afd22f28228`。内部compiler/runtime/实际精度尚未核对，不继承历史2.2.0环境结论。更小 `...small-bilingual-zh-en-2023-02-16.tar.bz2` 同日发布，SHA256 `74c38b5f2e021bfee8c4ad6646b85b2c88d050076d815e8821a56e0754799ebe`。zh14M的RKNN成品未在已查官方文档确认，标 investigate。[官方RKNN文档](https://k2-fsa.github.io/sherpa/onnx/rknn/models.html) · [release资产身份API](https://api.github.com/repos/k2-fsa/sherpa-onnx/releases/tags/asr-models)
- **扩展调查**：`sherpa-onnx-streaming-paraformer-bilingual-zh-en.tar.bz2` 是真正在线模型，有INT8 encoder/decoder约158M+68M，FP32约607M+218M，不支持时间戳。相较14M增加资源预算，是中文混说/方言方向的备用实验，不凭大小判定不能部署；当前未确认RK3566 RKNN路径和上游权重许可。[官方Paraformer文档](https://k2-fsa.github.io/sherpa/onnx/pretrained_models/online-paraformer/paraformer-models.html)

## TTS

- **主候选**：`vits-melo-tts-zh_en.tar.bz2`，HF `csukuangfj/vits-melo-tts-zh_en` revision `a0d5c6a264c0ef92d70d8661d8cc502d79627cd6`；`model.onnx` 为FP32基线，`model.int8.onnx` 为独立待测制品。官方文档说明163MB、44.1kHz、一名说话人，英文限lexicon已有词。上游 `myshell-ai/MeloTTS-Chinese` revision `af5d207a364ea4208c6f589c89f57f88414bdd16` 明示MIT；转换仓模型卡无license元数据，保留来源及MIT文本，不能把sherpa代码许可证当权重许可。使用 sherpa-onnx v1.13.8 / ORT CPU，不宣称神经级增量TTS；可用分句提交减少首次等待，需另测。[官方ONNX说明](https://k2-fsa.github.io/sherpa/onnx/tts/pretrained_models/vits.html) · [上游模型卡](https://huggingface.co/myshell-ai/MeloTTS-Chinese) · [转换制品](https://huggingface.co/csukuangfj/vits-melo-tts-zh_en)
- **仅研究备选**：`matcha-icefall-zh-baker/model-steps-3.onnx`（约72M）+ `vocos-22khz-univ.onnx`（约51M），22.05kHz中文女声，含lexicon/tokens及日期、数字、电话FST。声学模型HF revision `f74e0b9e5bc0517becc070e9d51e0853f485e82d`。使用 sherpa-onnx v1.13.8 / ORT CPU FP32。官方明确 Baker 训练集仅非商业用途；产品商业部署不能默认入选。文档Raspberry Pi 4结果不是RK3566测量，不外推。[官方Matcha说明](https://k2-fsa.github.io/sherpa/onnx/tts/pretrained_models/matcha.html)
- **未入主候选**：VITS AISHELL3发布者提供 `vits-aishell3.onnx` 和 `vits-aishell3.int8.onnx`，HF revision `e3e808eaab2385b812286c6707323362251bba65`，模型卡缺license。AISHELL3数据集Apache-2.0不能自动等同此权重许可；官方目录显示8kHz输出，语音带宽也需考虑。[转换作者模型卡](https://huggingface.co/csukuangfj/vits-zh-aishell3) · [数据集](https://www.openslr.org/93/)

## LLM

- **主候选**：`Qwen/Qwen2.5-0.5B-Instruct-GGUF` revision `9217f5db79a29953eb74d5343926648285ec7e67`，`qwen2.5-0.5b-instruct-q4_k_m.gguf`，491400032 bytes，SHA256 `74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db`，Apache-2.0。官方提供 llama.cpp 用法。CPU、短上下文作为机器人基线；文件小不等于中文任务成功率够用。[官方模型卡](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF)
- **备选**：`Qwen/Qwen3-0.6B-GGUF` revision `23749fefcc72300e3a2ad315e1317431b06b590a`，官方仓当前仅 `Qwen3-0.6B-Q8_0.gguf`，639446688 bytes，SHA256 `9465e63a22add5354d9bb4b99e90117043c7124007664907259bd16d043bb031`，Apache-2.0。对话用 `/no_think` 或运行框架正确关闭thinking，并保留chat模板；不能把思考内容送TTS。不能写成官方Q4_K_M制品；自量化是新制品需hash及质量复验。[官方模型卡](https://huggingface.co/Qwen/Qwen3-0.6B-GGUF)
- **更新候选观察**：`Qwen/Qwen3.5-0.8B` revision `2fc06364715b967f1860aea9cf38778875588b17`，Apache-2.0，混合架构、带视觉编码器。llama.cpp官方README已以 `ggml-org/Qwen3.5-0.8B-GGUF` 为示例，该runtime维护者仓revision `807dfd9a6fadbf703207aac3bfb0b2b3040d077c` 提供 `Qwen3.5-0.8B-Q4_0.gguf` / Q8_0 / BF16。与旧llama.cpp b6500不能默认兼容；升级runtime并验证纯文本CPU路径后才进入比较，不因“0.8B”或新版本自动胜出。[Qwen模型卡](https://huggingface.co/Qwen/Qwen3.5-0.8B) · [llama.cpp](https://github.com/ggml-org/llama.cpp) · [runtime维护者GGUF](https://huggingface.co/ggml-org/Qwen3.5-0.8B-GGUF)
- **不选官方RKLLM NPU路线**：官方 release-v1.3.1 支持平台表列 RK3588、RK3576、RK3562、RV1126B，没有RK3566；RKNN支持RK3566不能推出RKLLM支持。LLM维持llama.cpp CPU基线；Mali GPU后端性能及BSP驱动兼容仍未知。[官方RKLLM平台表](https://github.com/airockchip/rknn-llm)

## 执行前冻结

模型revision、确切文件SHA256、sherpa/ORT/llama commit、CPU编译参数、线程、上下文、ASR端点和输入块大小必须写入新实验manifest。首次可用partial、说完到final、LLM首token与首可播句、TTS首PCM和实际扬声器出声边界分别记录。分句TTS不是自动具备全双工打断、回声消除或连续交互恢复；这些留给完整链路验收。

模型大小与许可证字段通过发布者HF API核对；GitHub release日期及digest通过官方API核对。未下载模型，未保存录音，未把第三方或其它硬件速度作为本板证据。网页及API为2026-10-22查阅时状态；执行时按上列revision和hash固定，避免滚动release覆盖。
