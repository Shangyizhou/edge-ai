# 研究网站（GitHub Pages）

正式入口：https://shangyizhou.github.io/edge-ai/

初学者先读`learn.html`（`studies/voice-interaction/learn.md`），量化支线见`quantization.html`，实际接入见`deployment.html`。三份正文直接由Markdown生成，避免维护两份长文；自动加入目录和阅读样式。

主要阅读顺序为概览 → 方案与选型 → 测试与对比 → 机器人中的表现；实验与证据为辅助入口，研究方法与进度页保留。详情从现有Markdown生成，图表由ASR复测JSON和INT8功能JSON生成，不运行模型。

## 构建与预览

建议Python3.12及独立虚拟环境：

```sh
python -m pip install -r tools/research_site/requirements.txt
python tools/research_site/build.py /tmp/edge-ai-site-preview
python -m http.server 8080 --directory /tmp/edge-ai-site-preview
```

打开 `http://localhost:8080`。输出目录必须不存在，避免覆盖已有结果。构建只读取Git已跟踪文档与证据；新增文档需要先git add。生成页面不提交Git。

## 怎样更新

- 当前建议：`index.html`；候选与选择：`solutions.html`；数据及解释：`models.html`、`app.js`；组合方案与验证：`integration.html`；研究方法：`process.html`。内容判断与对应Markdown一起更新。
- 模型图表：`build.py`读取冻结实验JSON，仅汇总qualification三轮，按供音方式分组，不混入screening。
- 新实验：先按SOP生成结构化数据，再明确更新数据源和解释；不把未测填成0，不比较不兼容场景。
- 详细文档：直接编辑`studies/`、`docs/`中的Markdown，自动生成阅读页及标题搜索。
- 布局和交互：`layout.html`、`style.css`、`app.js`。不用外部字体、CDN或服务端。

数据源见网站`data.json`的`sources`字段。页面附构建提交号；模型数值由历史测量而非实时监控得到。历史HTML、JSON和日志按跟踪文件原样复制，Markdown内部链接映射到网页；非发布文件链接到同一提交的GitHub源码。仓库外绝对源码路径只保留说明，不生成不可访问链接。

## 发布与检查

`.github/workflows/pages.yml`在相关内容推送main时构建、检查本地HTML文件链接并通过官方Pages Actions发布。首次需仓库Pages来源设置为GitHub Actions（build_type=workflow）。使用`github-pages`环境；只给部署任务pages和OIDC写权限。

发布artifact只含构建输出，无`.git`、`.local`、`.vscode`、凭据、外部模型、音频或SDK。`studies/`下已跟踪的公开证据随站点提供，原始内容不改写。构建仅检查文件目标，不校验外部网站或所有片段锚点。

本轮浏览器验证覆盖桌面1440px、手机390px、两种供音方式、指标切换、标题搜索、详情导航和手机横向溢出；截图和浏览器安装放在仓库外。
