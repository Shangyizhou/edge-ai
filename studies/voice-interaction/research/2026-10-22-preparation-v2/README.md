# 新版 skill：第 1 步测试准备与协议冻结

日期：2026-10-22。skill来源 `Shangyizhou/personal-skills`，commit `2d0d5e873454d17ec77e6b9a7810195db1130bf1`。已同步到本机，原版备份路径及安装文件哈希见[同步记录](skill-sync.json)。

## 当前决定

首轮仍优先准备中文Zipformer14M CPU混合INT8、Qwen2.5-0.5B-Instruct Q4_K_M、MeloTTS中文FP32。新版要求已补齐：每个候选的保留理由、具体下一次实验、执行或暂缓条件，以及可用于适配器实现的测试协议。

**设计和用例清单已冻结，执行资产冻结尚未完成。** 不能将此描述为已具备可直接运行的全部配置。此次未执行推理、下载权重、启动ROS或更改生产配置；此前本地实测和模型共识文本均未作为本轮推荐或质量参考。

## 已核实与缺口

- [当前设备快照](device.json)：RK3566 OPi3B、4核、实际MemTotal、内核和OS；NPU驱动读取仍有权限缺口，不继承历史版本。
- [ASR用例清单](asr-fixtures.json)：6条现有音频均重新核对SHA256。这里只复用输入资产；机器人指令旧模型共识转写已清除，仅两条FLEURS独立参考用于CER。初筛3条，复测6条，音频不入Git。
- [LLM/TTS用例](text-fixtures.json)：6条固定中文任务及逐条判定rubric、4条TTS文本；覆盖状态复述、否定、数字、未知事实、结构化意图和短回复。结构化输出只检查文本，不执行动作。
- [模型资产准备检查](asset-readiness.json)：限定搜索根下未发现精确目标zh14M、官方Qwen2.5/Qwen3及Matcha资产；发现Melo目录。目录存在不代表模型revision/hash与目标一致。旧私有微调Qwen及旧bilingual不作为替代。
- CPU运行库的确切binary、实际加载库、commit/ABI/hash，模型全资产hash，当前驱动和NPU编译器metadata仍需准备；不能把研究中指定的版本当作已安装事实。

## 可直接指导实现的测试约定

完整参数、指标定义和候选映射见[benchmark-plan.json](benchmark-plan.json)。它是**实现规格**，不是现有benchmark.py可直接运行的配置文件。

ASR和TTS固定2线程；LLM固定2线程、context2048、batch128、microbatch64、KV f16、最多96新token、temperature0，不复用prompt缓存。ASR100ms绝对时间回放与非实时吞吐分开，尾静音3.2s；端点参数固定。ASR INT8与FP32保持其余条件一致，不称CPU/NPU受控对照。

每进程加载一次，首请求单列、独立预热后再测，待机窗口3s，进程树资源每200ms采样。单候选预算600s、单case90s、首轮总预算1800s；达到任一预算保留已完成输出并停止。入围后独立3轮复测。MemAvailable低于600MiB中止本轮进程，是实验保护条件，不是产品验收门槛。

计时用monotonic时钟：ASR首partial相对第一块提交，final相对文件末尾计划到达时刻；无人工末音不称人工EOS等待。LLM请求到首非空token、首个标点闭合可播短句分开。TTS请求到首可用PCM与全部PCM分开，若API仅整句返回就如实记录；本轮不测扬声器首音。

资源按加载/待机/推理分窗，记录PSS/RSS、CPU核秒/整机容量占比及主机余量。保存逐条逐轮数据和样本量，P50/P95注明nearest-rank及n，小样本不声称稳定尾延迟。质量、执行完成和性能达标分开表示；无业务阈值时产品验收UNKNOWN。

## 候选到实验的顺序

| 候选 | 下一步 | 改变选择的证据 |
| --- | --- | --- |
| zh14M CPU INT8 | 补齐资产后先筛选，并配同包FP32 | 独立参考识别退化、资源超预算或积压触发替换/调整 |
| RKNN bilingual | 暂缓；先核验compiler/runtime/driver及精度 | 兼容和同任务输出成立后，才加入资源比较 |
| Melo FP32 | 核验资产后4条文本首PCM、RTF及听检 | 数字/否定句发音失败或等待不合适触发替换 |
| Matcha + Vocos | 暂缓；限定非商业研究用途 | 用相同文本证明质量收益且资源可接受后才考虑 |
| Qwen2.5 Q4 | 补齐官方资产后6条固定任务 | 逐项任务失败或首可播句等待不合适触发备选 |
| Qwen3 Q8 | 第二批；核验模板关闭thinking | 相同任务质量改善且等待/资源可接受才替换 |

“超预算/不合适”需按已记录建议或后续用户门槛解释，不据此证明整块RK3566硬件无法满足需求。原生partial、普通话优先、半双工仍为起点假设，业务延迟/CER/内存门槛尚未经用户确认。

## 交付与执行边界

[新版离线报告](report.html) · [选型JSON](selection.json) · [实现规格](benchmark-plan.json) · [工单#7](https://github.com/Shangyizhou/edge-ai/issues/7)。旧[资料筛选报告](../2026-10-22-local-stack/report.html)原样保留，官方来源结论沿用该轮证据，不声称本轮重新检索全部模型。

开始推理前必须满足资产、运行库、输入hash和适配器能力检查；未确认业务阈值不妨碍研究性筛选，但不能出产品PASS。下一项可执行工作是补齐首选资产及运行库，并按本规格生成适配器运行配置。当前状态：`DESIGN_FROZEN_ASSET_FREEZE_PENDING`，完整交互仍为 `INSUFFICIENT_EVIDENCE`。
