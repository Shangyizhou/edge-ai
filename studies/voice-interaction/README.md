# 机器人本地语音：现在怎么选，下一步做什么

更直观的阅读入口：[研究看板](https://shangyizhou.github.io/edge-ai/) · [资源图表](https://shangyizhou.github.io/edge-ai/models.html) · [研究进度](https://shangyizhou.github.io/edge-ai/process.html)。

更新：2026-10-21。目标设备：Orange Pi 3B / RK3566 / 标称4GB内存。

我们要让机器人在本地完成“听懂 → 思考 → 说话”，同时为视觉检测留出资源。**ASR节点已接入验证，完整语音交互尚未验收。**

## 当前建议

| 部分 | 现在怎么做 | 为什么 |
| --- | --- | --- |
| ASR | 暂时沿用已验证的FP16 NPU配置 | 已有ROS接入证据；是否比CPU更合适，仍缺同精度公平对照 |
| ASR量化 | 当前INT8候选不用 | 只有joiner量化成功，识别明显退化 |
| LLM、TTS | 保留现有CPU候选，暂不定最终组合 | 已有单模块短测，实际对话和完整听说体验待验证 |

这里“沿用”指继续验证现有集成，不是已经证明NPU是最优后端。[选型依据与缺口](models.md)

## 三个关键观察

| 观察 | 已有数据 | 能说明什么 |
| --- | --- | --- |
| ASR资源取舍 | CPU/NPU方案占整机CPU容量约29%/5%，峰值PSS约128/215 MiB | 不同精度部署方案的三轮中位数；不能归因为纯后端收益。[完整对照](models.md#asr听懂说了什么) |
| INT8识别退化 | 两条独立音频CER由27.27%升至87.88% | 仅joiner量化的混合方案当前不采用。[量化尝试](experiments/rk3566/2026-10-21-asr-int8-ptq/results.md) |
| ASR与视觉共跑 | 640×352、30fps，45秒回放完成1350/1350帧 | 短回放成立，真实摄像头和长期表现未验证。[组合验证](integration.md) |

## 下一步，先抓一件事

**补齐ASR同源同精度CPU/NPU对照。** 核验权重、实际运算精度和流式配置，再用现有小语料复测；无法匹配则记录具体缺口，不以不同精度替代。[待解决工单 #1](https://github.com/Shangyizhou/edge-ai/issues/1)

之后再扩展LLM/TTS复测，测完整链路各段等待，根据瓶颈决定优化什么。INT8误差定位属于可选支线，不是后续研究的前置条件。

## 想了解原因，从这里往下看

| 阅读入口 | 回答什么 | 当前进度 |
| --- | --- | --- |
| [准备](plan.md) | 要做成什么、设备与候选、怎样测 | ASR轻量协议已有；完整交互预算待明确 |
| [单模型对比](models.md) | ASR、LLM、TTS各自测了什么，如何选择 | 已有候选与数据；公平对照及质量证据仍有缺口 |
| [机器人验证](integration.md) | 共跑、ROS接入和完整体验是否成立 | ASR节点与短时共跑已验证；完整交互未验收 |

只看现状读本页即可；参数、来源与原始记录从详情页继续进入。按批次查数据用[实验索引](experiments/rk3566/README.md)，查看已有图表用[ASR评测页](experiments/rk3566/2026-10-21-asr-lite-v1/evaluation/report.html)或[历史只读视图](comparisons/2026-10-21-legacy-v1/README.md)。
