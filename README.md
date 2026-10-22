# Edge AI

在 **RK3566 · Orange Pi 3B · 4GB** 上验证机器人本地语音交互：**听懂 → 理解 → 回答 → 发声**。

**[查看 HTML 报告 ↗](https://shangyizhou.github.io/edge-ai/)** · [语音评测主报告](https://shangyizhou.github.io/edge-ai/reports/voice-screening/report.html) · [任务进展](https://github.com/Shangyizhou/edge-ai/issues/7)

## 当前进展

| 模块 | 当前方案 | 验证情况 |
| --- | --- | --- |
| ASR · 语音识别 | Zipformer zh14M · 混合 INT8 / FP32 | 完成 3 条语音对照，业务指令转写经用户确认 |
| LLM · 理解与调用 | Qwen2.5-0.5B · Q4_K_M | 已做通用生成测试，原生工具调用尚未验证 |
| TTS · 语音合成 | MeloTTS zh_en · FP32 | 已生成音频，合成等待较长，听感待评审 |

**下一步：**准备 Qwen3 小模型的业务 LoRA 验证，先在 Mac 训练，再回板子测工具调用与资源消耗。训练尚未开始，完整语音链路与机器人共跑尚未验收。

## 资料入口

[模型与证据](studies/voice-interaction/models.md) · [实验记录](studies/voice-interaction/experiments/rk3566/README.md) · [业务适配方案](studies/voice-interaction/research/2026-10-22-qwen-adaptation/README.md) · [推进计划](studies/voice-interaction/plan.md)

<sub>当前结论仅依据本轮 skill 流程；旧资料已[归档](archives/README.md)。配置、日志与哈希保留在仓库，模型权重和录音存放于仓库外。生产代码维护在 ros-robot。</sub>
