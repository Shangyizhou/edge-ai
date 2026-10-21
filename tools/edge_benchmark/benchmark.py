"""运行短矩阵、监控整棵推理进程树，并从已存事实生成静态报告。"""

import argparse
import hashlib
import html
import json
import math
import os
import platform
import re
import resource
import shutil
import signal
import subprocess
import sys
import time
import wave
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def write_json(path: Path, value) -> None:
    """把配置和结果保存为可直接复测的 UTF-8 JSON。"""
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2))


def memory_info() -> dict:
    """读取主机可用内存，以实际失败历史要求的水位作停止依据。"""
    return {
        line.split(":")[0]: int(line.split()[1])
        for line in Path("/proc/meminfo").read_text().splitlines()
        if line.split(":")[0] in {"MemAvailable", "SwapFree"}
    }


def process_tree(pid: int) -> list:
    """枚举本次 worker 的子进程，退出竞态按进程消失处理。"""
    result = [pid]
    try:
        children = Path(f"/proc/{pid}/task/{pid}/children").read_text()
    except FileNotFoundError:
        return []
    for child in children.split():
        result.extend(process_tree(int(child)))
    return result


def observe(pid: int) -> dict:
    """记录存活推理树资源；PSS区分共享页，RSS总和允许重复共享页。"""
    rss = pss = swap = ticks = threads = 0
    for child in process_tree(pid):
        try:
            stat = Path(f"/proc/{child}/stat").read_text().rsplit(")", 1)[1]
            fields = stat.split()
            ticks += sum(int(fields[i]) for i in (11, 12, 13, 14))
            threads += int(fields[17])
            detail = Path(f"/proc/{child}/smaps_rollup").read_text()
        except (FileNotFoundError, ProcessLookupError):
            continue
        values = {
            line.split(":")[0]: int(line.split()[1])
            for line in detail.splitlines()[1:]
        }
        rss += values["Rss"]
        pss += values["Pss"]
        swap += values["Swap"]
    sensors = {}
    for sensor in Path("/sys/class/thermal").glob("thermal_zone*/temp"):
        sensors[str(sensor)] = int(sensor.read_text()) / 1000
    clocks = {}
    for clock in Path("/sys/devices/system/cpu").glob(
        "cpu[0-9]*/cpufreq/scaling_cur_freq"
    ):
        clocks[str(clock)] = int(clock.read_text())
    npu = Path("/sys/class/devfreq/fde40000.npu/cur_freq")
    if npu.exists():
        clocks[str(npu)] = int(npu.read_text()) // 1000
    return {
        "rss_kib": rss,
        "pss_kib": pss,
        "swap_kib": swap,
        "cpu_seconds": ticks / os.sysconf("SC_CLK_TCK"),
        "threads": threads,
        "host": memory_info(),
        "temperatures_c": sensors,
        "cpu_frequency_khz": clocks,
    }


def limit_worker(max_as_mib: int) -> None:
    """对子进程设置明确的虚拟地址上限，禁止生成 core 文件。"""
    resource.setrlimit(resource.RLIMIT_AS, (max_as_mib * 1024**2,) * 2)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def stop_group(process: subprocess.Popen) -> None:
    """结束本次独立进程组，回收超时后仍运行的原生推理。"""
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()
    # worker可能先于孙进程退出，回收同组剩余者，不把父退出当作清理证明。
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def command_for(config: dict, directory: Path, python: str) -> list:
    """在实际变化的引擎 Seam 选择命令，不扩展机器人运行时。"""
    if config["kind"] == "summer":
        (directory / "texts.txt").write_text("\n".join(config["texts"]) + "\n")
        return [
            config["binary"],
            config["model"],
            str(config["threads"]),
            str(directory / "texts.txt"),
            str(directory),
            str(config.get("length_scale", 1.0)),
        ]
    if config["kind"] == "command":
        return [
            part.replace("{output}", str(directory))
            for part in config["command"]
        ]
    return [
        python,
        str(Path(__file__).with_name("workers.py")),
        str(directory / "config.json"),
        str(directory),
    ]


