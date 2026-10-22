"""Measure transformations and render read-only stage views."""

import base64
import json
import subprocess
import time
from pathlib import Path

from .benchmark import asset_manifest, file_hash, write_json
from .lineage import freeze_sources
from .measure import ResourceSampler
from .report import esc, number


def check_export_request(request):
    if request.get("schema") != "edge-model-export/request-v1":
        raise ValueError("unsupported export request schema")
    if not request.get("run_id") or not request.get("operations"):
        raise ValueError("run_id and explicit operations are required")
    known = set(request.get("artifacts", {}))
    for operation in request["operations"]:
        if operation.get("kind") not in ("merge", "convert", "quantize"):
            raise ValueError("unknown export operation")
        if not operation.get("command") or not operation.get("output"):
            raise ValueError(
                "each operation requires argv and output artifact"
            )
        if any(source not in known for source in operation.get("inputs", [])):
            raise ValueError("operation input is not an identified artifact")
        identity = operation["output"]["id"]
        if identity in known:
            raise ValueError("output artifact IDs must be new")
        known.add(identity)


def export(request, output):
    """Execute explicit argv with weights outside evidence."""
    check_export_request(request)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "request.json", request)
    artifacts = {}
    for identity, path in request.get("artifacts", {}).items():
        artifacts[identity] = asset_manifest({"model_path": path})
    result = {
        "schema": "edge-model-export/result-v1",
        "run_id": request["run_id"],
        "status": "running",
        "source": {"kind": "device_measurement"},
        "request_sha256": file_hash(output / "request.json"),
        "artifacts": artifacts,
        "stages": [],
        "measurement_sources": freeze_sources(
            output,
            [
                "stages.py",
                "measure.py",
                "benchmark.py",
                "convert_hf.py",
                "lineage.py",
            ],
        ),
        "quality_status": "NOT_EVALUATED",
        "next_step": "prepare output artifact with actual loading/smoke, "
        "then benchmark using the frozen task suite",
    }
    for index, operation in enumerate(request["operations"]):
        target = Path(operation["output"]["path"])
        if target.exists():
            raise FileExistsError(
                "refusing to overwrite existing artifact: " + str(target)
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        log_path = output / f"{index:02d}-{operation['kind']}.log"
        stage = {
            "operation": operation["kind"],
            "command": operation["command"],
            "inputs": operation.get("inputs", []),
            "output_id": operation["output"]["id"],
            "status": "running",
        }
        result["stages"].append(stage)
        started = time.perf_counter()
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                operation["command"],
                stdout=log,
                stderr=subprocess.STDOUT,
                cwd=operation.get("cwd"),
            )
            sampler = ResourceSampler(
                process.pid, request.get("sampling_interval_seconds", 0.2)
            ).start()
            while process.poll() is None:
                time.sleep(0.05)
            # Retired children keep their last observed CPU counters.
            # Memory peaks remain sampled observations.
            stage["resources"] = sampler.stop()
        stage["wall_seconds"] = time.perf_counter() - started
        stage["exit_code"] = process.returncode
        write_json(output / f"{index:02d}-resources.json", sampler.samples)
        if process.returncode or not target.exists():
            stage["status"] = "failed"
            stage["error"] = (
                "process failed or requested output artifact is absent"
            )
            result["status"] = "failed"
        else:
            stage["status"] = "completed"
            artifacts[operation["output"]["id"]] = asset_manifest(
                {"model_path": str(target)}
            )
        write_json(output / "results.json", result)
        if stage["status"] == "failed":
            break
    if all(stage["status"] == "completed" for stage in result["stages"]):
        result["status"] = "completed"
    result["evidence"] = [
        {"path": p.name, "sha256": file_hash(p)}
        for p in sorted(output.iterdir())
        if p.is_file() and p.name != "results.json"
    ]
    write_json(output / "results.json", result)
    return result


