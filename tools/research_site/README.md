# 静态 HTML 报告入口

GitHub Pages 只提供轻量报告列表，点击后直接打开独立 HTML，不套文档侧栏或展示 SOP。当前包含用户确认格式的语音单模块评测、资料选型、最小推理就绪。

```sh
python tools/research_site/build.py /tmp/edge-ai-report-site
python -m http.server 8080 --directory /tmp/edge-ai-report-site
```

输出目录必须不存在。构建只用 Python 标准库；报告列表在 `build.py` 的 `REPORTS` 中维护。独立报告原有相对路径保持不变，当前研究证据复制到 `evidence/`，不把 Markdown 转成网站页面。

主报告展示快照位于 `studies/voice-interaction/reports/2026-10-22-voice-screening/`。公开版不携带录音，试听仍使用 Mac 离线版；模型权重、录音与运行库均在 Git 外。冻结的实验 HTML 和测量结果不覆盖、不重新推理。当前 ros-robot 原生 tool_calls 尚未验证。

推送 main 后由 `.github/workflows/pages.yml` 自动构建并发布。
