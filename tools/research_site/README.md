# GitHub Pages 发布边界

`publication.json` 是唯一发布清单：逐文件记录来源、目标和 SHA256，另列报告首页与旧链接别名。构建器不遍历实验树、不复制原始结果、不注入额外导航。

```sh
python3 -m tools.edge_workflow.report /新的报告目录
python3 tools/research_site/build.py /新的站点目录
python3 -B -m unittest tools.research_site.test_build
```

正式报告生成器读取已保存的实验，不运行模型。更新正式发布内容时，在新目录生成并审阅，再把生成目录放到 `studies/voice-interaction/reports/`，使用 `report --publication-manifest` 生成白名单；提交报告与清单。生成器的 `generation.json` 记录输入身份，不发布该文件。

当前公开：正式 Qwen 对照总结、工作流各阶段示例、语音单模块结果，共三个目录入口。预留最终测试样本、内部数据报告、原始实验 JSON、录音、模型和设备明细均不自动发布。旧实验报告地址仅保留清单明确列出的别名，其他历史路径不保证继续可用。

构建拒绝来源哈希改变、目录穿越、重复目标、内部文件链接及缺失本地链接。网页须可离线阅读；外部资料链接可以跳转，但不得依赖远程脚本和图片。Pages 部署仍由主分支工作流控制，本次 PR 不部署。