def run_case(config: dict, root: Path, python: str) -> dict:
    """运行一组配置；超时保留已完成事件，并停止整个推理树。"""
    directory = root / config["id"]
    directory.mkdir()
    write_json(directory / "config.json", config)
    worker_source = Path(__file__).with_name("workers.py")
    write_json(
        directory / "measurement-source.json",
        {
            "workers_sha256": hashlib.sha256(
                worker_source.read_bytes()
            ).hexdigest(),
            "runner_sha256": hashlib.sha256(
                Path(__file__).read_bytes()
            ).hexdigest(),
        },
    )
    command = command_for(config, directory, python)
    env = dict(
        os.environ,
        MALLOC_ARENA_MAX="1",
        OMP_NUM_THREADS=str(config.get("threads", 1)),
        OPENBLAS_NUM_THREADS="1",
    )
    env.update(config.get("env", {}))
    started = time.monotonic()
    reason = None
    samples = []
    with (directory / "stdout.log").open("w") as stdout, (
        directory / "stderr.log"
    ).open("w") as stderr:
        process = subprocess.Popen(
            command,
            stdout=stdout,
            stderr=stderr,
            env=env,
            start_new_session=True,
            preexec_fn=lambda: limit_worker(config.get("max_as_mib", 2304)),
        )
        samples.append(observe(process.pid))
        try:
            with (directory / "resources.jsonl").open("w") as resource_log:
                while process.poll() is None:
                    current = observe(process.pid)
                    current["elapsed_seconds"] = time.monotonic() - started
                    samples.append(current)
                    resource_log.write(json.dumps(current) + "\n")
                    resource_log.flush()
                    if current["elapsed_seconds"] > config["timeout"]:
                        reason = (
                            "suite_budget"
                            if config.get("budget_limited")
                            else "timeout"
                        )
                    elif current["host"]["MemAvailable"] < 384 * 1024:
                        reason = "host_memory_guard"
                    elif current["host"]["SwapFree"] < 512 * 1024:
                        reason = "host_swap_guard"
                    if reason:
                        break
                    time.sleep(0.2)
        except KeyboardInterrupt:
            reason = "interrupted"
        finally:
            stop_group(process)
    elapsed = time.monotonic() - started
    events_file = directory / "events.jsonl"
    events = (
        [json.loads(line) for line in events_file.read_text().splitlines()]
        if events_file.exists()
        else []
    )
    if config["kind"] == "summer":
        for pcm in directory.glob("*.pcm"):
            with wave.open(str(pcm.with_suffix(".wav")), "wb") as audio:
                audio.setparams((1, 2, 16000, 0, "NONE", ""))
                audio.writeframes(pcm.read_bytes())
    result = {
        "id": config["id"],
        "config": config,
        "command": command,
        "status": reason or ("ok" if process.returncode == 0 else "error"),
        "returncode": process.returncode,
        "wall_seconds": elapsed,
        "peak_rss_mib": max(s["rss_kib"] for s in samples) / 1024,
        "peak_pss_mib": max(s["pss_kib"] for s in samples) / 1024,
        "peak_swap_mib": max(s["swap_kib"] for s in samples) / 1024,
        "cpu_seconds": max(s["cpu_seconds"] for s in samples),
        "peak_threads": max(s["threads"] for s in samples),
        "min_host_available_mib": min(
            s["host"]["MemAvailable"] for s in samples
        )
        / 1024,
        "events": events,
    }
    write_json(directory / "result.json", result)
    print(result["id"], result["status"], f"{elapsed:.2f}s", flush=True)
    return result


