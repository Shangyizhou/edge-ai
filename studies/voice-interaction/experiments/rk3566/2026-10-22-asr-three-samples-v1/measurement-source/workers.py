"""直接调用各推理引擎，逐例落盘，不接机器人动作或声卡。"""

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
import wave
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def emit(output: Path, event: dict) -> None:
    """每个完成事件立即保存，后续超时也保留前面结果。"""
    with (output / "events.jsonl").open("a") as stream:
        stream.write(json.dumps(event, ensure_ascii=False) + "\n")


def await_gate(config: dict) -> None:
    """共存实验就绪后等同一触发点，单模块实验无需门禁。"""
    if "gate_file" in config:
        while not Path(config["gate_file"]).exists():
            time.sleep(0.01)


def asr(config: dict, output: Path) -> None:
    """保持旧 ASR 权重，分别记录计算耗时和音频时间轴。"""
    # Sherpa/numpy 只在对应 Adapter 中加载，LLM 不承担该初始化成本。
    import numpy as np
    import sherpa_onnx

    model = Path(config["model"])
    start = time.monotonic()
    recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
        tokens=str(model / "tokens.txt"),
        encoder=str(model / "encoder-epoch-99-avg-1.int8.onnx"),
        decoder=str(model / "decoder-epoch-99-avg-1.onnx"),
        joiner=str(model / "joiner-epoch-99-avg-1.int8.onnx"),
        num_threads=config["threads"],
        decoding_method=config.get("decoding_method", "greedy_search"),
        max_active_paths=config.get("max_active_paths", 4),
        enable_endpoint_detection=True,
        rule2_min_trailing_silence=config.get("endpoint_silence", 1.2),
        provider="cpu",
        model_type="zipformer",
    )
    emit(
        output,
        {
            "event": "loaded",
            "load_seconds": time.monotonic() - start,
            "engine_version": sherpa_onnx.__version__,
        },
    )
    await_gate(config)
    if "residency_stop_file" in config:
        while not Path(config["residency_stop_file"]).exists():
            time.sleep(0.02)
    for index, filename in enumerate(config["wavs"]):
        with wave.open(filename) as audio:
            if (
                audio.getframerate(),
                audio.getnchannels(),
                audio.getsampwidth(),
            ) != (16000, 1, 2):
                raise ValueError("ASR input must be 16kHz mono S16 WAV")
            samples = (
                np.frombuffer(
                    audio.readframes(audio.getnframes()), dtype=np.int16
                ).astype(np.float32)
                / 32768
            )
        duration = len(samples) / 16000
        # 1. 明确添加尾部静音，端点位置按音频轴记录而非虚构真人末音。
        padded = np.concatenate([samples, np.zeros(40000, np.float32)])
        stream = recognizer.create_stream()
        first_partial = None
        first_partial_wall = None
        endpoint = None
        text = ""
        decode_seconds = 0.0
        started = time.monotonic()
        chunk = config.get("chunk_samples", 1600)
        for offset in range(0, len(padded), chunk):
            if config.get("realtime", False):
                available = min(offset + chunk, len(padded)) / 16000
                remaining = started + available - time.monotonic()
                if remaining > 0:
                    time.sleep(remaining)
            decode_start = time.monotonic()
            stream.accept_waveform(16000, padded[offset : offset + chunk])
            while recognizer.is_ready(stream):
                recognizer.decode_stream(stream)
            text = recognizer.get_result(stream)
            cursor = min(offset + chunk, len(padded)) / 16000
            if text and first_partial is None:
                first_partial = cursor
                first_partial_wall = time.monotonic() - started
            if recognizer.is_endpoint(stream) and text and endpoint is None:
                endpoint = cursor
            decode_seconds += time.monotonic() - decode_start
        stream.input_finished()
        decode_start = time.monotonic()
        while recognizer.is_ready(stream):
            recognizer.decode_stream(stream)
        text = recognizer.get_result(stream)
        decode_seconds += time.monotonic() - decode_start
        emit(
            output,
            {
                "event": "sample",
                "index": index,
                "input": filename,
                "audio_seconds": duration,
                "seconds": decode_seconds,
                "wall_seconds": time.monotonic() - started,
                "rtf": decode_seconds / duration,
                "transcript": text,
                "first_partial_audio_s": first_partial,
                "first_partial_wall_seconds": first_partial_wall,
                "endpoint_audio_s": endpoint,
                "endpoint_from_file_end_s": (
                    endpoint - duration if endpoint is not None else None
                ),
                "appended_silence_s": 2.5,
                "realtime": config.get("realtime", False),
            },
        )


