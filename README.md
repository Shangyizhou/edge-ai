# edge-ai

端侧 AI 的实际部署、性能验证和复测记录。以后在设备上走通的部署步骤、遇到的失败、解决方法和 benchmark 统一沉淀到这里。

第一批内容是 RK3566（4×Cortex-A55、4GB RAM）上的旧 streaming Zipformer ASR、SummerTTS、微调 Qwen，以及 sherpa-onnx/Piper/Melo TTS 对照。ASR 的 RKNN/NPU 路径已经实际跑通；Summer 和 Qwen 使用 CPU。

新增 ros-robot YOLOv6 的 CPU 重导出候选/NPU 对照、30fps 图像回放、真实 ROS 检测节点与活跃 ASR 共跑测试。

| 要做什么 | 入口 |
| --- | --- |
| 查看首轮结论和参数对比 | [RK3566 实测记录](reports/rk3566/2026-10-21/results.md) |
| 打开静态图表报告 | [report.html](reports/rk3566/2026-10-21/report.html)（克隆后用浏览器打开） |
| 查看 YOLO、30fps 和 ASR 共跑 | [YOLO 实测结论](reports/rk3566/2026-10-21-yolo/results.md) · [静态报告](reports/rk3566/2026-10-21-yolo/report.html) |
| 查看常驻流式 ASR、端点参数与30fps共跑 | [流式实测结论](reports/rk3566/2026-10-21-asr-streaming/results.md) |
| 查看生产ROS ASR的NPU接入、恢复与共跑 | [ROS节点验证](reports/rk3566/2026-10-21-asr-ros/results.md) |
| 重跑或生成报告 | [benchmark 使用说明](tools/edge_benchmark/README.md) |
| 按实际步骤部署 | [RK3566 部署入口](deployments/rk3566/README.md) |
| 查官方依据和失败调查 | [ASR/TTS/NPU](docs/research/rk3566/research-speech.md) · [llama/Qwen](docs/research/rk3566/research-llm.md) · [YOLO](docs/research/rk3566/research-yolo.md) |
| 追溯原始任务 | [范围和确认记录](docs/history/2026-10-21/spec.md) |

## 内容组织

- `deployments/<board>/`：实际部署步骤、版本、模型身份、命令、已知失败和验证方式。
- `tools/`：独立可复用的 benchmark 与适配器；可选 YOLO ROS 回放仅启动隔离检测节点。
- `docs/research/<board>/`：官方资料、参数依据和调查过程；历史判断以最后实测结论为准。
- `reports/<board>/<date>/`：冻结的配置、结果、资源记录、日志和静态报告，包含失败项。
- `docs/history/`：迁移前的范围记录，保留原项目上下文。
- `.local/`：本机资产和完整音频结果入口，Git 忽略。

代码、文档及选定的实测证据进入 Git；权重、录音、音频输出、SDK、虚拟环境、凭据和构建产物留在仓库外。现有机器的 `.local/artifacts` 指向 `/home/orangepi/.cache/ros-robot-edge-benchmark`；旧模型与工具路径见部署文档。历史 JSON 中的绝对路径是当时事实，复测时复制配置调整路径，不重写历史结果。

## 快速检查

```sh
python3 -m unittest discover -s tools/edge_benchmark -p 'test_*.py'
python3 tools/edge_benchmark/benchmark.py report reports/rk3566/2026-10-21
```

生成报告只读取保存的数据，不加载模型、不发起网络请求、不播放或执行机器人动作。完整实测报告原件包含音频，位于外置 `runs/comparison-20261021`；Git 内的可审阅快照省略音频并重新生成页面，数值和日志保留。

## 后续记录方式

每次真实部署写明设备/系统、代码版本、模型来源与hash、依赖、实际执行命令、成功输出和失败修复。每轮实验新建日期目录，保留配置、输入身份、原始结果及测量口径；候选方案与未执行步骤明确标记，不当作已验证。复测入口与部署说明随变更同步更新。

本次从 `ros-robot` 的 `codex/edge-inference-benchmark-research-20261021` 分支迁入，来源提交及逐文件hash见 [迁移来源](reports/rk3566/2026-10-21/migration-provenance.json)。原 ROS 业务和暂停的集成分支不属于这个仓库。