def inventory(suite: dict) -> dict:
    """固定环境和输入资产身份，避免事后只按路径猜测权重。"""
    paths = {Path(__file__), Path(__file__).with_name("workers.py")}
    paths.update(Path(p) for p in suite.get("extra_assets", []))
    cases = list(suite["cases"])
    for case in cases:
        cases.extend(case.get("members", []))
        model = case.get("model")
        if model:
            path = Path(model)
            if path.is_dir():
                paths.update(path.glob("*.onnx"))
                paths.update(path.glob("*.rknn"))
                paths.add(path / "tokens.txt")
            else:
                paths.add(path)
        paths.update(Path(p) for p in case.get("wavs", []))
        if case.get("binary"):
            paths.add(Path(case["binary"]))
        for key in ("image", "labels", "decoder", "fixtures"):
            if case.get(key):
                paths.add(Path(case[key]))
        if case["kind"] == "streaming_asr":
            fixtures = json.loads(Path(case["fixtures"]).read_text())
            selected = case.get("fixture_ids")
            paths.update(
                Path(f["path"])
                for f in fixtures["fixtures"]
                if selected is None or f["id"] in selected
            )
        if case["kind"] == "sherpa_tts":
            paths.update(
                Path(p)
                for p in case["vits"].values()
                if isinstance(p, str) and Path(p).is_file()
            )
        if case["kind"] == "piper":
            paths.add(Path(case["model"] + ".json"))
        if case["kind"] == "native_asr":
            paths.add(Path(case["command"][0]))
    files = []
    for path in sorted(paths):
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        files.append(
            {
                "path": str(path),
                "bytes": path.stat().st_size,
                "sha256": digest.hexdigest(),
            }
        )
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "cpuinfo": Path("/proc/cpuinfo").read_text(),
        "host_memory": memory_info(),
        "assets": files,
        "suite": suite,
        "python": sys.version,
    }


def comparison_charts(results: list) -> str:
    """以最常见的同一输入展示短样本指标，不混入并发场景。"""
    panels = []
    groups = [
        ({"asr"}, "ASR 同录音计算 RTF · 越低越快", "rtf"),
        (
            {"summer", "sherpa_tts", "piper"},
            "TTS 同文本 RTF · 越低越快",
            "rtf",
        ),
        ({"llama"}, "Qwen 同提示生成 token/s · 越高越快", "tokens"),
    ]
    for kinds, title, metric in groups:
        points = []
        for result in results:
            case = result["config"]
            if case["kind"] not in kinds or result["status"] != "ok":
                continue
            inputs = case.get("texts", case.get("wavs", []))
            for event in result["events"]:
                if event["event"] != "sample":
                    continue
                value = (
                    event.get("timings", {}).get("predicted_per_second")
                    if metric == "tokens"
                    else event.get("rtf")
                )
                if value is not None:
                    points.append(
                        (inputs[event["index"]], result["id"], value)
                    )
        if not points:
            continue
        common = Counter(point[0] for point in points).most_common(1)[0][0]
        matched = [
            (name, value) for text, name, value in points if text == common
        ]
        maximum = max(value for _, value in matched)
        bars = "".join(
            f"<div class='barrow'><a href='#{html.escape(name)}'>"
            f"{html.escape(name)}</a><div class='track'><span style='width:"
            f"{100 * value / maximum:.1f}%'>{value:.3f}</span></div></div>"
            for name, value in matched
        )
        panels.append(
            f"<section><h2>{title}</h2><p>{html.escape(common)}</p>{bars}</section>"
        )
    return "".join(panels)