def request_json(url: str, data=None, timeout=10) -> dict:
    """向本机模型入口发一次 JSON 请求。"""
    body = None if data is None else json.dumps(data).encode()
    request = Request(
        url, data=body, headers={"Content-Type": "application/json"}
    )
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def native_asr(config: dict, output: Path) -> None:
    """使用官方 CLI 实测 RKNN 或 CPU，一次只解码一个文件。"""
    (output / "ready").write_text("ready")
    await_gate(config)
    for index, filename in enumerate(config["wavs"]):
        command = config["command"] + [filename]
        started = time.monotonic()
        result = subprocess.run(command, capture_output=True, text=True)
        wall_seconds = time.monotonic() - started
        log = result.stdout + result.stderr
        (output / (str(index) + "-native.log")).write_text(log)
        result.check_returncode()
        match = re.search(
            r"Elapsed seconds: ([\d.e+-]+), Audio duration \(s\): "
            r"([\d.e+-]+).* = ([\d.e+-]+)",
            log,
        )
        if match is None:
            raise ValueError("native ASR CLI omitted expected timing record")
        texts = [
            json.loads(line)
            for line in log.splitlines()
            if re.match(r'^\{\s*"text"', line)
        ]
        emit(
            output,
            {
                "event": "sample",
                "index": index,
                "input": filename,
                "seconds": float(match[1]),
                "audio_seconds": float(match[2]),
                "rtf": float(match[3]),
                "wall_seconds": wall_seconds,
                "start_monotonic": started,
                "end_monotonic": started + wall_seconds,
                "transcript": texts[-1]["text"] if texts else None,
                "timing_precision": "official CLI, 2 significant digits",
                "command": command,
                "includes_model_reload": True,
                "appended_silence_s": 0.8,
            },
        )


