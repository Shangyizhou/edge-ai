# RK3566 下一轮语音性能调研：成熟 NPU 路线核查

日期：2026-10-21（Asia/Shanghai）。本次只查官方文档、源码和小型元数据，没有下载模型、转换、推理或修改生产代码。筛选条件为中文可用、明确支持 RK3566、优先直接部署产物、不自研模型转换和后端；视觉维持缩放后输入 640×352、30fps。

## 结论与优先级

**本次没有确认到同时满足上述条件的新增中文 NPU TTS 候选，白名单为 0。** 不应将框架支持 RKNN、VITS 模型可下载、RK3588 的部署成功，拼接成 RK3566 中文 TTS 即用结论。

**首先把 benchmark 中跑通的 NPU ASR 接到机器人常驻语音链路。** 当前生产适配器仍逐个 WAV 启动 `subprocess.run`，且显式传入 `--provider=cpu`；所以“板上已有 NPU benchmark”不等于“机器人当前 ASR 已走 NPU”。采用官方 Sherpa RKNN API/麦克风示例保持模型常驻，复杂度中等，主要在生命周期、音频块喂入和 endpoint/重置，而非重训或自研转换。[当前适配器](/home/orangepi/code/ros-robot/ros2_ws/src/robot_voice/robot_voice/sherpa_asr.py:65)、[官方麦克风示例入口](https://k2-fsa.github.io/sherpa/onnx/rknn/models.html)

优先继续使用已经跑通的 Zipformer NPU 组合，补常驻模型的实时语音回放、首个 partial、末音到 final、积压和 P95，并在 YOLO 30fps 下复测。已有共跑记录使用不断重启 CLI 的约 10 秒文件，包含加载，主要证明共享 NPU 时吞吐干扰；尚不能判断用户说完后的等待。已有 YOLO 共跑 ASR 计算 RTF 从约 0.30 升至 0.50～0.52，但视觉吞吐维持 30fps。[现有板端报告](../../object-detection/experiments/rk3566/2026-10-21-yolo/results.md)

ASR 的成熟路线已经存在：Sherpa 官方明确列 RK3566，并提供目标专用 RKNN Zipformer 下载与文件/麦克风示例。本机成功组合仍应固定到已验证的历史 compiler 2.2.0 产物和 runtime 2.2.0；不能因上游有更新包就抹掉本机的兼容性证据。[官方支持板列表](https://k2-fsa.github.io/sherpa/onnx/rknn/index.html)、[官方下载与运行例子](https://k2-fsa.github.io/sherpa/onnx/rknn/models.html)、[本地已通过组合记录](speech.md)

## TTS 核查边界

Rockchip 源码固定为 `837db8e992815ff8647eadb709f07067f4bc3a71`，避免移动分支与网页缓存版本混用。

| 路线 | 官方明确支持 RK3566 | 可获取产物与缺口 | 是否进入本轮中文 NPU 候选 |
| --- | --- | --- | --- |
| Rockchip MMS-TTS | 是，示例支持列表逐项列出 | 官方示例为英文 `facebook/mms-tts-eng`；提供 encoder/decoder ONNX、RKNN 转换脚本及 C++/Python demo；本次未确认现成目标专用 `.rknn` 下载 | 否，英文示例不能充当中文方案 |
| Sherpa VITS / Melo | 未确认该 TTS 后端的 RKNN 实现 | VITS/Melo 路径创建 `Ort::Session`；不能把 Sherpa ASR 的 RKNN 支持当成这些 TTS 模型的支持 | 否，未确认成熟即用路径 |

来源：[MMS-TTS 固定版说明](https://github.com/airockchip/rknn_model_zoo/blob/837db8e992815ff8647eadb709f07067f4bc3a71/examples/mms_tts/README.md)、[固定版模型下载脚本](https://github.com/airockchip/rknn_model_zoo/blob/837db8e992815ff8647eadb709f07067f4bc3a71/examples/mms_tts/model/download_model.sh)、[Sherpa VITS/Melo 执行代码](https://github.com/k2-fsa/sherpa-onnx/blob/master/sherpa-onnx/csrc/offline-tts-vits-model.cc)。本次核查的 Rockchip `examples` 清单只有 `mms_tts` 这一项 TTS，没有 `melo_tts` 示例；这只是该官方仓范围内的事实，不代表互联网中不存在第三方实现。[官方目录](https://github.com/airockchip/rknn_model_zoo/tree/837db8e992815ff8647eadb709f07067f4bc3a71/examples)

MMS-TTS 并非“全程 CPU 零占用”：固定版转换脚本显式把 encoder 两个算子放到 CPU；C++ 运行包含 tokenizer/CPU middle process 和两次 NPU 调用，固定词表 38、输入长度 200、16kHz 输出。改中文至少还要处理模型、中文前端/词表和导出兼容性，已超出直接部署示例的范围。[转换脚本](https://github.com/airockchip/rknn_model_zoo/blob/837db8e992815ff8647eadb709f07067f4bc3a71/examples/mms_tts/python/convert.py)、[C++ 约束](https://github.com/airockchip/rknn_model_zoo/blob/837db8e992815ff8647eadb709f07067f4bc3a71/examples/mms_tts/cpp/process.h)、[导出脚本](https://github.com/airockchip/rknn_model_zoo/blob/837db8e992815ff8647eadb709f07067f4bc3a71/examples/mms_tts/python/export_onnx.py)。

官方表给出英文 MMS-TTS token-200 FP16 在 RK3566/RK3568 列的参考 RTF 0.311；该数字不是本机实测，也不能用于推断中文速度或与 YOLO/ASR 共跑速度。[官方参考表](https://github.com/airockchip/rknn_model_zoo/blob/837db8e992815ff8647eadb709f07067f4bc3a71/README.md)

## 工作量判断与下一轮验收建议

以下是依据接入要求作出的工程判断，不是实测耗时或交付承诺。

| 项目 | 复杂度 | 主要工作及成功条件 |
| --- | --- | --- |
| 常驻 NPU ASR + 实时回放 benchmark | 低～中 | 复用已成功模型/runtime；增加持续 PCM 喂入与计时，报告 partial、endpoint、积压、CPU 核秒和质量 |
| endpoint 规则扫描 | 低 | 仅在延迟分解后修改静音阈值；保留短停顿/慢说样本，验证提前截断率；这优化 final 等待，不保证加快 NPU 算子 |
| YOLO + 常驻 ASR 共跑 | 中 | 30fps 输入保持不变，观察视觉 P95、掉帧和 ASR 滞后；确定资源瓶颈后再做提交节奏/排队优化 |
| 英文 MMS-TTS 官方 demo | 中 | 仍需两模型转换、构建、compiler/runtime兼容性验证和 benchmark 适配；只适合英文功能探针 |
| 将 MMS-TTS 改中文，或给现有 VITS/Melo 新写 RKNN 后端 | 高且不确定 | 缺已核验目标产物，涉及前端/导出/后端验证；不作为本轮提速承诺 |

NPU TTS 未来若找到成熟中文产物，先测单独运行，再测 YOLO+ASR+TTS 三者共跑；不能认为迁入 NPU 必然降低系统总延迟。短期若仅需更快开口，可研究现有 TTS 的分句、固定提示词缓存与常驻，分别报告首段时延与 CPU 成本，不能将它们表述为实现了 TTS NPU 卸载。
