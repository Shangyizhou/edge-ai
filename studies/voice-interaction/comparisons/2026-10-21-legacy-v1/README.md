# 历史评测只读视图

[静态页面](report.html) · [结果JSON](results.json) · [数据口径](../../../../docs/methodology/result-format.md)。由原始记录只读转换，不重新推理，不改变历史实验状态。

来源为RK3566首轮ASR/TTS/Qwen、流式ASR、ROS ASR及已有YOLO实验中的60条可映射result.json。源码/模型hash等细节通过evidence链接回原文件；原始共跑子模块事件仍在对应源目录。本视图仅覆盖各批次根目录及其直接case，以及显式指定的ROS共跑ASR；嵌套诊断矩阵仍保留在原目录，未递归混入。转换器、模板及schema身份在JSON的producer中。

所有条目均为legacy，没有新版比较键。不同任务、适配器、场景与单模块/共跑/应用范围分开展示；不生成加速倍率或总分。未知模型精度、MemTotal、阶段资源、可靠转写等保留null或未评估；旧模型一致输出不计算CER。历史计时范围见各条metrics.scope，不能据同名RTF直接排名。

当前新协议的完整试点见[ASR v1](../../experiments/rk3566/2026-10-21-asr-lite-v1/results.md)。后续补测以新实验追加，不回填为旧实验已经遵循新协议。
