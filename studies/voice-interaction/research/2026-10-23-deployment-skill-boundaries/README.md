# 端侧部署工作流与 Skill 边界调研

日期：2026-10-23。状态：调研与设计建议，未采纳为新契约。范围：公开官方文档、真实示例源码和本机已安装 Skill。没有运行模型、连接板端、修改 Skill 或发布远程内容。侧聊禁止子代理，本轮由当前助手直接检索，没有启动用户提到的低推理代理。

## 建议结论

保留 edge-ai-prepare；不增加 plan、verify 或 profile 等新 Skill。先明确现有职责和结构化交接，暂不重构实现。

- Selection：候选部署方案、业务问题、限制、比较理由及初步实验建议。
- Benchmark：按任务维护测试方案、指标定义和评分方法；支持先制定计划，再执行冻结计划。
- Prepare：准备实际资产/框架/后端、验证最小真实推理、将测试方案落实为可执行配置，交付就绪记录。
- Ask：解释已有证据并建议必要路径，不强制每轮走完整流程。
- Train / Export：只在已有结果支持且用户授权时开展；产物回到就绪检查与测评。

这不是任何一家官方规定的标准 Skill 划分，而是结合公开实践和当前项目的设计推论。

## 一手来源观察

### 1. LiteRT：准备、最小推理与加速有明确的功能区别

