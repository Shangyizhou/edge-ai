"""Passive four-step workflow report; no model imports or subprocesses."""

import html
from pathlib import Path


def review(output, title, sections, status="准备记录"):
    output = Path(output)
    assets = Path(__file__).resolve().parent / "assets"
    css = (assets / "workflow.css").read_text()
    js = (assets / "workflow.js").read_text()
    nav = "".join(
        '<a href="#s%d" class="navitem"><b>%s</b><small>查看本环节</small></a>'
        % (i, html.escape(label))
        for i, (label, body) in enumerate(sections)
    )
    body = "".join(
        '<section class="paper" id="s%d"><h2>%s</h2>%s</section>'
        % (i, html.escape(label), content)
        for i, (label, content) in enumerate(sections)
    )
    page = (
        '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'
        + html.escape(title)
        + "</title><style>"
        + css
        + '</style><header><div class="top"><b>Edge AI</b><span>'
        + html.escape(status)
        + '</span></div></header><div class="wrap"><div class="intro"><h1>'
        + html.escape(title)
        + '</h1><p>记录实际输入与检查范围；准备完成不代表模型质量通过。</p></div><div class="step-layout"><nav class="step-nav">'
        + nav
        + "</nav><main>"
        + body
        + "</main></div></div><script>"
        + js
        + "</script></html>"
    )
    (output / "report.html").write_text(page, encoding="utf-8")


def table(rows):
    return (
        '<div class="scroll"><table>'
        + "".join(
            "<tr>"
            + "".join("<td>" + html.escape(str(v)) + "</td>" for v in row)
            + "</tr>"
            for row in rows
        )
        + "</table></div>"
    )


def paragraph(value):
    return "<p>" + html.escape(str(value)) + "</p>"


def label(value):
    return {
        "frozen": "已冻结",
        "blocked": "待处理",
        "completed": "执行完成",
        "failed": "执行失败",
        "PASS": "通过",
        "FAIL": "失败",
        "UNKNOWN": "未知",
        "NOT_RUN": "未执行",
        "READY_FOR_BENCHMARK": "已可开始测评",
        "PARTIALLY_READY": "部分候选已就绪",
        "NOT_READY": "尚未就绪",
        "development": "开发诊断",
        "validation": "训练验证",
        "final": "最终测试",
        "native-tool-persona-v1": "工具调用、角色与聊天",
        "asr-transcription-v1": "语音识别",
    }.get(value, value)