def llama(config: dict, output: Path) -> None:
    """常驻一次 llama-server，测真实短提示与首内容延迟。"""
    with socket.socket() as allocation:
        allocation.bind(("127.0.0.1", 0))
        port = allocation.getsockname()[1]
    command = [
        config["binary"],
        "-m",
        config["model"],
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "-t",
        str(config["threads"]),
        "-tb",
        str(config["threads"]),
        "-c",
        str(config.get("context", 1024)),
        "-b",
        str(config.get("batch", 128)),
        "-ub",
        str(config.get("microbatch", 64)),
        "-ctk",
        config.get("kv", "f16"),
        "-ctv",
        config.get("kv_v", config.get("kv", "f16")),
        "-fa",
        "off",
        "-ngl",
        "0",
        "--no-warmup",
    ]
    if not config.get("repack", True):
        command.append("--no-repack")
    origin = "http://127.0.0.1:" + str(port)
    start = time.monotonic()
    with (output / "native.log").open("w") as log:
        if config.get("protocol_id") == "rk3566-voice-screen-v2":
            emit(
                output,
                {
                    "event": "phase",
                    "name": "loading",
                    "state": "start",
                    "monotonic_seconds": time.monotonic(),
                },
            )
        server = subprocess.Popen(command, stdout=log, stderr=log)
        try:
            # 1. 启动期连接拒绝/503只表示尚未就绪，原生退出即暴露失败。
            while True:
                if server.poll() is not None:
                    raise RuntimeError("llama-server exited during startup")
                try:
                    health = request_json(origin + "/health")
                except HTTPError as error:
                    if error.code != 503:
                        raise
                except URLError:
                    pass
                else:
                    if health["status"] == "ok":
                        break
                time.sleep(0.1)
            emit(
                output,
                {
                    "event": "loaded",
                    "load_seconds": time.monotonic() - start,
                    "command": command,
                },
            )
            if config.get("protocol_id") == "rk3566-voice-screen-v2":
                emit(
                    output,
                    {
                        "event": "phase",
                        "name": "loading",
                        "state": "end",
                        "monotonic_seconds": time.monotonic(),
                    },
                )
            await_gate(config)
            if config.get("protocol_id") == "rk3566-voice-screen-v2":
                for stage in ("first_request", "warmup"):
                    emit(
                        output,
                        {
                            "event": "phase",
                            "name": stage,
                            "state": "start",
                            "monotonic_seconds": time.monotonic(),
                        },
                    )
                    request_json(
                        origin + "/completion",
                        {
                            "prompt": "<|im_start|>user\n你好<|im_end|>\n<|im_start|>assistant\n",
                            "n_predict": 8,
                            "temperature": 0,
                            "cache_prompt": False,
                        },
                        timeout=90,
                    )
                    emit(
                        output,
                        {
                            "event": "phase",
                            "name": stage,
                            "state": "end",
                            "monotonic_seconds": time.monotonic(),
                        },
                    )
                emit(
                    output,
                    {
                        "event": "phase",
                        "name": "idle",
                        "state": "start",
                        "monotonic_seconds": time.monotonic(),
                    },
                )
                time.sleep(3)
                emit(
                    output,
                    {
                        "event": "phase",
                        "name": "idle",
                        "state": "end",
                        "monotonic_seconds": time.monotonic(),
                    },
                )
            # 2. Use explicit protocol template; preserve legacy defaults.
            for index, text in enumerate(config["texts"]):
                if config.get("protocol_id") == "rk3566-voice-screen-v2":
                    emit(
                        output,
                        {
                            "event": "phase",
                            "name": "inference",
                            "state": "start",
                            "monotonic_seconds": time.monotonic(),
                        },
                    )
                prompt = "Human: " + text + "<|im_end|>\nAssistant:"
                system = config.get("system", "")
                if system:
                    prompt = "System: " + system + "<|im_end|>\n" + prompt
                if config.get("chat_template") == "chatml":
                    prompt = (
                        (
                            ("<|im_start|>system\n" + system + "<|im_end|>\n")
                            if system
                            else ""
                        )
                        + "<|im_start|>user\n"
                        + text
                        + "<|im_end|>\n<|im_start|>assistant\n"
                    )
                payload = {
                    "prompt": prompt,
                    "stream": True,
                    "cache_prompt": False,
                    "n_predict": config.get("max_tokens", 64),
                    "seed": 42,
                    "temperature": config.get("temperature", 0.7),
                    "top_p": 0.8,
                    "top_k": 20,
                    "min_p": 0.0,
                    "repeat_penalty": 1.0,
                }
                (output / (str(index) + "-request.json")).write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2)
                )
                request = Request(
                    origin + "/completion",
                    data=json.dumps(payload).encode(),
                    headers={"Content-Type": "application/json"},
                )
                started = time.monotonic()
                first = None
                first_sentence = None
                last_content_at = None
                reply = ""
                final = {}
                trace_path = output / (str(index) + "-stream.jsonl")
                with urlopen(request, timeout=90) as response, trace_path.open(
                    "w"
                ) as trace:
                    for line in response:
                        if (
                            config.get("protocol_id")
                            == "rk3566-voice-screen-v2"
                            and time.monotonic() - started > 90
                        ):
                            raise TimeoutError("LLM input exceeds 90s")
                        if not line.startswith(b"data: "):
                            continue
                        chunk = json.loads(line[6:])
                        trace.write(
                            json.dumps(
                                {
                                    "received_seconds": time.monotonic()
                                    - started,
                                    "chunk": chunk,
                                },
                                ensure_ascii=False,
                            )
                            + "\n"
                        )
                        trace.flush()
                        content = chunk.get("content", "")
                        if content and first is None:
                            first = time.monotonic() - started
                            emit(
                                output,
                                {
                                    "event": "first_token",
                                    "index": index,
                                    "ttft_seconds": first,
                                },
                            )
                        if content:
                            last_content_at = time.monotonic() - started
                        reply += content
                        if first_sentence is None and re.search(
                            r"[。！？]", reply
                        ):
                            first_sentence = time.monotonic() - started
                            emit(
                                output,
                                {
                                    "event": "first_sentence",
                                    "index": index,
                                    "seconds": first_sentence,
                                },
                            )
                        final = chunk
                if config.get("protocol_id") == "rk3566-voice-screen-v2":
                    emit(
                        output,
                        {
                            "event": "phase",
                            "name": "inference",
                            "state": "end",
                            "monotonic_seconds": time.monotonic(),
                        },
                    )
                emit(
                    output,
                    {
                        "event": "sample",
                        "index": index,
                        "input": text,
                        "seconds": time.monotonic() - started,
                        "ttft_seconds": first,
                        "first_sentence_seconds": first_sentence,
                        "transport_observed_decode_tokens_per_second": (
                            (final["tokens_predicted"] - 1)
                            / (last_content_at - first)
                            if isinstance(final.get("tokens_predicted"), int)
                            and final["tokens_predicted"] > 1
                            and first is not None
                            and last_content_at > first
                            else None
                        ),
                        "started_monotonic_seconds": started,
                        "reply": reply,
                        "timings": final.get("timings", {}),
                        "stop_type": final.get("stop_type"),
                        "stopped_limit": final.get("stopped_limit"),
                        "tokens_predicted": final.get("tokens_predicted"),
                        "tokens_evaluated": final.get("tokens_evaluated"),
                    },
                )
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()


