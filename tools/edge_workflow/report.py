"""Generate curated public reports from frozen records, without model runtimes."""

import argparse
import hashlib
import html
import json
import re
import shutil
from pathlib import Path

from .archive import CACHE
from .presentation import paragraph, review, table

ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / "studies/voice-interaction"


def build(output, root=ROOT):
    output = Path(output)
    if output.exists():
        raise FileExistsError("use a fresh report output directory")
    output.mkdir(parents=True)
    study = Path(root) / "studies/voice-interaction"
    mac = study / "experiments/mac/2026-10-23-workflow-pilot-v1"
    board = study / "experiments/rk3566/2026-10-23-workflow-validation-v1"
    sources = {}
    created = []

    def evidence(path):
        if path.is_file():
            return path
        restored = CACHE / path.relative_to(root)
        if not restored.is_file():
            raise FileNotFoundError(
                "Restore archived inputs first: python -m tools.edge_workflow.archive"
            )
        return restored

    def load(path):
        actual = evidence(path)
        sources[str(path.relative_to(root))] = hashlib.sha256(
            actual.read_bytes()
        ).hexdigest()
        return json.loads(actual.read_text())

    def emit(name, title, sections):
        folder = output / name
        folder.mkdir(parents=True)
        review(folder, title, sections)
        created.append(folder / "report.html")
        return name + "/report.html"

    def links(entries):
        return "".join(
            '<p><a href="'
            + html.escape(href)
            + '">'
            + html.escape(label)
            + "</a></p>"
            for href, label in entries
        )

    # All links name curated sibling pages, never file:// or raw experiment trees.
    data = load(mac / "data-isolation-audit.json")
    training = load(mac / "train32/results.json")
    export = load(mac / "export/results.json")
    asr = load(board / "asr-inference-summary.json")
    emit(
        "workflow",
        "端侧模型工作流使用实例",
        [
            (
                "这一轮验证了什么",
                paragraph(
                    "这是32微步技术试跑，用于检验数据、环境、训练、导出和测评的交接。上一轮768微步模型仍为独立研究结果，两者不混为同一轮。"
                )
                + table(
                    [
                        ("流程交接", "完成"),
                        ("试跑模型质量", "仍有失败，不晋升主候选"),
                        ("新最终测试", "未运行"),
                        ("机器人动作与共跑", "未执行"),
                    ]
                ),
            ),
            (
                "先准备任务与数据",
                paragraph(
                    "先确定任务和评分，再按来源组划分用途；训练数据与评测数据各自准备，可以审阅后停止。"
                )
                + links(
                    [
                        ("../workflow-data/report.html", "数据与代表样本"),
                        ("../workflow-evaluation/report.html", "评测准备"),
                    ]
                ),
            ),
            (
                "运行与学习",
                paragraph(
                    "准备推理环境并完成最小真实推理；先测原始模型，只有必要时才训练。训练与导出各自管理执行环境。"
                )
                + links(
                    [
                        ("../workflow-selection/report.html", "选型与后端"),
                        ("../workflow-readiness/report.html", "就绪检查"),
                        ("../workflow-training/report.html", "训练曲线"),
                        ("../workflow-export/report.html", "合并与量化"),
                    ]
                ),
            ),
            (
                "根据实测决定",
                paragraph(
                    "最终候选和配置确定后才做最终测评；诊断集可以反馈改进。此次保留原主候选，没有自动延长训练。"
                )
                + links(
                    [
                        (
                            "../workflow-benchmark/report.html",
                            "Qwen与ASR实际结果",
                        ),
                        ("../qwen-main/report.html", "上一轮独立研究结果"),
                        ("../../reports.html", "返回报告列表"),
                    ]
                ),
            ),
        ],
    )
    emit(
        "workflow-selection",
        "选型实例：Qwen 与香橙派",
        [
            (
                "建议先验证什么",
                paragraph(
                    "历史研究优先验证Qwen3-0.6B原生工具调用。先测原始模型，不把微调当成必选步骤。研究建议与后续实测分别成立。"
                ),
            ),
            (
                "设备与限制",
                table(
                    [
                        ("Mac M5 / 16GB统一内存", "用于试跑、按需训练和转换"),
                        (
                            "Orange Pi 3B / RK3566 / 约3.83GiB系统内存",
                            "部署候选以ARM CPU验证",
                        ),
                    ]
                )
                + paragraph(
                    "磁盘与可用内存是运行时状态，不能拿历史快照作为当前预算。"
                ),
            ),
            (
                "框架与后端",
                table(
                    [
                        ("Mac试跑/训练", "MLX-LM", "Apple GPU / Metal"),
                        ("Mac GGUF检查", "llama.cpp", "Metal"),
                        ("香橙派本轮路线", "llama.cpp", "ARM CPU"),
                    ]
                )
                + paragraph(
                    "RK3566的普通RKNN支持不能证明Qwen可在其NPU运行。历史补充核查的RKLLM官方平台列表没有RK3566；新部署仍须核对当次版本。"
                )
                + links(
                    [
                        (
                            "https://github.com/airockchip/rknn-llm",
                            "RKLLM官方支持列表",
                        )
                    ]
                ),
            ),
            (
                "下一步",
                paragraph("用准备和测评证明兼容与质量；需要时才训练或量化。")
                + links([("../workflow/report.html", "回到工作流")]),
            ),
        ],
    )
    examples = load(mac / "data-review-examples/examples.json")
    example_html = "".join(
        "<details><summary>"
        + html.escape(e["label"])
        + "</summary>"
        + paragraph(e["user"])
        + "<pre>"
        + html.escape(json.dumps(e["target"], ensure_ascii=False, indent=2))
        + "</pre></details>"
        for e in examples
    )
    emit(
        "workflow-data",
        "数据准备：先分用途，再制作样本",
        [
            (
                "学习和测试的目标",
                paragraph(
                    "本轮使用合成工具调用、角色与聊天样本验证技术链路。下面只展示训练/验证代表样本，不公开新最终题目。"
                )
                + example_html,
            ),
            (
                "数据规模",
                table(
                    [
                        ("训练", data["counts"]["train"]),
                        ("验证", data["counts"]["valid"]),
                        ("开发诊断", data["counts"]["development"]),
                        ("预留最终", data["counts"]["final"]),
                        ("来源组", data["groups"]),
                    ]
                ),
            ),
            (
                "分组与检查",
                paragraph(
                    "分组先于扩写；声明组与归一化完全重复检查通过，不代表所有语义近重复、基座训练污染或访问隔离已排除。格式检查与标签语义复核分别成立。"
                ),
            ),
            (
                "冻结与复用",
                paragraph(
                    "实验引用数据版本，修改数据建立新版本。原件和备份由数据清单追踪，HTML不是数据权威；已观察最终例不能重新称为未见测试。"
                )
                + links([("../workflow/report.html", "回到工作流")]),
            ),
        ],
    )
    plan = load(mac / "frozen-evaluation/plan.json")
    emit(
        "workflow-evaluation",
        "评测准备：把问题写成可执行方案",
        [
            (
                "比较的问题",
                paragraph(
                    "比较原始模型与技术adapter的工具调用、角色和普通聊天；格式、意图与设备动作分开。"
                ),
            ),
            (
                "数据和评分",
                table(
                    [
                        ("开发诊断", plan["samples"]),
                        (
                            "工具调用",
                            "原生、JSON、Schema、Registry、精确工具参数",
                        ),
                        ("角色", "自动规则仅诊断；完整语义审核另计"),
                        ("聊天", "是否误调用工具"),
                    ]
                ),
            ),
            (
                "测量口径",
                paragraph(
                    "有效调用等待计到纯接收校验；失败保留在质量分母。输入处理与生成速度分开；Mac RSS不与MLX分配相加，Linux PSS另列。"
                ),
            ),
            (
                "预算和停止",
                paragraph(
                    "本轮单阶段上限600秒。准备模式不执行模型，冻结计划后再核对环境并测量。"
                )
                + links([("../workflow/report.html", "回到工作流")]),
            ),
        ],
    )
    emit(
        "workflow-readiness",
        "准备：证明候选模型能真实运行",
        [
            (
                "复用已有环境",
                paragraph(
                    "核对模型、框架、后端与执行入口；匹配时复用，改变制品或设备时重查受影响部分。"
                ),
            ),
            (
                "最小真实推理",
                paragraph(
                    "Mac基座完成一次真实工具请求。新GGUF制品在独立冒烟后再进入正式12例回归，下载、编译和健康接口不代替生成。"
                ),
            ),
            (
                "目标设备兼容",
                paragraph(
                    "香橙派ARM CPU真实运行；最后的准备入口与只读预检也在板端Python 3.8实际验证。Mac解析成功不代表板端兼容。"
                ),
            ),
            (
                "交给测评",
                paragraph(
                    "交付实际候选、就绪记录和冻结配置。最小推理只证明运行，不证明整体质量。"
                )
                + links([("../workflow/report.html", "回到工作流")]),
            ),
        ],
    )
    curve = mac / "training-report/curves/pilot32.svg"
    target = output / "workflow-training/curve.svg"
    target.parent.mkdir(parents=True)
    shutil.copyfile(evidence(curve), target)
    sources[str(curve.relative_to(root))] = hashlib.sha256(
        evidence(curve).read_bytes()
    ).hexdigest()
    created.append(target)
    # The curve folder already exists, so emit the page without creating it twice.
    train_sections = [
        (
            "为什么只跑32微步",
            paragraph(
                "目的为训练/制品交接可行性，不是充分学习或主候选优化。基座为官方Qwen3-0.6B，新建adapter，未延续上轮adapter。"
            ),
        ),
        (
            "配置与成本",
            table(
                [
                    ("训练数据", 60),
                    ("验证数据", 18),
                    (
                        "微步/优化器更新",
                        str(training["microsteps"])
                        + " / "
                        + str(training["optimizer_updates"]),
                    ),
                    ("学习率", training["config"]["learning_rate"]),
                    ("LoRA rank", 8),
                    ("全阶段秒", round(training["wall_seconds"], 2)),
                    (
                        "MLX峰分配GB",
                        round(training["mlx_peak_allocated_bytes"] / 1e9, 2),
                    ),
                ]
            ),
        ),
        (
            "真实曲线",
            '<img src="curve.svg" alt="实际训练、验证损失与学习率曲线" style="width:100%;height:auto">'
            + paragraph(
                "只画实际回调，不插补任务分数；完整样本最大926tokens，监督前缀通过，无截断。低loss不等于角色或工具任务通过。"
            ),
        ),
        (
            "选择与停止",
            paragraph(
                "该adapter仍有能力失败，仅作为技术制品继续验证导出；未晋升生产候选，未开启最终测评。"
            )
            + links([("../workflow/report.html", "回到工作流")]),
        ),
    ]
    review(target.parent, "32微步训练技术试跑", train_sections)
    created.append(target.parent / "report.html")
    stages = [
        (
            x["operation"],
            round(x["wall_seconds"], 3),
            "执行完成" if x["status"] == "completed" else x["status"],
        )
        for x in export["stages"]
    ]
    emit(
        "workflow-export",
        "导出：合并、转换与量化分别记录",
        [
            (
                "输入与目的",
                paragraph(
                    "本次32微步adapter与官方基座进入新的输出目录，原模型保留。文件名不是谱系证据，准确来源由请求与制品身份绑定。"
                ),
            ),
            (
                "执行成本",
                table([("操作", "墙钟秒", "状态")] + stages)
                + paragraph(
                    "转换成本不包含未记录的端到端开销，也不是推理速度。"
                ),
            ),
            (
                "文件与质量",
                table(
                    [
                        (
                            "F16 GGUF 字节",
                            export["artifacts"]["f16"]["total_bytes"],
                        ),
                        (
                            "Q4 GGUF 字节",
                            export["artifacts"]["q4_k_m"]["total_bytes"],
                        ),
                    ]
                )
                + paragraph(
                    "文件大小不是推理内存。12例转换回归分项计数相同，但仍有失败，不能宣称量化无损。"
                ),
            ),
            (
                "下一步",
                paragraph(
                    "新制品做就绪检查和相同输入的测评，不因转换成功而替换旧主候选。"
                )
                + links([("../workflow/report.html", "回到工作流")]),
            ),
        ],
    )
    quality = []
    for folder, label in [
        (mac / "base-development", "Mac 原始模型 / 24例"),
        (mac / "adapter-development", "Mac 32微步 / 24例"),
        (board / "board-base", "香橙派 原始Q4 / 12例"),
        (board / "board-pilot", "香橙派 32微步Q4 / 12例"),
    ]:
        d = load(folder / "results.json")
        q = d["summary"]
        quality.append(
            (
                label,
                str(q["native_calls"]) + "/" + str(q["tool_samples"]),
                str(q["tool_expected_behavior"])
                + "/"
                + str(q["tool_samples"]),
                str(q["persona_valid"]) + "/" + str(q["persona_samples"]),
            )
        )
    asr_rows = [
        (
            "混合INT8" if "int8" in x["candidate"] else "FP32",
            round(x["compute_rtf_median"], 3),
            round(x["cpu_capacity_percent"], 2),
            round(x["peak_pss_mib"], 2),
        )
        for x in asr["cases"]
    ]
    emit(
        "workflow-benchmark",
        "测评：Qwen和ASR使用不同指标",
        [
            (
                "受控范围",
                paragraph(
                    "每项比较声明数据与控制条件。Mac与板端的缓存/KV不同，是部署组合对照，不是纯硬件加速倍率。"
                ),
            ),
            (
                "Qwen质量",
                table(
                    [("方案", "工具格式", "工具及参数精确", "角色自动规则")]
                    + quality
                )
                + paragraph(
                    "角色列只作诊断。聊天分别4/4和1/1无误调用，不能据此宣布自然对话已验收。"
                ),
            ),
            (
                "ASR与资源",
                table(
                    [
                        (
                            "精度",
                            "计算RTF中位数",
                            "推理窗CPU% / 四核",
                            "峰PSS MiB",
                        )
                    ]
                    + asr_rows
                )
                + paragraph(
                    "每精度3条已知录音；各2条公开参考共66字符、30字符错误。机器人命令用户确认另列，RTF含尾部补零计算、不含加载与实时等待。"
                ),
            ),
            (
                "失败与决定",
                paragraph(
                    "ASR首轮完成3条推理后报告器失败，修正后在新目录完成6条正式请求，旧失败保留。板端Qwen冷首次约169秒。流程完成不代表模型质量达标，不自动加长训练。"
                )
                + links([("../workflow/report.html", "回到工作流")]),
            ),
        ],
    )
    final = load(
        study
        / "experiments/final/2026-10-22-qwen-final132-v1/final-summary.json"
    )
    rows = []
    for run in final["runs"]:
        c = next(x for x in run["cohorts"] if x["cohort"] == "combined")
        label = ("香橙派" if "board" in run["run_id"] else "Mac") + (
            " 微调Q4" if "selected" in run["run_id"] else " 原始Q4"
        )
        rows.append(
            (
                label,
                str(c["native_calls"]) + "/" + str(c["tool_samples"]),
                str(c["tool_expected_behavior"])
                + "/"
                + str(c["tool_samples"]),
                str(c["contextual_persona_pass"])
                + "/"
                + str(c["persona_samples"]),
            )
        )
    emit(
        "qwen-main",
        "Qwen主实验：768微步模型的独立测评",
        [
            (
                "与工作流试跑的区别",
                paragraph(
                    "本页来自上一轮300训练/60验证、768微步模型的正式独立集。当时每组132例，两模型两设备共528正式请求；不是本轮32微步的结果。"
                ),
            ),
            (
                "格式与能力",
                table(
                    [
                        (
                            "方案",
                            "工具原生格式",
                            "工具与参数精确",
                            "角色上下文审阅",
                        )
                    ]
                    + rows
                ),
            ),
            (
                "资源与边界",
                paragraph(
                    "板端微调Q4工具有效调用P50/P95约11.57/27.33秒，峰PSS约600.30MiB、CPU约46.04%整机四核容量；新服务/KV冷首例约174.27秒。角色审阅来自assistant，无人工验收；格式通过不等于语义、动作或产品验收。"
                ),
            ),
            (
                "结论与后续",
                paragraph(
                    "角色仍21/36，保留失败。该集已观察，未来只能作为历史/回归，不能用于调参后再称未见。机器人生产接入和共跑尚未验收。"
                )
                + links(
                    [
                        ("../workflow/report.html", "查看工作流技术实例"),
                        ("../../reports.html", "返回报告列表"),
                    ]
                ),
            ),
        ],
    )
    # Existing reviewed voice summary is already a self-contained, no-audio public page.
    voice = study / "reports/2026-10-22-voice-screening/report.html"
    dest = output / "voice-screening/report.html"
    dest.parent.mkdir()
    text = voice.read_text()
    text = re.sub(
        r"<section\b[^>]*id=[\"\']evidence[\"\'][^>]*>.*?</section>",
        '<section id="evidence"><h2>证据范围</h2><p>本页是已确认语音报告的公开展示副本。原始配置、输出、参考来源与哈希保存在研究仓库；本页不携带录音或原始证据下载。</p></section>',
        text,
        flags=re.S,
    )
    text = re.sub(
        r"<a\b[^>]*href=[\"\']data:[^>]*>.*?</a>", "", text, flags=re.S
    )
    dest.write_text(text)
    sources[str(voice.relative_to(root))] = hashlib.sha256(
        voice.read_bytes()
    ).hexdigest()
    created.append(dest)
    return {
        "files": [str(p.relative_to(output)) for p in created],
        "sources": sources,
    }