def vision_summary(events: list) -> dict:
    """按实测帧与输入预算计算吞吐、丢帧及短样本延迟分位数。"""
    frames = [e for e in events if e["event"] == "frame"]
    samples = [
        e for e in events if e["event"] == "sample" and "processed" in e
    ]
    if not frames or not samples:
        return {}
    frame_times = sorted(e["seconds"] * 1000 for e in frames)
    latencies = sorted(e["latency_seconds"] * 1000 for e in frames)
    processed = sum(e["processed"] for e in samples)
    dropped = sum(e["dropped"] for e in samples)
    elapsed = sum(e["seconds"] for e in samples)
    return {
        "frames": processed,
        "fps": processed / elapsed,
        "dropped": dropped,
        "offered": sum(e["offered_frames"] for e in samples),
        "mean_frame_ms": sum(frame_times) / len(frame_times),
        "scope": frames[0].get("scope", "backend"),
        "infer_mean_ms": sum(e.get("infer_seconds", 0) for e in frames)
        * 1000
        / len(frames),
        "post_mean_ms": sum(e.get("post_seconds", 0) for e in frames)
        * 1000
        / len(frames),
        "frame_p95_ms": frame_times[math.ceil(len(frames) * 0.95) - 1],
        "latency_p50_ms": latencies[math.ceil(len(frames) * 0.5) - 1],
        "latency_p95_ms": latencies[math.ceil(len(frames) * 0.95) - 1],
        "latency_max_ms": latencies[-1],
        "over_33ms_percent": 100
        * sum(t > 1000 / 30 for t in frame_times)
        / len(frame_times),
    }


def vision_table(results: list) -> str:
    """在同一报告单列视觉吞吐，避免与语音 RTF 混淆。"""
    rows = []
    for result in results:
        summary = vision_summary(result["events"])
        if not summary:
            continue
        infer = (
            f"{summary['infer_mean_ms']:.2f}"
            if summary["scope"] == "backend"
            else "—"
        )
        post = (
            f"{summary['post_mean_ms']:.2f}"
            if summary["scope"] == "backend"
            else "—"
        )
        rows.append(
            f"<tr><td>{html.escape(result['id'])}</td>"
            f"<td>{summary['fps']:.2f}</td>"
            f"<td>{summary['frames']}/{summary['offered']}</td>"
            f"<td>{summary['dropped']}</td>"
            f"<td>{infer}</td>"
            f"<td>{post}</td>"
            f"<td>{summary['frame_p95_ms']:.2f}</td>"
            f"<td>{summary['latency_p95_ms']:.2f}</td></tr>"
        )
    if not rows:
        return ""
    return (
        "<section><h2>YOLO 固定图像回放</h2>"
        "<p>复用实际 RKNN/RGA 推理与后处理；不含相机、ROS 传输、"
        "标注和图像编码。最新帧调度与 ROS 双队列并非同一流程。"
        "带 ros 标识的配置运行真实节点，包含 DDS、双队列、绘图和检测发布，"
        "处理 p95 对应端到端时延；仍不含相机采集与 MJPEG 解码。"
        "p95 为本轮样本分位数，不能代替长期稳定性验证。</p>"
        "<div class='scroll'><table><tr><th>配置</th><th>完成 FPS</th>"
        "<th>处理/输入</th><th>丢帧</th><th>推理均值 ms</th>"
        "<th>后处理均值 ms</th><th>整帧 p95 ms</th>"
        "<th>输入到完成 p95 ms</th></tr>"
        + "".join(rows)
        + "</table></div></section>"
    )


def streaming_summary(events: list) -> dict:
    """从常驻流事件汇总计算占用与延迟，缺失端点不记作零等待。"""
    samples = [
        e
        for e in events
        if e["event"] == "sample" and "first_partial_seconds" in e
    ]
    blocks = [e for e in events if e["event"] == "asr_block"]
    if not samples:
        return {}
    finals = [
        e["endpoint_after_energy_seconds"]
        for e in samples
        if e["endpoint_after_energy_seconds"] >= 0 and not e["eof_residual"]
    ]
    return {
        "utterances": len(samples),
        "model_creations": sum(e.get("model_creations", 0) for e in events),
        "compute_rtf": sum(e["seconds"] for e in samples)
        / sum(e["audio_seconds"] for e in samples),
        "compute_per_supplied_second": sum(e["seconds"] for e in samples)
        / sum(e["supplied_audio_seconds"] for e in samples),
        "endpoint_delays": finals,
        "missing_final_endpoints": len(samples) - len(finals),
        "max_submit_lateness_ms": max(
            (e["submit_lateness_seconds"] * 1000 for e in blocks), default=0
        ),
        "max_completion_lag_ms": max(
            (e["completion_lag_seconds"] * 1000 for e in blocks), default=0
        ),
    }


