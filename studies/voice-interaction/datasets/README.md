# 数据版本与恢复

这里长期维护数据的身份、来源、划分和恢复方法。模型权重、录音、完整训练数据及备份包保存在 Git 外。Git 中保留适合公开的小型评测输入和历史证据；公开网页另有白名单，不等同于整个仓库。

## 目录与职责

- `catalog.json`：数据版本入口。同一版本冻结后不覆盖；改样本、标签或划分就创建新版本。
- `<数据名>/<版本>/manifest.json`：来源、样本数、用途、文件 SHA256、存储位置及隔离限制。
- `backups.json`：已执行的双设备备份与恢复验证记录。它不是异地灾备保证。
- `../experiments/index.json`：从保存的结果重建的实验索引，连接数据版本、请求配置、代码快照与结果。不补造历史缺失字段。
- `../reports/`：可重新生成的报告。排版变更不产生新的数据版本或测量结果。

当前四组数据：新工作流的合成工具数据、原正式微调训练数据、已用于历史验收的132条套件、三个 ASR 输入。历史132条已被开发过程观察，不能作为未来未见测试集；新预留24条只作数据治理检查，没有执行模型推理。共享文件系统也不构成安全隔离。

## 使用顺序

先定义任务和评分规则，再按语义来源组划分 Train/Validation/Development/Final。Train 只接收训练与验证交付物；开发评测可以反馈错误类型，最终验收样本不能反复用于调参。Prepare 检查模型和运行环境；Benchmark 使用冻结输入与评分器。每轮记录新实验，失败也保留。

`repo://` 从仓库根目录解析；`edge-ai://` 从 `EDGE_AI_ASSET_ROOT` 解析，默认 `~/.local/share/edge-ai`；`ssh://` 是远端定位记录，不自动下载。迁移设备时修改外部根目录或增加副本记录，保持数据内容哈希不变。目录路径不代表身份，SHA256 才用于校验。

```sh
python3 -m tools.edge_workflow.registry verify
python3 -m tools.edge_workflow.registry index studies/voice-interaction/experiments/index.json
python3 -m tools.edge_workflow.backup create /外部存储/datasets-v2.tar.gz
python3 -m tools.edge_workflow.backup restore /外部存储/datasets-v2.tar.gz /新的恢复目录 --sha256 实际备份哈希
```

默认校验和备份跳过预留最终集；经授权的保管备份可加 `--include-final`。恢复只写新的目录，并检查整包和每个成员；不会覆盖现有数据。恢复后按备份索引的逻辑 URI 安装到新的存储根目录，再重新运行校验。Git 中的 manifest 与外部备份包共同完成恢复；只克隆仓库不能恢复全部数据。

## 长期保留与清理

长期保留来源及许可说明、划分依据、冻结配置、原始结果、代码快照、数据清单和重要决策。模型大文件及音频用外部存储和校验身份管理。当前先使用目录、JSON 清单和验证命令，不引入 DVC/MLflow 服务。

原实验里被哈希清单引用的旧 HTML 也属于历史证据，保留原样。重复的总结、原型不作为 Pages 入口；它们可以在可验证归档之后退出当前视图。不要依据日期批量删除实验。隐私录音与硬件明细不进入 Pages。Git 历史中已有的内容不会因发布白名单而变成私密资料。

## 已迁移到 Hugging Face 的工作流实验

2026-10-23的两轮工作流原始记录共917个文件，已从代码仓库移出，并校验删除对应的本地展开副本。正式HTML、工具代码、数据版本和结果索引保留。完整记录位于私有仓库 `Shangyizhou/xiaomo-robotics-data`；固定版本、包哈希见 [远端归档清单](remote-archive.json)。需要有权限的HF账号，先运行 `hf auth login`。

```sh
# 使用安装有huggingface_hub的Python，恢复到Git外的本地目录
python -m tools.edge_workflow.archive
# 恢复完成后可以重新生成报告
python -m tools.edge_workflow.report /新的报告目录
```

默认恢复到 `~/.local/share/edge-ai/archive-cache/20261023-v1`，不写回Git目录，不覆盖已有恢复目录。日常浏览已提交HTML不需要下载归档。数据清单中的新工作流输入也指向此恢复根目录；未恢复时校验会报告缺失，这是按需下载的预期状态。

移除记录是后续提交：原PR分支的前序Git提交仍含这些文件，本次不会强推或重写历史。私有HF下载需要认证，公开Pages报告不依赖私有下载才能浏览。
