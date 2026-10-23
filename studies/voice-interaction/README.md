# 机器人本地语音 · 当前 skill 流程

更新：2026-10-22。Orange Pi 3B / RK3566 / 标称4GB，实际MemTotal约3.83GiB。目标是本地“听懂 → 回答 → 合成 → 播放”，后续再验证机器人共跑。

当前入口只保留按skill重新选型后的流程。旧实验和旧结论已[仓库外归档](../../archives/README.md)，不作为当前推荐依据。

## 当前结论

| 部分 | 已确认什么 | 尚未确认什么 |
| --- | --- | --- |
| ASR zh14M混合INT8 / FP32 | 同3条有声材料真实运行；机器人指令输出与用户确认文本一致。实时INT8 CPU26.05%、PSS115.28MiB；FP32 CPU29.47%、PSS158.69MiB | 两条公开参考子集CER均45.45%；不代表整体识别率或完整交互达标 |
| Qwen3-0.6B LoRA Q4 / 最终独立集 | Mac与RK3566各132条：84/84工具请求原生/JSON/Schema/Registry通过，聊天12/12无调用；板端CPU46.04%四核容量、峰PSS600.30MiB，工具完整调用P50/P95约11.57/27.33s | 人设Codex上下文审核两端均21/36、各10条误调用；语义精确Mac73/84、板端72/84；KV冷首例约174s；角色内化、生产与共跑未达完整验收 |
| Qwen2.5-0.5B Q4_K_M | 通用6任务检查5/6；另外6工具的fc/res兼容路径诊断0/3 | 0/3只覆盖兼容路径，不能外推当前ros-robot原生tool_calls；原生调用未测 |
| Qwen3-0.6B BF16 / Mac MLX Metal | 14条开发用例原生基线：精简system工具格式/Schema/Registry 10/10、人设1/3；完整system工具格式8/10、人设3/3 | 仅未微调Mac小集对照；不能继承旧兼容路径结论或推断新权重板端效果 |
| Qwen3-0.6B LoRA 32微步试点 | 已实际训练4次优化器更新，327680可训练参数，MLX峰值约2.090GB；adapter/合并/F16/Q4分别完成7例冒烟，代表工具3/3、角色1/3；Q4约396.7MB | 该7例只证明小步训练及合并转换通路，不作为完整工具、人设或产品验收 |
| Qwen3-0.6B 选定LoRA / Mac验证 | 300训练/60验证；原短提示人设上下文审核1/18→17/18；选定路由短提示（不含事实）下工具JSON/Schema 36/36、人设18/18、工具精确33/36 | 合成验证与Codex审核，不是人工/生产验收；仍有跟随开关和字符串复制失败；验证集用于选配，独立结果另列；不能由此认定角色已可靠内化 |
| 选定权重 F16/Q4/Q5/Q8 / Mac同条件 | 原生/JSON/Schema各36/36；工具精确33/30/31/33，人设审核18/18、18/18、16/18、18/18；Q4约396.7MB，Q8约639.4MB | Q4语义有损，Q5也损失人设；Q8为质量参照。板端独立结果另列，不能套用Mac资源 |
| Melo zh_en FP32 | 原4条文本均生成有效WAV，整句PCM就绪约18.9–25.8秒 | 尚未试听评审，发音/自然度与实际扬声器等待未知 |

ASR资源只取本轮3条有声输入的实时推理窗，CPU为被测进程树占整机4核容量、PSS为200ms采样峰值。各模块独立运行，不相加推算共跑。[模型详情](models.md)列出精度、框架、后端与证据。

## 当前保留的流程

1. [资料选型](research/2026-10-22-local-stack/README.md)：官方来源与候选，忽略旧本地实测。
2. [冻结准备](research/2026-10-22-runtime-preparation/README.md)：资产与执行配置；早期加载检查不能当作推理通过。
3. [实际就绪](experiments/rk3566/2026-10-22-preparation-smoke-v1/README.md)：ASR解码、LLM生成、TTS合成均完成最小真实推理。
4. [单模块初筛](experiments/rk3566/2026-10-22-voice-screening-v2-r1/README.md)、[ASR三条材料对照](experiments/rk3566/2026-10-22-asr-three-samples-v1/README.md)：原始输入/输出、资源、计时与哈希保留。
5. [业务兼容路径诊断](experiments/rk3566/2026-10-22-qwen-business-fit-v1/README.md)：保存失败证据；当前目标已澄清为原生tool_calls，不沿用该兼容协议训练。
6. [Qwen3业务LoRA方案](research/2026-10-22-qwen-adaptation/README.md)：保留当时尚未训练的研究记录，后续范围以当前规格和实验为准。
7. [Mac原生调用与人设基线](experiments/mac/2026-10-22-qwen-native-baseline-v1/README.md)：同一官方Qwen3、9个选定工具、14条开发输入，对照完整/精简system；真实输出、资源与失败均保留。[离线HTML](experiments/mac/2026-10-22-qwen-native-baseline-v1/report.html)。
8. [最小LoRA与导出试点](experiments/mac/2026-10-22-qwen-lora-export-pilot-v1/README.md)：真实32微步、合并/转换/量化和逐制品冒烟；保留转换兼容与本地代理失败及修复记录。

