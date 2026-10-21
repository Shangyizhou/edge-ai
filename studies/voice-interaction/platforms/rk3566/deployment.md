# RK3566 语音模型已验证部署

验证日期：2026-10-21。设备4核Cortex-A55、4GB RAM、Linux aarch64、Python3.8，CPU408–1800MHz；系统驱动/内核没有因本轮实验更换。

| 模块 | 已走通路线 | 入口 |
| --- | --- | --- |
| ASR CPU | sherpa-onnx1.13.8 + 旧bilingual Zipformer混合int8 | [ASR部署](asr.md) |
| ASR NPU | 同源官方2025-03-19 compiler2.2.0 RKNN + runtime2.2.0 | [ASR部署与失败排查](asr.md) |
| SummerTTS | 旧C++/Eigen/OpenMP实现 + 原single_speaker_fast权重 | [TTS部署](tts.md) |
| sherpa/Piper TTS | huayan非小雅音色、中文VITS、Melo ONNX | [TTS部署](tts.md) |
| Qwen | 旧微调Qwen GGUF + 现有ARM llama.cpp CPU | [Qwen部署](qwen.md) |

视觉模型的部署另见[目标检测主题](../../../object-detection/platforms/rk3566/deployment.md)。

本目录是已实际执行路径的整理，不是假定从空系统一键安装就全部成功。公开下载URL/尺寸/hash见 [资产清单](assets)；旧项目源码、私有微调权重、历史录音按本机外置路径使用，未上传。

首先核对 [首轮报告](../../experiments/rk3566/2026-10-21-baseline/results.md) 中的版本、精度和测量差异；复测配置在 `tools/edge_benchmark/*.json`。配置包含本板已有绝对路径，换机器需要调整顶层python、binary、model、wavs、vits、env，以及native命令里的路径。不要批量改写报告中的历史配置。

Summer和Qwen没有在本轮通过RK3566 NPU验证。框架支持RK NPU不等于每个模型都有可用后端；当前NPU实测覆盖ASR与YOLOv6，包括二者活跃共跑。