def streaming_table(results: list) -> str:
    """单列流式结果，并标清能量锚点与追加静音口径。"""
    rows = []
    for result in results:
        s = streaming_summary(result["events"])
        if not s:
            continue
        finals = " / ".join(f"{t:.3f}" for t in s["endpoint_delays"])
        rows.append(
            f"<tr><td>{html.escape(result['id'])}</td>"
            f"<td>{s['model_creations']}</td><td>{s['utterances']}</td>"
            f"<td>{s['compute_rtf']:.3f}</td>"
            f"<td>{s['compute_per_supplied_second']:.3f}</td>"
            f"<td>{finals or '—'}</td>"
            f"<td>{s['missing_final_endpoints']}</td>"
            f"<td>{s['max_submit_lateness_ms']:.1f}</td></tr>"
        )
    if not rows:
        return ""
    return (
        "<section><h2>常驻流式 ASR</h2><p>实时音频块回放；端点等待相对"
        "固定能量末端，非人工真人末音。RTF包括追加静音的计算，分母为"
        "原文件长度；供音占用比分母另含追加静音。提交滞后不等于模型"
        "内部全部缓冲。缺失端点不作零等待成功。</p><div class='scroll'>"
        "<table><tr><th>配置</th><th>模型创建</th><th>素材数</th>"
        "<th>计算RTF</th><th>供音占用比</th><th>逐例端点等待s</th>"
        "<th>缺失端点</th><th>最大提交滞后ms</th></tr>"
        + "".join(rows)
        + "</table></div></section>"
    )


