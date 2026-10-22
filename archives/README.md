# 旧流程归档

按用户2026-10-22要求，当前仓库只展示按skill重新选型后的流程。旧语音实验、旧YOLO研究、历史量化/共跑结果、旧研究与平台说明、历史配置和旧看板页面移至仓库外，不再进入当前索引或网站。

- 归档目录：`/home/orangepi/local-data/edge-ai-archives/2026-10-22-pre-skill/`
- 整理前研究资料与工具快照（不是完整Git仓库备份）：该目录的 `workspace-snapshot.tar.gz`。
- 移出文件原样副本：该目录的 `files/`，按原相对路径保存。
- [逐文件清单与SHA256](2026-10-22-pre-skill.json)：区分移出文件和整理前备份，保留恢复所需原路径。

已归档1,373个旧文件（42,415,900字节），361个本轮原始流程文件逐项核对未变。[校验记录](verification-2026-10-22.json)。

操作先归档、逐项比对哈希，再移动；没有永久删除原始证据。当前四轮实验及本轮research目录的文件内容、原始报告和哈希保持不变。模型、音频、运行库、生产ros-robot和其他仓库不受此次整理影响。

## 恢复

先恢复到一个空的仓库外目录，核对清单后只取需要的历史路径，避免覆盖当前工作：

```sh
mkdir -p /tmp/edge-ai-history-restore
tar -xzf /home/orangepi/local-data/edge-ai-archives/2026-10-22-pre-skill/workspace-snapshot.tar.gz -C /tmp/edge-ai-history-restore
```

归档当前只在此板子的仓库外目录，不会随Git克隆传到Mac，也未上传远端。需要迁移时，另行复制压缩包和manifest；Git历史仍保留已经提交过的历史内容。本次未重写Git历史，未提交、推送或发布Pages。
