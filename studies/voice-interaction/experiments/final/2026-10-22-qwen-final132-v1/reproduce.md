# 重现与工作流交接

## 边界与固定身份

预注册选择见[最终计划](../../../research/2026-10-22-mac-qwen-plan/final-evaluation-plan.json)，本轮启动前的精确请求hash见[launch-freeze.json](launch-freeze.json)。`final-suite.json`包含原120与独立补充12，逐例cohort不可删除；原始封存JSONL bytes与SHA保持原样。`cohort-audit.json`记录对300训练/60验证的精确输入与来源家庭排除检查。

运行时llama.cpp固定`e3797b184d428c7a019362612b76971f60af6670`。基座Q4仅去除已证实重复的tied lm_head存储，保留596049920真实独立参数；最终采用`matched-base-dedup-v2`，不是早期重复head诊断制品。选择、格式能力、人设事实、动作语义、生产集成分别判断。

每设备132×2完整最终请求；Mac与板端独立分组、各自模型串行。另有两次板端已知验证样本准备冒烟，以及一次Mac初始后台启动中断的3个已保存请求。这些附加运行不加入canonical528质量与延迟分母。中断未改变冻结请求；完整132重新运行，原3例保留为基础设施失败证据。

“首例冷”只指新server的空KV/前缀缓存，未控制OS文件页缓存，未运行drop_caches。Mac cache off、板端cache on；每例保存full prompt usage、实际evaluated prefill、cached、output与native时间。`predicted_n`输出数与原生decode的`n_gen-1`步数分开，不重算吞吐。资源为实际server PID递归树，推理与纯校验窗口；200ms是等待配置，实际间隔和开销另由raw events汇总。整机swap和余量不能归因模型。

## 五个技能的真实衔接

维护来源为[personal-skills提交9982deb](https://github.com/Shangyizhou/personal-skills/commit/9982debfcc8f02ee9a20894b0a656c9e761d693a)。本轮benchmark使用该来源安装副本；`source-identities.json`记录实际文件hash。项目保留角色/数据/实验适配器，技能只提供数据无关契约与dispatcher。

| 能力 | 输入 | 输出及实际证据 |
| --- | --- | --- |
| selection | 设备需求、候选、测量结果、冻结事实审核 | 验证阶段预选Q4；本轮`final-summary.json`与`lifecycle.json/report.html`解释最终所有门槛，不用最终结果重新选择 |
| prepare | 候选hash、实际runtime与dev输入、后续冻结配置 | `preparation/request.json/checks.json/output/readiness.json`；两个板端真实开发样本证明最小原生推理 |
| finetune | 300/60源分组数据、BF16基座、LoRA配置 | [选定训练实验](../../mac/2026-10-22-qwen-selected9-adaptation-v1/README.md)；训练result-v1、adapter hash与资源，最终集未加载 |
| export | base/adapter制品manifest、版本化operation/input/output链 | [合并量化实验](../../mac/2026-10-22-qwen-selected-precision-v1/README.md)；merge/convert/quantize result-v1与逐精度实际验证 |
| benchmark | `final14-DEVICE-MODEL-request.json`（candidate+suite+generation+server） | `runs/RUN/benchmark/results.json`、逐例输出/events、实际runtime/assets、退出与dispatcher结果 |

准备报告的PASS只验证最小功能，正式benchmark才测全量132。dispatcher仅检查声明结构，`source.kind=device_measurement`不是密码学真实性证明；实际模型/命令/来源/日志/hash一起提供证据。

## 原始运行命令

模型/venv/build留在Git外，真实路径已保留在请求和runtime中。先校验资产hash与空间，不删除旧模型。SSH目标为`orangepi-ts`。运行新副本需要新输出目录；不要覆盖本轮冻结运行。以下命令会启动真实模型，应在独立复现实验目录执行：

```sh
# Mac，源checkout /tmp/edge-ai-ticket-14，Python3.12.14
PY=/Users/syz/.local/share/edge-ai/qwen-lifecycle/venv/bin/python
$PY /Users/syz/.codex/skills/edge-model-benchmark/scripts/run_benchmark.py \
  --request /Users/syz/.local/share/edge-ai/qwen-lifecycle/ticket14/final14-mac-base-request.json \
  --output /NEW/EMPTY/OUTPUT --cwd /tmp/edge-ai-ticket-14 \
  --command "$PY" -m tools.qwen_lifecycle.mac_run

# 板端：新source目录，不覆盖T12或生产ros-robot
PY=/home/orangepi/.local/share/edge-ai/qwen-ticket12/venv/bin/python
$PY /home/orangepi/.local/share/edge-ai/qwen-ticket14/edge-model-benchmark/scripts/run_benchmark.py \
  --request /home/orangepi/.local/share/edge-ai/qwen-ticket14/inputs/final14-board-base-request.json \
  --output /NEW/EMPTY/OUTPUT \
  --cwd /home/orangepi/.local/share/edge-ai/qwen-ticket14/source \
  --command "$PY" -m tools.qwen_lifecycle.board_run
```

本轮实际队列见`source/queue.py`，每平台base→selected，所有case不裁剪。原source测量快照在每次运行的`source/`；最后维护源码可能增加只读报告或未来路径修复，不能当成历史执行字节。Mac历史launcher顶层result的旧evidence相对路径缺少`benchmark/`，本轮分析采用原始`benchmark/results.json`（路径可解析）；旧launcher记录保持原样。维护版Mac launcher已与board一致修复未来handoff路径，未重写本轮快照或重跑质量。

## 离线重渲染（不启动模型）

在任意带标准Python的edge-ai checkout根目录：

```sh
python3 -m tools.qwen_lifecycle.final_report \
  studies/voice-interaction/experiments/final/2026-10-22-qwen-final132-v1/lifecycle.json \
  /tmp/qwen-lifecycle-rerender.html
```

`lifecycle.json`包含阶段数据、四组全部原始回复、明确的上下文审核与冻结身份。主HTML同样内嵌这些内容和可下载JSON，无网络依赖即可核心阅读；`evidence.zip`携带本次原始配置、逐例events、源码和manifest。历史阶段的完整raw是指向仓库内旧实验的伴随链接，不声称递归内嵌所有旧文件。独立`inference-report.html`由已安装selection的read-only adapter从同4个benchmark result-v1重渲染，关键词人设规则只作辅助，不替代主报告的上下文审核。

最终报告静态验证包括锚点、相对链接、HTML转义、自包含核心阅读、右侧导航与移动端CSS规则。既定浏览器文件预览被拒绝，未使用HTTP、其他浏览器或Playwright规避；实际桌面/手机视觉效果仍未验证。

根集成已通过`ae5b10de2a12057cc0405dacab26730c70429c10`为新的Qwen实验前缀增加静态站点导出排除规则；本轮未发布Pages，这些数据默认不进入公开静态导出。公开发布需要单独操作。

板端复用T12的GCC9.4 Cortex-A55 CPU构建，`GGML_CPU_REPACK=OFF`、OpenMP ON；实际使用`--no-repack`。这是保守实测组合，不代表硬件最大能力，未进行GPU/NPU推理。
