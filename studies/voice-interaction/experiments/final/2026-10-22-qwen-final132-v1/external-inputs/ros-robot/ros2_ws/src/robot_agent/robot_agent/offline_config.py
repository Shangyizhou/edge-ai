"""启动边缘验证离线模型、设备与预算；不加载模型或打开音频。"""

import math
import shutil
from pathlib import Path
from typing import Dict

ASSETS = {
    "asr": ("encoder", "decoder", "joiner", "tokens"),
    "llm": ("model_path",),
    "tts": ("model", "tokens", "lexicon"),
}

NATIVE_NUMBERS = {
    "asr": {
        "sample_rate": int,
        "max_audio_age_ms": int,
        "max_audio_queue": int,
        "max_frame_samples": int,
        "num_threads": int,
        "endpoint_silence": float,
        "endpoint_speech_silence": float,
        "endpoint_max_seconds": float,
    },
    "llm": {
        "context_tokens": int,
        "micro_batch_tokens": int,
        "threads": int,
    },
    "tts": {"num_threads": int},
}


def select_backend(config: Dict) -> str:
    """旧配置缺省在线，显式未知值属于配置错误。"""
    backend = config.get("backend", "online")
    if backend not in ("online", "offline"):
        raise ValueError("backend 必须为 online 或 offline")
    return backend


def offline_parameters(config: Dict) -> Dict:
    """验证外部资产并返回三个原生节点参数，不创建运行时资源。"""
    section = config.get("offline")
    if not isinstance(section, dict):
        raise ValueError("offline 必须配置三个本地模型")
    if set(section) != set(ASSETS):
        raise ValueError("offline 只接纳 asr、llm、tts 参数对象")
    checkout = Path(__file__).resolve().parents[4]
    parameters = {}
    for kind, fields in ASSETS.items():
        values = section.get(kind)
        if not isinstance(values, dict):
            raise ValueError("offline." + kind + " 必须为参数对象")
        allowed = set(fields) | set(NATIVE_NUMBERS[kind])
        if kind == "asr":
            allowed.add("provider")
        if kind == "tts":
            allowed.add("rule_fsts")
        if kind == "llm":
            allowed.add("cache_type")
        if set(values) - allowed:
            raise ValueError("offline." + kind + " 含未知原生参数")
        parameters[kind] = dict(values)
        for name, expected in NATIVE_NUMBERS[kind].items():
            if name not in values:
                continue
            value = values[name]
            accepted = (int, float) if expected is float else (int,)
            if (
                type(value) not in accepted
                or not math.isfinite(value)
                or value <= 0
            ):
                raise ValueError(
                    "offline." + kind + "." + name + " 必须为正数"
                )
            if expected is float:
                parameters[kind][name] = float(value)
        for name in fields:
            filename = values.get(name)
            if not isinstance(filename, str) or not filename:
                raise ValueError("offline." + kind + "." + name + " 缺失")
            path = Path(filename).expanduser().resolve()
            if (
                not path.is_file()
                or checkout == path
                or checkout in path.parents
            ):
                raise ValueError(name + " 必须为源码外的模型资产文件")
            parameters[kind][name] = str(path)
    asr = parameters["asr"]
    if asr.get("provider", "cpu") not in ("cpu", "rknn"):
        raise ValueError("offline.asr.provider 必须为 cpu 或 rknn")
    if asr.get("provider") == "rknn" and asr.get("num_threads", 2) != 1:
        raise ValueError("offline.asr RKNN 必须配置 num_threads=1")
    if parameters["asr"].get("sample_rate", 16000) != 16000:
        raise ValueError("offline.asr.sample_rate 必须为 16000")
    if parameters["asr"].get("max_frame_samples", 1600) > 1600:
        raise ValueError("offline.asr.max_frame_samples 不能超过 1600")
    if parameters["llm"].get("context_tokens", 4096) < 128:
        raise ValueError("offline.llm.context_tokens 至少为 128")
    llm = parameters["llm"]
    if llm.get("micro_batch_tokens", 1) > llm.get("context_tokens", 4096):
        raise ValueError("offline.llm.micro_batch_tokens 不能超过上下文")
    if llm.get("cache_type", "f16") not in ("f16", "q8_0"):
        raise ValueError("offline.llm.cache_type 必须为 f16 或 q8_0")
    rules = parameters["tts"].get("rule_fsts")
    if not isinstance(rules, str) or not rules:
        raise ValueError("offline.tts.rule_fsts 必须配置")
    rule_paths = [
        Path(name).expanduser().resolve() for name in rules.split(",")
    ]
    if any(
        not path.is_file() or checkout in path.parents for path in rule_paths
    ):
        raise ValueError("rule_fsts 必须为源码外的资产文件")
    parameters["tts"]["rule_fsts"] = ",".join(map(str, rule_paths))
    for name in ("record_device", "play_device"):
        if not isinstance(config.get(name), str) or not config[name].strip():
            raise ValueError(name + " 必须显式配置")
    for name, default in (
        ("record_executable", "arecord"),
        ("play_executable", "aplay"),
    ):
        command = config.get(name, default)
        if not isinstance(command, str) or shutil.which(command) is None:
            raise ValueError(name + " 不可执行")
    for name, default in (
        ("shutdown_timeout", 5),
        ("startup_timeout", 120),
        ("provider_timeout", 60),
        ("speech_timeout", 60),
        ("silence_timeout", 120),
        ("asr_control_timeout", 2),
        ("capture_timeout", 10),
        ("action_timeout", 5),
    ):
        value = config.get(name, default)
        if (
            type(value) not in (int, float)
            or not math.isfinite(value)
            or value <= 0
        ):
            raise ValueError(name + " 必须为正有限秒数")
    control_timeout = config.get("asr_control_timeout", 2)
    if control_timeout > 5:
        raise ValueError("asr_control_timeout 必须不超过五秒")
    max_tokens = config.get("max_tokens", 512)
    if type(max_tokens) is not int or not 1 <= max_tokens <= 4096:
        raise ValueError("max_tokens 必须为 1..4096 整数")
    if config.get("speech_timeout", 60) > 300:
        raise ValueError("speech_timeout 不能超过 TTS 的 300 秒预算")
    for name, default in (
        ("model_attempts", 1),
        ("tts_attempts", 1),
        ("tts_failure_threshold", 5),
        ("memory_recent_turns", 6),
        ("memory_max_chars", 4096),
    ):
        value = config.get(name, default)
        if type(value) is not int or value < 1:
            raise ValueError(name + " 必须为正整数")
    for name, default in (
        ("playback_enabled", False),
        ("save_reply_audio", False),
        ("save_turn_records", True),
    ):
        if type(config.get(name, default)) is not bool:
            raise ValueError(name + " 必须为 JSON 布尔值")
    output = config.get("output_dir")
    if not isinstance(output, str) or not output:
        raise ValueError("output_dir 必须配置")
    directory = Path(output).expanduser().resolve()
    if directory == checkout or checkout in directory.parents:
        raise ValueError("output_dir 必须在源码目录外")
    return parameters
