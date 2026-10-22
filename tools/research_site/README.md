# 静态 HTML 报告入口

GitHub Pages 只提供轻量报告列表，点击后直接打开独立 HTML，不套文档侧栏或展示 SOP。当前包含用户确认格式的语音单模块评测、资料选型、最小推理就绪。

```sh
python tools/research_site/build.py /tmp/edge-ai-report-site
python -m http.server 8080 --directory /tmp/edge-ai-report-site
```

输出目录必须不存在。构建只用 Python 标准库；报告列表在 `build.py` 的 `REPORTS` 中维护。独立报告原有相对路径保持不变，未被排除的研究证据复制到 `evidence/`，不把 Markdown 转成网站页面。

主报告展示快照位于 `studies/voice-interaction/reports/2026-10-22-voice-screening/`。公开版不携带录音，试听仍使用 Mac 离线版；模型权重、录音与运行库均在 Git 外。冻结的实验 HTML 和测量结果不覆盖、不重新推理。Qwen 独立原生 tool_calls 试点与量化对照已执行；ros-robot 生产接入及完整交互尚未验收。

推送 main 后由 `.github/workflows/pages.yml` 自动构建并发布。

对外报告入口使用 `reports.html`；根首页也保留报告列表，避免旧根页面缓存影响新入口。

发布时，`report_navigation.py` 为报告与入口添加右侧固定导航：执行流程、章节锚点与返回顶部；移动端为顶部可折叠目录。只修改构建副本，不改写原始实验 HTML 或上游来源快照。


Qwen 新报告先离线交付。`build.py` 的 `UNPUBLISHED_DIRECTORIES` 是仓库根目录相对路径的静态导出排除列表：整个 Mac 实验目录、板端 `2026-10-22-qwen-pilot32-board-v1`、研究计划 `2026-10-22-mac-qwen-plan`、最终实验 `final/2026-10-22-qwen-final132-v1`。构建在遍历这些目录前跳过，HTML、JSON、Markdown 与原始来源均不复制；未来最终实验目录即使尚不存在也受此规则覆盖。新增报告公开需要后续单独的发布决定，并明确修改对应排除项；报告列表不是发布白名单。

现有 main 推送触发规则仍可重建并发布已有网站，手动发布入口也保持原样；上述 Qwen 离线目录不会因此进入发布产物。此规则不改写冻结证据或现有三个报告入口。

静态导出检查：`python -m unittest discover -s tools/research_site -p 'test_*.py'`。
