# Qwen3 原生调用与角色基线 · Mac

日期：2026-10-22。对应 #9。官方 Qwen3-0.6B 未微调，固定9个实际工具，
10条工具输入（含一条双调用）、3条角色输入、1条普通聊天，共14条开发样例；
完整与精简system分别运行一轮，未执行训练、设备动作、生产接入或板端测量。

[实测HTML](report.html) · [精简system原始结果](short/results.json) ·
[完整system原始结果](full/results.json) · [准备交接](preparation/output/report.html)。

## 当前观察

| 提示 | 原生 / JSON / Schema / Registry | 函数与参数期望 | 角色固定规则 | prompt中位数 | decode中位数 |
| --- | --- | --- | --- | --- | --- |
| 精简system | 均10/10 | 10/10 | 1/3 | 879 tokens | 63.77 tokens/s |
| 完整项目system | 均8/10 | 7/10 | 3/3 | 2038 tokens | 51.58 tokens/s |

精简提示下，模型已能处理这组简单工具，主要缺口是“小沫”和用户创造角色的固定设定：
真实回答包括“我叫机器人助手…”、“由人工智能助手创建的角色”。完整提示能保留这三项角色
检查，却在部分工具输入中给出文字或非预期调用。原始输出均保留，不据此断言长提示普遍更差。
这给后续“精简system＋微调”的实验提供了明确对照，不能把10条例子推广为完整业务可靠。

## 模型、设备与资源

官方revision `c1899de289a04d12100db370d81485cdf75e47ca`，有效共享参数596,049,920；
存储张量项751,632,384含重复的共享输出矩阵，权重文件1,503,300,328 bytes。
HF BF16 / MLX-LM0.32.2 / MLX0.32.4 / Apple M5 Metal / 16GiB统一内存；
transformers5.20.2，完整依赖见environment.txt。此处CPU不是RK3566 ARM。

| 提示 | TTFT中位数 | prefill中位数 | CPU整机10核容量 | 采样峰值RSS |
| --- | --- | --- | --- | --- |
| 精简 | 0.208s | 4275.26 tokens/s | 3.32% | 644.20MiB |
| 完整 | 0.547s | 3770.42 tokens/s | 2.94% | 665.67MiB |

CPU包括生成与纯校验进程树，不含Metal GPU利用率。报告单列每例MLX峰值分配，
它与RSS可能重叠，不相加也不称PSS。资源每200ms采样，CPU按窗口时长加权；
加载单列，14例单轮不代表稳定P95。运行前编译任务已结束，无本任务并行训练。

MLX原生prefill计时包括首个生成token，generation_tokens计数可能包含EOS；
速度字段保留该边界。TTFT在模板token化后进入生成计时；完整有效调用等待包含
模板、生成、解析和Registry纯校验。跨运行时不得不加说明地作纯速度归因。

## 证据、准备和复现

原始request/suite、各case/事件/资源、模型hash、实际source-manifest及Registry源码
快照保留。preparation为真实执行后从证据重建的准备记录，不倒称运行前已生成就绪证明。
Registry wrapper只实例化能力声明并调用validate_calls；没有调用handler。

sources保存实际运行时的采集源码；view-source是随后仅补充MLX内存标签的展示源码。
重渲染没有重新推理，原case/events/results保持不变。manifest逐文件记录内容hash。

开发集不会直接作为最终独立测试集，后续切分需按原始语义/改写来源隔离。
模型和环境在Git外；复现时从固定官方revision准备模型和依赖，生成新的request，
将model_path和registry_validator的argv改为本机实际位置，再调用tools.qwen_lifecycle
benchmark入口。不要覆盖此冻结run。

静态HTML结构、链接/锚点、数据转义和响应式CSS已检查；实际浏览器视觉预览受
当前浏览器文件URL策略限制，未冒充已完成浏览器视觉验收。后续可在获准预览环境复核。
