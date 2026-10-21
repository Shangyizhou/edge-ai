# 常驻流式 ASR：测量方法与接口语义

日期：2026-10-21（Asia/Shanghai）。本注记固定核查 Sherpa-ONNX **v1.13.8**，仅讨论方法；性能数字由实际运行报告提供。模型/runtime仍使用本机已验证组合，不因 API 文档版本而更换模型。

## API 与计时边界

常驻一个 `SherpaOnnxOnlineRecognizer`，为独立文件建立新 stream；连续会话遇到 endpoint 时先保存结果再 reset，继续喂入 PCM。`InputFinished` 表示之后不再输入音频，只在完整输入结束后调用，随后 drain `IsReady`。它不是每句的端点通知。[C API](https://github.com/k2-fsa/sherpa-onnx/blob/v1.13.8/sherpa-onnx/c-api/c-api.h)、[输入结束实现](https://github.com/k2-fsa/sherpa-onnx/blob/v1.13.8/sherpa-onnx/csrc/online-stream.cc)

规则默认是 rule1 无需识别出文字的 2.4 秒静音、rule2 已识别出文字后的 1.2 秒静音、rule3 总句长 20 秒；任一规则成立即可触发。扫描 1.2/0.8/0.6 秒应只改 rule2，并固定其余规则。这里的“静音”来自解码器连续 blank，**不是声学 VAD 或真人末音标注**。[规则定义](https://github.com/k2-fsa/sherpa-onnx/blob/v1.13.8/sherpa-onnx/csrc/endpoint.h)、[规则判定](https://github.com/k2-fsa/sherpa-onnx/blob/v1.13.8/sherpa-onnx/csrc/endpoint.cc)、[RKNN 解码与端点](https://github.com/k2-fsa/sherpa-onnx/blob/v1.13.8/sherpa-onnx/csrc/rknn/online-recognizer-transducer-rknn-impl.h)

RKNN stream reset保留 encoder 状态，清理/更新解码结果及已处理帧计数；底层特征及未消费输入不被丢弃。因而跨独立测试样本用新 stream，避免前句上下文影响。RKNN `IsReady` 需已输入特征足以覆盖模型 `ChunkSize`，每次消费 `ChunkShift`；这两项来自模型，不能把输入 20ms PCM 等同于每 20ms 推理或输出一次。减小喂入块不一定降低模型的固有前看延迟。[RKNN stream实现](https://github.com/k2-fsa/sherpa-onnx/blob/v1.13.8/sherpa-onnx/csrc/rknn/online-recognizer-transducer-rknn-impl.h)、[模型块元数据](https://github.com/k2-fsa/sherpa-onnx/blob/v1.13.8/sherpa-onnx/csrc/rknn/online-zipformer-transducer-model-rknn.cc)

模型 token timestamps 为解码时间轴，RKNN结果还提供分段 start_time；这些不是结果送到调用方的墙钟时间，更不是人工末音时间。[结果转换](https://github.com/k2-fsa/sherpa-onnx/blob/v1.13.8/sherpa-onnx/csrc/rknn/online-recognizer-transducer-rknn-impl.h)

计时应分别保存模型加载、首个非空 partial、每次 decode 的墙钟与累计时间、PCM原定到达时间和实际提交时间、endpoint、EOF drain。真实节奏输入按单调钟绝对截止时间回放，落后时不人为重设时间起点。文件末补静音也必须以真实节奏喂入，并独立记录补静音长度；否则会低估端点等待。计算RTF不含回放sleep，累计推理时间/音频长度；墙钟RTF则必然接近1或更高，应分开标注。积压可报告PCM提交滞后，但它不等于模型内部全部待处理时间。

## 本轮轻量样本及标签限制

准备位置：`/home/orangepi/.cache/ros-robot-edge-benchmark/streaming/fixtures/metadata.json`。JSON保存源绝对路径、源/产物SHA256、裁剪偏移、样本数、能量锚点算法。四个文件共 **29.077125 秒**，另计实时补静音。

| id | 长度（秒） | 能量末端锚点（秒） | 来源/处理 |
| --- | ---: | ---: | --- |
| official0 | 10.053125 | 9.80 | 本机历史已验证RK3566模型包 `test_wavs/0.wav` |
| command | 5.888 | 4.48 | 已有历史真人命令fixture，PCM不变，重写WAV容器 |
| command-pause080 | 6.368 | 4.96 | command的1.94–2.26秒低能量区间换成0.8秒零样本 |
| command-pause120 | 6.768 | 5.36 | 同一区间换成1.2秒零样本 |

能量锚点定义：16kHz PCM16，依次计算不重叠20ms窗RMS，取最后一个高于 **−35dBFS** 窗的右边界；不足20ms的最后一窗按实际长度截断。**这不是经听辨校验的真人说话结束时间**。延迟只能写“相对能量末端锚点的 endpoint 延迟”，不能写真人末音P95或用户说完后的准确等待。原命令检测到的有效能量从1.26秒开始，低能量区间1.94–2.26秒；派生文件精确删除源样本 `[31040,36160)`，分别插入12800/19200个零样本。此区间仅按能量选取，未做人听或音素校验；不能保证完全无轻声语音，合成静音也不同于真实环境噪声。

命令参考文本“机器人请让底盘上前移动二十厘米”来自先前CPU/NPU识别一致性记录，**不是独立人工转写**。可比较与该既有文本的一致性，以及受控停顿是否触发句中切分，但不能声称数据集准确率或代表性提前截断率。官方文件也没有本轮人工转写。已存在的“开始人物跟踪”fixture由Piper生成，不应冒充真人语音，且过短，不优先用于共跑调度测量。[已有实测记录](../../../reports/rk3566/2026-10-21/results.md)、[模型官方下载入口](https://k2-fsa.github.io/sherpa/onnx/rknn/models.html)

样本数很小，建议逐条公开事件时间与文本，将P95标作本小样本/解码事件统计，不能外推真实对话分布。与YOLO共跑保持缩放后640×352、30fps，并报告实际输入/完成帧数、检测P95、ASR计算RTF与端点等待的变化；固定图像回放不能代替真实相机链路。

## 为什么1.2秒与0.8秒可能得到相同端点

只读检查本机已部署历史 `encoder.rknn` 的内嵌 custom metadata，确认 **`T=71;decode_chunk_len=64`**。文件SHA256为 `f98fe4e452b9e1c3783ba4c47fc96d4e8ae4ae6a63aa796fd810e324d914a492`，完整路径见样本JSON的模型目录。官方RKNN实现将 `T` 作为 `ChunkSize`、`decode_chunk_len` 作为 `ChunkShift`；10ms特征步长下分别是 **710ms窗口、640ms推进**。这不是说纯计算需要640ms，而是解码状态按640ms音频跨度更新。初次可解码还受特征窗、严格小于的 `IsReady` 判断和输入块对齐影响，不能仅拿710ms推算首字时延。[元数据读取及返回](https://github.com/k2-fsa/sherpa-onnx/blob/v1.13.8/sherpa-onnx/csrc/rknn/online-zipformer-transducer-model-rknn.cc)、[解码步进](https://github.com/k2-fsa/sherpa-onnx/blob/v1.13.8/sherpa-onnx/csrc/rknn/online-recognizer-transducer-rknn-impl.h)

RKNN端点把 `num_trailing_blanks × 4 × 0.01` 转为秒，即每个blank计40ms；但调用者只能在完整decode更新结果后看到新的累计blank。如果某一步累计静音同时跨过0.8和1.2秒，两种阈值就会在同一输入游标触发。因而本轮两档端点游标相同，与模型推进粒度一致；**单凭时间相同不能断言参数未生效，也不能确证具体一次事件的唯一原因**，需要逐步blank计数才能彻底归因。另有rule1/rule3并行触发，不能忽略。[RKNN端点换算](https://github.com/k2-fsa/sherpa-onnx/blob/v1.13.8/sherpa-onnx/csrc/rknn/online-recognizer-transducer-rknn-impl.h)

配置转发链路已核查：本轮probe设 `enable_endpoint=1`、`rule2_min_trailing_silence=endpoint`；v1.13.8 C API将该非零值传入 `endpoint_config.rule2.min_trailing_silence`；RKNN识别器构造时用整个 `endpoint_config` 创建端点模块。因此从源码上没有发现rule2被忽略。要改变640ms固有推进量需要不同chunk结构的模型/导出产物，不能简单把PCM输入块从100ms改为20ms就承诺相应收益。[C API配置转发](https://github.com/k2-fsa/sherpa-onnx/blob/v1.13.8/sherpa-onnx/c-api/c-api.cc)、[RKNN构造与判定](https://github.com/k2-fsa/sherpa-onnx/blob/v1.13.8/sherpa-onnx/csrc/rknn/online-recognizer-transducer-rknn-impl.h)
