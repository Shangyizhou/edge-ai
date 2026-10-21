# ASR：旧 Zipformer 的 CPU / NPU 部署

## CPU 已有环境

- Python：`/home/orangepi/venvs/sherpa-onnx/bin/python`，sherpa-onnx1.13.8与numpy。
- 模型：`/home/orangepi/models/voice/sherpa-onnx-streaming-zipformer-small-bilingual-zh-en-2023-02-16`。
- 使用`encoder-epoch-99-avg-1.int8.onnx`、`decoder-epoch-99-avg-1.onnx`、`joiner-epoch-99-avg-1.int8.onnx`、`tokens.txt`，与旧robot选择的文件身份一致。逐文件hash保存在报告manifests。

从本仓库根目录复测，必须指定新输出目录：

```sh
python3 tools/edge_benchmark/benchmark.py run \
  tools/edge_benchmark/asr-native-control.json \
  .local/runs/asr-native-cpu-new
```

CPU应用式100ms分块、greedy/beam以及真实节奏回放分别见`pilot.json`和`asr-interaction.json`。Python实现追加2.5秒尾静音，native CLI追加0.8秒，不能将两组直接归因于后端差异。

## NPU 成功组合

- RKNN Sherpa包：`sherpa-onnx-v1.13.8-rknn-linux-aarch64-shared`。
- **模型必须用官方历史revision `5ff8b9e4d971c082a808b229bf0e3060b1f2c926`（2025-03-19，compiler2.2.0）的同源RK3566包**。
- 外置`librknnrt.so`2.2.0；系统driver0.9.6，未替换系统`/lib/librknnrt.so`。
- 模型与运行时下载地址、SHA-256见[原始资产清单](assets/npu-historical-downloads.json)和[运行时清单](assets/npu-downloads.json)。成功模型包SHA为`5ffbbc179e608f6b8836a279fbada0893de7ca156aa96ba63644cc7db1f8e3ce`。

已经执行通过的原生命令：

```sh
NPU_ROOT=/home/orangepi/.cache/ros-robot-edge-benchmark/npu
NPU_MODEL="$NPU_ROOT/historical/5ff8b9e4d971c082a808b229bf0e3060b1f2c926/sherpa-onnx-rk3566-streaming-zipformer-small-bilingual-zh-en-2023-02-16"
LD_LIBRARY_PATH="$NPU_ROOT/runtime-2.2.0" \
  "$NPU_ROOT/sherpa-onnx-v1.13.8-rknn-linux-aarch64-shared/bin/sherpa-onnx" \
  --provider=rknn --num-threads=1 \
  --encoder="$NPU_MODEL/encoder.rknn" \
  --decoder="$NPU_MODEL/decoder.rknn" \
  --joiner="$NPU_MODEL/joiner.rknn" \
  --tokens="$NPU_MODEL/tokens.txt" \
  /home/orangepi/models/voice/sherpa-onnx-streaming-zipformer-small-bilingual-zh-en-2023-02-16/test_wavs/0.wav
```

正式资源记录用`asr-npu.json`；补测已有真人录音用`asr-recorded-control.json`。真人录音CPU/NPU均输出“机器人请让底盘上前移动二十厘米”，输出只保存为文本。NPU组降低CPU核秒，解码RTF未明显优于CPU；精度、加载和设备内存边界见报告。

## 实际失败与修复

当前官方compiler2.1包在encoder op42 `Split:/Gather_64_2sl_2sp`失败；仅替换runtime2.1/2.2/2.3.2/2.5都未解决。2025-02-27 compiler2.3包发生SIGSEGV。改用上面固定的compiler2.2历史产物后通过，无需重新导出、构建onnxoptimizer或更换内核。不能只写“升级runtime即可”。

`SetCoreMask`非RK3588提示在成功运行时仍存在，不是本次失败根因。NPU参数`num_threads=1`对应native core选择，不能当CPU线程数扫描。[完整调查与官方来源](../../docs/research/rk3566/research-speech.md)。

## 常驻流式路径（独立benchmark验证）

已用官方v1.13.8 C API及上述固定RKNN模型/runtime组合验证：模型只加载一次，
按100ms音频块实时送入；端点时reset stream，继续接收PCM。无需重新转换模型。
配置、构建和复测见[工具说明](../../tools/edge_benchmark/README.md#persistent-rknn-streaming-asr)。

本轮是独立探针，尚未修改ros-robot的生产ASR适配器。后续集成优先将
逐WAV启动子进程改成常驻识别器，音频采集与解码通过有界队列衔接，
保存partial/endpoint事件并处理超时、取消、恢复。先保持rule2=1.2秒；
0.6秒虽然更快，但本轮会拆分自然指令，应先制定唤醒词/命令分段协议。
[本轮数据与限制](../../reports/rk3566/2026-10-21-asr-streaming/results.md)。

## 生产C++ ROS节点NPU接入补充

ros-robot的`robot_inference/asr_node`已在本地交付提交`68e2c1b`接入显式
`provider=rknn`、单核选择及ASR专用SDK/runtime构建配置。此路径复用既有常驻
节点、有界音频Topic和启停Service；旧`robot_voice`CLI前端继续独立保留。
真实ROS回放、新流恢复与生产ASR/YOLO共跑已测；
[原始结果及复现入口](../../reports/rk3566/2026-10-21-asr-ros/results.md)。
未启完整Agent、麦克风或播放，不能将此补充写成四进程语音总体验收。
