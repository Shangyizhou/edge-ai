# edge-ai

**网页入口：[Edge AI 研究台](https://shangyizhou.github.io/edge-ai/)** · 建议、资源图表、研究进度与可检索证据。[网站维护与本地预览](tools/research_site/README.md)。

端侧模型的调研、部署与性能测试记录。按研究主题查阅，每个主题集中保存调研依据、设备部署方法和实验结果。

| 研究主题 | 做了什么 | 阅读入口 |
| --- | --- | --- |
| 语音交互 | RK3566上的ASR、TTS、Qwen对照；流式ASR、生产ROS节点NPU接入及视觉共跑 | [语音交互：当前建议与下一步](studies/voice-interaction/README.md) |
| 目标检测 | ros-robot YOLOv6 CPU候选/NPU对照、640×352@30fps回放及ASR共跑 | [目标检测总览](studies/object-detection/README.md) |

从主题首页看当前建议、关键数据和下一步，再按需查依据。语音交互的详情收敛为[准备](studies/voice-interaction/plan.md)、[单模型对比](studies/voice-interaction/models.md)、[机器人验证](studies/voice-interaction/integration.md)三页。新增研究主题放在`studies/<topic>/`，共用测试工具保留在`tools/`。

## 目录约定

```text
studies/<topic>/
├── README.md                 # 当前建议、关键数据、下一步
├── plan.md                   # 准备：目标、设备、候选与怎样测
├── models.md                 # 单模型对比：筛选、复测与选择
├── integration.md            # 机器人验证：共跑、接入与完整体验
├── research/                 # 官方资料、候选方案和测量方法
├── platforms/<device>/       # 设备说明、部署步骤和外部资产清单
├── experiments/<device>/     # 实验索引和各轮完整记录
├── comparisons/              # 跨实验只读视图，链接原始证据
└── history/                  # 历史需求和决策（有需要时建立）
tools/edge_benchmark/          # 多主题共用的测试工具
```

上面是语音交互的阅读布局；其他主题按已有内容逐步采用，不预建空页面。日常页面汇总判断，研究资料和实验目录保留详细证据。

通用流程和结果格式集中在[研究方法](docs/methodology/README.md)。新增实验按统一协议保存；历史实验目录保留原布局和证据。跨主题实验只保留一份原始证据，通过链接引用。

## 研究方法

通用方法已确认为[端侧模型轻量评测SOP](docs/methodology/model-evaluation-sop.md)（v1.1）：资源和性能优先，少量固定用例，先单模块后共跑，结构化结果生成静态HTML。已完成[ASR现成方案试点](studies/voice-interaction/experiments/rk3566/2026-10-21-asr-lite-v1/results.md)，同精度CPU/NPU受控主基线待补齐。数据契约与入口见[方法索引](docs/methodology/README.md)；历史证据按原比较口径保留。

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
