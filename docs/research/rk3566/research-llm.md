# llama.cpp／旧 robot Qwen 板端基准：资料与候选实验

调研日期：2026-10-21（Asia/Shanghai）。
状态：供本轮需求访谈使用的研究草案；矩阵、预算和通过线尚未最终确定。
本次仅阅读本地历史和官方网络资料，没有安装、下载模型、编译或启动推理。

## 已有证据决定起点

板端历史记录为 Orange Pi 3B／RK3566，4×Cortex-A55，约 3922MiB RAM、
1961MiB swap。旧启动脚本引用 `Qwen3-0.6B-BF16.gguf`；最近集成试跑实际使用
`qwen3-robot-q8_0.gguf`（639443232 字节）。文件名不能证明二者来自相同微调权重。
正式比较前应核实旧模型实际路径、SHA-256、GGUF 元数据、chat template、微调来源；
以同一权重来源派生的量化版本才能讨论“量化带来的差异”。
证据：[既有性能记录](/home/orangepi/code/ros-robot/.scratch/offline-agent-integration/offline-llm-performance-backlog.md)。

历史完整 60 工具目录为 5663 输入 tokens：4096 context 放不下，
6400 context／q8 KV／micro64／4 线程运行 600 秒仍未完成预填充；无首 token，
因此没有有效解码吞吐或工具正确率结果。另一次 8192 context／f16 KV／micro128
运行期间宿主重启，原因未确定，不能写成已确认 OOM。
这些失败不能当作其他短提示、旧项目输入方式或其他模型配置的性能结论。
证据同上。

## 用户补充教程的证据边界

参考附件：[离线 Agent／LoRA／量化部署教程](/home/orangepi/.codex/attachments/a9680490-2228-43fd-8100-54e97ea9e782/19-机器人端侧大模型Agent-离线版本-Lora微调，量化、部署-合并版.pdf)。
以下页码为 PDF 物理页，按提取文本的 formfeed 分页核对，共82页。

- 第4页的训练样例含专用 system 和 `res`／`fc` 输出，支持“测试时需要匹配实际微调协议”这一调查方向；
  不能由单条示例推断所有训练样本或当前 GGUF 已学会全部现有工具。
- 第40–42页描述 LoRA 合并目录转出 `Qwen3-0.6B-BF16.gguf` 并调用 CLI。
  这里提供资产来源线索，没有证明当前 Q8 文件与旧 BF16 完全同源。
- 第46页举 Q8_0、Q5_K_M、Q4_K_M 量化例子，示例针对8B；这些预设可作为后续同源量化候选，
  不能把示例的适用结论直接推广为本板0.6B模型最佳参数。
- 第47页的旧流水线先流式发布 res、完成后再分发 fc。它说明历史实现，
  本次 benchmark 只做 dry-run 并记录输出，不据此恢复任何硬件动作时序。
- 第79–80页性能表的背景是8核／16GB，含解码9.6 tokens/s、Q8模型约610M及其他资源数字。
  第82页又列7.6／9.8 tokens/s与若干准确率，缺少同条件完整配置和原始样本。
  均只作为教程历史声称保存，不能标成 RK3566 实测、也不能据其证明量化质量或速度收益。

这份教程提供测试对象与质量样例的线索，不提供本板可直接复用的性能排名。

## 官方资料给出的可复用测量接口

`llama-bench` 提供 pp（提示处理）、tg（生成）和 pg（提示后生成），
文档示例采用 pp512／tg128；支持重复、JSON／JSONL 原始输出、上下文深度。
它不包含 tokenizer 与 sampler 耗时，因此只能作为推理内核对照，不能代替用户可感知延迟。
多参数列表会组合运行所有配置，不能把候选参数全部逗号展开。
[官方 llama-bench 文档](https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/llama-bench/README.md)。

官方服务具有 `/health`、`/apply-template`、`/tokenize`、流式 `/completion` 和
`/v1/chat/completions`；可获取 prompt／generation timing 及缓存 token 数。
`threads-batch` 用于提示处理；`batch-size` 是逻辑批上限，`ubatch-size` 是物理微批上限；
KV 类型独立于权重量化。`cache_prompt` 能复用公共前缀，需与清 KV 的测量分别报告。
这些为当前上游接口，不能假定旧 vendor revision 已支持所有选项；落地前读取实际
`--help` 和对应 revision 文档，不静默忽略不支持的配置。
[官方 server 文档](https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/server/README.md)。