9. [关键工具与人设适配](experiments/mac/2026-10-22-qwen-selected9-adaptation-v1/README.md)：真实300训练/60验证，三轮训练与完整/精简提示对照，保留全部失败；选择阶段保持最终集封存，最终评估另列。[配对HTML](experiments/mac/2026-10-22-qwen-selected9-adaptation-v1/report.html)。

10. [合并与同权重量化对照](experiments/mac/2026-10-22-qwen-selected-precision-v1/README.md)：adapter/merged 60条原文一致，F16/Q4/Q5/Q8及同布局未微调Q4实际加载验证，所有语义和人设失败保留。[离线HTML](experiments/mac/2026-10-22-qwen-selected-precision-v1/report.html)。

11. [板端LoRA试点与缓存/KV](experiments/rk3566/2026-10-22-qwen-pilot32-board-v1/README.md)：23次开发执行，隔离新运行时与失败记录；九工具目录q8KV缓存冷/重复/前缀变更约166.3/9.7/11.9秒，模型进程树峰PSS约565.6MiB，仅为试点权重和指定样本。

12. [最终跨设备独立集与生命周期](experiments/final/2026-10-22-qwen-final132-v1/README.md)：原120条与额外12条多调用分别记录，每个模型/设备132条；四组528次正式请求，保留Mac启动中断额外3条。格式与聊天通过，人设21/36部分达成。[完整离线HTML](experiments/final/2026-10-22-qwen-final132-v1/report.html)。

## 下一步

本轮六张工单的实现与实测交付见[集成PR #15](https://github.com/Shangyizhou/edge-ai/pull/15)。三个新增技能已从[personal-skills PR #3](https://github.com/Shangyizhou/personal-skills/pull/3)源码安装，支持benchmark、finetune、export的独立交接；本仓库拥有实际数据与执行适配器。

M5/16GB已实际完成0.6B LoRA，无需LLaMA-Factory；选定768微步/96次优化器更新，全阶段约621.6s，MLX峰active约2.80GB（不等于整机总占用）。板端采用Q4权重＋q8 KV、2048上下文和前缀缓存，实测字段与未知项见最终报告。原生格式试点通过，但验证人设18/18降至独立21/36，下一轮需新来源训练/验证及新的封存集；不得沿用已观察最终集调参后再称未见测试。业务适配继续保留Schema、工具白名单和执行控制。

完整语音交互、ROS/视觉共跑与硬件动作均未验收，不因最小推理或几条成功样例宣称产品通过。[准备计划](plan.md) · [接入边界](integration.md) · [实验索引](experiments/rk3566/README.md)。

当前认可格式已固化为[独立HTML主报告](reports/2026-10-22-voice-screening/report.html)，公开版不携带录音；网站只提供报告列表。可试听的Mac离线版仍在临时目录 `/tmp/edge-voice-report-draft/report-mac.html`；它支持Mac离线查看和试听。原实验HTML/JSON未修改；当前展示格式已写入本机edge-model-selection。

新Qwen离线目录由静态导出排除列表保护，公开发布是单独步骤。HTML完成静态引用/核心离线/响应式规则检查，浏览器视觉未验证。

## 2026-10-23 工作流适配验证

[数据与任务化工作流](experiments/mac/2026-10-23-workflow-pilot-v1/README.md)及[板端Qwen/ASR](experiments/rk3566/2026-10-23-workflow-validation-v1/README.md)已完成新执行与交接验证，保留ASR首次报告失败。32微步模型只作技术试跑，未替换上表主候选；最终新集未开启，机器人动作与共跑未执行。[分环节总报告](experiments/mac/2026-10-23-workflow-pilot-v1/workflow-overview/report.html)。

## 数据与正式报告入口

- [数据版本及备份恢复](datasets/README.md)：四组已登记数据、用途与隔离限制。
- [保存的实验索引](experiments/index.json)：派生目录，历史未登记关联保留为未知。
- [公开报告生成及 Pages 白名单](../../tools/research_site/README.md)：正式报告与原始证据分开管理。
- [工作流报告总览](reports/2026-10-23-curated/workflow/report.html)：只读回放；32微步试跑不能替代原正式模型验收。

- [HF模型下载](https://huggingface.co/Shangyizhou/xiaomo-qwen3-0.6b/tree/0bd09b627bb133b8a9f5a71cfeb8225a421d33ba) · [模型固定版本清单](releases/selected9-768-v3.json) · [HF数据归档](https://huggingface.co/datasets/Shangyizhou/xiaomo-robotics-data/tree/3f78791304c9c0b1457d6674273ba3e46927f4b5)（均需授权访问）。
