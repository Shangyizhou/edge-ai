# Qwen3 最小 LoRA、合并与 GGUF 导出实测

日期：2026-10-22。对应工单[#10](https://github.com/Shangyizhou/edge-ai/issues/10)。本轮完成小规模实际训练与制品闭环，不代表关键工具全覆盖、人设适配或香橙派验收完成。

[阶段 HTML](report.html) · [逐条原生调用/角色 HTML](inference.html) · [训练曲线](loss.svg) · [准备交接](preparation/output/readiness.json)

## 结论与当前制品

Apple M5 / 16GB / MLX-LM0.32.2 / MLX0.32.4 / Metal，官方Qwen3-0.6B基座，唯一参数596,049,920。20条训练、5条验证开发样例，3个代表工具（无参/数值/字符串）和已核实角色事实；最终独立测试集未创建或加载。

- 实际32个微步、梯度累积8，只有4次优化器更新；last8层的q/v LoRA rank8，训练参数327,680（约0.055%）。本轮不是完整业务训练。
- 最终可复现种子同时设置MLX与NumPy。完整样本最长469 tokens，容量2048；所有目标的非思考推理前缀与loss mask相同，无静默截断。
- 实际训练阶段6.461秒，全流程加载/预检/训练/验证7.644秒；这是先前试跑后已热的运行环境，不能用它与首轮冷启动差异宣称优化。训练loss从3.004降至0.503，5条验证loss从2.757降至0.612。
- 整轮训练进程树CPU占Mac10逻辑核容量约4.73%，采样RSS峰值473.20MiB；MLX峰值分配1,993.20MiB，二者可能重叠，不相加。CPU不代表Metal GPU利用率。训练监督token速率与生成速率分开保存。
- adapter、合并HF权重、GGUF F16、GGUF Q4都完成实际加载与同一7条开发样例推理。每版3条工具均原生/JSON/Schema/真实Registry **3/3**；角色固定规则仍 **1/3**，普通聊天1/1。人设需要后续扩大训练，不能据loss下降说已学会。

| 变换 | 实际墙钟 | 输出制品大小 |
| --- | --- | --- |
| BF16基座+adapter合并 | 2.634秒 | HF目录1,203,585,805 bytes |
| 合并HF→GGUF F16（含tokenizer兼容桥） | 10.273秒 | 1,198,182,336 bytes |
| 同一F16→Q4_K_M | 5.582秒 | 396,704,704 bytes（约378.33MiB） |

官方基座文件包含重复的tied lm_head存储，实际文件约1.503GB；合并目录变小主要包含序列化/共享权重去重，不能归因LoRA压缩。adapter目录约2.63MB，含最终和一个检查点副本。模型大小不是运行RAM。

Q4供下一步板端独立试点使用，外置位置记录在export结果。MLX原生生成未施加grammar，llama-server的native API使用原生工具grammar，且框架/计时边界不同；这里只核查制品链与最小能力，不将MLX/GGUF差异当纯量化速度或质量收益。正式同运行时量化对照留待后续工单。

## 实际路径与保留的失败

普通MLX fuse产生HF兼容权重，随后由完整固定源码的llama.cpp转换；没有调用不支持Qwen3的MLX直接GGUF exporter。

首次转换因TF5保存的tokenizer_config中extra_special_tokens列表不兼容固定TF4.57.6转换器而失败，见attempt-converter-failure。解决方法是保留原合并制品，证明其与基座词表及非思考工具模板token序列一致，在新staging目录恢复原始tokenizer字节；张量引用不变，证明见tokenizer-fidelity.json。没有改写官方基座或原始合并制品。

首个Q4客户端冒烟受Mac环境代理影响，返回502且本地服务无请求记录，见attempt-proxy-failure；随后HTTP adapter使用显式direct配置，真实运行通过。不能把这次传输失败当成模型效果。首次未显式固定NumPy顺序的开发训练及其制品仍在外置存储；本目录主结果采用双种子修正后的新run。

用于合并权重的早期开发冒烟曾与服务初始化重叠，外置原文保留；主结果重新串行执行，不用重叠窗口作资源对照。所有最终模型作业和独立服务均已退出。

## 可复现入口

项目命令为tools.qwen_lifecycle的finetune、export、benchmark、stage-report，公开输入输出契约和真实请求见各阶段子目录。模型、两个隔离Python环境、converter源码及二进制在Git外；本目录只保存身份、配置、原始输出/日志/采样、数据和源码快照。

- training：20/5数据、配置、每例token/mask证明、原始callback和采样、自动冻结的实际训练源码。
- export：逐步命令、输入输出manifest、耗时/资源、实际转换日志及转换器源码/二进制身份。
- adapter/merged/f16/q4：相同7条开发用例的原生输出、分层校验和原始流事件；模型不执行动作。
- preparation：根据已执行加载/最小推理/配置证据补记的prepare交接，明确它不是更早的准备时点。HTTP重放必须重新启动独立服务并绑定新PID。
- implementation-source：推理结束后、代码格式化前保存的采集与初版视图源码；推理采集逻辑在执行与快照之间没有语义变更。训练/导出使用run内自动提前冻结的collector-source。最终只读视图源码另存view-source，不倒写原始快照。

新增finetune/export技能维护在personal-skills，数据和用户角色不写死在技能中；实际请求/结果均通过对应技能handoff检查。12项项目公开边界测试、两个技能handoff测试及两个skill结构校验通过。HTML仅做静态ID/本地引用/可携带数据检查；浏览器file://被策略阻止，视觉验收未验证。无ROS、无真实设备动作、无公开网站发布。
