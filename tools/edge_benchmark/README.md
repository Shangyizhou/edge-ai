# RK3566 short inference benchmark

This standalone tool measures files and model output. It does not start ROS,
capture a microphone, play sound, execute model function calls, or modify robot
configuration. The existing integration branch remains independent.

Exception: the optional YOLO ROS replay starts only an isolated detector and
file-image publisher in ROS domain 177. It does not start robot bringup,
tracking, motors or camera capture.

The public entry points are `run CONFIG OUTPUT_DIRECTORY` and
`report OUTPUT_DIRECTORY`. Each run needs a new output directory; records are
never silently overwritten. Edit `pilot.json` for asset locations and input
sentences. Dependencies and assets are external, rather than downloaded when a
benchmark starts.

## Existing board setup

The CPU ASR Python is `/home/orangepi/venvs/sherpa-onnx/bin/python` with
sherpa-onnx 1.13.8 and numpy. The orchestrator itself uses Python 3.8 standard
library only. Qwen uses the existing ARM llama-server, pinned to its actual
binary hash in each manifest. The old robot source is commit
`22cd28d2d63ba1165f3fbceba205e02ed94f204d`; Summer weights must match the SHA-256
recorded in the research notes. No model is copied into this checkout.

Build the Summer measurement Adapter separately, without ROS or audio output:

```sh
cmake -S tools/edge_benchmark/native \
  -B /home/orangepi/.cache/ros-robot-edge-benchmark/build/summer \
  -DCMAKE_BUILD_TYPE=Release \
  -DSUMMER_SOURCE_DIR=/home/orangepi/code/robot/offline-agent/tts
cmake --build /home/orangepi/.cache/ros-robot-edge-benchmark/build/summer -j2
```

The CMake target reads the existing legacy source list to compile the exact
inference/frontend files, excluding its ROS server and vendored test programs.
The wrapper controls OpenMP/Eigen threads and invokes the existing infer
Interface; it does not reimplement synthesis. Summer's selected legacy
pipeline uses 16kHz mono S16 output. Raw PCM and WAV are both retained.

RK3566 ASR NPU deployment uses the official RK3566 model and RKNN Sherpa
1.13.8 build with a private runtime 2.2.0 directory. Do not replace
`/lib/librknnrt.so`. URLs, checksums, driver observations and commands are in
the research notes and external `npu/download-manifest.json`.

## Run and inspect

From this worktree:

```sh
python3 tools/edge_benchmark/benchmark.py run \
  tools/edge_benchmark/pilot.json \
  /home/orangepi/.cache/ros-robot-edge-benchmark/runs/pilot-01
python3 tools/edge_benchmark/benchmark.py report \
  /home/orangepi/.cache/ros-robot-edge-benchmark/runs/pilot-01
python3 -m unittest discover -s tools/edge_benchmark -p 'test_*.py'
```

`manifest.json` fixes the suite, inputs, model hashes, executable/source hashes
and environment. Each case preserves config, command, stderr/stdout, completed
events and 200ms process-tree resource samples. `report.html` is standalone;
WAV controls and raw-result links use paths within the same output directory.
Copy the entire run directory when sharing the report.
Computing hashes reads the files and may warm the filesystem cache. Startup
numbers are process initialization in the observed cache state, not measured
cold-disk performance. No global cache is cleared.

Cases run serially. Limits cover loading and inference: a configurable virtual
address ceiling (default 2304MiB), no core files, a case wall-clock budget and
host guards at 384MiB MemAvailable / 512MiB SwapFree. These are experiment
limits, not interaction SLAs. Each worker gets a new process group; timeout
and teardown terminate all owned descendants. A failed case preserves completed
samples and permits the next case. Programming errors remain visible in logs.

## Interpretation

- ASR Python cases use 100ms chunks plus an explicit 2.5s silence tail; compute
  RTF excludes real-time pacing. Endpoint is measured on the supplied audio
  axis relative to the file end, not a hand-annotated speech end.
- Official native RKNN CLI uses its own 0.8s tail and reports rounded decoding
  timing. Match it with the same native CPU CLI before attributing differences
  solely to NPU. Separate Python chunked cases are application-style evidence.
- Summer times inference before writing audio. First and subsequent requests
  share a loaded model, and remain individually visible.
- Qwen uses the custom legacy `Human:/Assistant:` template, no tool directory,
  no grammar and no prompt-cache reuse; raw request JSON stores sampling,
  actual text and output-token cap. TTFT is first nonempty generated content,
  rather than the first protocol chunk. Truncation is retained as a result
  fact, not silently retried. Native logs preserve pp/tg timings.