def sherpa_tts(config: dict, output: Path) -> None:
    """通过 Sherpa 的常驻 Python Interface 合成完整 PCM。"""
    import numpy as np
    import sherpa_onnx

    started = time.monotonic()
    vits = sherpa_onnx.OfflineTtsVitsModelConfig(**config["vits"])
    model = sherpa_onnx.OfflineTtsModelConfig(
        vits=vits, num_threads=config["threads"], provider="cpu"
    )
    setup = sherpa_onnx.OfflineTtsConfig(
        model=model, **config.get("tts_config", {})
    )
    synthesizer = sherpa_onnx.OfflineTts(setup)
    emit(
        output, {"event": "loaded", "load_seconds": time.monotonic() - started}
    )
    for index, text in enumerate(config["texts"]):
        started = time.monotonic()
        audio = synthesizer.generate(text, sid=0, speed=1.0)
        seconds = time.monotonic() - started
        pcm = (np.clip(audio.samples, -1, 1) * 32767).astype(np.int16)
        with wave.open(str(output / (str(index) + ".wav")), "wb") as stream:
            stream.setparams((1, 2, audio.sample_rate, 0, "NONE", ""))
            stream.writeframes(pcm.tobytes())
        emit(
            output,
            {
                "event": "sample",
                "index": index,
                "input": text,
                "seconds": seconds,
                "samples": len(pcm),
                "sample_rate": audio.sample_rate,
                "rtf": seconds / (len(pcm) / audio.sample_rate),
            },
        )


def piper(config: dict, output: Path) -> None:
    """复用 Piper 常驻模型，等文件关闭后记录完整 PCM 就绪。"""
    command = [
        config["binary"],
        "--model",
        config["model"],
        "--config",
        config["model"] + ".json",
        "--output_dir",
        str(output),
    ]
    log_path = output / "native.log"
    started = time.monotonic()
    with log_path.open("w") as log:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=log,
            text=True,
            bufsize=1,
        )
        try:
            # 1. 官方旧 CLI 在首次读 stdin 前写出就绪标记。
            while "Output directory:" not in log_path.read_text():
                if process.poll() is not None:
                    raise RuntimeError("Piper exited before readiness")
                time.sleep(0.01)
            emit(
                output,
                {
                    "event": "loaded",
                    "load_seconds": time.monotonic() - started,
                    "thread_control": "ORT runtime default",
                    "command": command,
                },
            )
            for index, text in enumerate(config["texts"]):
                started = time.monotonic()
                process.stdin.write(text + "\n")
                process.stdin.flush()
                filename = process.stdout.readline().strip()
                if not filename:
                    raise RuntimeError("Piper exited without output path")
                # 2. 路径打印早于文件关闭，随后 RTF 日志作完成屏障。
                while (
                    log_path.read_text().count("Real-time factor:") < index + 1
                ):
                    if process.poll() is not None:
                        raise RuntimeError(
                            "Piper exited before WAV completion"
                        )
                    time.sleep(0.005)
                seconds = time.monotonic() - started
                source = Path(filename)
                with wave.open(str(source)) as audio:
                    samples = audio.getnframes()
                    sample_rate = audio.getframerate()
                (output / (str(index) + ".wav")).write_bytes(
                    source.read_bytes()
                )
                emit(
                    output,
                    {
                        "event": "sample",
                        "index": index,
                        "input": text,
                        "seconds": seconds,
                        "samples": samples,
                        "sample_rate": sample_rate,
                        "rtf": seconds / (samples / sample_rate),
                        "timing_scope": "frontend+inference+WAV+ready_poll",
                    },
                )
        finally:
            process.stdin.close()
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            process.stdout.close()


