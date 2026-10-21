# ASR / TTS 板端 benchmark 一手资料底稿

检索日期：2026-10-21（Asia/Shanghai）。这是调研事实与候选实验，不冻结用户决策。仅阅读本地资料、官方网页/源码与小型 GitHub 元数据；没有下载权重、安装运行时、执行推理、录音、播放或驱动硬件。

## 1. 先固定模型身份

旧 ASR 是 `sherpa-onnx-streaming-zipformer-small-bilingual-zh-en-2023-02-16`，实际使用 int8 encoder、FP32 decoder、int8 joiner 和配套 tokens；本机真实文件与旧仓 LFS SHA-256 对应。旧 vendor Sherpa 1.11.3，与已有外置 1.13.8 应分别记录，不能把升级运行时的影响当作配置影响。来源：[本地资产审计](/home/orangepi/code/ros-robot/.scratch/offline-agent-integration/legacy-offline-agent-source-audit.md)。

TTS 要区分 **推理引擎、训练出的语音模型、文本前端、声码器/采样率**。SummerTTS 是 Eigen/C++ 的 VITS 实现；Piper 是另一套运行时与 voice 格式；sherpa-onnx 能加载 VITS、Melo 导出以及 Piper 模型。因此“Piper 与 sherpa 对比”可以是同一 voice 的引擎对比，也可以是不同 voice 的整体方案对比，报告必须明确两者。[SummerTTS](https://github.com/huakunyang/SummerTTS)、[sherpa 的 Piper 转换指南](https://k2-fsa.github.io/sherpa/onnx/tts/piper.html)。

当前小雅权重是另一项 Piper voice，不是旧 SummerTTS；用户已明确不使用小雅，不能让它成为主测试模型。旧 SummerTTS `single_speaker_fast.bin` 本地仍是 133 字节 LFS 指针，目标 80,050,316 字节，SHA-256 `87b774813258a3636b3f1d9adddd3652ede503b4e8f4eb3c39065cba2a4951c4`。[本地资产审计](/home/orangepi/code/ros-robot/.scratch/offline-agent-integration/legacy-offline-agent-source-audit.md)。

**公开获取路径已经找到，无须先要求用户提供 Summer 权重。** 官方 README 的 2025-07-10 更新说模型已直接放进仓库；本次 GitHub contents API 返回 `models/single_speaker_fast.bin` 大小 80,050,316，Git blob SHA-1 `d7189bf49094c765a4cff960f9b69aec344355df`，并给出公开 raw 下载地址。尺寸与本地目标一致；尚未下载核验 SHA-256，因此当前只能证明官方真实大文件可获取，不能宣布与旧权重逐字节相同。[官方模型页面](https://github.com/huakunyang/SummerTTS/blob/main/models/single_speaker_fast.bin)、[官方 contents 元数据](https://api.github.com/repos/huakunyang/SummerTTS/contents/models/single_speaker_fast.bin)、[README](https://github.com/huakunyang/SummerTTS)。

## 2. 部署与 API：已有足够材料实现小型适配器

| 方案 | 直接入口 | 核心参数 / 约束 |
| --- | --- | --- |
| 旧 Zipformer ASR | Sherpa `OnlineRecognizer.from_transducer`；AcceptWaveform → IsReady/DecodeStream → GetResult → IsEndpoint/Reset | threads、CPU provider、greedy/modified beam、max active paths、endpoint；encoder/decoder/joiner 与 tokens 必须成套 |
| SummerTTS | 独立 CMake；`infer(text, sid, lengthScale, dataLen)` 返回 int16 PCM；模型加载与 infer 分开计时 | sid=0 单说话人；lengthScale 越大越慢；线程通过 OpenMP/Eigen 控制，不是现成的 `--num-threads` CLI |
| sherpa VITS / Melo | `OfflineTtsConfig` / `OfflineTts` / `generate` 或 C++ CLI `sherpa-onnx-offline-tts` | num_threads、provider、model/tokens/lexicon/dict/FST、sid、speed、noise_scale、noise_scale_w、max_num_sentences |
| Piper | 当前维护仓 `OHF-Voice/piper1-gpl`；`PiperVoice.load` 后重复 `synthesize` / `synthesize_wav` | `.onnx` + `.onnx.json`；speaker、length_scale、noise_scale、noise_w_scale；源码当前创建默认 ORT SessionOptions，直接 load API 没有 threads 参数 |

来源：[Sherpa 流式示例](https://github.com/k2-fsa/sherpa-onnx/blob/master/python-api-examples/speech-recognition-from-microphone.py)、[Summer API](https://github.com/huakunyang/SummerTTS)、[Sherpa 非播放 TTS 示例](https://github.com/k2-fsa/sherpa-onnx/blob/master/python-api-examples/offline-tts.py)、[Piper Python API](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/API_PYTHON.md)、[Piper Session 源码](https://github.com/OHF-Voice/piper1-gpl/blob/main/src/piper/voice.py)。

旧 Summer 和官方 CMake 都启用 `-fopenmp`。Eigen 官方给出 `OMP_NUM_THREADS`、`omp_set_num_threads`、`Eigen::setNbThreads`；只有部分运算能并行，因此设置 4 不能等同于全部计算使用 4 核，需记录实际 CPU 与线程。Piper 做 1/2/4 线程对比应显式控制 ORT session（小型 benchmark 适配器或支持该控制的 C API），不能仅设置 `OMP_NUM_THREADS` 就声称 ORT 线程已受控。[官方 CMake](https://github.com/huakunyang/SummerTTS/blob/main/CMakeLists.txt)、[Eigen 线程文档](https://libeigen.gitlab.io/eigen/docs-nightly/TopicMultiThreading.html)、[Piper 源码](https://github.com/OHF-Voice/piper1-gpl/blob/main/src/piper/voice.py)。

原 `rhasspy/piper` 已归档，README 指向 `OHF-Voice/piper1-gpl`。部署时固定实际版本/commit、构建、ORT、前端资源，而不是写一个模糊的“Piper 最新版”。[原仓 README](https://github.com/rhasspy/piper/blob/master/README.md)。

## 3. 官方参考能说明什么

Sherpa 官方公布 **Raspberry Pi 4 Model B Rev 1.5** 的 TTS RTF 表，不是 RK3566 实测。挑选与本任务相关的行如下；数值用于选实验优先级，不能作为板端验收值。

| Sherpa 上的 voice | 1 线程 RTF | 2 线程 RTF | 4 线程 RTF |
| --- | ---: | ---: | ---: |
| Melo zh_en | 6.727 | 3.877 | 2.518 |
| VITS zh-ll | 4.275 | 2.494 | 1.593 |
| Piper en_US glados（英文参考） | 0.812 | 0.480 | 0.349 |
| Piper en_US libritts_r（英文参考） | 0.790 | 0.493 | 0.357 |

来源：[官方 RTF 表](https://k2-fsa.github.io/sherpa/onnx/tts/pretrained_models/rtf.html)。它不包含本机 Summer 与中文 huayan 的对照；英文 Piper 速度也不能直接移植到中文。最直接的启示是：**“约 115MB/163MB，所以较轻、能实时”不成立**，具体模型运算结构与输出采样率都要记录。

官方模型页列 Melo zh_en 163MB、44.1kHz、1 speaker；zh-ll 约115MB、16kHz、5 speakers。Melo 英文仅能处理 lexicon 已有词，需保留中英混合/OOV 现象。页面模型清单、tar 包大小与实际 ONNX 字节数也应分别存储。[官方 VITS 模型页](https://k2-fsa.github.io/sherpa/onnx/tts/pretrained_models/vits.html)。

中文 Piper `zh_CN-huayan-medium` 官方配置为22,050Hz、espeak `cmn`；length_scale=1、noise_scale=0.667、noise_w=0.8，可作为固定默认起点。[官方 voice 配置](https://huggingface.co/rhasspy/piper-voices/blob/main/zh/zh_CN/huayan/medium/zh_CN-huayan-medium.onnx.json)。Sherpa 转换指南对标准 Piper 路线主要增加 ONNX metadata、从 JSON 生成 tokens、附 espeak 数据，因此可以保留同一 tensor 权重进行引擎对比；转换后整文件 hash 会变，应另外验证图/tensor 身份。中文前端、句切及默认噪声必须对齐，不能假定自动一致。[官方转换指南](https://k2-fsa.github.io/sherpa/onnx/tts/piper.html)。

## 4. 指标与实验口径建议（待收敛）

| 类别 | 推荐记录 | 意义和易错点 |
| --- | --- | --- |
| 共同 | 初始化/模型加载时间、首次请求、warm 请求；wall time、user/system CPU time、RSS 峰值、PSS（可得时）、进程/线程数、温度/频率/内存可用/swap | 文件大小不能替代运行 RAM；CPU% 需明确100%表示1核还是整板，保留 CPU seconds 可重算 |
| TTS | 每句总合成耗时、输出音频时长、RTF=合成秒/音频秒、首个可用 PCM 时延、持续 PCM 交付间隔、句长；均值/中位/P95/失败率 | RTF<1 才是该测例平均快于播放；首段时延不是总时延；分句吐出不等于单句内部流式；不把实际扬声器耗时混入纯推理 |
| ASR 吞吐 | 不按真实时间等待的文件解码耗时/音频时长、总 CPU、峰值 RSS | 这是计算速度；不能当作用户说完后的等待时间 |
| ASR 流式 | 按时间重放 PCM 的首个非空 partial、音频积压、真实语音末尾到 endpoint/final 的 lag、endpoint 漏检/提前切断 | 必须有语音末尾标注或另存估计方法；真实重放 wall/音频比通常接近1，不能拿它当 compute RTF |
| ASR 质量 | 中文 CER=(替换+删除+插入)/参考字符数；英文 WER；命令关键词正确率；逐句原始文本与标准化文本 | CER 标准化规则固定；无人工/数据集 reference 只测性能，不能宣称识别准确率；TTS 回录不代表真人识别质量 |
| TTS 质量 | 发音、数字/日期/量词/多音字/中英、截断/静音/爆音；保留待听音频与逐句备注 | 内部少量听测是工程观察，不冒称受控 MOS；ASR 识别合成音的分数不能代替音质 |

RTF 的官方执行例子按 `Elapsed seconds / Audio duration` 输出；上述采样/分层是针对可重测 benchmark 的工程建议。[ASR 官方例子](https://k2-fsa.github.io/sherpa/onnx/pretrained_models/online-transducer/zipformer-transducer-models.html)、[TTS 官方非播放示例](https://github.com/k2-fsa/sherpa-onnx/blob/master/python-api-examples/offline-tts.py)。主观语音质量的正式 MOS 设计有受控方法，不能从一次内部试听推断。[ITU-T P.800](https://www.itu.int/rec/T-REC-P.800-199608-I/en)。

候选 pilot：

1. **ASR 保持旧精确权重**：CPU线程1/2/4 × greedy，共3组；再在合适线程上加 modified_beam_search、max_active_paths=4（示例默认），可加8作扩展但8是实验采样点。第二阶段对照同发布包 FP32与旧混合int8；二者必须同一语料，报告CER差异。
2. **ASR endpoint 另做交互实验**：先按官方默认 rule1=2.4秒静音、rule2=1.2秒静音且已有非空识别、rule3=20秒；再只改 rule2为0.6/0.8秒观察提前切断与等待。这两个较短值是待测假设，不是业界统一标准。[endpoint 源码](https://github.com/k2-fsa/sherpa-onnx/blob/master/sherpa-onnx/csrc/endpoint.h)。
3. **TTS 主配置**：Summer fast、Sherpa zh-ll、Sherpa Melo zh_en、Piper huayan，CPU线程1/2/4；同一套短/中/长中文，默认语速、固定speaker/噪声；加 Sherpa huayan 同权重组以区分引擎与 voice。先串行独立测量，避免把同时加载的资源竞争混入基线。
4. **少量扩展**：Summer mid 对 fast；最佳线程配置上 lengthScale=0.8/1.0/1.2；Sherpa max_num_sentences=1 对较大批处理，以首段延迟与总RTF一同判断。0.8/1.2是采样点，改变语速也改变音频时长，必须保留实际秒数，不能仅比RTF挑“最快”。

解码选择与默认 beam 来源：[官方流式 API 示例](https://github.com/k2-fsa/sherpa-onnx/blob/master/python-api-examples/speech-recognition-from-microphone.py)。VITS 噪声默认0.667/0.8、length_scale=1来自[官方 VITS 配置](https://github.com/k2-fsa/sherpa-onnx/blob/master/sherpa-onnx/csrc/offline-tts-vits-model-config.h)；这里没有假定更改噪声就必然提速或提升音质。

## 5. NPU 的精确边界

Sherpa 官方 RKNN 支持板列表确实含 **RK3566**。模型页开头明确说明可把示例的 `rk3588` 替换为 `rk3566`，且 Release API 本次确认存在目标专用旧 small bilingual Zipformer 包。不能把 RK3588 模型直接当作 RK3566 模型；本次可直接获取 RK3566 转换产物，无须从现有 ONNX 重新转换。[官方 RKNN 支持板列表](https://k2-fsa.github.io/sherpa/onnx/rknn/index.html)、[模型列表](https://k2-fsa.github.io/sherpa/onnx/rknn/models.html)。官方另明确警告不能把 rknn_model_zoo 的 Zipformer 给 Sherpa 使用，自行转换要从 PyTorch checkpoint 开始，不能任意把现有 Sherpa ONNX 直接转 RKNN。[导出说明](https://k2-fsa.github.io/sherpa/onnx/rknn/export.html)。

Summer 官方呈现的是 Eigen CPU，没有现成 RKNN 推理入口；Piper 当前源码为 ORT CPU/CUDA入口。Sherpa “支持RK NPU”是框架能力，不能据此宣称本次VITS/Melo/Piper语音模型可在RK3566直接NPU推理。若扩展NPU，模型转换与后端验证应单独记录，CPU基线先提供可比结果。[Summer](https://github.com/huakunyang/SummerTTS)、[Piper provider 源码](https://github.com/OHF-Voice/piper1-gpl/blob/main/src/piper/voice.py)、[Sherpa RKNN](https://k2-fsa.github.io/sherpa/onnx/rknn/index.html)。

## 6. 尚未完成的验证

- 官方 Summer bin 下载后的 SHA-256 与旧LFS目标核验，以及旧模型在板上加载。
- 实际板型/CPU/内存/内核/温控/频率与部署环境的实验清单；本报告不将用户给出的RK3566配置冒充本次探测结果。
- Piper 具体固定版本、ARM64与本机Python兼容；显式ORT线程适配器；huayan 在两个引擎的前端一致程度。
- 固定有reference的真人ASR语料，以及TTS试听样本；没有这些不能产生可用性排名。
- 所有 RK3566 推理时延、资源与质量结果。本次官方外板数字没有填入本板结果列。

## 7. 继续部署时的 RKNN 事实（2026-10-21）

用户随后已授权实际推进并要求 NPU 跑通。本节是部署核查，尚未声称模型推理通过。

只读本机观察：aarch64、Ubuntu20.04；系统 `/lib/librknnrt.so` 最终指向 `/usr/lib/librknnrt.so`，strings 为 `1.4.0 (a10f100eb@2022-09-09T09:07:14)`；`/sys/module/rknpu/version` 为 `0.9.6`。`/sys/class/devfreq/fde40000.npu` 存在，可用频率200/297/400/600/700/800/900MHz，governor=`rknpu_ondemand`，观察时600MHz。用户已在video组，`/dev/dri/card0`、`card1`、`renderD128`、`renderD129`存在。现有 CPU Sherpa 的ldd不含librknnrt，不能宣称它已有RKNN支持。

官方可获取、已核Release/API元数据的部署资产：

| 资产 | 下载字节 | 标识 |
| --- | ---: | --- |
| `sherpa-onnx-rk3566-streaming-zipformer-small-bilingual-zh-en-2023-02-16.tar.bz2` | 49,600,373 | 官方Release SHA-256 `74c38b5f2e021bfee8c4ad6646b85b2c88d050076d815e8821a56e0754799ebe` |
| `sherpa-onnx-v1.13.8-rknn-linux-aarch64-shared.tar.bz2` | 28,250,944 | 官方Release SHA-256 `6fa85c2615feb5d3e501cbeee00f6f321720164ea50239683e7c37a3baea8353` |
| `librknnrt.so` at RKNN-Toolkit2 `v2.2.0` | 7,192,616 | Git blob SHA-1 `22362e8704bfb83245202ea68a2d293056ffb749`；本地下载后另算SHA-256 |

直接来源：[RK3566模型下载](https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-rk3566-streaming-zipformer-small-bilingual-zh-en-2023-02-16.tar.bz2)、[1.13.8 RKNN运行时下载](https://github.com/k2-fsa/sherpa-onnx/releases/download/v1.13.8/sherpa-onnx-v1.13.8-rknn-linux-aarch64-shared.tar.bz2)、[Rockchip runtime v2.2.0](https://github.com/airockchip/rknn-toolkit2/blob/v2.2.0/rknpu2/runtime/Linux/librknn_api/aarch64/librknnrt.so)。小型元数据来自[ASR Release API](https://api.github.com/repos/k2-fsa/sherpa-onnx/releases/tags/asr-models)、[Sherpa Release API](https://api.github.com/repos/k2-fsa/sherpa-onnx/releases/tags/v1.13.8)、[Rockchip contents API](https://api.github.com/repos/airockchip/rknn-toolkit2/contents/rknpu2/runtime/Linux/librknn_api/aarch64/librknnrt.so?ref=v2.2.0)。

采用 `/home/orangepi/.cache/ros-robot-edge-benchmark/npu/` 外置部署与 `LD_LIBRARY_PATH`，不替换系统runtime或内核驱动。Sherpa官方安装页给出runtime2.2.0示例，并要求ldd出现librknnrt；模型页说明旧runtime会报 `Invalid RKNN model version 6`。2.2.0在本机driver0.9.6的实际相容性仍需加载和推理确认，不仅凭版本字符串判断。[安装说明](https://k2-fsa.github.io/sherpa/onnx/rknn/install.html)、[已知模型版本错误](https://k2-fsa.github.io/sherpa/onnx/rknn/models.html)。

Python RKNN wheel也存在cp38/aarch64/manylinux_2_27版本，但初轮优先独立C++预制二进制以免改动既有CPU虚拟环境。[官方RKNN wheels索引](https://k2-fsa.github.io/sherpa/onnx/rk-npu.html)。

部署完成：两个压缩包下载后SHA-256均与官方Release digest相同；外置runtime本地SHA-256为 `1170e5f99f2db7ed4d3a4c2bdbed941b7363bd090e0c28b4e210f40614327911`。下载URL、字节数、hash保存在 `/home/orangepi/.cache/ros-robot-edge-benchmark/npu/download-manifest.json`，三个API响应也原样保存在同目录。解压后的encoder/decoder/joiner分别43,451,066 / 7,998,898 / 6,480,159字节。`ldd`已确认选中外置runtime2.2.0和包内ORT，独立可执行程序 `--help` 正常，仍未执行模型。

准备好的推理命令（由协调者与CPU实验串行执行）：

```bash
NPU_ROOT=/home/orangepi/.cache/ros-robot-edge-benchmark/npu
NPU_MODEL="$NPU_ROOT/sherpa-onnx-rk3566-streaming-zipformer-small-bilingual-zh-en-2023-02-16"
LD_LIBRARY_PATH="$NPU_ROOT/runtime-2.2.0" \
  "$NPU_ROOT/sherpa-onnx-v1.13.8-rknn-linux-aarch64-shared/bin/sherpa-onnx" \
  --provider=rknn --num-threads=1 \
  --encoder="$NPU_MODEL/encoder.rknn" \
  --decoder="$NPU_MODEL/decoder.rknn" \
  --joiner="$NPU_MODEL/joiner.rknn" \
  --tokens="$NPU_MODEL/tokens.txt" \
  "$NPU_MODEL/test_wavs/0.wav"
```

**RKNN的num_threads不是CPU线程扫描参数。** 固定1（自动）作为首组；Sherpa1.13.8源码把该参数交给NPU core mask：1为auto、0为core0、负数为其他核/组合。不把CPU的1/2/4矩阵机械套给RK3566 NPU。[固定版本源码](https://github.com/k2-fsa/sherpa-onnx/blob/v1.13.8/sherpa-onnx/csrc/rknn/utils.cc)。

本机 `sherpa-onnx-version` 实际输出：Sherpa1.13.8、Git `11afbd00`、Git date 2026-09-10、ORT1.28.2；runtime字符串确认2.2.0。解压模型SHA-256：encoder=`f5e509c3ce7faadc40dd9d74f6e403414d219bb75ff2d469f456b3724a7d852c`，decoder=`28b259cfd8cb870b6913fbab8b91c68e1b37b8dd847ad25424b645e1b1224774`，joiner=`be7add9881fd645e1d916b3bc05a73efa371a6f0e2cba3442f511407f8c6eb3f`。这标识实际部署产物，不以文档示例日期替代实际版本。

## 8. TTS 候选部署记要（2026-10-21）

已获授权下载官方候选，仍不运行推理，以便协调者串行测量。外置根目录 `/home/orangepi/.cache/ros-robot-edge-benchmark/`。

| 资产 | 下载字节 | 下载后本地SHA-256 |
| --- | ---: | --- |
| `assets/tts/sherpa-onnx-vits-zh-ll.tar.bz2` | 118,810,709 | `f7393d1bbc59709d5f52ea76cd5bceeec62f6a29f9c1f79ff64b4c15ec841f3a` |
| `assets/tts/vits-melo-tts-zh_en.tar.bz2` | 167,006,755 | `e58351ed7149f290a54534538badd4077cdbe6fddc964b24d0bee870415d1514` |
| `assets/tts/vits-piper-zh_CN-huayan-medium.tar.bz2` | 67,255,926 | `dbdfec42b91d9cee31cce9ff4b3e9c305eb6fbf60546d071f7e46273554cce6b` |
| `piper/piper_linux_aarch64.tar.gz` | 26,004,717 | `fea0fd2d87c54dbc7078d0f878289f404bd4d6eea6e7444a77835d1537ab88eb` |
| `assets/tts/piper-huayan-original/zh_CN-huayan-medium.onnx` | 63,201,294 | `9929917bf8cabb26fd528ea44d3a6699c11e87317a14765312420be230be0f3d` |

前三项来自[Sherpa官方tts-models Release](https://github.com/k2-fsa/sherpa-onnx/releases/tag/tts-models)，Piper来自[固定旧Release2023.11.14-2](https://github.com/rhasspy/piper/releases/tag/2023.11.14-2)。这四个历史Release资产API未提供独立digest，故本地hash是复测身份标识，不冒充上游校验签名。huayan原始ONNX来自[官方voice仓](https://huggingface.co/rhasspy/piper-voices/tree/main/zh/zh_CN/huayan/medium)，其SHA-256已与HuggingFace API的LFS oid一致。实际URL、字节、hash保存在 `assets/tts/download-manifest.json` 与 `assets/tts/piper-huayan-original/download-manifest.json`。

Piper原始huayan的4822字节JSON与MODEL_CARD同时下载。JSON SHA-256=`d521dc45504a8ccc99e325822b35946dd701840bfb07e3dbb31a40929ed6a82b`；配置为espeak/cmn、22050Hz、单说话人、默认noise=0.667、length=1、noise_w=0.8。MODEL_CARD记录训练数据HuaYan_TTS、dataset license unknown；这是原模型卡事实，不自行推断许可结论。[配置](https://huggingface.co/rhasspy/piper-voices/blob/main/zh/zh_CN/huayan/medium/zh_CN-huayan-medium.onnx.json)、[模型卡](https://huggingface.co/rhasspy/piper-voices/blob/main/zh/zh_CN/huayan/medium/MODEL_CARD)。

独立Piper路径为 `piper/piper/piper`。板上`--version`实际返回 **1.2.0**，并非当前维护分支；`--help`、`ldd`已通过，依赖包内ORT1.14.1、espeak-ng和piper_phonemize，无需PyTorch/Python升级。默认espeak数据位于 `piper/piper/espeak-ng-data`。此旧版选择是复现实验的已固定部署版本，不称最新版。

Piper该版本没有CLI线程选项。固定源码 `loadModel` 中 `SetIntraOpNumThreads(1)` 是注释，实际使用默认ORT线程；它还关闭图优化、CPU arena与memory pattern。精确1/2/4线程需要小型C++入口，在 `loadVoice` 之前设置 `voice.session.options.SetIntraOpNumThreads(n)`（并记录inter-op等实际设置）；仅 `OMP_NUM_THREADS=n` 不能证明ORT线程受到控制。CPU affinity仅限制可用核数，若采用应明确记为core budget，不冒称线程数。[固定版本piper.hpp](https://github.com/rhasspy/piper/blob/2023.11.14-2/src/cpp/piper.hpp)、[固定版本loadModel](https://github.com/rhasspy/piper/blob/2023.11.14-2/src/cpp/piper.cpp)、[CLI](https://github.com/rhasspy/piper/blob/2023.11.14-2/src/cpp/main.cpp)。

Piper原生日志的infer/RTF仅围绕ORT `session.Run` 计时；外层需要另测包含文本前端和PCM处理的总合成wall time，避免直接与其他引擎全生成时间混比。`--json-input`可保持同一进程多次请求，逐行指定text/output_file；纯文本配单输出文件会先读完整stdin合并，不能误作常驻逐句API。[固定版本源码](https://github.com/rhasspy/piper/blob/2023.11.14-2/src/cpp/piper.cpp)、[主程序](https://github.com/rhasspy/piper/blob/2023.11.14-2/src/cpp/main.cpp)。

现有Sherpa1.13.8 `sherpa-onnx-offline-tts --help` 已本机核查：`--vits-dict-dir`已标记不使用，不必传旧文档中的dict；`--tts-max-num-sentences`默认1；`--vits-data-dir`一旦设置会忽略lexicon。后续配置应以实际固定版本为准。zh-ll路径为 `assets/tts/sherpa-onnx-vits-zh-ll/`，Melo为 `assets/tts/vits-melo-tts-zh_en/`，各使用下列同结构配置，sid固定0作首轮（zh-ll可另列speaker）：

```text
--provider=cpu --num-threads=1
--vits-model=<模型目录>/model.onnx
--vits-tokens=<模型目录>/tokens.txt
--vits-lexicon=<模型目录>/lexicon.txt
--tts-rule-fsts=<模型目录>/phone.fst,<模型目录>/date.fst,<模型目录>/number.fst
--sid=0 --vits-length-scale=1 --tts-max-num-sentences=1
```

Piper原始voice入口配置是 `--model=<缓存>/assets/tts/piper-huayan-original/zh_CN-huayan-medium.onnx --config=<同目录>/zh_CN-huayan-medium.onnx.json --espeak_data=<缓存>/piper/piper/espeak-ng-data`，输出仅落盘不播放。线程与前端未对齐前，报表应把它列成“Piper1.2默认ORT”方案，不能标为受控1线程。

Piper常驻协议已按固定2023源码确认：`--output_dir <绝对目录>`时，每条stdin文本行生成一条WAV，stdout以绝对路径加换行输出并flush，同一进程只loadVoice一次。stderr初始化顺序为 `Loaded voice in … second(s)` → `Initialized piper` → `Output directory: <绝对路径>`，均在第一次 `getline(cin, line)`前；可等最后一条作为ready，单独记进程启动至ready的初始化wall。每次写入文本加换行并flush后，读取对应stdout路径；但源码打印路径时ofstream仍在作用域内，须再等stderr的 `Real-time factor: …`（位于分支作用域结束之后）才将WAV作为完整文件读取，以避免最后close/flush的小竞态。stderr应持续读取，不用quiet屏蔽此协议信号。[固定版本主程序](https://github.com/rhasspy/piper/blob/2023.11.14-2/src/cpp/main.cpp)、[初始化日志实现](https://github.com/rhasspy/piper/blob/2023.11.14-2/src/cpp/piper.cpp)。

### 本轮 Summer / Qwen 的 NPU 后端精确限制

Summer原生实现为Eigen算子与专用`.bin`，没有现成RKNN入口；该本机旧源码的CMake、TTSModel与SynthesizerTrn接口也未出现RKNN/RKLLM。旧llama.cpp构建使用CPU，旧源码CMake未提供RKNN/RKLLM；当前上游llama.cpp后端表亦无Rockchip NPU。Rockchip的独立RKLLM虽列Qwen3等模型家族，但官方支持平台列 **RK3588/RK3576/RK3562/RV1126B，没有RK3566**，并要求在PC转换得到`.rkllm`再用其runtime，不能直接加载本次旧微调GGUF或等同于llama.cpp改一个参数。故本轮应记录“Summer与旧Qwen+llama.cpp无已支持原生RK3566 NPU运行路线”；ASR采用已获取的目标专用RKNN路线实际验证，不用替换模型来冒充其余两项NPU通过。[Summer官方实现](https://github.com/huakunyang/SummerTTS)、[llama.cpp后端表](https://github.com/ggml-org/llama.cpp#supported-backends)、[Rockchip RKLLM支持平台及部署步骤](https://github.com/airockchip/rknn-llm)。

### TTS 解压与同图确认

四个候选包均已完成解压，没有运行推理。Sherpa huayan路径 `assets/tts/vits-piper-zh_CN-huayan-medium/`，包含 `zh_CN-huayan-medium.onnx`、`tokens.txt`、`espeak-ng-data/`；正确配置为vits.model/tokens/data_dir，不能误配zh-ll/Melo的lexicon路线。

已用标准ONNX protobuf线格式只读提取两个huayan的完整GraphProto字节并计算hash，无需导入推理框架：原始文件63,201,294B、SHA-256=`9929917bf8cabb26fd528ea44d3a6699c11e87317a14765312420be230be0f3d`；Sherpa文件63,201,423B、SHA-256=`04234ec24907e9efa7e153669e07d4e0cf6d260adc005323aa929386dae53f86`；两者完整计算图（含initializer权重）SHA-256完全相同：`bd3b8d0a193824126aed8d793fd9de846d4642f2ad91189f5893134c6bd34c29`。Sherpa新增metadata标识vits/piper/Chinese/cmn/espeak/1 speaker/22050Hz。该结果证明此批下载的两个模型具有相同图和权重；证据保存在 `assets/tts/huayan-graph-comparison.json`。这与[官方仅增加metadata的转换步骤](https://k2-fsa.github.io/sherpa/onnx/tts/piper.html)一致。

同图不代表整个前端与运行时相同：Piper1.2包内ORT1.14.1，Sherpa版本另记；espeak库、数据和分句实现仍需分别记录。可指定同一个espeak-ng-data目录减少变量，但只有实际音素序列对照才可声称前端完全一致。

## 9. NPU 功能失败与逐项诊断（不是性能测量）

实际模型试跑纠正了第7节“可部署”的证据边界：完整ASR尚未跑通。首次日志 `/home/orangepi/.cache/ros-robot-edge-benchmark/runs/npu-functional-01/npu-functional-under-build/0-native.log` 中模型加载成功，但第一次encoder `rknn_run` 返回-1，算子为 `op id:42, Split:/Gather_64_2sl_2sp`，程序exit255。重复的SetCoreMask提示本身不是本次故障原因；真正失败伴随内核RKNPU约6秒job timeout、task counter0、irq0。所有试跑均与Summer编译并行，因此只当功能诊断，不能收入CPU/NPU性能排行。

采用单变量、每次20秒硬超时的功能回放，固定同一RK3566模型、Sherpa1.13.8、同一真人wav，保留失败日志：

| 探针 | 结果 | wall（含加载、等待失败，不是有效推理速度） |
| --- | --- | ---: |
| runtime2.2.0，core auto（复现） | exit255，同op42 | 8.06秒 |
| runtime2.1.0（与模型compiler版本匹配），core auto | exit255，同op42 | 7.48秒 |
| runtime2.2.0，仅core mask改0 | exit255，同op42 | 7.44秒 |
| runtime2.3.2，core auto | exit255，同op42 | 7.54秒 |
| 最新runtime2.5.0，core auto | exit255，同op42，run返回-2 | 9.08秒 |
| 原同包joiner，独立C API零输入 | init/run/outputs_get均0 | 0.32秒 |
| 原同包decoder，独立C API零输入 | init/run/outputs_get均0 | 0.38秒 |
| 原同包encoder，独立C API零输入 | inputs_set成功，run=-1，同op42 | 7.79秒 |

结论：不能再将“换成匹配runtime或改core mask”作为已验证解法；也不是整个NPU不可用或纯权限故障。故障已缩小到此encoder编译产物与当前驱动/执行路径，脱离Sherpa仍复现。decoder/joiner的功能成功不代表完整ASR成功。原失败不覆盖、不删除；诊断日志和摘要在 `cache/npu/diagnostics/`，原组件独立C API回放程序亦保留供复测。

额外runtime均外置：2.1.0文件7,155,496B、SHA-256=`0f1c5db6c649c8705759308aa56ecffc3295c7eb465f9ec9170882f44004aa8d`；2.3.2文件7,726,232B、SHA-256=`d31fc19c85b85f6091b2bd0f6af9d962d5264a4e410bfb536402ec92bac738e8`。[官方2.1.0](https://github.com/airockchip/rknn-toolkit2/blob/v2.1.0/rknpu2/runtime/Linux/librknn_api/aarch64/librknnrt.so)、[官方2.3.2](https://github.com/airockchip/rknn-toolkit2/blob/v2.3.2/rknpu2/runtime/Linux/librknn_api/aarch64/librknnrt.so)。系统runtime1.4.0和driver0.9.6均未修改。

上游[Issue2583](https://github.com/k2-fsa/sherpa-onnx/issues/2583)存在完全相同RK3566、同模型、同op42的报告；原报告称尝试2.2/2.3/2.3.2均失败。当前没有维护者确认的修复；技术答复为机器人生成建议，不能当权威兼容结论。这里只用该报告作同症状线索，实际判断基于本机上述回放。

### 同源encoder重新导出的可行性与成本

官方toolkit2在v2.3.0后支持ARM64编译；v2.3.2仓确有Python3.8、manylinux2.17、aarch64编译wheel。已经只下载wheel和依赖清单到 `cache/npu/conversion/`，没有安装：文件37,803,535B，SHA-256=`d78e2ecd77502988dc2dcd46d665102be8fb15f4d4d541ef272f6abaabca0eda`。[官方ARM64编译wheel](https://github.com/airockchip/rknn-toolkit2/blob/v2.3.2/rknn-toolkit2/packages/arm64/rknn_toolkit2-2.3.2-cp38-cp38-manylinux_2_17_aarch64.manylinux2014_aarch64.whl)、[官方变更记录](https://github.com/airockchip/rknn-toolkit2/blob/v2.3.2/CHANGELOG.md)。

wheel内部METADATA与[官方cp38依赖清单](https://github.com/airockchip/rknn-toolkit2/blob/v2.3.2/rknn-toolkit2/packages/arm64/arm64_requirements_cp38.txt)一致：torch>=1.10.1且<=2.2.0、onnx1.16.1、onnxoptimizer0.2.7、ORT>=1.16、protobuf3.20.3、numpy<=1.26.4、scipy、opencv、psutil、ruamel.yaml、tqdm、fast-histogram。完整隔离环境预计需要数百MB至1GB以上额外资源，安装/编译可能需数十分钟且4GB板上存在峰值内存限制；这是未实测的工作量估计，不能保证10分钟完成，也不应与正式CPU测量同时运行。

同源原始checkpoint有官方公开副本 `csukuangfj/k2fsa-zipformer-bilingual-zh-en-t/exp/pretrained.pt`，HF元数据大小123,972,187B、LFS SHA-256=`d3285a7cf654abcdb3ee83f364a4378cdd1e691b29ae9ee2b6119202b2bd8a3e`。其32/64/96不同chunk FP32 ONNX也有公开文件，但官方明确要求先按目标导出参数重导ONNX，不能直接任意使用现成ASR ONNX。[checkpoint模型仓](https://huggingface.co/csukuangfj/k2fsa-zipformer-bilingual-zh-en-t/tree/main/exp)、[官方RKNN导出约束](https://k2-fsa.github.io/sherpa/onnx/rknn/export.html)。

官方同源流程先用checkpoint与tokens执行 `pruned_transducer_stateless7_streaming/export-onnx-zh.py`，设置dynamic-batch0、enable-int8-quantization0、decode-chunk-len64、2/2/2/2/2层、encoder dims256、attention dims192等固定原模型架构，再用 `export_rknn.py --target-platform rk3566`。当前[官方run_rknn.sh](https://github.com/k2-fsa/icefall/blob/master/.github/scripts/librispeech/ASR/run_rknn.sh)仍仅在toolkit2.1.0分支导出该旧small模型；[官方工作流](https://github.com/k2-fsa/icefall/blob/master/.github/workflows/rknn.yml)也区分旧stateless7与新zipformer配不同toolkit。因此2.3.2重编译旧模型属于待验证修复实验，不能宣称官方已保证；必须保留同源权重与转化元数据，先过独立encoder执行，再过完整ASR与CPU文本对照。

进一步包可得性预检已消除部分估计风险：

- [PyTorch2.2.0](https://pypi.org/project/torch/2.2.0/)有官方`cp38-manylinux2014_aarch64` wheel，86,596,601B，已经下载，不需源码构建Torch。
- [k2官方CPU索引](https://k2-fsa.github.io/k2/cpu.html)提供`k2-1.24.4.dev20260625+cpu.torch2.2.0-cp38-cp38-manylinux_2_17_aarch64.manylinux2014_aarch64.whl`，2,487,394B，已经下载，其METADATA只要求torch2.2.0与graphviz，无需源码构建k2。
- 同源checkpoint已经下载，本地SHA-256与HF LFS oid一致。官方icefall源码归档已下载11,990,871B，固定commit `1c388ad9be94c0ee9de76f7a6ed45b1cff677d13`，未执行训练。
- 官方导出入口确实直接import k2，并从train导入构造函数而连带引入lhotse、sentencepiece、tensorboard等；k2并非不存在的ARM依赖。可直接沿官方入口尝试，不必先重写训练模块或使用伪造k2替身。
- 真正缺预制ARM wheel的是toolkit固定的onnxoptimizer0.2.7。已核[PyPI官方文件清单](https://pypi.org/project/onnxoptimizer/0.2.7/)，仅x86/mac/win wheel及16,843,540B源码；源码已下载。[构建脚本](https://github.com/onnx/optimizer/blob/v0.2.7/setup.py)支持`MAX_JOBS`，可设1；[CMake](https://github.com/onnx/optimizer/blob/v0.2.7/CMakeLists.txt)包含protobuf/ONNX C++，因此应有界尝试而不是假定只解压wheel即可。
- 本机已具备cmake、g++与Python3.8头文件；上游[Issue336](https://github.com/airockchip/rknn-toolkit2/issues/336)的缺cmake/编译器原因不适用于本机。协调者正在做纯CPU基线，已暂停全部模型试跑、转换与重安装，只继续资料与依赖下载；后续使用新的外置venv，限制onnxoptimizer构建并发与300–600秒尝试窗口，不改系统/既有venv，不自动开启数小时编译。

后续下载预检已完成：`pip download --only-binary=:all:`成功取得Torch2.2.0、torchaudio2.2.0、ONNX1.16.1、ORT1.19.2、numpy1.24.4、scipy1.10.1、lhotse1.25.0、lilcom、sentencepiece、tensorboard及全部依赖wheel，输出在 `cache/npu/conversion/wheels`，日志 `wheel-download.log`；没有安装或修改既有venv。因此目前除onnxoptimizer0.2.7外，没有发现必须编译其他训练依赖的阻塞。

新的隔离环境路径为 `cache/npu/conversion/venv`。系统Python缺ensurepip，默认venv创建只完成基础目录；已通过既有pip的 `--python <新venv>` 管理能力仅给新环境安装pip24.3.1/setuptools69.5.1/wheel0.45.1，未更改既有环境或安装系统包。重型wheel解压、onnxoptimizer构建和encoder转换等待协调者正式测量完成后进行。

时效性补核：[官方Release API](https://api.github.com/repos/airockchip/rknn-toolkit2/releases/latest)确认RKNN toolkit最新版本为 **v2.5.0，2026-10-20发布**；上述2.3.2是固定候选，不称最新版。另已外置下载2.5.0 aarch64 runtime，8,189,368B、SHA-256=`4b6cc575bedf8952b13db4b1190fa3b3d2ac213f00be774ff6ccd19d651970c0`，在 `cache/npu/runtime-2.5.0/librknnrt.so`。协调者CPU基线完成后的非性能窗口已做9.08秒功能探针，仍同op42失败，非修复；日志 `cache/npu/diagnostics/runtime-2.5.0-core-auto.log`。随后再次暂停模型试跑与大解压，等待下一轮公平测量完成。[官方2.5.0 runtime](https://github.com/airockchip/rknn-toolkit2/blob/v2.5.0/rknpu2/runtime/Linux/librknn_api/aarch64/librknnrt.so)。

### 官方历史产物检查

检查了作者官方HF RKNN模型仓84条历史提交，以及icefall旧small导出脚本的完整修改历史。没有找到compiler1.x的官方旧small产物。导出脚本于2025-02-27的[首次提交db9fb8a](https://github.com/k2-fsa/icefall/commit/db9fb8ad3113aaa54c81f71c3d64ea445fe3dd5d)加入；该时点[工作流实际使用toolkit2.3.0](https://github.com/k2-fsa/icefall/blob/db9fb8ad3113aaa54c81f71c3d64ea445fe3dd5d/.github/workflows/rknn.yml)，与当前固定2.1.0不同。因此不能假定所有历史包内部encoder完全相同，也不能因当前包失效就跳过已公开的历史编译图。

找到并下载两个官方历史同名RK3566包，均与其HF LFS SHA-256核对一致，暂只下载、未在CPU公平测量时解压或执行：

| HF commit / 日期 | 字节 | SHA-256 |
| --- | ---: | --- |
| `07febd4650c823d5369ba59c95729491013a0bb6` / 2025-02-27 | 49,576,255 | `54e499826b23ffdf2c50a12c9c8e842644d6950010bb43f11b4d3d3051c1a2c9` |
| `5ff8b9e4d971c082a808b229bf0e3060b1f2c926` / 2025-03-19 | 49,580,340 | `5ffbbc179e608f6b8836a279fbada0893de7ca156aa96ba63644cc7db1f8e3ce` |

缓存为 `cache/npu/historical/<commit>.tar.bz2`，附download-manifest.json。[2025-02-27模型树](https://huggingface.co/csukuangfj/sherpa-onnx-rknn-models/tree/07febd4650c823d5369ba59c95729491013a0bb6/streaming-asr)、[2025-03-19模型树](https://huggingface.co/csukuangfj/sherpa-onnx-rknn-models/tree/5ff8b9e4d971c082a808b229bf0e3060b1f2c926/streaming-asr)。压缩包hash不同不等同于encoder不同，需要解压比对实际组件hash/compiler字符串；尚未称其可修复。

同源身份也有历史证据：首次工作流的[small导出入口](https://github.com/k2-fsa/icefall/blob/db9fb8ad3113aaa54c81f71c3d64ea445fe3dd5d/.github/scripts/librispeech/ASR/run_rknn.sh)引用相同`k2fsa-zipformer-bilingual-zh-en-t/exp/pretrained.pt`和2/2/2/2/2层、256 encoder dims等旧架构。原模型仓2024-03-20提交`8a7306b4d4d40c3cb1bdb80e8f2f605167570af3`的PT LFS hash也是`d3285a7cf654abcdb3ee83f364a4378cdd1e691b29ae9ee2b6119202b2bd8a3e`，与当前下载PT完全相同，支持这些公开导出流程使用同源旧权重；不把另一个ASR模型当作修复。[历史checkpoint](https://huggingface.co/csukuangfj/k2fsa-zipformer-bilingual-zh-en-t/tree/8a7306b4d4d40c3cb1bdb80e8f2f605167570af3/exp)。

### NPU 完整 ASR 已通过功能验证：使用同源历史compiler2.2.0产物

协调者正式CPU队列结束后，完成两份历史包的解压与短功能验证：

| 产物 | 实际compiler | runtime | 结果 |
| --- | --- | --- | --- |
| 2025-02-27 `07febd…` | 2.3.0 | 2.3.2 | 2.54秒SIGSEGV |
| 同上 | 2.3.0 | 2.5.0 | 2.49秒SIGSEGV |
| **2025-03-19 `5ff8b9…`** | **2.2.0** | **2.2.0** | **完整ASR exit0，有最终解码文本** |

成功产物三个文件的本地身份：encoder62,934,129B、SHA-256=`f98fe4e452b9e1c3783ba4c47fc96d4e8ae4ae6a63aa796fd810e324d914a492`；decoder7,999,529B、SHA-256=`a9e8ac8bcab7a491d17be862a64f430b3933a7a96a28032ae86973dee6aa353f`；joiner6,480,086B、SHA-256=`c56e476ce84b0e9d37567badbdb356f491b0c2ef78dab5ddb7a3cc1c71220353`。compiler2.2.0而非当前官方包的2.1.0，是这次修复的关键配置差异；不能归因于runtime升级，因为runtime仍是先前2.2.0。

成功历史包的tokens.txt与旧CPU资产逐字节hash相同，均为 `a8e0e4ec53810e433789b54a5c0134a7eaa2ffca595a6334d54c00da858841d3`，配合已核对的历史checkpoint与导出来源固定同源身份；FP16 RKNN与旧混合int8 CPU应作为不同部署精度列出。

成功日志 `cache/npu/diagnostics/historical-20250319-runtime2.2.0.log`，摘要同名json；加载0.934秒，程序wall4.398秒，native decode2.9秒/音频10秒、打印RTF0.29，文本为“昨天是 MONDAY TODAY IS AFTER TOMORROW是星期三”。**这只是完整功能通过，不当作公平性能结论或准确率验收**；需协调者在相同干扰条件、语料、采样口径下另做NPU/CPU对照。SetCoreMask非RK3588提示依然存在，但未阻止成功执行，因此不能把它当此次失败根因。

可直接复测的已成功命令：

```bash
NPU_ROOT=/home/orangepi/.cache/ros-robot-edge-benchmark/npu
NPU_MODEL="$NPU_ROOT/historical/5ff8b9e4d971c082a808b229bf0e3060b1f2c926/sherpa-onnx-rk3566-streaming-zipformer-small-bilingual-zh-en-2023-02-16"
LD_LIBRARY_PATH="$NPU_ROOT/runtime-2.2.0" \
  "$NPU_ROOT/sherpa-onnx-v1.13.8-rknn-linux-aarch64-shared/bin/sherpa-onnx" \
  --provider=rknn --num-threads=1 \
  --encoder="$NPU_MODEL/encoder.rknn" \
  --decoder="$NPU_MODEL/decoder.rknn" \
  --joiner="$NPU_MODEL/joiner.rknn" \
  --tokens="$NPU_MODEL/tokens.txt" \
  /home/orangepi/models/voice/sherpa-onnx-streaming-zipformer-small-bilingual-zh-en-2023-02-16/test_wavs/0.wav
```

已成功路线不需修改内核/驱动、系统库、模型训练或源码构建onnxoptimizer；先前失败证据与不同compiler产物全部保留。此前第9节的“完整ASR尚未跑通”描述的是当前官方compiler2.1包，不再扩大为所有同源RK3566产物不可用。新的重导出准备环境继续保留，当前无需启动它。
