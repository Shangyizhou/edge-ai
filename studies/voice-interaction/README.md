# 机器人本地语音 · 当前 skill 流程

更新：2026-10-22。Orange Pi 3B / RK3566 / 标称4GB，实际MemTotal约3.83GiB。目标是本地“听懂 → 回答 → 合成 → 播放”，后续再验证机器人共跑。

当前入口只保留按skill重新选型后的流程。旧实验和旧结论已[仓库外归档](../../archives/README.md)，不作为当前推荐依据。

## 当前结论

| 部分 | 已确认什么 | 尚未确认什么 |
| --- | --- | --- |
| ASR zh14M混合INT8 / FP32 | 同3条有声材料真实运行；机器人指令输出与用户确认文本一致。实时INT8 CPU26.05%、PSS115.28MiB；FP32 CPU29.47%、PSS158.69MiB | 两条公开参考子集CER均45.45%；不代表整体识别率或完整交互达标 |
| Qwen2.5-0.5B Q4_K_M | 通用6任务检查5/6；另外6工具的fc/res兼容路径诊断0/3 | 0/3只覆盖兼容路径，不能外推当前ros-robot原生tool_calls；原生调用未测 |
| Qwen3-0.6B BF16 / Mac MLX Metal | 14条开发用例原生基线：精简system工具格式/Schema/Registry 10/10、人设1/3；完整system工具格式8/10、人设3/3 | 仅未微调Mac小集对照；不能继承旧兼容路径结论或推断新权重板端效果 |
| Qwen3-0.6B LoRA 32微步试点 | 已实际训练4次优化器更新，327680可训练参数，MLX峰值约2.090GB；adapter/合并/F16/Q4分别完成7例冒烟，代表工具3/3、角色1/3；Q4约396.7MB | 只证明小步训练及合并转换通路；完整工具/人设适配、板端与产品验收仍未完成 |
| Qwen3-0.6B 选定LoRA / Mac验证 | 300训练/60验证；原短提示人设上下文审核1/18→17/18；选定路由短提示（不含事实）下工具JSON/Schema 36/36、人设18/18、工具精确33/36 | 合成验证与Codex审核，不是人工/生产验收；仍有跟随开关和字符串复制失败；最终封存集、量化及板端评测未完成 |
| Melo zh_en FP32 | 原4条文本均生成有效WAV，整句PCM就绪约18.9–25.8秒 | 尚未试听评审，发音/自然度与实际扬声器等待未知 |

ASR资源只取本轮3条有声输入的实时推理窗，CPU为被测进程树占整机4核容量、PSS为200ms采样峰值。各模块独立运行，不相加推算共跑。[模型详情](models.md)列出精度、框架、后端与证据。

## 当前保留的流程

1. [资料选型](research/2026-10-22-local-stack/README.md)：官方来源与候选，忽略旧本地实测。
2. [冻结准备](research/2026-10-22-runtime-preparation/README.md)：资产与执行配置；早期加载检查不能当作推理通过。
3. [实际就绪](experiments/rk3566/2026-10-22-preparation-smoke-v1/README.md)：ASR解码、LLM生成、TTS合成均完成最小真实推理。
4. [单模块初筛](experiments/rk3566/2026-10-22-voice-screening-v2-r1/README.md)、[ASR三条材料对照](experiments/rk3566/2026-10-22-asr-three-samples-v1/README.md)：原始输入/输出、资源、计时与哈希保留。
5. [业务兼容路径诊断](experiments/rk3566/2026-10-22-qwen-business-fit-v1/README.md)：保存失败证据；当前目标已澄清为原生tool_calls，不沿用该兼容协议训练。
6. [Qwen3业务LoRA方案](research/2026-10-22-qwen-adaptation/README.md)：保留当时尚未训练的研究记录，后续范围以当前规格和实验为准。
7. [Mac原生调用与人设基线](experiments/mac/2026-10-22-qwen-native-baseline-v1/README.md)：同一官方Qwen3、9个选定工具、14条开发输入，对照完整/精简system；真实输出、资源与失败均保留。[离线HTML](experiments/mac/2026-10-22-qwen-native-baseline-v1/report.html)。
8. [最小LoRA与导出试点](experiments/mac/2026-10-22-qwen-lora-export-pilot-v1/README.md)：真实32微步、合并/转换/量化和逐制品冒烟；保留转换兼容与本地代理失败及修复记录。

9. [关键工具与人设适配](experiments/mac/2026-10-22-qwen-selected9-adaptation-v1/README.md)：真实300训练/60验证，三轮训练与完整/精简提示对照，保留全部失败；最终测试仍封存。[配对HTML](experiments/mac/2026-10-22-qwen-selected9-adaptation-v1/report.html)。

## 下一步

实施已进入[集成PR #15](https://github.com/Shangyizhou/edge-ai/pull/15)：#9基线、#10最小LoRA导出与#11工具/人设验证完成，#12香橙派试点与#13同权重量化对照独立推进。三个新增技能已从[personal-skills PR #3](https://github.com/Shangyizhou/personal-skills/pull/3)来源安装，本仓库维护实验结果。

先选关键有用工具，冻结Schema、原生调用样例和独立测试集；Mac做小规模LoRA，将固定SystemPrompt行为和重复示例尽量学入模型，推理继续提供精简指令及选定工具目录。首轮独立验证Agent原生tool_calls、JSON合法和Schema接收，模型调通后再改旧项目代码，不以旧C++或全60工具业务覆盖作为前置条件。[细化计划及用户范围澄清](research/2026-10-22-mac-qwen-plan/README.md)：已确认M5/16GB、磁盘剩约58GiB，SSH可达RK3566；训练依赖、基线及最小LoRA导出已实际验证，完整适配与板端结果仍在补齐。部署优先评估Q4_K_M与小上下文，KV和共跑资源仍需测量。

完整语音交互、ROS/视觉共跑与硬件动作均未验收，不因最小推理或几条成功样例宣称产品通过。[准备计划](plan.md) · [接入边界](integration.md) · [实验索引](experiments/rk3566/README.md)。

当前认可格式已固化为[独立HTML主报告](reports/2026-10-22-voice-screening/report.html)，公开版不携带录音；网站只提供报告列表。可试听的Mac离线版仍在临时目录 `/tmp/edge-voice-report-draft/report-mac.html`；它支持Mac离线查看和试听。原实验HTML/JSON未修改；当前展示格式已写入本机edge-model-selection。
