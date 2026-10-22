# RK3566 机器人本地语音模型重新筛选

日期：2026-10-22（Asia/Shanghai）。本轮仅做官方资料筛选，**不使用历史本地实测作选型依据**，也未运行模型。历史实验、配置、源码快照和输出保持原样。

## 首轮建议

| 模块 | 优先验证 | 备选或调查 |
| --- | --- | --- |
| ASR | Streaming Zipformer 中文14M，sherpa-onnx CPU，encoder/joiner INT8 + decoder FP32；同包FP32作质量对照 | RK3566专用 bilingual Zipformer RKNN；先核验compiler/runtime/driver |
| LLM | Qwen2.5-0.5B-Instruct，官方GGUF Q4_K_M，llama.cpp CPU | Qwen3-0.6B官方Q8_0，关闭thinking；Qwen3.5-0.8B列第二批调查 |
| TTS | MeloTTS zh_en，sherpa-onnx CPU FP32 | Matcha zh Baker + Vocos，仅非商业研究备选 |

这是一套优先实验组合，不能宣称最快、准确率最好或交互达标。选择依据是公开制品、中文功能、运行路径和小规模；不把其它硬件测速移植到RK3566。官方RKLLM平台列表没有RK3566，LLM先走CPU。

## 环境和需求

只读确认当前设备为Orange Pi 3B/RK3566、4核A55、aarch64、Ubuntu20.04 Orange Pi1.0.8、kernel5.10.160，MemTotal4017020KiB（约3.83GiB）。见[设备快照](device.json)。当前NPU驱动接口权限不足，历史0.9.6仅供环境调查，不是此次核验结果。

用户确认：本地ASR、LLM、TTS完成机器人语音交互，排除旧实测。现有项目还要求为ROS和YOLO留资源。普通话优先、ASR原生partial/final、半双工短回复和按句TTS是本轮起点假设，双工/打断/AEC以及英文覆盖尚待需求冻结。未收到用户确认的延迟、质量、内存、功耗阈值。

建议首轮预算为ASR/LLM/TTS进程树峰值PSS分别300/1000/400MiB，主机最低MemAvailable 600MiB；这是实验目标提议，不能由文件尺寸推算实际可用性。LLM建议先context2048、回复64–96token、2线程；对话使用固定模板。ASR和TTS线程分别冻结，避免多模块线程过量。

## 复现边界

- CPU ASR/TTS：sherpa-onnx v1.13.8，commit `11afbd009a7f8c08f4bcf2fc1b265d0df4670fbf`。该tag shared aarch64默认ORT1.28.2，依赖包SHA256见[源码快照](sources/sherpa-ort-aarch64.cmake)。实际构建、加载库及ABI仍需新实验冻结；不混入旧安装。
- 两个LLM：llama.cpp b6500，commit `a7a98e0fffed794396b3fbad4dcdbbc184963645`，CPU候选构建；不把支持架构当作本机执行验收。模型revision、文件名和发布SHA256见JSON。
- RKNN：当前公开下载资产已更新，compiler及精度未核对，不沿用历史兼容结论；不是已配齐可直接跑的组合。与中文14M不同模型，不作为同源后端对照。
- Melo上游MIT，转换模型需保留许可溯源；Matcha Baker训练集限非商业，商业产品不作为默认选择。各模型身份和许可来源见[官方核查记录](../2026-10-22-local-stack-sources.md)。

## 产物与后续验证

[离线HTML报告](report.html) · [结构化选型JSON](selection.json) · [官方来源核查](../2026-10-22-local-stack-sources.md) · [来源快照及SHA256清单](sources-manifest.json)。HTML仅由JSON生成；JSON中的补充调查记录在本说明及官方核查中展开。

后续遵循[轻量SOP](../../../../docs/methodology/model-evaluation-sop.md)：环境/资产冻结→单模块固定小集一轮→仅入围配置三轮复测→ROS/YOLO共跑→完整听说链路。优先复用6–10条、约1分钟材料，不新增大规模标注要求。质量有可靠参考才计算；P95需如实注明小样本局限，不把重复轮次当独立语料。

ASR首partial和final交付、LLM首token和首可播句、TTS首PCM和扬声器首音分别计时；用户末音无人工标签时用能量锚点或文件边界并注明。按句合成不自动等于增量TTS，全双工、播放回声、打断、恢复监听需另验。

本轮执行状态：未执行。性能、质量、共跑与完整交互：UNKNOWN。完整验收结论：**INSUFFICIENT_EVIDENCE**。不生成伪造benchmark结果或PASS。
