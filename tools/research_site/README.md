# 当前skill流程网站

只从当前 `studies/`、通用 `docs/`、归档说明和根README生成页面；不再读取旧ASR/NPU/YOLO记录或旧图表配置。旧看板源码已保存在仓库外归档快照中。

首页、选型、模型、接入、准备和证据入口直接复用当前Markdown，没有另一套硬编码旧结论。新旧schema与样本范围不混为统一榜单；原始实验HTML和文件原样复制。

```sh
python -m pip install -r tools/research_site/requirements.txt
python tools/research_site/build.py /tmp/edge-ai-current-site
python -m http.server 8080 --directory /tmp/edge-ai-current-site
```

输出目录必须不存在。生成器包含当前本地文件（包括未提交的新实验），跳过Python缓存；不读取仓库外模型、音频、SDK或归档压缩包。`data.json`只列本轮结果来源，不汇总不兼容指标。归档manifest可查，旧实验不再进入网站或索引。

本地构建检查生成的相对HTML目标。冻结上游文档片段中未附带的相对路径显示为来源说明；原始记录中的外部绝对路径/本机音频不代表已发布资源。生成不运行模型或机器人动作，也不发布远端。

`.github/workflows/pages.yml`仍在main推送后构建发布，当前本地改动尚未提交或推送，已上线旧站不会自动改变。
