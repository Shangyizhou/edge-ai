# RK3566 benchmark / 研究 / 部署记录迁入

Status: claimed
Type: task
Target: git@github.com:Shangyizhou/edge-ai.git
Branch: codex/import-rk3566-benchmark-20261021

## Scope

将已经实际执行的端侧部署、benchmark、研究和首轮结果集中到edge-ai；后续实际部署按设备/日期持续记录。原ROS业务保持原状，不复制权重、录音、构建输出、凭据或附件PDF。

## Acceptance

- [x] benchmark/native wrapper/config/tests与原实现一致迁入。
- [x] 调研与首轮38案例原始数值、资源、失败日志、hash和HTML可追溯。
- [x] 已走通的CPU/NPU ASR、Summer、候选TTS、Qwen部署整理为手册。
- [x] Ruff、clang-format、公开接口测试、本地Markdown/HTML链接及资产排除检查通过。
- [ ] 读取目标远端已有内容后完成兼容整合并推送；不覆盖未知远端历史。

## Evidence

原来源分支最后提交becd9b8，完整来源见reports/rk3566/2026-10-21/migration-provenance.json。Git快照只含选定文本证据与报告，音频在外置完整run中保留。

2026-10-21：原GitHub账号停用；新生成独立SSH key并将公钥给用户，当前仓库core.sshCommand仅选择新key，不改原项目SSH行为。最近访问新key返回Permission denied(publickey)，等待用户在新账号添加。目标URL已由用户更正为Shangyizhou/edge-ai。