def publication(output, generated, path, root=ROOT):
    output = Path(output).resolve()
    root = Path(root).resolve()
    files = []
    for name in generated["files"]:
        source = output / name
        files.append(
            {
                "source": str(source.relative_to(root)),
                "destination": "reports/" + name,
                "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            }
        )
    catalog = [
        {
            "title": "Qwen正式研究结果",
            "description": "768微步模型的132例独立测评，保留角色与语义失败。",
            "href": "reports/qwen-main/report.html",
        },
        {
            "title": "工作流使用实例",
            "description": "32微步技术试跑：数据、就绪、训练、导出到两类任务测评。",
            "href": "reports/workflow/report.html",
        },
        {
            "title": "语音单模块评测",
            "description": "ASR、LLM、TTS独立模块结果，公开版不携带录音。",
            "href": "reports/voice-screening/report.html",
        },
    ]
    aliases = {
        "evidence/studies/voice-interaction/research/2026-10-22-local-stack/report.html": "reports/workflow-selection/report.html",
        "evidence/studies/voice-interaction/experiments/rk3566/2026-10-22-preparation-smoke-v1/readiness/report.html": "reports/workflow-readiness/report.html",
    }
    Path(path).write_text(
        json.dumps(
            {
                "schema": "edge-ai-publication/v1",
                "catalog": catalog,
                "files": files,
                "aliases": aliases,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("output", type=Path)
    p.add_argument("--publication-manifest", type=Path)
    a = p.parse_args()
    result = build(a.output)
    if a.publication_manifest:
        publication(a.output, result, a.publication_manifest)
    (a.output / "generation.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    print("Generated", len(result["files"]), "curated report files")


if __name__ == "__main__":
    main()