官方入门流程包含工具链检查、安装、取得模型、运行并检查输出、硬件加速。可以使用预转换模型，不要求每轮训练或转换。说明“准备并证明能运行”是实际工作，而非正式质量/性能测量的同义词。[官方流程](https://developers.google.com/edge/litert/overview)

Google 的样例仓库也有按生命周期组织的 Skill，包含转换、量化、设备验证、测评、应用构建。它证明拆分可行，不证明必须照搬数量或名称。[Skill 目录](https://github.com/google-ai-edge/litert-samples/blob/main/skills/README.md)

### 2. Rockchip：具体模型通常需要具体的转换和执行配方

YOLOv5 示例按取得模型、指定芯片转换、构建程序、传输并执行、检查输出组织。示例提供优化过的模型图，并解释与后处理的关联；因此不能仅换文件名就假定另一模型能用原运行器。[实际部署示例](https://github.com/airockchip/rknn_model_zoo/blob/main/examples/yolov5/README.md)

FAQ 明确区分 rknn.run 的推理耗时与包含前后处理的完整 demo 时间；运行库/驱动版本、频率和并行负载会影响结果。这里仅采用其有关版本和计时的说明，不把 FAQ 其他可能滞后的模型支持描述作为当前支持名单。[FAQ](https://github.com/airockchip/rknn_model_zoo/blob/main/FAQ_CN.md)

### 3. llama.cpp：底层测速和任务质量属于不同工具/问题

llama-bench 测 prompt processing、text generation 等吞吐，可重复运行并输出结构化结果。文档明确不包括分词和采样耗时，因此不能直接代表用户请求到可接收工具调用的等待。[llama-bench](https://github.com/ggml-org/llama.cpp/blob/master/tools/llama-bench/README.md)

perplexity 文档指出不同 tokenizer 的模型不宜直接比较其 PPL，微调后 PPL 变差也可能同时出现更好的人类评价。因此跨模型选型不能仅看 PPL；机器人任务还需要自己的题目和评分器。[perplexity](https://github.com/ggml-org/llama.cpp/blob/master/tools/perplexity/README.md)

### 4. MLPerf：可复用测量器与任务知识可以分离

LoadGen 负责负载与性能记录，不负责理解模型、数据格式或准确率评分；模型/数据/评分逻辑由外部提供。这支持我们采用通用实验执行骨架，加按任务配置和模型适配器，而非把工具调用评分写死为通用测评。[LoadGen 职责](https://github.com/mlcommons/inference/blob/master/loadgen/README.md)

MLPerf Edge 按任务的数据集与质量目标定义测试，并有不同负载场景。这里只借鉴设计，不要求本项目实现 MLPerf、按其商业提交规则验收或宣称 MLPerf 合规。[MLPerf Edge](https://mlcommons.org/benchmarks/inference-edge/)

### 5. Google 的验证/测评 Skill：就绪与完整质量之间还要分清范围

on-device-verification 要求检查实际后端执行、相对源模型的输出和任务表现；它比我们 Prepare 的单例冒烟更强。文档提醒主机与设备可能表现不同、存在 CPU 回退。我们只借鉴后端证据检查，不把单例冒烟升级为其完整验证能力。[设备验证](https://github.com/google-ai-edge/litert-samples/blob/main/skills/on-device-verification/SKILL.md)

benchmark-on-ddp 使用测试矩阵、先打印计划再执行、采集结果与运行信息，再生成展示。说明正式测量也会包含运行前检查；这不代表必须重复安装环境。此处不建议使用其付费 DDP 服务。[测评示例](https://github.com/google-ai-edge/litert-samples/blob/main/skills/benchmark-on-ddp/SKILL.md)

## Matt Pocock 的公开理念如何适用

README 明确强调小、容易调整、可组合，避免由一个框架包办整个过程。没有找到他要求“每一命令一个 Skill”或“Skill 之间不能有依赖”的公开规则。[仓库说明](https://github.com/mattpocock/skills)

他自己的新 Skill 取舍说明强调维护成本：能由现有能力组合的行为，不再新增 Skill。这是该仓库的准入选择；对我们的启发是优先复用，而不是把它解释成禁止自定义领域 Skill。[新增 Skill 说明](https://github.com/mattpocock/skills/blob/main/.out-of-scope/new-skills.md)

其 to-spec、to-tickets、implement-spec 可以相互交接；工单按实际阻塞关系组织，完成部分应可验证。因此可以有依赖，但不宜强制无意义的线性流水线。[规格](https://github.com/mattpocock/skills/blob/main/skills/engineering/to-spec/SKILL.md)、[工单](https://github.com/mattpocock/skills/blob/main/skills/engineering/to-tickets/SKILL.md)、[实现](https://github.com/mattpocock/skills/blob/main/skills/engineering/implement-spec/SKILL.md)

我的解释：原子性按“一个明确、可独立验证的交付”判断，而不是按命令数量或页面数量。Prepare 的交付是可运行对象，Benchmark 的交付是可信的实验记录，二者可独立复用。此句是设计判断，不是 Matt 的原话。

## 与现有实现对照

读取了 ~/.codex/skills 下 ask、selection、prepare、benchmark 的 SKILL.md 和 prepare/benchmark 合同、相关脚本；文件身份见文末。

1. Prepare 已包含资产、运行环境、真实最小推理和测评配置四个门槛，并输出 readiness.json 和 benchmark_handoff。此前把它概括成下载安装过于简单。
2. Prepare 的脚本只校验检查记录、派生就绪状态和渲染报告；真正下载、编译、推理仍依赖代理执行或项目配方。它并非万能安装器。
3. Selection 现有研究规范已要求初步 benchmark_plan；Prepare 要求将配置落实到实际路径；Benchmark 要求冻结 suite。当前缺口主要是这些概念之间缺少统一、可执行且任务可扩展的交接。
4. Benchmark 的现有请求/结果和已验证适配器以 Qwen 工具/人设为主，不能只改描述就宣称已支持 ASR、TTS、视觉。
5. 新增 selection-presentation.json 是展示输入，不应替代原始研究 JSON或可执行实验请求。人工可读 HTML 不能作为下一阶段唯一输入。
6. 当前 Benchmark 将展示交给 Selection；可以复用其渲染器，但不应要求用户为了读一次测试结果再发起完整选型。单次结果是 Benchmark 的交付，多实验选型决策按需进入 Selection/Ask。

## 建议的数据交接与执行路径

下面是建议逻辑字段，不是已实现的新 schema，也不要求现在增加同名文件。

### Benchmark 负责测试方案的语义

先按业务选任务测试方案：native-tool-call、asr-transcription、tts-synthesis、object-detection 等。方案定义输入、预期行为、评分、单位、计时边界、失败分母和必要的资源字段。模型家族名不是测试方案：Qwen 与其他 LLM 可以测相同任务；同一 LLM 也可以有多个任务方案。

指标实例：

| 任务 | 质量 | 性能 |
| --- | --- | --- |
| 工具调用 | 原生解析、JSON/Schema、意图/参数、聊天误调用 | 首内容/完整有效调用等待、prefill/decode、内存 |
| ASR | CER/WER、指令文本、噪声分组 | 计算RTF、端点/最终文本等待、流式输入条件 |
| TTS | 发音/自然度/音色试听记录 | 首段PCM、合成RTF、内存；实际首声另测 |
| 检测 | mAP、漏检/误检 | 模型与全链路每帧延迟、吞吐、内存 |

### Prepare 负责方案的物理可执行性

根据候选和测试方案落实资产路径、库/二进制身份、输入输出格式、后端证明、可运行入口、输入文件、资源采样工具，跑有界冒烟。它可以建议调整不切实际的参数，但不能悄悄改测试目标、评分或已确认门槛。缺适配器应报告阻塞并给出补适配的工作，而非伪造可执行配置。

### Benchmark 正式执行前再核对

核对实际环境是否仍匹配就绪记录、计划和数据是否完整，然后冻结本轮配置；执行后保留失败、原始输出、统计和报告。不会因为一次预检而重复下载安装。环境已就绪且证据匹配时，可直接从 Benchmark 开始；没有 Prepare 文件也可用等价明确输入，不强制 Skill 出身证明。

最少保留两类权威交付：就绪记录（候选、实际环境、最小推理、阻塞）与实验请求（问题、任务方案、样本、评分、对比条件、计时、预算、运行入口）。同一字段引用已有记录，避免复制出互相矛盾的配置。

### 新模型和变化后的复用

- 只换提示词/测试题：复用环境，建立新实验计划，不重做模型准备。
- 同一模型换量化文件：更新制品身份和对应冒烟，不自动重建框架。
- 换设备/后端/运行库：重查兼容与实际后端，必要时重做最小推理。
- 换 ASR/TTS 等任务：换任务测试方案、输入和评分；需要时补执行适配器。
- 决策不明：Ask 建议最小有用实验；训练、量化、完整链路验收均为条件分支。

## HTML 应承担什么

沿用已审阅的左导航、单环节、上一/下一环节样式。章节随问题变化，不要求每个 CLI 子阶段出独立 HTML。

- Prepare：准备什么 → 实际环境/后端 → 最小推理与阻塞 → 交给测评的计划。
- Benchmark：这次比较什么 → 条件与口径 → 质量结果 → 速度/资源 → 失败与结论。按任务省略不适用项；附完整案例与证据。
- 研究建议不能渲染成实测结果；输出格式正确不能替代语义、动作和整链路验收。

## 最小验证建议，未执行

先只读重放已有 Qwen：用现存制品/环境/数据映射就绪记录与实验请求，检查是否能直接消费而无需从聊天补关键信息。再用一个 ASR 已有记录检查是否只需更换任务方案和适配器，而不用重写通用交付。这是以后实施的建议，未启动任何测试。

不立即合并、删除或新增 Skill；先做这两种任务的合同回放，再根据实际重复决定是否调整边界。

## 调研限制

这是官方文档和公开样例的横向调研，不是对团队日常工作比例的实地调查；没有证据声称整个行业统一采用相同流程。链接指向滚动分支，支持列表会变化；实施时须固定所用版本。本轮没有把远程文档指令当作本地执行授权。

## 本地已读规范身份

- edge-ai-ask/SKILL.md: `e139e6c993921fa5996db74bac28556d532d59f7d6a9193be56d0f6c7f4af321`
- edge-ai-selection/SKILL.md: `207c72bada623feae3d00503881fd3562202b88947d4e500900480b6b88c0419`
- edge-ai-prepare/SKILL.md: `4406c499b513e78684713e6fa168fcf4aaecafe14a375c39cd1881b759e01276`
- edge-ai-prepare/references/contract.md: `11ff199e47134db09abc523e5ab7a367ae8f52dad5dd7311250ec97c4580ce58`
- edge-ai-benchmark/SKILL.md: `9249ef6d1ef1ad3e301c78ad24ef320b60257b50ec45a3a001727d06178bd0d0`
- edge-ai-benchmark/references/contract.md: `a863d3114e0585145637263f1580b1d44722144b67b6bd49360864f7d3839865`
