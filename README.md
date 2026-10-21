# edge-ai

端侧模型的调研、部署与性能测试记录。按研究主题查阅，每个主题集中保存调研依据、设备部署方法和实验结果。

| 研究主题 | 做了什么 | 阅读入口 |
| --- | --- | --- |
| 语音交互 | RK3566上的ASR、TTS、Qwen对照；流式ASR、生产ROS节点NPU接入及视觉共跑 | [语音交互总览](studies/voice-interaction/README.md) |
| 目标检测 | ros-robot YOLOv6 CPU候选/NPU对照、640×352@30fps回放及ASR共跑 | [目标检测总览](studies/object-detection/README.md) |

从主题总览开始，先看结论和验证范围，再按需查部署、实验与原始数据。新增研究主题放在`studies/<topic>/`，共用测试工具保留在`tools/`。

## 目录约定

```text
studies/<topic>/
├── README.md                 # 目标、当前进展与阅读入口
├── research/                 # 官方资料、候选方案和测量方法
├── platforms/<device>/       # 设备说明、部署步骤和外部资产清单
├── experiments/<device>/     # 实验索引和各轮完整记录
└── history/                  # 历史需求和决策（有需要时建立）
tools/edge_benchmark/          # 多主题共用的测试工具
```

本轮先完成文件归类和入口整理。已有实验目录整体搬迁，保留内部布局；后续可在主题内继续整理当前结论和待办。跨主题实验只保留一份原始证据，通过链接引用。

## 复测与数据

[benchmark使用说明](tools/edge_benchmark/README.md)包含配置、执行方式和报告生成方法。报告内的绝对路径、源码hash和来源清单表示测量当时的事实，不随目录迁移改写。

```sh
python3 -m unittest discover -s tools/edge_benchmark -p 'test_*.py'
python3 tools/edge_benchmark/benchmark.py report studies/voice-interaction/experiments/rk3566/2026-10-21-baseline
```

生成报告只读取保存的数据，不加载模型或执行机器人动作。代码、文档和实测证据进入Git；模型权重、录音、SDK、凭据与构建产物放在仓库外。`.local/artifacts`是本机外部缓存入口。

原始工作从ros-robot迁入，来源提交和逐文件hash见[迁移来源](studies/voice-interaction/experiments/rk3566/2026-10-21-baseline/migration-provenance.json)。ros-robot生产实现仍在其自身仓库维护。

## 协作约定

工作与规格记录在[GitHub Issues](https://github.com/Shangyizhou/edge-ai/issues)。
代理入口见[AGENTS.md](AGENTS.md)，领域术语见[GLOSSARY.md](GLOSSARY.md)，
工程技能配置在[docs/agents/](docs/agents/)。研究过程与实验数据继续按主题归档。
