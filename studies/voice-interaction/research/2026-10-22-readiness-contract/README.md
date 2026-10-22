# 部署准备 skill 的 RK3566 实例

2026-10-22。新增本机skill `edge-model-prepare`：选型JSON → 准备请求 → 逐项证据检查 → 就绪JSON/离线HTML → 基准测试配置交接。入口位于 `/home/orangepi/.codex/skills/edge-model-prepare/SKILL.md`；本目录保存可复查的实例。

[新结论HTML](output/report.html) · [就绪JSON](output/readiness.json) · [输入请求](request.json) · [检查事实](checks.json)。证据目录仅含历史配置和元数据，没有权重、录音或可执行文件；绝对路径是历史来源，不可当作其它机器的安装目标。

**三个首选候选均为LOADED_ONLY，整体尚未达到READY_FOR_BENCHMARK。** 资产、运行库、构造/健康检查及配置核验已有证据；最小真实ASR解码、LLM生成和TTS合成均未执行。旧READY_FOR_SCREENING只代表当时的哈希/路径及加载范围，不能充当最小功能跑通。

这是对相同历史证据采用更明确的阶段定义，不是一次新实测。原[准备报告](../2026-10-22-runtime-preparation/README.md)保留不动。缺少的下一步是每模块一个固定样例的最小推理及原始输出记录，然后才能由新skill交接正式初筛。

skill采用短入口、按需契约与独立实例；默认优先复用或获取兼容二进制，必要时才从固定源码构建。包含输入转换器、证据检查和同源HTML渲染器，12项单元测试通过。当前只生成并安装在本机，未推送personal-skills仓库。