def coexistence(config: dict, output: Path) -> None:
    """三模型分别常驻，ASR待机，LLM和TTS同时工作后统一收尾。"""
    # 共存与独立实验共享实际命令组装，避免另一条性能旁路。
    from benchmark import command_for

    gate = output / "start"
    stop = output / "stop-asr"
    children = []
    logs = []
    started = time.monotonic()
    try:
        # 1. 三个模型各自加载并发出可观察就绪事件，暂不开始请求。
        for member in config["members"]:
            directory = output / member["id"]
            directory.mkdir()
            settings = dict(member, gate_file=str(gate))
            if member["kind"] == "asr":
                settings["wavs"] = []
                settings["residency_stop_file"] = str(stop)
            (directory / "config.json").write_text(
                json.dumps(settings, ensure_ascii=False, indent=2)
            )
            command = command_for(settings, directory, sys.executable)
            if member["kind"] == "summer":
                command.append(str(gate))
            stdout = (directory / "stdout.log").open("w")
            stderr = (directory / "stderr.log").open("w")
            logs.extend([stdout, stderr])
            child = subprocess.Popen(
                command,
                stdout=stdout,
                stderr=stderr,
                env=dict(os.environ, OMP_NUM_THREADS=str(member["threads"])),
            )
            children.append((member, directory, child))
        while True:
            ready = 0
            for member, directory, child in children:
                if child.poll() is not None:
                    raise RuntimeError(member["id"] + " exited before gate")
                path = directory / "events.jsonl"
                if path.exists() and '"loaded"' in path.read_text():
                    ready += 1
            if ready == len(children):
                break
            time.sleep(0.05)
        emit(
            output,
            {
                "event": "loaded",
                "load_seconds": time.monotonic() - started,
                "mode": "ASR resident idle; LLM/TTS overlap",
            },
        )
        # 2. 同时放行输出；ASR保留权重但不解码，符合半双工处理期间状态。
        gate.write_text("start")
        for member, directory, child in children:
            if member["kind"] != "asr":
                if child.wait() != 0:
                    raise RuntimeError(member["id"] + " failed during overlap")
        stop.write_text("stop")
        for member, directory, child in children:
            if child.wait() != 0:
                raise RuntimeError(member["id"] + " failed on shutdown")
        # 3. 保留每个模块的请求时延，不把并发总时间当作逐模块时间。
        next_index = 0
        for member, directory, child in children:
            for line in (directory / "events.jsonl").read_text().splitlines():
                event = json.loads(line)
                if event["event"] != "sample":
                    continue
                source_index = event["index"]
                event.update(
                    index=next_index,
                    source_index=source_index,
                    module=member["id"],
                )
                emit(output, event)
                pcm = directory / (str(source_index) + ".pcm")
                if pcm.exists():
                    with wave.open(
                        str(output / f"{next_index}.wav"), "wb"
                    ) as f:
                        f.setparams((1, 2, 16000, 0, "NONE", ""))
                        f.writeframes(pcm.read_bytes())
                next_index += 1
    finally:
        for member, directory, child in children:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
        for log in logs:
            log.close()


def yolo(config: dict, output: Path) -> None:
    """调用真实 RKNN/RGA 后端，保留逐帧耗时与检测输出。"""
    command = [
        config["binary"],
        config["model"],
        config["labels"],
        config["image"],
        str(output),
        str(config["width"]),
        str(config["height"]),
        str(config["frames"]),
        str(config.get("fps", 0)),
        str(config.get("confidence", 0.3)),
        str(config.get("nms", 0.3)),
        str(config.get("threads", 1)),
        config.get("gate_file", "-"),
    ]
    subprocess.run(command, check=True)