- CPU is cumulative core-seconds; 100% means one core. RSS sum can count shared
  pages twice; PSS is separately sampled. RKNN device memory may not be fully
  represented by host process RSS, so report host/driver facts separately.
- Short screening is not a quality ranking, MOS study or stable p95 estimate.
  Chinese transcripts, generated replies and WAVs are saved for later review.
  Repeated final candidates and realistic coexistence are separate suites.

Research, scope decisions and delivery tracking:
[deployment](../../studies/voice-interaction/platforms/rk3566/deployment.md),
[research](../../studies/voice-interaction/research/speech.md) and
[results](../../studies/voice-interaction/experiments/rk3566/2026-10-21-baseline/results.md).

## Focused reruns and combined report

`pilot.json` is the short three-module CPU/thread baseline and now selects the
verified RKNN compiler 2.2.0 artifact. The initial run's manifest retains its
failed compiler 2.1.0 paths. `asr-native-control.json` and `asr-npu.json` provide
the matched native CLI comparison; `asr-interaction.json` adds paced/beam cases.
`asr-recorded-control.json` uses a second historical speech recording, without
capturing any new audio. An empty transcript is preserved as an observed result.

`tts-comparison.json` covers non-Xiaoya huayan/Piper, Chinese VITS and Melo;
`tts-matched-baseline.json` adds Summer on exactly that corpus.
Piper 1.2 uses its runtime's default intra-op threads; its OMP environment does
not imply the ONNX Runtime pool is limited to one thread. Sherpa explicitly
controls its thread count. The equivalent huayan graphs use different frontend
and runtime versions, so this is a deployment comparison.

`quantize.json` derives Q8/Q5/Q4 from the original BF16 model. Quantization is
preparation, not inference timing. `qwen-profiles.json` uses the confirmed
`--no-repack` workaround for Q4; initial failing manifests remain unchanged.
`qwen-runtime-diagnostics.json` isolates that switch and preserves BF16 partial
stream output. `qwen-working-profiles.json` varies batch/microbatch, context
capacity and K-cache precision after the workaround. Short prompts do not
measure the cost or quality of filling a 2048-token history. Sampling is fixed;
no quality score is inferred from throughput.

`coexistence.json` keeps ASR idle and resident while Summer/Qwen requests overlap.
It measures competition for resources, rather than a full spoken conversation.

```sh
python3 tools/edge_benchmark/benchmark.py combine /tmp/combined-results \
  /path/to/run-one /path/to/run-two
python3 tools/edge_benchmark/benchmark.py report /tmp/combined-results
```

The destination must be new and case IDs must be unique. Combining copies raw
case directories and source manifests; it does not rerun inference. Optional
`notes.json` is a JSON list of plain-text observations displayed above the
charts. Charts select the most common identical input within each module;
ASR native CLI and simultaneous cases remain separate in the full table.
Initialization scope differs by adapter: ASR/sherpa time the model constructor,
whereas Qwen/Piper include native child startup. Compare these as deployment
facts rather than identical cold-start measurements. Sampled resource peaks
are not a kernel high-water measurement.

## YOLOv6 CPU / NPU and active ASR

`yolo.json` uses the agreed target: **30 FPS, pre-scaled 640x352 RGB**.
It measures CPU 1/2/4 threads, NPU backend, actual ROS detector with and
without annotated RGB publication, and two active ASR NPU overlap runs.
The suite uses a fixed public image rather than a camera. Model loads and
three warmup frames precede timing. Per-frame detections/timing and aggregate
completed FPS, offered frames, drops and short-sample latency percentiles
are retained. `yolo-scheduling.json` compares ASR CPU at the same target input.
Earlier large-input, unpaced and reduced-rate experiments are archived in
`diagnostics/yolo-input-*.json`; they are not the target configuration.

Build against the actual external ros-robot backend and postprocessor:

```sh
source /opt/ros/foxy/setup.bash
cmake -S tools/edge_benchmark/native/yolo \
  -B /home/orangepi/.cache/ros-robot-edge-benchmark/build/yolo \
  -DCMAKE_BUILD_TYPE=Release \
  -DYOLO_SOURCE_DIR=/home/orangepi/code/ros-robot/ros2_ws/src/rknn_yolov6 \
  -DRKNN_API_INCLUDE_DIR=/home/orangepi/sdk/rknn/include \
  -DBUILD_ROS_YOLO=ON \
  -Drobot_interfaces_DIR=/home/orangepi/code/ros-robot/ros2_ws/install/robot_interfaces/share/robot_interfaces/cmake
cmake --build /home/orangepi/.cache/ros-robot-edge-benchmark/build/yolo -j2
python3 tools/edge_benchmark/benchmark.py run \
  tools/edge_benchmark/yolo.json /path/to/new-yolo-run
```

