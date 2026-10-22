# Qwen3 最小 LoRA Q4 · RK3566 独立验证

工单 #12。沿用 #10 的32微步/4次优化器更新试点 Q4_K_M，只验证独立部署、原生工具 intake 和 Linux 采集。[离线阶段 HTML](report.html) · [KV准备交付](prepare/report.html) · [缓存组合准备](prepare-cache/report.html) · [派生指标](analysis.json)。

本轮5个独立服务轮次、23次开发推理：两组各7例（3工具、3人设、1聊天），三组各3次 volume_set 缓存对照。共8条不同用户输入，重复执行不当成独立材料。九工具目录已原样传入，实际调用只覆盖 start_camera、volume_set、play_music 三种；其余六种不据此宣称通过。没有读取 sealed final，更未执行处理器、旧 C++、ROS 或硬件动作。

## 当前结论

同一试点Q4在两种KV均可原生生成并经JSON/原始Schema/同源Registry接收。短组工具均3/3、聊天均1/1；人设 f16 为0/3，q8_0 为1/3。f16姓名输出“小安”，q8_0输出“小沫”；Mac同Q4为1/3。固定规则结果保留，不能将试点人设推广为稳定能力。

| 组 | CPU/4核容量 | 峰PSS MiB / 实际RAM | prefill中位 tok/s | decode中位 tok/s | 工具预期 | 人设规则 |
|---|---:|---:|---:|---:|---:|---:|
| f16-e379-v2 | 49.12% | 699.22 / 17.82% | 6.731 | 2.504 | 3/3 | 0/3 |
| q8-e379-v2 | 49.25% | 594.60 / 15.16% | 6.715 | 3.290 | 3/3 | 1/3 |
| cache-false-v2 | 49.07% | 670.42 / 17.09% | 6.806 | 1.801 | 3/3 | 0/0 |
| cache-true-v2 | 47.68% | 700.07 / 17.85% | 2.522 | 1.756 | 3/3 | 0/0 |
| cache-q8-true-v1 | 48.54% | 565.57 / 14.42% | 3.958 | 2.692 | 3/3 | 0/0 |

缓存组prefill中位数来自不同实际评估量，不能据此跨模式排名模型速度。三组九目录对照的9次调用均与预期参数一致。缓存减少重复前缀计算的等待，不能解释成模型吞吐增加十倍；完整输入、实际prefill与原生cached计数分别保留。

| 组 / 例 | 完整输入 | 实际prefill | 原生cached | 输出 / decode步数 | 首内容 s | HTTP s | 完整有效调用 s |
|---|---:|---:|---:|---:|---:|---:|---:|
| cache-false-v2 / repeat_1 | 883 | 883 | 0 | 21 / 20 | 134.220 | 140.876 | 142.714 |
| cache-false-v2 / repeat_2 | 883 | 883 | 0 | 21 / 20 | 134.149 | 140.819 | 142.273 |
| cache-false-v2 / prefix_changed | 883 | 883 | 0 | 21 / 20 | 134.214 | 140.879 | 142.395 |
| cache-true-v2 / repeat_1 | 883 | 883 | 0 | 21 / 20 | 134.524 | 141.209 | 143.057 |
| cache-true-v2 / repeat_2 | 883 | 1 | 882 | 21 / 20 | 5.019 | 11.975 | 13.431 |
| cache-true-v2 / prefix_changed | 883 | 12 | 871 | 21 / 20 | 9.486 | 16.366 | 17.872 |
| cache-q8-true-v1 / repeat_1 | 883 | 883 | 0 | 21 / 20 | 159.960 | 164.426 | 166.290 |
| cache-q8-true-v1 / repeat_2 | 883 | 1 | 882 | 21 / 20 | 3.565 | 8.220 | 9.682 |
| cache-q8-true-v1 / prefix_changed | 883 | 12 | 871 | 21 / 20 | 6.029 | 10.487 | 11.940 |

建议 #14 从有真实准备证据的 q8_0 KV + cache_prompt=true 组合冻结配置，在新 selected 制品上先完成独立加载/开发冒烟，再完整执行全部132条 final；不得删样本。q8缓存冷首例比f16更慢，暖/变更前缀更快；不要只拿重复请求预算全部final，更不能根据这几例宣称P95。GGML_CPU_REPACK=OFF 是保守构建，不代表RK3566最优速度或硬件上限。

## 身份、准备与失败

