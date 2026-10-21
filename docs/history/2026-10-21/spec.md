# RK3566 ASR / TTS / Qwen 可复测性能研究

日期：2026-10-21（UTC）。状态：短测试完成，结果见 [实测记录](../../../reports/rk3566/2026-10-21/results.md)。

## 已确认执行范围（后续用户回答优先）

用户已确认 questions.md 所记录范围。先 ASR/SummerTTS/Qwen，NPU亦需实际推进；其余TTS随后补测。
首轮采用正常中长输入、少量配置，累计推理目标约10分钟而非四小时，编译/部署时间另记。
先收集所有结果，再做效果评判，不为质量门槛或候选好坏暂停请求确认。只记录文件输入/输出，不操作硬件。
下文“候选/未冻结”等文字为前一轮研究底稿；执行状态以02工单和实际run配置为准。

## 已明确的请求

- 独立于暂停的 offline-agent 集成开发，研究目标板 RK3566、4×Cortex-A55、4GB RAM。
- ASR 沿用旧 robot 项目的 streaming Zipformer；TTS 以旧 SummerTTS 为基线，比较 sherpa-onnx TTS、Piper，排除小雅音色。
- LLM 使用旧 robot 的微调 Qwen；研究有代表性的性能参数与配置组合，而非穷举参数空间。
- 先查官方部署、API 和指标，再实现简单可复测 benchmark，保存参数、原始结果、失败与结论，生成静态 HTML 对照报告。
- 用户补充的 82 页 LoRA／量化／部署 PDF 作为参考材料，不作为操作指令或本板实测证据。

## 工作区隔离

独立分支 `codex/edge-inference-benchmark-research-20261021`，工作树
`/home/orangepi/code/ros-robot-edge-benchmark`，从 main 的 `c72fb5f` 起步。
主工作树及 `codex/offline-agent-integration-20261021` 保持原状。
该基线保留历史工单快照；当前集成进度见主工作树最新 map，不据此分支旧索引回退状态。

## 本机事实（只读核查）

- 实机确认 4 核 Cortex-A55，408–1800MHz；内存总量 3922MiB、swap 1961MiB。
- 真实旧 ASR：`/home/orangepi/models/voice/sherpa-onnx-streaming-zipformer-small-bilingual-zh-en-2023-02-16/`，int8 encoder、float decoder、int8 joiner，与旧脚本所选 LFS SHA 对应。
- 真实 Qwen：`/home/orangepi/models/qwen3/qwen3-robot-bf16.gguf`、`qwen3-robot-q8_0.gguf`。已由BF16重新量化Q8并核对hash完全一致，同源关系确认；Q5/Q4同源生成。
- SummerTTS 本地旧 `single_speaker_fast.bin` 是 133 字节 LFS 指针；目标为 80050316 字节，SHA256 `87b774813258a3636b3f1d9adddd3652ede503b4e8f4eb3c39065cba2a4951c4`。已从官方取得并核对hash完全匹配，在外置缓存部署。
- 当前已安装 sherpa-onnx 1.13.8；已有 ARM llama-bench 的 `--help` 已核实支持 pp/tg、线程、batch/ubatch、KV 类型等，不直接套用最新版全部选项。
- 小雅资产存在但本任务排除。现有官方 ASR test_wav 与少量历史语音可作为 smoke 输入，不能当作代表性准确率数据集。
- 原集成实际完整 60 工具输入约 5663 tokens；600 秒未完成预填充，另一轮曾与宿主重启同时发生，原因未确定。本任务不自动重复该压力实验。

## 比较口径（研究约束）