def report(root: Path) -> Path:
    """只从已保存事实重建 HTML，失败和未完成例保持可见。"""
    results = [
        json.loads(path.read_text())
        for path in sorted(root.glob("*/result.json"))
    ]
    rows = []
    details = []
    for result in results:
        case = result["config"]
        events = result["events"]
        case_samples = [e for e in events if e["event"] == "sample"]
        values = ", ".join(f"{e['seconds']:.3f}" for e in case_samples)
        ratios = ", ".join(
            f"{e['rtf']:.3f}" for e in case_samples if "rtf" in e
        )
        first_tokens = ", ".join(
            f"{e['ttft_seconds']:.3f}"
            for e in case_samples
            if e.get("ttft_seconds") is not None
        )
        if not first_tokens:
            first_tokens = ", ".join(
                f"{e['ttft_seconds']:.3f}"
                for e in events
                if e["event"] == "first_token"
            )
        generation = ", ".join(
            f"{e['timings']['predicted_per_second']:.2f}"
            for e in case_samples
            if "predicted_per_second" in e.get("timings", {})
        )
        identity = html.escape(result["id"])
        load = next(
            (e["load_seconds"] for e in events if e["event"] == "loaded"), None
        )
        load_cell = f"{load:.3f}" if load is not None else "—"
        rows.append(
            f"<tr><td><a href='#{identity}'>{identity}</a></td>"
            f"<td>{html.escape(result['status'])}</td>"
            f"<td>{len(case_samples)}</td><td>{load_cell}</td>"
            f"<td>{values or '—'}</td><td>{ratios or '—'}</td>"
            f"<td>{first_tokens or '—'}</td><td>{generation or '—'}</td>"
            f"<td>{result['peak_rss_mib']:.1f}</td>"
            f"<td>{result['peak_pss_mib']:.1f}</td>"
            f"<td>{result['peak_swap_mib']:.1f}</td>"
            f"<td>{result['wall_seconds']:.1f}</td>"
            f"<td>{100 * result['cpu_seconds'] / result['wall_seconds']:.0f}%"
            f"</td></tr>"
        )
        samples_html = []
        for event in case_samples:
            index = event["index"]
            audio = root / result["id"] / (str(index) + ".wav")
            audio_html = (
                f"<audio controls preload='none' src='"
                f"{identity}/{index}.wav'></audio>"
                if audio.exists()
                else ""
            )
            samples_html.append(
                "<pre>"
                + html.escape(json.dumps(event, ensure_ascii=False, indent=2))
                + "</pre>"
                + audio_html
            )
        details.append(
            f"<section id='{identity}'><h2>{identity}</h2>"
            "<details><summary>完整参数</summary><pre>"
            + html.escape(json.dumps(case, ensure_ascii=False, indent=2))
            + "</pre></details>"
            + "<details><summary>逐例输入输出与音频</summary>"
            + "".join(samples_html)
            + "</details>"
            + f"<p><a href='{identity}/stderr.log'>错误日志</a> · "
            f"<a href='{identity}/resources.jsonl'>资源时间序列</a> · "
            f"<a href='{identity}/result.json'>原始结果</a></p>"
            + "<p>原生输出/流式记录："
            + " · ".join(
                f"<a href='{identity}/{html.escape(path.name)}'>"
                f"{html.escape(path.name)}</a>"
                for path in sorted((root / result["id"]).glob("*.log"))
            )
            + " · ".join(
                f"<a href='{identity}/{html.escape(path.name)}'>"
                f"{html.escape(path.name)}</a>"
                for path in sorted(
                    (root / result["id"]).glob("*-stream.jsonl")
                )
            )
            + "</p></section>"
        )
    document = """<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>RK3566 推理配置实测</title><style>
body{font:16px/1.6 system-ui;background:#f4f6f9;color:#172338;margin:0}
main{max-width:1400px;margin:auto;padding:28px}h1{font-size:30px}
section,.panel{background:white;padding:22px;border-radius:12px;margin:20px 0}
table{border-collapse:collapse;width:100%;font-size:14px}td,th{padding:10px;
border-bottom:1px solid #dae1eb;text-align:left}th{background:#eaf0f8}
pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6f9;padding:14px}
a{color:#225cca}audio{width:min(100%,500px)}.scroll{overflow:auto}
.barrow{display:grid;grid-template-columns:minmax(180px,340px) 1fr;gap:12px;
margin:8px 0;font-size:14px}.track{background:#edf1f7;border-radius:4px}
.track span{display:block;background:#4a78be;color:white;min-width:48px;
box-sizing:border-box;padding:2px 8px;border-radius:4px}h2{font-size:21px}
</style><main><h1>RK3566 · ASR / TTS / Qwen / YOLO 实测</h1>
<p>4×Cortex-A55 · 4GB RAM · 文件输入/输出 · 无机器人动作</p>
<div class="panel"><b>读数口径</b><p>加载与逐例推理分开。
RTF = 计算秒数 / 音频秒数，
低于1表示该例平均快于音频时长。ASR人为追加2.5秒静音，端点相对文件尾，
不冒充真人末音延迟。NPU官方CLI另用0.8秒尾静音，每文件重新加载，
时间只保留CLI输出精度；与Python分块组不是完全同条件。未播放时记录PCM就绪，
不称首声。RSS为进程树合计，
可能重复共享页；PSS另列。CPU、温度、频率详见原始时间序列。</p>
<p>少量筛查样本不提供稳定P95或正式MOS；超时/加载失败不计为零延迟成功。
三基线优先，效果和最终选型待结果齐全后评判。首次请求与后续请求按序号保留。</p>
<a href="manifest.json">环境、模型身份和完整矩阵</a></div>
<div class="panel scroll"><table><tr><th>配置</th><th>状态</th><th>完成例</th>
<th>加载 s</th><th>逐例计算 s</th><th>逐例 RTF</th><th>TTFT s</th>
<th>生成 token/s</th><th>RSS MiB</th><th>PSS MiB</th><th>Swap MiB</th>
<th>进程墙钟 s</th><th>平均CPU 含启动</th></tr>"""
    notes_path = root / "notes.json"
    notes = json.loads(notes_path.read_text()) if notes_path.exists() else []
    observations = (
        "<section><h2>观察与使用建议</h2><ul>"
        + "".join(f"<li>{html.escape(note)}</li>" for note in notes[:4])
        + "</ul><details><summary>更多现象、失败原因与解释边界</summary><ul>"
        + "".join(f"<li>{html.escape(note)}</li>" for note in notes[4:])
        + "</ul></details></section>"
        if notes
        else ""
    )
    target = root / "report.html"
    target.write_text(
        document.replace(
            '<div class="panel scroll">',
            observations
            + comparison_charts(results)
            + vision_table(results)
            + streaming_table(results)
            + '<div class="panel scroll">',
        )
        + "".join(rows)
        + "</table></div>"
        + "".join(details)
        + "</main></html>"
    )
    return target


