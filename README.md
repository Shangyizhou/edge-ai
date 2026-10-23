# Edge AI

在 **RK3566 · Orange Pi 3B · 4GB** 上验证机器人本地语音交互：**听懂 → 理解 → 回答 → 发声**。

**[查看 HTML 报告 ↗](https://shangyizhou.github.io/edge-ai/reports.html)** · [语音评测主报告](https://shangyizhou.github.io/edge-ai/reports/voice-screening/report.html) · [任务进展](https://github.com/Shangyizhou/edge-ai/issues/7)

## 当前进展

| 模块 | 当前方案 | 验证情况 |
| --- | --- | --- |
| ASR · 语音识别 | Zipformer zh14M · 混合 INT8 / FP32 | 完成 3 条语音对照，业务指令转写经用户确认 |
| LLM · 理解与调用 | Qwen3-0.6B LoRA · Q4_K_M | Mac/RK3566独立集各84/84工具请求通过原生/JSON/Schema；板端PSS约600MiB，人设仅21/36 |
| TTS · 语音合成 | MeloTTS zh_en · FP32 | 已生成音频，合成等待较长，听感待评审 |

**[Qwen生命周期离线报告](studies/voice-interaction/experiments/final/2026-10-22-qwen-final132-v1/report.html)**：已完成基线、Mac LoRA、合并转换、量化、RK3566与528次正式请求。原生格式试点通过；人设仍有误调用，角色配置尚不能可靠省略。板端工具完整调用P50/P95约11.6/27.3秒，KV冷首例约174秒。

**下一步：**用新来源训练数据和新封存集改进角色/路由泛化；生产接入、完整语音链路和机器人共跑另行验证。新Qwen报告默认不进入Pages导出。

## 资料入口

[模型与证据](studies/voice-interaction/models.md) · [实验记录](studies/voice-interaction/experiments/rk3566/README.md) · [业务适配方案](studies/voice-interaction/research/2026-10-22-qwen-adaptation/README.md) · [推进计划](studies/voice-interaction/plan.md)

<sub>当前结论仅依据本轮 skill 流程；旧资料已[归档](archives/README.md)。配置、日志与哈希保留在仓库，模型权重和录音存放于仓库外。生产代码维护在 ros-robot。</sub>
