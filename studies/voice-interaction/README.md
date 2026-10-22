# 机器人本地语音 · 当前 skill 流程

更新：2026-10-22。Orange Pi 3B / RK3566 / 标称4GB，实际MemTotal约3.83GiB。目标是本地“听懂 → 回答 → 合成 → 播放”，后续再验证机器人共跑。

当前入口只保留按skill重新选型后的流程。旧实验和旧结论已[仓库外归档](../../archives/README.md)，不作为当前推荐依据。

## 当前结论

| 部分 | 已确认什么 | 尚未确认什么 |
| --- | --- | --- |
| ASR zh14M混合INT8 / FP32 | 同3条有声材料真实运行；机器人指令输出与用户确认文本一致。实时INT8 CPU26.05%、PSS115.28MiB；FP32 CPU29.47%、PSS158.69MiB | 两条公开参考子集CER均45.45%；不代表整体识别率或完整交互达标 |
| Qwen2.5-0.5B Q4_K_M | 通用6任务检查5/6；另外6工具的fc/res兼容路径诊断0/3 | 0/3只覆盖兼容路径，不能外推当前ros-robot原生tool_calls；原生调用未测 |
| Melo zh_en FP32 | 原4条文本均生成有效WAV，整句PCM就绪约18.9–25.8秒 | 尚未试听评审，发音/自然度与实际扬声器等待未知 |

ASR资源只取本轮3条有声输入的实时推理窗，CPU为被测进程树占整机4核容量、PSS为200ms采样峰值。各模块独立运行，不相加推算共跑。[模型详情](models.md)列出精度、框架、后端与证据。

## 当前保留的流程

1. [资料选型](research/2026-10-22-local-stack/README.md)：官方来源与候选，忽略旧本地实测。
2. [冻结准备](research/2026-10-22-runtime-preparation/README.md)：资产与执行配置；早期加载检查不能当作推理通过。
3. [实际就绪](experiments/rk3566/2026-10-22-preparation-smoke-v1/README.md)：ASR解码、LLM生成、TTS合成均完成最小真实推理。
4. [单模块初筛](experiments/rk3566/2026-10-22-voice-screening-v2-r1/README.md)、[ASR三条材料对照](experiments/rk3566/2026-10-22-asr-three-samples-v1/README.md)：原始输入/输出、资源、计时与哈希保留。
5. [业务兼容路径诊断](experiments/rk3566/2026-10-22-qwen-business-fit-v1/README.md)：保存失败证据；当前目标已澄清为原生tool_calls，不沿用该兼容协议训练。
6. [Qwen3业务LoRA方案](research/2026-10-22-qwen-adaptation/README.md)：工具目录仍传递，训练目标是当前ros-robot业务规则与原生调用。尚未训练。

## 下一步

先准备独立Mac训练项目：从ros-robot导出工具定义、来源commit/hash、原生调用训练样例和独立测试集；Mac做小规模LoRA/QLoRA验证，模型合并、转换、量化后回板子测调用正确率与资源。Mac硬件由用户报告，尚未检查依赖或实跑。

完整语音交互、ROS/视觉共跑与硬件动作均未验收，不因最小推理或几条成功样例宣称产品通过。[准备计划](plan.md) · [接入边界](integration.md) · [实验索引](experiments/rk3566/README.md)。

当前认可格式已固化为[独立HTML主报告](reports/2026-10-22-voice-screening/report.html)，公开版不携带录音；网站只提供报告列表。可试听的Mac离线版仍在临时目录 `/tmp/edge-voice-report-draft/report-mac.html`；它支持Mac离线查看和试听。原实验HTML/JSON未修改；当前展示格式已写入本机edge-model-selection。