def combine(sources: list, output: Path) -> Path:
    """复制已存实验生成可搬运总报告，保留来源且拒绝覆盖同名案例。"""
    output.mkdir(parents=True)
    manifests = output / "manifests"
    manifests.mkdir()
    origins = []
    for source in sources:
        shutil.copyfile(
            source / "manifest.json", manifests / f"{source.name}.json"
        )
        for result in source.glob("*/result.json"):
            shutil.copytree(result.parent, output / result.parent.name)
        origins.append(str(source))
    write_json(output / "manifest.json", {"source_runs": origins})
    return report(output)


def run_suite(suite: dict, output: Path) -> Path:
    """串行运行矩阵，累计预算到限只留下未测项，不丢弃已完成例。"""
    identifiers = [case["id"] for case in suite["cases"]]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("case ids must be unique")
    if any(
        re.fullmatch(r"[A-Za-z0-9_-]+", name) is None for name in identifiers
    ):
        raise ValueError("case ids may only contain letters, digits, _ and -")
    output.mkdir(parents=True)
    write_json(output / "manifest.json", inventory(suite))
    started = time.monotonic()
    pending = []
    for index, case in enumerate(suite["cases"]):
        if time.monotonic() - started >= suite["budget_seconds"]:
            pending.append(case["id"])
            continue
        remaining = suite["budget_seconds"] - (time.monotonic() - started)
        limited = dict(
            case,
            timeout=min(case["timeout"], remaining),
            requested_timeout_seconds=case["timeout"],
            budget_limited=remaining < case["timeout"],
        )
        result = run_case(limited, output, suite["python"])
        report(output)
        if result["status"] == "interrupted":
            pending.extend(c["id"] for c in suite["cases"][index + 1 :])
            break
    write_json(output / "pending.json", pending)
    return report(output)


def request_stop(signum: int, frame) -> None:
    """把操作员停止转为正常清理路径，保留已经完成的测量。"""
    raise KeyboardInterrupt


def main() -> None:
    """提供运行、合并和报告入口，报告生成不重跑模型。"""
    signal.signal(signal.SIGTERM, request_stop)
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="operation", required=True)
    run = commands.add_parser("run")
    run.add_argument("config", type=Path)
    run.add_argument("output", type=Path)
    render = commands.add_parser("report")
    render.add_argument("output", type=Path)
    merge = commands.add_parser("combine")
    merge.add_argument("output", type=Path)
    merge.add_argument("sources", nargs="+", type=Path)
    args = parser.parse_args()
    if args.operation == "run":
        target = run_suite(
            json.loads(args.config.read_text()), args.output.resolve()
        )
    elif args.operation == "combine":
        target = combine(
            [p.resolve() for p in args.sources], args.output.resolve()
        )
    else:
        target = report(args.output.resolve())
    print(target)


if __name__ == "__main__":
    main()