Qwen 官方建议使用针对本机 CPU 的本地编译；预编译产物可能缺少合适优化。
Qwen3 支持依赖 llama.cpp 版本，官方记录从 b5092 起支持，旧项目 vendor 的
实际兼容能力仍需按其代码与成功加载证据确认。
[Qwen llama.cpp 部署文档](https://qwen.readthedocs.io/en/latest/run_locally/llama.cpp.html)。

官方性能诊断建议从 1 线程开始逐步翻倍，线程过多可能过度竞争。
因此本板采用 1／2／4 线程是有依据的代表配置，不默认“四线程必然最快”。
[llama.cpp 性能诊断](https://raw.githubusercontent.com/ggml-org/llama.cpp/master/docs/development/token_generation_performance_tips.md)。

权重量化是另一独立因素：官方示例包括 Q8_0、Q4_K_M，并支持 importance matrix。
量化并不承诺质量等价，不能拿不同微调来源的 Q8 与 BF16 直接归因比较。
[Qwen llama.cpp 量化文档](https://qwen.readthedocs.io/en/latest/quantization/llama.cpp.html)。

## 建议统一记录的指标

以下为本项目建议口径；通过线需要用户确定，不是官方 RK3566 性能承诺。

| 指标 | 定义与用途 |
| --- | --- |
| 启动／加载耗时 | 启动进程至模型就绪；另记首请求，避免把加载混入 warm 请求 |
| pp tokens/s | 实际新处理的提示 tokens／提示处理秒数；缓存命中 tokens 单列 |
| tg tokens/s | 采用 runtime 提供的生成 timing 口径，保留 token 数、秒数；不混用不同分母 |
| TTFT | 请求发送至首个非空生成 token／文本内容；SSE 心跳、角色空块不算首 token |
| 首个可用回答时间 | 思考内容、前置协议之后首次可交付的 res 文本；工具场景另记首个完整可校验 fc |
| 端到端完成时间 | 请求发送至正常结束；输出上限截断与自然 EOS 分别标记 |
| ITL／TPOT | 流式块到达间隔与每 token 平均延迟分开，不能把多 token SSE 块称单 token 延迟 |
| 峰值 RSS／PSS、swap | 模型进程及子进程树，主机 MemAvailable／SwapFree 同步记录 |
| CPU 与温度 | CPU 累计核秒、平均／峰值占用、频率／温度轨迹；100%＝一个逻辑核，四核上限约400% |
| 成功／失败 | 正常结束、超时、内存守卫、加载错误、不支持参数、截断；失败不填零耗时参与均值 |
| 基本输出质量 | 中文回复可用性、JSON／res／fc 解析率、函数名与参数正确率、未知调用拒绝结果 |

小样本先报告每次原始值、中位数、min／max。3 次样本不足以稳定估计 p95；
等配置筛选后再决定是否用更多重复估计尾延迟。软件测量无法可靠给出整板瓦特或焦耳；
无外部功耗计时将能耗标记未测，不能由 CPU% 换算功率。

## 参数分组，避免把采样策略当作算力配置

| 参数组 | 代表候选 | 解释 |
| --- | --- | --- |
| 权重 | 旧 robot 实际权重；同源 Q8_0；可选同源 Q5_K_M／Q4_K_M | BF16／Q8 来源先确认，Q5／Q4 作为后续量化扩展，不能替换成普通未微调 Qwen |
| CPU | generation threads 1／2／4；batch threads 显式记录 | 初轮两个线程值保持相同；仅预填充明显受限时单独调 batch threads |
| 工作负载 | pp128／pp512；tg32 筛查后 tg128；pg128,32 | 512／128 接近官方常用量级，小档用于本板先验失败后的渐进试跑 |
| context／历史 | context1024 起，必要时2048；后续4096 | context 是容量，实际输入长度另测；不把空 context 容量误称已处理历史 |
| batch／microbatch | 初始 b128／ub64；再试 b256／ub64、b256／ub128 | 保持 ub≤b，逐项调整，不默认微批越大越好 |
| KV | f16 对照 q8_0 | 只在编译版本与后端支持时比较；记录准确 K、V 类型及 flash attention 状态 |
| 提示与协议 | 旧式无 system／无工具目录；最小 res/fc 协议 | grammar 有／无为单独质量与速度因素；全量目录先保留历史失败，不重放600秒 |
| 运行状态 | 进程重启首次请求；常驻无 KV 命中；显式前缀命中 | 进程冷启动不等于磁盘 page cache 冷；不为测试强制清全机缓存 |
| 构建与后端 | 现有 vendor ARM CPU build，必要时再对照固定新版 | 编译器、Release、编译选项、提交哈希、检测到的CPU能力、后端、库版本都存档 |

上下文、KV、batch 等选项的含义依据上述官方 server 文档；表内数值为针对当前板子和
历史失败提出的实验选择，并非业界统一最佳参数。权重大小不等于峰值进程内存。

Qwen3 官方给出的非思考采样为 temperature=0.7、top_p=0.8、top_k=20、min_p=0；
思考模式为 0.6／0.95／20／0，且不建议思考模式 greedy。
模式、template、seed、输出上限和 penalty 影响生成内容与长度，必须存档；
它们不用于大规模性能笛卡尔扫描。本项目旧模型经过微调，不能假定官方通用 Qwen3
的思考开关或模板仍成立，需先检查实际 GGUF 与旧输入。
[Qwen3-0.6B 官方模型说明](https://huggingface.co/Qwen/Qwen3-0.6B)。

建议性能内核部分固定 tg token 数；应用质量部分固定文本任务与最大输出预算，保留
实际输出与停止原因。这样避免“答得更短”被误判成后端更快，也不把长链思考当作
普通机器人回复的必要负载。

## 候选分阶段矩阵：本轮仅讨论，不执行

1. **资产与接口核对**：模型路径／hash／元数据、实际 vendor revision 与 `--help`，
   选择与旧项目一致的输入模板；确认可用 RAM 与现有进程，不启动 ROS 全链路。
2. **最小冒烟**：一份同源已确认模型，context1024、b128／ub64、1线程、f16 KV，
   短提示和最多32输出 tokens，单次墙钟上限建议60秒；只运行1次。
   若加载或内存预检不通过，记录失败，不自动扩大内存／context。
3. **线程筛选**：保持其余参数，1／2／4线程逐个运行；分别测 pp128 和 tg32，
   成功后仅对可行配置加入 pp512／tg128。每次独立子进程，允许逐项停止。
4. **内存与批处理**：只对线程筛选优胜点比较 b128／ub64、b256／ub64、b256／ub128；
   context2048 作为容量对照；只选择一个基准点比较 f16 与 q8_0 KV。
   不做 threads×batch×context×KV 的全组合。
5. **真实短任务**：普通中文回答、一个短动作、带参数动作、重复动作、非法调用，
   对比旧输入和最小协议；记录格式／动作质量，只做 dry-run。若需要讨论60工具
   目录，先 tokenize 与容量预检；现有600秒失败为已知对照，不默认再试。
6. **量化或新版 runtime 扩展**：只有同源资产和初轮可行性清楚后才考虑，先一份
   权重量化／一份新版构建，以减少变量；不得同时换权重、模板和 runtime 后归因。
7. **重复与报告**：先1次筛查、最终候选至少3次，保存配置、原始日志、采样记录和输出；
   HTML 展示配置对照、每次观测、失败原因、适用建议，明确哪些仅为文档推断。

上述阶段是预算受限的筛选法；60秒仍是诊断墙钟上限，不能写成机器人响应 SLA。

## 必须延续的资源边界及待确认点

历史最后两次受控试验使用 RLIMIT_AS=1536MiB、core=0、MALLOC_ARENA_MAX=1，
250ms 监控，MemAvailable<384MiB 或 SwapFree<512MiB 即终止。
当时 user systemd 的 MemoryMax 未实际落实 memory cgroup；不能把设置属性当作内存隔离。
旧代码在每轮 Goal 清 KV，因此常驻模型不等于前缀缓存复用。
证据：[既有性能记录](/home/orangepi/code/ros-robot/.scratch/offline-agent-integration/offline-llm-performance-backlog.md)。

建议本轮首批沿用这些已验证能落实的硬界，串行只跑一个模型进程；
独立 watchdog 覆盖加载、预填充、生成全阶段，超限终止整个子进程树，保留终止原因。
RLIMIT_AS 限虚拟地址，不等于 RSS：某模型因 mmap／虚拟预留加载失败，应记作预算内不可行，
不能误写成物理内存耗尽。watchdog 是已有重启事件后的约束，不承诺排除板级掉电或内核故障。
不自动增加 swap、不无限重试、不提高 nice 优先级、不清系统 page cache。

需要访谈统一：旧模型以哪个已确认权重为准；同源量化是否纳入本轮；
主要目的为交互短任务还是吞吐探索；是否需要三模型共存／并发阶段；
用户能接受的总测试时间、可用内存预算、TTFT与回答完成目标；质量先用小型人工核对集
还是扩展标准数据集。没有这些答案前，不能声称最终选型或生产配置已确定。

## 板端同源身份补核（2026-10-21）

从旧BF16经现有llama-quantize重新生成的Q8与原Q8 SHA-256完全一致：`27dc23f5d549e8e4c11defbafcbb8e405db995ef82e32a3cc2fa0b56b6c5f615`。Q5_K_M/Q4_K_M直接由同一BF16生成，原先“尚未证实”的谱系问题已经解决。原生Q4 CPU_REPACK加载崩溃；固定输入，仅关闭repack后完成，后续对照沿用`--no-repack`。详见[实测记录](../../../reports/rk3566/2026-10-21/results.md)和各run manifest，而非将该问题解释成量化质量结论。
