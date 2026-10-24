# 统一 Benchmark 入口

Qwen 和 ASR 的新测试使用 [固定代码流程](WORKFLOW.md)：配置 → plan → run → MLflow；无需安装 Skill，新入口默认不生成 HTML。旧接口与以下历史说明保持兼容。

# 当前流程的测量工具

共用执行器、适配器、资源采样和离线校验代码保留。旧模型/YOLO/量化试验配置JSON已[仓库外归档](../../archives/README.md)，当前可执行配置与输入身份以[本轮运行准备](../../studies/voice-interaction/research/2026-10-22-runtime-preparation/README.md)及各个新实验的冻结副本为准。

[当前实验索引](../../studies/voice-interaction/experiments/rk3566/README.md)提供真实结果、日志、协议、清单与哈希。需要读历史时从归档恢复到独立目录，勿让旧配置成为当前默认执行路径。

## 验证与重绘

```sh
python3 -B -m unittest discover -s tools/edge_benchmark -p 'test_*.py'
python3 -B studies/voice-interaction/experiments/rk3566/2026-10-22-voice-screening-v2-r1/measurement-source/report.py --render
```

第一条是离线工具测试；第二条只从本轮results.json重绘原报告，不运行模型。报告格式确认前在临时副本迭代，不覆盖冻结数据。历史v1原生ASR validator和本轮Python v2执行协议不同，不能仅凭名称混用。

实际新推理需要冻结新实验范围、输入、模型与运行时身份，写到新的输出目录，不重复运行历史execute.py覆盖旧结果。生产代码在ros-robot维护，这里的实验源码副本只作证据。