def yolo_cpu(config: dict, output: Path) -> None:
    """仅 CPU 视觉 worker 加载 ORT/OpenCV 和共享后处理适配器。"""
    from yolo_cpu import run

    run(config, output)


def streaming_asr(config: dict, output: Path) -> None:
    """一次加载模型，以固定音频节奏测常驻 RKNN 流式识别。"""
    fixtures = json.loads(Path(config["fixtures"]).read_text())["fixtures"]
    selected = set(config.get("fixture_ids", [f["id"] for f in fixtures]))
    rows = [f for f in fixtures if f["id"] in selected]
    if len(rows) != len(selected):
        raise ValueError("unknown streaming fixture id")
    (output / "fixtures.json").write_text(
        json.dumps(
            {"schema_version": 1, "fixtures": rows},
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    path = output / "fixtures.tsv"
    path.write_text(
        "".join(f"{f['path']}\t{f['energy_end_s']}\n" for f in rows)
    )
    command = [
        config["binary"],
        config["model"],
        str(output),
        str(path),
        str(config["endpoint_silence"]),
        str(config.get("chunk_ms", 100)),
        str(int(config.get("realtime", True))),
        str(config.get("tail_seconds", 3.2)),
        config.get("gate_file", "-"),
        config.get("provider", "rknn"),
        str(config.get("idle_seconds", 0)),
        str(config.get("threads", 1)),
    ]
    # 保存实际加载的共享库身份；库映射不独自证明调用了某个后端。
    child = subprocess.Popen(command)
    captured = False
    while child.poll() is None:
        if not captured and (output / "ready").exists():
            try:
                (output / "backend-maps.txt").write_text(
                    Path(f"/proc/{child.pid}/maps").read_text()
                )
                captured = True
            except FileNotFoundError:
                pass
        time.sleep(0.02)
    if child.returncode:
        raise subprocess.CalledProcessError(child.returncode, command)


def vision_asr(config: dict, output: Path) -> None:
    """同时放行视觉与活跃 ASR，保留各进程的原始日志和事件。"""
    gate = output / "start-gate"
    children = []
    logs = []
    try:
        for member in config["members"]:
            directory = output / member["id"]
            directory.mkdir()
            child_config = dict(member, gate_file=str(gate))
            path = directory / "config.json"
            path.write_text(json.dumps(child_config))
            log = (directory / "native.log").open("w")
            logs.append(log)
            env = dict(os.environ, **member.get("env", {}))
            child = subprocess.Popen(
                [sys.executable, __file__, str(path), str(directory)],
                env=env,
                stdout=log,
                stderr=log,
            )
            children.append((member, directory, child))
        # 1. 常驻 ASR 与 YOLO 均完成预热；旧 native CLI 在门禁后加载。
        while not all((d / "ready").exists() for _, d, _ in children):
            for member, directory, child in children:
                if child.poll() is not None:
                    raise RuntimeError(member["id"] + " exited before gate")
            time.sleep(0.01)
        gate.write_text("start")
        for member, directory, child in children:
            if child.wait() != 0:
                raise RuntimeError(member["id"] + " failed during overlap")
    finally:
        # 2. 即使子项失败，也合并已完成事件供复核。
        index = 0
        for member, directory, child in children:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
            events = directory / "events.jsonl"
            if events.exists():
                for line in events.read_text().splitlines():
                    event = json.loads(line)
                    if event["event"] == "sample":
                        event.update(source_index=event["index"], index=index)
                        index += 1
                    event["module"] = member["id"]
                    emit(output, event)
        for log in logs:
            log.close()


def main() -> None:
    """单个子进程只运行一种 Adapter，便于独立计量和回收。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    from voice_v2 import run as voice_v2

    adapters = {
        "voice_v2_asr": voice_v2,
        "voice_v2_tts": voice_v2,
        "asr": asr,
        "llama": llama,
        "sherpa_tts": sherpa_tts,
        "native_asr": native_asr,
        "piper": piper,
        "coexistence": coexistence,
        "yolo": yolo,
        "yolo_cpu": yolo_cpu,
        "vision_asr": vision_asr,
        "streaming_asr": streaming_asr,
    }
    adapters[config["kind"]](config, args.output)


if __name__ == "__main__":
    main()
