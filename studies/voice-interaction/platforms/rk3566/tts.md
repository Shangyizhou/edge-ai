# TTS：Summer 基线与候选部署

## SummerTTS 旧实现

旧代码：`/home/orangepi/code/robot/offline-agent/tts`，来源提交`22cd28d2d63ba1165f3fbceba205e02ed94f204d`。benchmark只编译推理/前端清单，不构建ROS服务和vendored测试。依赖C++17编译器、CMake、OpenMP，Eigen3.4.0从旧目录使用。

旧仓权重文件可能只是Git LFS指针；本次实际从[官方raw模型](https://raw.githubusercontent.com/huakunyang/SummerTTS/main/models/single_speaker_fast.bin)取得80,050,316字节，SHA-256为`87b774813258a3636b3f1d9adddd3652ede503b4e8f4eb3c39065cba2a4951c4`，与旧LFS目标完全一致。模型位于外置`assets/single_speaker_fast.bin`。

从本仓库根目录构建现有测量适配器：

```sh
cmake -S tools/edge_benchmark/native \
  -B .local/build/summer -DCMAKE_BUILD_TYPE=Release \
  -DSUMMER_SOURCE_DIR=/home/orangepi/code/robot/offline-agent/tts
cmake --build .local/build/summer -j2
```

上面是迁移后的等价构建目录；迁移前实际已构建通过的二进制在`/home/orangepi/.cache/ros-robot-edge-benchmark/build/summer/summer_probe`。本机配置仍引用该已验证二进制，代码无需ROS。

模型一次加载，1/2/4线程控制Eigen/OpenMP，输出16kHz单声道S16 PCM/WAV。`pilot.json`和`tts-matched-baseline.json`分别对应三基线/同文本对照。没有声卡播放，完整句PCM就绪不冒充首声延迟。

## sherpa-onnx / Piper

现有Python环境与ASR共用sherpa-onnx1.13.8。以下模型已在板端实际合成：

| 模型/部署 | 外置路径（缓存根目录下） |
| --- | --- |
| sherpa huayan | `assets/tts/vits-piper-zh_CN-huayan-medium` |
| 中文VITS | `assets/tts/sherpa-onnx-vits-zh-ll` |
| Melo zh_en ONNX | `assets/tts/vits-melo-tts-zh_en` |
| Piper原始huayan | `assets/tts/piper-huayan-original` |
| Piper1.2.0 aarch64可执行程序 | `piper/piper/piper` |

下载来源/压缩包hash见[清单](assets/tts-downloads.json)，原始Piper voice另有[清单](assets/piper-voice-downloads.json)。使用Piper固定release `2023.11.14-2`，不是当前维护仓最新版。VITS/Melo还需tokens、lexicon与phone/date/number FST，huayan需对应espeak-ng-data；配置完整记录于`tts-comparison.json`。

```sh
python3 tools/edge_benchmark/benchmark.py run \
  tools/edge_benchmark/tts-comparison.json \
  .local/runs/tts-comparison-new
```

Piper采用原生默认ORT线程池，不标为单线程。Sherpa huayan显式测1/2/4线程。两个huayan部署图/张量hash一致，但ORT为1.14.1/1.28.2、前端不同。未使用小雅音色，未将VITS/Melo加载成完整PyTorch服务。

旧Summer没有RKNN后端，本轮TTS全部CPU。模型许可信息按上游模型卡保留，源码/权重没有随本次迁移重新授权或打包。[指标与完整调查](../../research/speech.md)。
