# ros-robot YOLOv6：板端基准调研与测量约定

调研日期：2026-10-21（Asia/Shanghai）。本笔记记录静态检查和官方资料；实际性能以本轮 benchmark 原始结果为准，不以理论算力或上游其他板型 FPS 代替。

## 当前实现与资产

检查的 ros-robot revision 为 `b31ed9c122fc1502869ef18eb733ce0cec33beed`。AArch64 的 AUTO 构建选择 RKNN/RGA，CPU 备用后端是 Haar 人脸检测，**并非 CPU YOLOv6**，不能把 Haar 与 NPU YOLO 的时间当作硬件加速比。[构建选择](/home/orangepi/code/ros-robot/ros2_ws/src/rknn_yolov6/CMakeLists.txt)、[模块说明](/home/orangepi/code/ros-robot/ros2_ws/src/rknn_yolov6/README.md)。

默认外置模型 `/home/orangepi/models/ros-robot/vision/yolov6n_85.rknn`，5459846 字节，SHA-256 `ca65d65483b6a3cf141b6c4af569f0b9140803ce834d38aa6fe044bef22020d4`，与旧 robot 仓库 `src/rknn_yolov6/config/yolov6n_85.rknn` 完全相同。模块记录的输入为 640×352，原始相机为 1280×720 RGB；模型尺寸由 RKNN 张量属性读取，非 ROS 参数。非同尺寸输入使用 RGA 缩放，DMA32 heap 为 `/dev/dma_heap/system-uncached-dma32`。已验证 runtime 为 1.4.0；实际每轮应保存加载日志中的 runtime/driver，而非假定文档版本。[模型配置](/home/orangepi/code/ros-robot/ros2_ws/src/rknn_yolov6/config/rknn_yolov6.yaml)、[RKNN adapter](/home/orangepi/code/ros-robot/ros2_ws/src/rknn_yolov6/src/detector_backend_rknn.cpp)。

旧目录 `/home/orangepi/code/robot/rknn_export/models/yolov6n.onnx` 是 133 字节的 Git LFS 指针，真实文件大小应为 18612491 字节、SHA-256 `9168c197f757b312b70c53f8299c55def199c62a25f46871ff0d3efdea04dd52`；不能交给 CPU 引擎。尝试从 `https://media.githubusercontent.com/media/200166shang/robot/main/rknn_export/models/yolov6n.onnx` 及 revision `22cd28d2d63ba1165f3fbceba205e02ed94f204d` 恢复均返回 HTTP 404，未下载到模型。

旧 `models/yolov6n.pt` 存在（10511334 字节），定制的 `effidehead_distill_ns.py` 产出三个 85 通道张量，注释明确列出 640×352 输入的 44×80、22×40、11×20 输出；`export_onnx.py --img-size` 顺序是高、宽。PT 与现用 RKNN 缺少可核对的导出 manifest，故重新导出只能先作为待验证候选。[旧定制 head](/home/orangepi/code/robot/rknn_export/YOLOv6-0.3.0/yolov6/models/heads/effidehead_distill_ns.py)、[旧 exporter](/home/orangepi/code/robot/rknn_export/YOLOv6-0.3.0/deploy/ONNX/export_onnx.py)。