Set `BUILD_ROS_YOLO=OFF` to omit the ROS replay target. The core NPU probe
still needs installed rclcpp for the backend's logging dependencies, but never
initializes a ROS node. CPU uses ONNX Runtime and a small C ABI library compiled
from the exact same ros-robot postprocessor; it needs no active ROS node.
`yolo_cpu.py` requires the external Python environment recorded in the config.
Dependencies and inputs are prepared separately, never installed by `run`.

The current `.rknn` asset has no directly usable same-source ONNX file: its
legacy ONNX is an LFS pointer. A CPU candidate was re-exported from the existing
legacy PT at 352x640, using the legacy customized exporter. Its output layout
matches, but its identity with the deployed RKNN cannot be established by a
matching artifact hash. Treat this as a deployment comparison, not a proven
same-precision hardware speedup. Haar is never substituted for CPU YOLO.
Preparation versions, hashes, export command and failed attempts are in the
YOLO research/deployment notes and frozen evidence.

Backend `yolo` / `yolo_cpu` cases use a serial latest-frame policy: at 30 Hz,
old input slots are skipped rather than queued indefinitely. NPU timing includes
RKNN input, execution, float output retrieval and
real postprocessing. It excludes initial JPEG decode, ROS, annotation and
encoding. Model-sized input avoids the RGA resize branch; it does not change
the compiled model resolution. Target runs receive the already scaled image;
upstream scaling is outside this detector benchmark. CPU timing includes normalization,
ORT inference and the same postprocessing. First image decode is outside timing.

`*-ros-*` cases run the actual detector class with its real capacity-two
queues, drawing and detection publishing, and a composed RGB replay publisher.
DDS/rclcpp intra-process optimization is not enabled. These are separate scopes
from backend latency: frame latency is scheduled input to received detection.
`sent_frames` / `source_skipped` separate replay scheduling loss from missing
outputs; `dropped` counts all missing offered slots. Output drains for two
seconds; completed FPS uses max(input-window duration, last completion time),
not an arbitrary process wall-clock including initialization/drain wait.
An optional annotated subscriber enables annotated RGB publication, without
JPEG/web encoding. Neither scope includes USB capture or MJPEG decoding.

`vision_asr` launches members with independently configured runtime paths.
YOLO warms before the gate; the official ASR CLI starts loading after the gate
and decodes the same file repeatedly, reloading per request. This is an active,
unpaced file-throughput stress test, not realtime microphone streaming or
idle model residency. Each ASR sample records request monotonic intervals,
RTF and transcript; visual frames record completion timestamps. Compare
actual overlapping intervals and retain any nonoverlapping tail. Current CLI
intervals include loading; they cannot locate every NPU kernel. Root process-tree
PSS is the group total, not per-model NPU memory. Timeout/failed child cleanup
uses the existing process-group teardown contract.

The default target was confirmed as pre-scaled 640x352 at 30 FPS.
Frame counts use this 30 Hz input budget; a lower-rate diagnostic is never
reported as meeting the target. Upstream scaling is a separate stage.

## Persistent RKNN streaming ASR

`asr-streaming.json` replays four fixed 16kHz fixtures at their real arrival rate
(100ms blocks, 3.2s paced trailing silence), scanning rule2=1.2/0.8/0.6s.
Each recognizer is created once and warmed before the measurement gate.
Independent files get new stream state; endpoints reset the stream only.
The paired cases run actual ROS YOLO with already resized 640×352 input at
30fps for 45s. `asr-streaming-followup.json` adds one continuous six-turn
stream and the matched per-file CLI control. No microphone or motion nodes run.

Build against the matching public v1.13.8 C header and external validated SDK:

```sh
cmake -S tools/edge_benchmark/native/asr_stream -B /tmp/asr-stream-build \
  -DSHERPA_ROOT=/path/to/sherpa-onnx-v1.13.8-rknn-linux-aarch64-shared \
  -DSHERPA_INCLUDE_DIR=/path/to/include \
  -DRKNN_RUNTIME_DIR=/path/to/private-runtime-2.2.0
cmake --build /tmp/asr-stream-build -j2
python3 tools/edge_benchmark/benchmark.py run tools/edge_benchmark/asr-streaming.json /tmp/stream-results
```

