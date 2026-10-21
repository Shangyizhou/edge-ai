# YOLOv6：ros-robot 现用 NPU 与 CPU 候选

验证日期：2026-10-21。测试复用 ros-robot 当前检测后端、后处理和实际 ROS 节点；源文件、模型、二进制与运行库 hash 保存在报告 manifest。

- [实测结论与范围](../../reports/rk3566/2026-10-21-yolo/results.md)
- [静态报告](../../reports/rk3566/2026-10-21-yolo/report.html)
- [参数、来源与兼容调查](../../docs/research/rk3566/research-yolo.md)
- [构建与测量入口](../../tools/edge_benchmark/README.md#yolov6-cpu--npu-and-active-asr)

## 当前 NPU 路线

模型：`/home/orangepi/models/ros-robot/vision/yolov6n_85.rknn`，SHA-256 `ca65d65483b6a3cf141b6c4af569f0b9140803ce834d38aa6fe044bef22020d4`。模型输入 640×352，三个 85 通道输出。本轮目标是上游缩放后以 **640×352 RGB、30fps** 输入检测器。尺寸已匹配时，后端跳过 RGA 缩放分支；RKNN 输出以 `want_float=1` 取回，随后由现用 C++ YOLOv6 后处理解码。

实际成功组合：系统 `librknnrt.so` 1.4.0、driver 0.9.6。ASR 在独立进程使用私有 runtime 2.2.0，共跑不需要替换系统库。

本轮额外尝试视觉私有 runtime 2.2.0，现用后端在 core mask 初始化调用返回 -13 后退出，尚未执行模型推理。该结果不是模型在新版 runtime 上必然不可运行的证据；已有成功组合继续使用 1.4.0。

## CPU 候选与依赖准备

ros-robot 的 HAAR 后端不是 CPU YOLO，不能用作加速比基线。旧 ONNX 是 LFS 指针，未恢复真实文件；本轮用已有 PT 和旧定制 exporter 重导出 CPU 候选，记录如下：

- 外置环境：`/home/orangepi/.cache/ros-robot-edge-benchmark/yolo-venv`。
- PyTorch 2.4.1、ONNX 1.17.0、ONNX Runtime 1.19.2、numpy 1.24.4、opencv-python-headless 4.10.0.84。
- 新 ONNX：`/home/orangepi/.cache/ros-robot-edge-benchmark/assets/yolo/yolov6n.onnx`，SHA-256 `bd3703906b06991b65664cbf61f4c391d842eba066ff1376299a97575128ab6c`。
- CPU 使用 ORT CPUExecutionProvider，intra-op 为测试指定的 1/2/4，inter-op=1、串行图执行；输入 RGB 拉伸到 640×352、除以 255。
- 后处理用从当前 ros-robot `postprocess.cpp` 编译的 `libyolo_postprocess.so`，不是另写一套 Python NMS。

CPU 新模型的三输出形状匹配且可以检测，但现用 RKNN 的历史导出链缺少证明材料；不能将这组部署速度差称作严格同源、同精度的硬件加速倍数。CPU 检测仍是 benchmark 候选，尚未接入生产 ROS ONNX 后端。

外置 `assets/yolo/preparation.json` 记录下载 URL、文件尺寸/hash、导出命令和源代码身份，`requirements-freeze.txt` 固定环境版本。导出命令见调研笔记。系统 OpenCV 4.2 DNN 因缺少 ReduceMax 层未跑通，性能表不使用该失败项。

## 可调参数

| 参数 | 当前值 | 使用边界 |
| --- | --- | --- |
| confidence_threshold | 0.30 | 提高阈值会减少候选和部分后处理，也会漏掉低分目标；不能凭速度代替效果评判 |
| nms_threshold | 0.30 | 控制重叠框抑制，改变输出；本轮未做穷举扫参 |
| model_path | yolov6n_85.rknn | 变更输入尺寸、精度或模型需重新导出/转换并核对后处理 |
| enabled / always_process | true / true（package launch） | 可停用检测，或在没有下游订阅时节约推理；节点直接启动的默认 always_process 是 false |
| print_perf_detail | false | 逐层性能收集用于独立诊断，正式测速关闭 |
| use_multi_npu_core | false | RK3566 不把它当作多核提速选项 |
| 输入图像尺寸/频率 | **640×352、30Hz** | 上游完成缩放，检测器按此目标测量；不将降低帧率作为达标方案 |
| 标注图订阅 | 按案例设置 | 当前代码无订阅时也绘图；订阅后额外复制、发布和接收 RGB 图像 |

这些 ROS 参数在初始化时读取，改配置后须重启检测节点。benchmark 的 CPU `threads` 控制 ORT 线程；NPU probe 的 `threads` 只控制 OpenCV CPU 操作，不会增加 RK3566 NPU 核数。测试的固定图像输入不用于检测准确率结论。

## 复测与共跑

先按 benchmark README 构建，然后在仓库根目录运行，输出目录必须是新目录：

```sh
python3 tools/edge_benchmark/benchmark.py run \
  tools/edge_benchmark/yolo.json \
  /home/orangepi/.cache/ros-robot-edge-benchmark/runs/yolo-new
python3 tools/edge_benchmark/benchmark.py run \
  tools/edge_benchmark/yolo-scheduling.json \
  /home/orangepi/.cache/ros-robot-edge-benchmark/runs/yolo-scheduling-new
```

`yolo.json` 是 640×352、30fps 目标矩阵，包含 CPU 1/2/4 线程、NPU、实际 ROS 节点和 ASR NPU 共跑；`yolo-scheduling.json` 以相同目标输入补测 ASR CPU 单独/共跑对照。二者都是文件回放，不打开相机或麦克风。ROS 案例使用 domain177、localhost 和独立话题，仅构造检测节点及图片发布者，不启动整车。

ASR 共跑使用反复加载并解码文件的官方 CLI，是活跃吞吐压力，不是常驻模型实时流式交互。各请求时间区间含加载；重叠区间与退出后的尾段分别记录。进程树 PSS 包括多个进程的系统内存，不是 NPU 专用内存；设备分配可能没有完整反映在 PSS 中。

上游逐帧缩放、USB 相机采集、MJPEG 解码和 web 编码不计入本次检测器耗时。旧 1280×720 输入及 10Hz 案例仅作为历史诊断，保留于外置旧实验和 `tools/edge_benchmark/diagnostics/` 配置，不作为目标结论。