- 设备为 Rockchip RK3566 OPi3B、4个Cortex-A55、Ubuntu20.04 / Linux5.10.160、glibc2.31、ondemand；实际MemTotal4017020KiB（4113428480字节）。[复核](device-before.txt)、[OS/ABI](os-abi.txt)、[结束状态](device-after.txt)。旧模型、旧运行库、生产源码均保留。
- GGUF 396704704字节，SHA256 `8a1e5584a9f8ee04b1e54afad217f2dbb6f4e31ab0a1d8832d8faadda92e7a9b`。[Mac导出来源](../../mac/2026-10-22-qwen-lora-export-pilot-v1/README.md)、[base清单](base-artifact-manifest.json)。权重、源码SDK、构建和隔离venv在仓库外。
- 先复用22cd28d：默认direct I/O/repack配置加载时SIGABRT；关闭repack并改mmap后health ready，但原始Schema的 `\S` 在工具grammar转换时HTTP400。[诊断顺序](attempts.json)、[原失败](failed-runs/)。一次端口探测TIME_WAIT失败也保留并修复，未启动模型。
- 独立构建同Mac的 `e3797b184d428c7a019362612b76971f60af6670`，GCC9.4.0、CPU native、REPACK OFF、OpenMP、无GPU；系统CMake3.16嵌套UI脚本失败，隔离venv CMake4.4.4修复。[构建配方](build-recipe.json)、[成功日志](build-e379-v2.log)、[首构建失败](build-e379-cmake316-failed.log)。官方ARM发布工作流与板端ABI的选择依据见配方，未声称所有预编译包不兼容。
- 新版已移除 `--mmap`，需 `--load-mode mmap`。首次四组均参数退出，原失败目录和queue退出记录保留；随后新request、新run目录重跑。
- e379接受原Schema，但明确警告不支持该非锚定pattern、grammar接受任意字符串。原Schema没有改写，JSON Schema和Registry后置纯校验仍严格执行。[计数来源与SHA](runtime-counter-source.json)、[九Schema一致性](board-schema-check.json)、[业务快照](business-source/registry_validate.py)。

## 测量口径与复跑

服务仅绑定127.0.0.1，2线程、单槽、2048上下文、512 batch /128 microbatch、FA on、温度0、最大输出128。完整提示词加输出预算逐例检查；九目录883+128=1011tokens，未截断。f16/q8、cacheoff/on分组执行，顺序记录在queue JSON。

权重SHA校验在启动前顺序读取文件，页缓存可能已预热；加载窗为启动服务至health ready，排除哈希，不能称冷盘启动。推理资源窗覆盖请求到纯intake结束，但CPU/PSS监控实际模型服务进程树，不将HTTP客户端伪装成模型进程。CPU除以实际4核容量；PSS为采样峰而非kernel高水位，200ms是调度等待间隔，实际间隔包含采样成本并保留原始时间戳。整机可用内存、swap使用/换入/换出及可读thermal-zone保存在逐例events；swap计数属整机，不能归因单模型。

完整input来自native usage；实际prefill为timings.prompt_n；缓存数直接来自native字段，未用差值猜测。predicted_n是输出总数，decode原生速率按n_gen-1步数计算，首token来自prefill末logits。首内容含HTTP与原生解析器缓冲，完整有效调用另含JSON/Schema/纯Registry子进程启动和校验；两者均非完整机器人交互。

`python -m tools.qwen_lifecycle.board_run NEW_REQUEST NEW_OUTPUT` 是板端入口，亦可由edge-model-benchmark dispatcher调用。复制冻结请求时使用新run_id和新输出目录，按实际路径调整model/suite/validator；不要覆盖历史目录。完整隔离路径、argv、来源SHA和下游建议见 [handoff](handoff.md)。

Mac Q4对照沿用T10原结果与证据：同7开发输入/同权重，Metal、声明context8192、默认未量化KV；板端CPU/context2048/KV/FA等不同，是部署方案对照，不能当纯后端或量化归因。Mac RSS、MLX分配和Linux PSS不等价，不相加。采集时source保留在每组source/；本页新view采用独立冻结renderer802d872，未追溯改写measurement快照或旧HTML。

静态引用、转义、嵌入JSON/ZIP、源哈希和响应式CSS检查见 [QA](qa.json)。浏览器file://策略拒绝后未尝试替代预览，视觉交互未验证。准备通过只覆盖已注明的加载/开发边界，生产集成、完整目录和共跑验收均未完成。