Adjust local binary/model/fixture paths in a copy of the config. Fixture JSON
contains `fixtures` entries with `id`, `path`, `energy_end_s` and provenance;
freeze it with WAV hashes. WAVs, headers, libraries and binaries stay outside Git.
The report distinguishes compute RTF from paced wall time and reports missing
endpoints explicitly. Energy anchors are not human EOS labels. See
[method](../../studies/voice-interaction/research/streaming-asr-method.md) and
[measured results](../../studies/voice-interaction/experiments/rk3566/2026-10-21-streaming-asr/results.md).

Production ROS ASR integration is recorded separately in
[ROS node validation](../../studies/voice-interaction/experiments/rk3566/2026-10-21-ros-asr/results.md).
That replay uses the actual robot_inference node and ROS audio/control contracts;
its event-reception latency includes DDS delivery, unlike the direct C API probe.
Native compute RTF and resource peaks were not collected in that integration run.

## 轻量评测 v1

执行流程与指标边界见[统一SOP](../../docs/methodology/model-evaluation-sop.md)和[结果格式](../../docs/methodology/result-format.md)。ASR首个[计划实例](../../studies/voice-interaction/experiments/rk3566/2026-10-21-asr-lite-v1/plan.json)复用外部CPU/NPU资产，不下载模型。

```sh
# 只生成配置并校验共享输入；输出须是新文件。
python3 tools/edge_benchmark/asr_suite.py /absolute/plan.json /tmp/screening.json --tier screening
python3 tools/edge_benchmark/benchmark.py run /tmp/screening.json /absolute/new-screening
python3 tools/edge_benchmark/asr_suite.py /absolute/plan.json /tmp/qualification.json --tier qualification
python3 tools/edge_benchmark/benchmark.py run /tmp/qualification.json /absolute/new-qualification

# 只读转换已有运行；不覆盖原结果或已有导出目录。
python3 tools/edge_benchmark/evaluation.py export /absolute/new-view /absolute/run-a /absolute/run-b
python3 tools/edge_benchmark/evaluation.py validate /absolute/new-view/results.json
python3 tools/edge_benchmark/evaluation.py report /absolute/new-view/results.json /absolute/new-view/report.html
python3 -m unittest discover -s tools/edge_benchmark -p 'test_*.py'
```

新版suite自动生成`evaluation/results.json`及`evaluation/report.html`。两种ASR场景、筛选/复测及两类对照分组展示；三轮显示中位数/范围，并保留逐轮输出。页面使用[静态模板](templates/evaluation.html)，只消费结果，不改变测量。

新计划需指定设备、素材清单、候选identity和adapter、两个强度的fixture_ids和总预算。每条候选保留框架/后端/精度/线程声明；模型来源、文件及SDK身份由manifest固定。路径是设备实例配置，移机时更新外部资产路径，并保留输入hash和协议条件；不往Git提交音频、模型或SDK。

旧suite不带evaluation时沿用原执行/报告入口。新版只读export将其标为legacy；协议、阶段或MemTotal等缺失信息不会从新环境回填。历史面板可查阅，不自动当作新版受控对照。动态库映射和provider结合检查实际运行路径，CPU也可能因SDK依赖映射RKNN库。

## ASR PTQ探索工具

`asr_ptq.py` 在独立外部转换环境运行，分别捕获真实流式状态校准及转换单个组件。需要固定的浮点ONNX、ORT、kaldi-native-fbank和对应版本RKNN Toolkit；依赖不由脚本安装。

```sh
python asr_ptq.py capture --model /absolute/float-onnx --output /absolute/new-calibration --fixtures /absolute/fixtures.json --fixture-ids official0 command --max-samples 16 --chunks-per-fixture 8
python asr_ptq.py build --model /absolute/float-onnx --component joiner --output /absolute/new-float
python asr_ptq.py build --model /absolute/float-onnx --component joiner --output /absolute/new-int8 --int8 --calibration /absolute/new-calibration
```

在tools/edge_benchmark目录运行示例，或使用脚本绝对路径。输出目录须新建；保留控制组、量化候选及原始状态类型。捕获仅覆盖指定少量块/帧，不能当作充分校准；现有实现针对旧Zipformer固定导出契约，并非通用ASR量化器。构建成功后仍需审核实际层精度、运行库、流式状态接口和质量，再进行性能复测。CPU动态INT8与RKNN静态W8A8不能仅按名称归入受控对照。

`native/asr_stream/rknn_component_probe.cpp` 为独立组件诊断，使用外置官方`rknn_api.h`和私有runtime编译；`--perf`显式启用层报告。零输入仅验证执行与精度，不评价识别质量或吞吐。runtime2.5.0在本设备出现profiling及完整ASR崩溃，详见[本次尝试](../../studies/voice-interaction/experiments/rk3566/2026-10-21-asr-int8-ptq/results.md)，不要自动替换已验证运行库。