def render_stages(records, training_plot=None, inference_report=None):
    """Render recorded stage results in the approved style."""
    css = Path(__file__).with_name("report.css").read_text()
    out = [
        '<!doctype html><html lang="zh-CN"><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        "<title>Qwen 微调、合并与转换 · 阶段实测</title>",
        "<style>"
        + css
        + '</style><nav class="rail"><strong>阶段导航</strong>',
        '<a href="#summary">结论与边界</a>',
    ]
    for index, record in enumerate(records):
        out.append(f'<a href="#stage-{index}">{esc(record["run_id"])}</a>')
    out.append(
        '<a href="#evidence">原始证据</a></nav><main><header>'
        '<span class="badge">实际训练 / 制品变换成本</span>'
        "<h1>从 LoRA 到可加载的部署制品</h1></header>"
        '<section id="summary"><h2>完成链路不等于能力验收</h2>'
        "<p>下面分别记录训练、合并、格式转换、量化的实际成本；"
        "原生调用与角色效果应阅读配套推理报告。少量训练步不证明完整业务或人设已学入。</p></section>"
    )
    if inference_report:
        if Path(
            inference_report
        ).name != inference_report or not inference_report.endswith(".html"):
            raise ValueError("related report must be a local HTML filename")
        out.append(
            '<p><a href="'
            + esc(inference_report)
            + '">查看 adapter、合并权重、F16 与 Q4 '
            '的逐条原生调用和角色输出</a></p>'
        )
    for index, record in enumerate(records):
        out.append(
            f'<section id="stage-{index}"><div class="eyebrow">'
            f"{esc(record['schema'])}</div>"
            f"<h2>{esc(record['run_id'])}</h2>"
            '<div class="method">训练tokens/s是监督token速率，'
            '不是生成tokens/s；'
            "CPU按整机逻辑核容量，内存是采样峰值，MLX分配与RSS可能重叠。"
            "每步输入与输出身份及原始日志保留，失败不会因渲染变为成功。</div>"
        )
        if record["schema"] == "edge-model-finetune/result-v1":
            res = record.get("resources", {})
            rss = res.get("peak_rss_bytes")
            mlx = record.get("mlx_peak_allocated_bytes")
            base = record.get("base_artifact", {})
            runtime = record.get("runtime", {})
            out.append(
                "<p>"
                + esc(base.get("model", "模型身份见配置"))
                + " · 参数 "
                + esc(base.get("parameter_count", "未记录"))
                + " · 基座精度 "
                + esc(base.get("precision", "未记录"))
                + " · MLX-LM "
                + esc(runtime.get("mlx-lm", "未记录"))
                + " / Metal（训练），LoRA rank "
                + esc(
                    record.get("config", {})
                    .get("lora_parameters", {})
                    .get("rank")
                )
                + "</p>"
            )
            out.append(
                '<div class="stats">'
                f"<span>状态 {esc(record['status'])}</span>"
                f"<span>微步 {record.get('microsteps', '未完成')}</span>"
                f"<span>优化器更新 "
                f"{record.get('optimizer_updates', '未完成')}</span>"
                f"<span>训练墙钟 "
                f"{number(record.get('training_wall_seconds'))} s</span>"
                f"<span>CPU容量 "
                f"{number(res.get('cpu_capacity_percent'))}%</span>"
                f"<span>峰值RSS "
                f"{number(rss / 1024**2 if rss is not None else None)}"
                " MiB</span><span>MLX峰值 "
                f"{number(mlx / 1024**2 if mlx is not None else None)}"
                " MiB（不相加）</span></div>"
            )
            out.append(
                '<div class="scroll"><table><tr><th>事件</th><th>上游微步</th>'
                "<th>loss</th><th>监督tokens/s</th><th>距开始秒</th></tr>"
            )
            for metric in record.get("metrics", []):
                info = metric["upstream"]
                loss = info.get("train_loss", info.get("val_loss"))
                out.append(
                    f"<tr><td>{esc(metric['kind'])}</td>"
                    "<td>"
                    f"{metric.get('microstep', info.get('iteration'))}</td>"
                    f"<td>{number(loss, 4)}</td>"
                    f"<td>{number(info.get('tokens_per_second'))}</td>"
                    f"<td>{number(metric['elapsed_seconds'])}</td></tr>"
                )
            out.append("</table></div>")
            if training_plot:
                image = base64.b64encode(training_plot).decode()
                out.append(
                    '<img alt="训练与验证 loss 曲线，原始数据见表" '
                    'style="max-width:100%;height:auto" '
                    f'src="data:image/svg+xml;base64,{image}">'
                )
        else:
            out.append(
                '<div class="scroll"><table><tr><th>步骤</th><th>状态</th>'
                "<th>墙钟s</th><th>CPU容量%</th>"
                "<th>峰值RSS MiB</th><th>输出bytes</th></tr>"
            )
            for stage in record.get("stages", []):
                res = stage.get("resources", {})
                artifact = record.get("artifacts", {}).get(
                    stage.get("output_id"), {}
                )
                rss = res.get("peak_rss_bytes")
                out.append(
                    f"<tr><td>{esc(stage['operation'])}</td>"
                    f"<td>{esc(stage['status'])}</td>"
                    f"<td>{number(stage.get('wall_seconds'))}</td>"
                    f"<td>{number(res.get('cpu_capacity_percent'))}</td>"
                    "<td>"
                    f"{number(rss / 1024**2 if rss is not None else None)}"
                    "</td>"
                    f"<td>{artifact.get('total_bytes', '未生成')}</td></tr>"
                )
            out.append("</table></div>")
        out.append(
            '<aside class="finding"><strong>本阶段发现</strong><p>'
            f"记录状态：{esc(record['status'])}。"
            "转换正常退出只证明制品生成，加载、原生推理和独立能力验收继续分开。"
            "</p></aside></section>"
        )
    payload = json.dumps(records, ensure_ascii=False, indent=2)
    encoded = base64.b64encode(payload.encode()).decode()
    out.append(
        '<section id="evidence"><h2>原始配置、指标与制品谱系</h2>'
        '<a download="stage-results.json" '
        f'href="data:application/json;base64,{encoded}">下载结果JSON</a>'
        "<details><summary>展开完整阶段结果</summary><pre>"
        + esc(payload)
        + "</pre></details></section></main>"
        '<script>const links=[...document.querySelectorAll(".rail a")];'
        'function nav(){let id="summary";for(const a of links){'
        'const s=document.querySelector(a.getAttribute("href"));'
        'if(s&&s.getBoundingClientRect().top<=150)id=s.id;}'
        'for(const a of links)a.classList.toggle("active",'
        'a.getAttribute("href")==="#"+id);}'
        'addEventListener("scroll",nav,{passive:true});nav();'
        "</script></html>"
    )
    return "\n".join(out)