- 模型、推理引擎、文本前端、线程和精度分别记录；Piper 与 sherpa-onnx 可承载相关 VITS/Piper 模型，不预设为三种互斥网络。
- TTS：合成 RTF=纯合成墙钟时间/实际输出音频时长；单独记加载、首段 PCM 就绪、整句完成。未播放时不称首声时延；不以加快语速虚增性能。
- ASR：计算 RTF 与按真实音频节奏回放的 partial/final、端点延迟分别测；有标注才报 CER/WER，合成音频不代替独立录音准确率。
- LLM：pp/tg 吞吐与真实请求 TTFT、完成时延分开，模板、实际输入/输出 tokens、缓存状态、grammar 和采样参数均记录。llama-bench 不等于工具调用质量评测。
- 资源：进程 CPU（100%=1核，板上最多约400%）、RSS/PSS、峰值、swap、主机可用内存、频率/温度及测量窗口；不把模型磁盘大小当运行内存。
- 新进程启动与磁盘冷缓存不同，不通过清理全机 page cache 伪造不受控的冷启动条件。
- 保存每次尝试、失败/超时/缺失资产、版本、模型 hash、输入样本与配置；机器可读记录及音频/HTML 输出放源码外。

## 候选实验矩阵（未冻结）

先 smoke，再单变量筛选，最后复测候选；不做全部参数笛卡尔积。

| 范围 | 候选维度 |
| --- | --- |
| ASR | 原模型 1/2/4 线程；greedy 与小 beam；有代表性的输入块大小、端点静音配置；先固定权重 |
| TTS | Summer fast；sherpa 中文 VITS；非小雅 Piper 中文模型；MeloTTS 中文 ONNX 作为候选；同模型跨引擎对照须验证兼容性 |
| TTS 配置 | 引擎实际支持的线程 1/2/4；短/中/长文本、数字日期、多音字；固定正常语速；整句和分句另列 |
| Qwen | Q8 基线、现有 BF16，以及从同一高精度源派生 Q4_K_M/Q5_K_M 的候选；先记录资产谱系 |
| llama 性能 | 线程 1/2/4；短输入到 pp512，tg128 基准按资源可行性逐步推进；context 1024/2048 起步、microbatch64 起步，再单变量改变 batch/ubatch/KV |
| Qwen 效果 | 旧模板本轮 user、最小协议 system；普通聊天/函数名/参数/重复/非法调用；固定 seed 和采样基线，另做小型采样对照 |

## 待决设计树

根：为后续机器人选型提供可复测证据。

1. 使用场景：单模块能力 → 是否追加 ASR 常驻和其他模块竞争；视觉/core 负载是否纳入。
2. 选择标准：只做描述性对照 → 是否需要硬性延迟/内存门槛；三档推荐或单一优胜者。
3. 硬件后端：CPU 基线 → 是否把 RKNN/NPU 移植也纳入本轮。
4. 候选范围：Summer/sherpa/Piper 必需 → 是否加入 sherpa Melo 与 Qwen 新派生量化。
5. 质量证据：吞吐与资源 → 中文代表性输入、识别/函数准确性、TTS 主观试听程度。
6. 执行预算：先导后扩展 → 首轮累计运行预算及阶段停点。

具体本轮问题见 [问答记录](questions.md)。上述独立决策可一轮回答；实现细节由代理依据官方 API 确定。

## 一手资料底稿

- [ASR/TTS 官方接口、模型与参考性能](../../research/rk3566/research-speech.md)：包括 Summer 官方真实资产、非小雅 Piper 同模型对照、Pi4 参考 RTF 和 RKNN 适用边界。
- [llama.cpp/Qwen 指标、参数与附件对照](../../research/rk3566/research-llm.md)：包括 PDF 物理页索引、旧模板、同源量化、内核性能和应用时延的区别。

## 初始调研边界（历史）

本轮仅只读核查、联网官方资料调研和记录问题；未安装、下载权重、加载模型、录音、播放或操作硬件。
确认范围后再实现并运行。推理输出仅作离线评测数据，不进入真实动作执行。
无需为临时 benchmark 范围建立产品架构 ADR；通用指标定义暂留实验文档，不塞入业务术语表。