Rockchip 官方明确提供 RK3566 YOLOv6、FP16/INT8 转换及 ONNX/PT/RKNN 推理路径，但当前官方示例的优化输出图与原版不同。下载“同名 yolov6n”不能证明与本机 85 通道模型同源；本次不把它替换成现用模型。[官方 YOLOv6 示例](https://raw.githubusercontent.com/airockchip/rknn_model_zoo/main/examples/yolov6/README.md)。

## 可配置项与边界

| 参数 | 默认/当前值 | 性能意义 |
|---|---|---|
| model_path | yolov6n_85.rknn | 更换模型、输入尺寸、精度须重新导出/转换并验证后处理兼容 |
| confidence_threshold / nms_threshold | 0.30 / 0.30 | 改变候选框与后处理负载，也会改变检测质量 |
| enabled / always_process | true / true（package launch） | 直接运行节点 always_process 默认为 false；无人订阅可不推理 |
| print_perf_detail | false | 开启逐层计时有额外性能开销，诊断轮与正式轮分开 |
| use_multi_npu_core | false | 不能作为 RK3566 多核加速开关；历史 API 的 core mask 仅支持 RK3588 |
| input_topic / detections_topic / annotated_topic | /camera/image_raw、/ai_msg_det、/camera/image_det | 单独命名可隔离 benchmark；当前每帧都会绘图，标注订阅额外增加 RGB 复制、发布和接收成本 |
| is_offline_image_mode / offline_images_path / offline_output_path | false / 空 / 空 | 离线流程含图像解码、保存及每帧 30 ms sleep，不适合拿日志当纯推理上限 |

来源：[参数读取与双阶段流程](/home/orangepi/code/ros-robot/ros2_ws/src/rknn_yolov6/src/rknn_yolov6_node.cpp)、[官方历史 RKNN API](https://raw.githubusercontent.com/airockchip/rknpu2/v1.4.0/runtime/RK356X/Linux/librknn_api/include/rknn_api.h)。参数在初始化时读取，没有通用动态调参 callback；启停另有 Bool 话题。现有双队列容量均为 2，满时丢最旧帧；日志 FPS 是从启动起累计完成数/经过时间，包含空闲，不能代表 RKNN 单次延迟。[队列源码](/home/orangepi/code/ros-robot/ros2_ws/src/rknn_yolov6/include/rknn_yolov6/bounded_queue.hpp)。

## 融入 benchmark 的测量约定

1. 保存 model hash、张量尺寸与量化属性、runtime/driver、CPU/NPU governor/频率、温度和输入图像 hash。正式计时排除初始化和预热；图像解码、缩放、输入设置、rknn_run、输出取回、NMS、ROS 发布分别标明覆盖范围。
2. 先测现用 RKNN adapter 的单进程吞吐与延迟，再测 30 Hz 节奏输入。每帧预算 33.33 ms；报告实际完成 FPS、输入/输出唯一帧数、丢帧、延迟 p50/p95/max、超 33.33 ms 比例。30 Hz 输入不等于 30 FPS 输出，也不能把串行平均倒数当成完整相机链路测量。
3. CPU 对照必须同源 ONNX、相同 RGB/归一化/尺寸与后处理。建议 CPU 1/2/4 线程；若只有现有 PT，需先证明导出及预测一致性。若未取得合法完整同源 CPU 模型，明确记为 blocked/unavailable，不报加速倍数。
4. 同时测 YOLO 单独、ASR NPU 单独、YOLO NPU+ASR NPU，以及可选 YOLO NPU+ASR CPU。共跑必须记录真实重叠区间；ASR 加载后空闲不算竞争。视觉固定 30 Hz，并另测 5/10/15 Hz 调度以确定可接受余量；ASR 固定相同录音、尾静音和输入节奏。
5. 共跑同时观察视觉 FPS/p95/丢帧与 ASR RTF/块处理延迟/识别文本，报告相对各自单独运行的退化。推测共享 NPU 调度、CPU 后处理和内存带宽会竞争；具体幅度只能由重叠实测确定，不能由 TOPS 相除计算。
6. PSS 是进程系统内存指标；同时报告系统 MemAvailable/swap，以及支持时的 RKNN weight/internal/DMA 查询。不可把进程 PSS 叫作 NPU 显存，也不可重复相加系统/DMA 统计。

官方 API 的 `RKNN_QUERY_PERF_RUN` 在输出获取后有效，以微秒返回推理时间；`RKNN_QUERY_MEM_SIZE` 给出模型与内部内存相关字段。逐层收集模式会降低帧率，因此正式测量保持关闭。不同版本结构布局必须使用匹配头文件，不能用新 API 结构强套旧 runtime。[历史 API](https://raw.githubusercontent.com/airockchip/rknpu2/v1.4.0/runtime/RK356X/Linux/librknn_api/include/rknn_api.h)、[当前 API](https://raw.githubusercontent.com/airockchip/rknn-toolkit2/master/rknpu2/runtime/Linux/librknn_api/include/rknn_api.h)。ASR 已知需私有 runtime 2.2.0；视觉现有系统 runtime 1.4.0。应按进程独立库路径运行，并保存各自加载库，避免全局替换影响既有环境。[现有 ASR 实测](../../../reports/rk3566/2026-10-21/results.md)。

## 本轮实际补齐的 CPU 路线与失败记录

原 LFS ONNX 未恢复；随后在源码外建立独立 `yolo-venv`，从现有 `yolov6n.pt` 通过旧定制 exporter 重导出 352×640 ONNX。实际版本：PyTorch 2.4.1、ONNX 1.17.0、ONNX Runtime 1.19.2、numpy 1.24.4、opencv-python-headless 4.10.0.84。输出确认是 `[1,85,44,80]`、`[1,85,22,40]`、`[1,85,11,20]`，与现用后处理匹配。新 ONNX SHA-256 为 `bd3703906b06991b65664cbf61f4c391d842eba066ff1376299a97575128ab6c`，不等于旧 LFS oid；不同 exporter 版本即使权重相同也可能产生不同文件，因此不能据此认定权重相同或不同，严格同源仍未证实。CPU 方案作为明确标注的重导出候选实测，而非跳过 CPU 对照。

实际导出命令（在旧 `rknn_export/YOLOv6-0.3.0` 目录）：

```sh
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=1 \
  /home/orangepi/.cache/ros-robot-edge-benchmark/yolo-venv/bin/python \
  deploy/ONNX/export_onnx.py \
  --weights /home/orangepi/.cache/ros-robot-edge-benchmark/assets/yolo/yolov6n.pt \
  --img-size 352 640 --device cpu
```

归一化采用 RGB /255，与[旧 RKNN 转换配置](/home/orangepi/code/robot/rknn_export/RKNN-Toolkit2/convert.py) 的 mean=0、std=255 一致。CPU 的三个头交由从 ros-robot 当前 `postprocess.cpp` 编译出的 C ABI 库处理，复用相同阈值、解码和 NMS。候选能检出与 NPU 类似的人和车辆，但框、置信度及数量有差异；固定图像的输出一致性观察不构成精度评测，也不证明严格同源。

先尝试系统 OpenCV 4.2.0 DNN，模型因缺少 `ReduceMax` 层实现而失败，未将失败计为速度。改用 ORT 后，最初把系统 `dist-packages` 加到 PYTHONPATH，造成系统 numpy 覆盖虚拟环境，触发 ABI 不兼容；最终在独立虚拟环境安装 OpenCV 后通过。ROS 回放初次缺少 robot_interfaces 动态 typesupport 路径，补齐该进程的 LD_LIBRARY_PATH 后通过。上述均为明确错误日志对应的环境/引擎兼容问题，未改系统库，也未修改现用机器人代码。

正式测量前已完成编译与安装。初轮 `yolo-01` 与准备阶段存在时间重叠，仅保留为探索记录；结论使用 `yolo-final-01`。本机外置 `assets/yolo/preparation.json` 固定导出命令、版本、URL、源文件和资产 hash；模型及准备环境不进入 Git。静态报告快照保留该清单与失败日志。

## 实际共跑口径

本轮使用现有官方 native ASR CLI 连续解码四次相同 10 秒 WAV（每次附加 0.8 秒静音），它是连续文件吞吐压力，**并非麦克风实时流式输入**。YOLO 完成加载和三帧预热后等待统一门禁，ASR 在门禁后加载。ASR 逐请求单调时钟区间包含模型加载，RTF 使用 CLI 报告的解码计算时间；不能把这些区间全部当作 NPU 正在执行 kernel。视觉保留逐帧时间，分析时单独计算请求重叠窗口，并保留 ASR 非重叠尾段。

另有实际 ROS 检测节点回放：真实容量二的双阶段队列、RGB 图像输入、绘图和检测消息发布都参与；发布者和检测节点组合在同一进程，rclcpp intra-process 优化未开启。带标注图订阅的案例还包括 RGB 标注图发布和接收。输入源是预解码固定图片，没有相机、MJPEG 解码、web 编码或网络视频消费者，不能把它称为完整相机链路达到 30 FPS。

正式矩阵另试了视觉进程私有 runtime 2.2.0：现用后端在初始化的 `rknn_set_core_mask` 返回 -13 后退出，未到推理阶段。这只能说明**当前后端调用与该运行库组合未通过**，不能据此判断 YOLO 模型在 2.2.0 本身是否可运行。正式共跑保留视觉系统 1.4.0、ASR 私有 2.2.0，两者按进程隔离，不全局替换。


## 用户确认的目标口径（优先于前面的探索矩阵）

目标固定为 **30fps，输入已经缩放到 640×352 RGB**。默认 `yolo.json`
与 `yolo-scheduling.json` 均按此设置；此前 `yolo-final-01` /
`yolo-scheduling-01` 中的 1280×720 输入、无节奏吞吐和 10Hz 案例保留为
输入诊断，不用于目标达标结论。目标复测为 `yolo-target30-01`。

检测器直接使用 640×352 输入并跳过尺寸不匹配时的 RGA 分支。上游缩放
是进入检测器前的工作，不在此阶段耗时中；不把降低帧率当作达成 30fps
的办法。分别以实际 ROS 完成 FPS、唯一输入/输出数量、丢帧和检测消息
延迟评判，而不是只用模型单次计算的倒数。此前在该输入口径下的短测
包括 ROS 单独 300/300、ASR NPU 共跑 600/600，后续延长目标窗口复核。
