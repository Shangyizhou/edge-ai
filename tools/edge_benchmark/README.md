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
[deployment](../../deployments/rk3566/README.md),
[research](../../docs/research/rk3566/research-speech.md) and
[results](../../reports/rk3566/2026-10-21/results.md).

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
[method](../../docs/research/rk3566/research-streaming-asr-method.md) and
[measured results](../../reports/rk3566/2026-10-21-asr-streaming/results.md).
