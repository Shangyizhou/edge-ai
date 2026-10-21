# 生产C++ ASR节点：RKNN接入与真实ROS回放

2026-10-21 UTC，RK3566 / Orange Pi 3B / 4GB。

**既有常驻C++ ASR节点已接入显式RKNN后端。通过实际ROS音频Topic/控制Service完成六次新流识别、暂停隔离、缺帧报错及新流恢复。** 本轮不启动Agent、声卡、播放或机器人动作，不宣称整套四进程已验收。

[派生汇总](summary.json) · [全部ROS事件与控制](result.json) · [原生日志](native.log) · [源码/库哈希及真实进程映射](measurement-source.json) · [此前端点扫描和YOLO共跑](../2026-10-21-streaming-asr/results.md)

## 实现

复用ros-robot的`robot_inference/asr_node`，而非扩展旧`robot_voice/sherpa_asr.py`CLI前端。按既定ADR0012，模型加载一次，唯一worker管理流和native调用，ROS回调交接有界音频队列。

- 显式`provider=cpu|rknn`，未知值拒绝；RK3566的rknn必须`num_threads=1`。缺省CPU路径保留，不静默回退。
- rule2端点默认1.2秒，offline示例同步；提供本机已验证模型路径的`rk3566-asr-npu.yaml`。
- `offline.asr.provider`通过配置校验和既有Launch参数链路交给节点。
- ASR可单独选择SDK，不改变TTS依赖；私有RKNN2.2作为可执行文件直接ELF依赖。`ldd`与运行中的`/proc/PID/maps`均确认使用外置2.2.0库，不替换系统1.4.0。

仅给主程序加RPATH曾仍解析到系统旧库，因为Sherpa库有自身`$ORIGIN` RUNPATH。初次启动检查因此中止，未纳入成功数据；修正直接依赖后重新回放。不要仅以参数目录存在判断运行时版本。

## 实测

16kHz PCM16，100ms真实节奏供音；每文件补3.2秒实时静音；独立ROS_DOMAIN_ID=179，仅本机通信。命令源与精确拼接来源见此前报告的fixture元数据。结果时间取ROS事件接收单调钟，包含Topic交付，与此前直接C API探针计时边界不同。

| 流 | 非空final数 | 相对能量末端的逐条等待s | 与既有命令文本一致 |
| --- | ---: | --- | --- |
| independent-0 | 1 | 1.598 | 1/1 |
| independent-1 | 1 | 1.573 | 1/1 |
| independent-2 | 1 | 1.590 | 1/1 |
| independent-3 | 1 | 1.702 | 1/1 |
| independent-4 | 1 | 1.570 | 1/1 |
| independent-5 | 1 | 1.713 | 1/1 |
| recovered | 1 | 1.574 | 1/1 |
| continuous | 6 | 1.574 / 1.690 / 1.920 / 2.011 / 1.523 / 1.820 | 4/6 |

六次独立新流均输出同一既有参考；故意从sequence=1发送的缺帧流输出`invalid, stale, or discontinuous audio frame`，随后新流恢复成功。暂停确认后提交旧流PCM未产生新事件。每轮只重建stream，未重新加载模型。

连续流有六个非空final，但末两轮仍出现“请”→“形”、“上前”→“向前”。这是相同PCM在受控实验中的文本一致性差异，不是独立人工转写准确率。新流实验支持现有回合恢复时销毁旧stream、确认新stream的方案；尚不能认定保留encoder状态是唯一原因。不要在每次endpoint后无条件销毁stream，否则可能丢失已提交但未消费的音频。连续流utterance_id有间隔是无文字端点同样递增编号，并非六个非空final缺失。

17次真实启停控制均得到applied确认，本小样本最慢180.4ms；进程SIGINT后正常退出，实测0.569秒。

暂停在文件尾静音后进行，没有测量真实RKNN调用中途硬取消。现有契约在decode边界应用控制；进程退出须等待native返回。decode中的竞争另由可控C ABI回归验证，不能把替身耗时写成实际NPU取消时延。

本轮以同一生产源文件和asr.cmake构建ASR目标；未重建全部LLM/TTS目标。本轮未采集进程树资源峰值，不能沿用旧探针的PSS作为本生产节点的实测值。

## 交付与下一步

实现提交`68e2c1b`，位于ros-robot当前本地交付分支`codex/offline-agent-integration-20261021`；构建、配置、复现说明及本地工单在`.scratch/asr-rknn-integration/`。源码快照仅用于核对测量时哈希；后续维护以ros-robot生产文件为准。模型、录音、SDK和可执行文件均留在仓库外。

生产ROS ASR与YOLO的同场复测已完成，见下节。下一步在既有四进程组装中验证ASR final→暂停→播报结束→新流恢复链路。四进程、麦克风、扬声器、长会话与独立人工转写验收仍保留。默认不启声卡，不执行硬件动作。

## 生产ROS节点与YOLO同场复测

加载完成后由公共门禁同时放行：YOLO已完成三帧预热，ASR模型已加载；ASR采用同一stream连续六轮回放。ASR实际起始比门禁晚0.029秒，供音43.528秒，位于YOLO的45秒窗口内。

- YOLO：640×352、30fps，**1350/1350帧，零丢帧**；输入到检测完成的本轮样本p95为39.98ms。
- ASR：六个非空final；相对能量末端等待为1.688 / 1.804 / 1.983 / 2.123 / 1.603 / 1.846秒。逐条文字见原始结果，仍有连续流后段变化。
- 真实进程映射分别确认ASR加载私有2.2.0、YOLO加载系统库，两种runtime没有在同一进程混用。
- [共跑汇总](coexistence/summary.json) · [同步与命令](coexistence/coordination.json) · [实际库映射](coexistence/mapped-libraries.json) · [ROS识别事件](coexistence/speech/result.json) · [逐帧检测](coexistence/vision/events.jsonl)。

该p95是固定图片回放下本轮1350帧样本统计，不代表真实相机或长期分布；未计上游缩放/JPEG/web编码。共跑供音和识别事件不提供native计算计时，因此本轮不报告计算RTF或硬件利用率。

## 回归检查

配置校验12项通过；ASR公开ROS生命周期及Launch回归18项通过（含NPU参数传递、native进行中的关闭等待、迟到结果隔离和错误恢复）。后者以C ABI替身验证故障契约，与上面的真实RKNN识别分开记录。Ruff格式/lint、C++格式与diff检查通过。
