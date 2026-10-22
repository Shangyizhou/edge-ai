# Qwen2.5-0.5B 的 ros-robot 业务适配验证

日期：2026-10-22。目标是检查本轮选定的官方 Qwen2.5-0.5B-Instruct Q4_K_M 能否理解现有 ros-robot prompt 与 function call 契约，不复用历史本地模型测量作为结论。

## 结论：当前组合未通过业务调用检查

本次6工具诊断小集，3条调用检查 **0/3通过**。第一条没有形成合法的参数调用，第二条重复调用并截断，第三条虽通过调用协议和Registry参数校验，却违背“只解释、不执行”的意图。实际原文见 `assessment.json` 与 `response-review.json`。

3次首内容等待约118.63–119.55秒，完整输出124.71–159.34秒；推理窗口CPU约49.48–49.88%（整机4核），PSS峰值最高约603.88MiB。项目offline.json的provider_timeout为60秒，本次为拿到诊断输出放宽至210秒；不能把该HTTP结果当成原ROS C++节点超时实测。

这些证据针对当前官方0.5B Q4模型与本地调用契约组合，尚未独立分离模型能力、prompt和格式影响；不外推所有Qwen或RK3566不可行。先做业务策略/示例提示对照，必要时比较另一候选，再考虑接入动作执行。

## 当前已确认的接入缺口

- 当前项目为 `/home/orangepi/code/ros-robot`，commit `23ef814cfb0a8c174b42b288454c30d5498e88d0`，开始与结束均核对源码身份。未修改生产项目。
- `create_default_actions` 加感知动作注册后，共60个业务工具。完整本地prompt按当前官方模型tokenizer计数约5664–5669 tokens（模板/输入略有不同）；超出当前2048上下文和项目4096示例，尚须保留回复预算。
- 项目 `offline.json` 指向另一份 `qwen3-robot-q8_0.gguf`。其训练模板、过往运行记录不能直接证明官方Qwen2.5支持相同业务。
- 在线路径是自然中文和原生 `tool_calls`；本地兼容路径是 `fc/res` JSON，调用字符串经 `_parse_legacy_reply` 转为 ToolCall，再交 `ActionRegistry.validate_calls` 整批绑定参数。JSON语法正确不代表调用正确。
- 在线完整系统提示包含否定、缺参、状态事实与动作边界；本地 `_prompt` 没有加载它，只包含简短JSON格式、工具限制与目录。因此还存在离线业务策略对齐问题。

## 本次诊断范围

只用现有官方Qwen和冻结的llama.cpp b6500 CPU二进制运行。为验证基本业务理解，从60个工具中取6个原始Schema：`volume_set`、`play_music`、`enable_lidar`、`disable_lidar`、`enable_tracking`、`start_following`。保留工具名、原说明、参数与默认值，没有手写替代schema。

只适配训练模板外壳为官方ChatML；保留本地system内容、项目fc-first grammar、真实解析器和参数校验。通过HTTP llama-server进行诊断，不冒充C++ ROS节点集成测量。3条固定输入、每条一轮生成，greedy、seed42、cache_prompt=false、最多128输出tokens，线程2、context2048、batch128、ubatch64、KV F16；正式输入前有最多8-token的预热请求和3秒待机。单请求210秒、总预算750秒，MemAvailable低于600MiB停止。

| 固定输入 | 预期调用 |
| --- | --- |
| 先把音量调到30，再播放夜曲。 | `volume_set(level=30)` → `play_music(song_name="夜曲")` |
| 不要开启跟随，只开启雷达融合。 | 仅 `enable_lidar()` |
| 只解释关闭雷达融合会发生什么，不要执行。 | 空调用列表，并提供说明 |

期望调用在推理前冻结于 `cases.json`。模型输出、解析失败或截断均保留。没有启动ROS、Agent执行器、动作handler、云服务、音频或运动设备；只组装工具声明和调用纯校验接口，连模拟动作也不执行。

## 结果、计时与证据

实际测量：`results.json`；分层复核：`assessment.json`。逐条保留 `request.json`、`stream.json`、`result.json` 与边界资源采样；全程200ms资源采样见 `resources.jsonl`，原生服务器记录见 `native.log`。完整/小目录及两种模板的prompt与token计数均保存，没有把超长完整目录静默截断后送入生成。

首内容计时从HTTP请求前到首个非空片段，完整等待到服务流收齐，包含prompt处理。CPU/PSS取每条请求窗口，加载、预热、待机另留日志；3次请求不构成稳定尾延迟或产品验收。

分层复核区分：生成是否正常结束 → JSON语法 → 本地调用协议 → Registry参数绑定 → 预期函数/参数/顺序。原生b6500用 `stop_type=eos` 表示生成完整，初始执行器误读了并不存在的 `stopped_eos` 字段；`assess.py` 从未修改的原始最终事件重新判定结束，不改变输出或耗时，并以5项离线回归检查防止把JSON语法、参数绑定与意图混为一谈。`results.json` 保留初始状态供追溯。

实际回复的说明质量与动作成功断言由Codex助手按 `review-rubric.json` 另行检查；没有独立人工复核。调用期望先冻结，回复细则是在第一条输出已知、第三条未返回时记录，见文件中的具体范围说明。

源码提取清单：`source-manifest.json`；只读分析：`project-audit.json`；模型/命令/hash：`execution-plan.json`；实际运行库一致性：`runtime-verification.json`。`measurement-source/` 保存提取、运行、分层复核及报告脚本，`project-source/` 为生产源码证据副本，生产维护仍在ros-robot。

报告入口：`/tmp/qwen-business-fit/report-mac.html`，使用已确认的结论先行、实际输入输出、资源与固定导航格式，JSON证据已内嵌，可单文件复制至Mac；不覆盖原语音模块HTML。

## 未验证的范围

不把6工具小集当60工具完整业务；未测缺参澄清、重复动作、多轮记忆、当前状态查询、工具执行回执、ROS集成或完整语音交互。本次不是模型重训练、提示词优化实验或全候选比较。完整prompt超上下文是当前组合的兼容问题，不证明整块RK3566无法完成机器人业务。
