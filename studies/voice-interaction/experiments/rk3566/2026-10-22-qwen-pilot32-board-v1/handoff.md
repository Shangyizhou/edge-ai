# Ticket12 → Ticket14

测量实现提交：`ed32c40`、`05132f0`；所有23次测量当时source已在各组source/冻结。新聚合view单独冻结root renderer `802d8722a2ee9420f7060ff2997e5d84ecc52645`（原修复681ec65），未改写旧measurement源码、逐例数据或旧生成HTML。

## 板端可复用资产

SSH alias：`orangepi-ts`。外部根目录 `/home/orangepi/.local/share/edge-ai/qwen-ticket12`。

- Python：`ROOT/venv/bin/python`，3.8.10；psutil7.2.2、jsonschema4.23.0、Pydantic2.10.6，CMake4.4.4。生产 `.venv` 未修改。完整 freeze 见 environment-after-build.txt。
- Runtime：`ROOT/build-e379/bin/llama-server`，0.7.0-dev build0，来源 `e3797b184d428c7a019362612b76971f60af6670`，GCC9.4.0 native Cortex-A55/ARM CPU，GGML_CPU_REPACK=OFF/OpenMP ON，无GPU。实际binary SHA256 `0cd701240687d518d7c67905d0c470f7cd4bf7fc89bffe6581e993a48cd88550`；各runtime.json另有共享库SHA/ldd；源码tar与来源见provenance/build-recipe。
- 原生模型：`ROOT/artifacts/qwen3-pilot32-q4_k_m.gguf`，396704704bytes，SHA256 `8a1e5584a9f8ee04b1e54afad217f2dbb6f4e31ab0a1d8832d8faadda92e7a9b`。仅pilot32，勿混成selected模型。
- 执行器：`ROOT/source/tools/qwen_lifecycle`；纯Registry：`ROOT/inputs/registry_validate.py` + 邻接ros-robot source snapshot，基于23ef814。目录均在仓库外。
- 当前最后配置：`ROOT/inputs/board-cache-q8-true-request-v1.json`。完整九Schema随suite展开保存，目录传9种工具，实际dev覆盖3种。

完整server argv（`ROOT`需展开为上述绝对路径）：

```text
ROOT/build-e379/bin/llama-server
-m ROOT/artifacts/qwen3-pilot32-q4_k_m.gguf
--host 127.0.0.1 --port 18082
-t 2 -tb 2 -c 2048 -np 1 -b 512 -ub 128 -ngl 0 --jinja
-ctk q8_0 -ctv q8_0 --no-repack --load-mode mmap --fit off -fa on
```

请求：`generation.cache_prompt=true, temperature=0, max_tokens=128, context_tokens=2048, timeout_seconds=600`；HTTP direct（禁环境proxy），stream usage启用，enable_thinking=false。新模型/完整sample需重新完整prompt+output预算。`--mmap`在本版本无效，旧失败原样保留。

`board_run`负责独立进程健康检查、完整token预算、动态monitor_pid、纯intake采集与finally清理。不要复制历史server PID。推荐在新source目录同步已集成工具，复制新request并改run_id/model/suite/new output；不覆盖旧runs或清理旧模型。

## 已实测结论

短7例：f16工具3/3、人设0/3、chat1/1；q8工具3/3、人设1/3、chat1/1。CPU加权49.12%/49.25%整机4核容量；PSS699.217/594.602MiB，实际RAM17.824%/15.157%；prefill中位6.731/6.715tok/s、decode中位2.504/3.290tok/s。Mac同Q4人设1/3，CPU f16姓名“小安”，q8与Mac“小沫”；不能外推稳定人设。

九目录缓存对照均通过expected：

| KV/cache | 例 | full/evaluated/cached | output/实际decode步数 | 首内容s | 完整有效调用s |
|---|---|---|---|---:|---:|
| f16/off | repeat_1 | 883/883/0 | 21/20 | 134.220 | 142.714 |
| f16/off | repeat_2 | 883/883/0 | 21/20 | 134.149 | 142.273 |
| f16/off | prefix_changed | 883/883/0 | 21/20 | 134.214 | 142.395 |
| f16/on | repeat_1 | 883/883/0 | 21/20 | 134.524 | 143.057 |
| f16/on | repeat_2 | 883/1/882 | 21/20 | 5.019 | 13.431 |
| f16/on | prefix_changed | 883/12/871 | 21/20 | 9.486 | 17.872 |
| q8/on | repeat_1 | 883/883/0 | 21/20 | 159.960 | 166.290 |
| q8/on | repeat_2 | 883/1/882 | 21/20 | 3.565 | 9.682 |
| q8/on | prefix_changed | 883/12/871 | 21/20 | 6.029 | 11.940 |

数值应以analysis.json逐例原生字段为准。decode速率按n_gen-1步数，首token来自prefill末logits；不能把输出总数除以decode时间重算，也不能把883当成warm实际prefill来报告千token/s。缓存省去前缀计算的等待，不是模型吞吐提高十倍。

九目录q8/on PSS565.574MiB=14.417%实际RAM；f16/on700.074MiB=17.846%；上下文/图形状不同，勿照搬短7例内存到此组。q8 cold更慢、warm/prefix更快，机制未归因。最高已观测thermal zone55C；实际采样间隔中位约269–274ms（200ms等待+采样自身成本）。短q8组host swap-in16KiB，九目录off与q8/on各4KiB，swap-out均0；均为整机，不能归因模型。

## 后续配置边界

优先有证据的q8KV+cacheon，先在selected模型做独立准备/开发冒烟，再冻结并完整执行全部132条final。不可删样本；不能只用exactrepeat的9.68秒预算全部测试。新user token量、输出步数、冷首例、纯Registry启动、动态prefix匹配均影响等待。保留full/evaluated/cached/output/native timing每例来源；不得强制复用不匹配前缀。

所有模型/queue/build owned进程已退出；结束时根盘可用5543056KiB、MemAvailable约3003796KiB，swap-used744856KiB；见device-after.txt。没有杀未知进程，没有改生产venv/代码，没有动作、ROS、旧C++、GPU租赁或发布行为。
