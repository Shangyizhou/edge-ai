"""交互共同组装：接纳推理 Adapters，保留在线依赖和配置默认值。"""

import json
import math
from pathlib import Path
from typing import Dict, Optional, Union

from robot_agent.actions.capabilities import (
    ActionCapabilities,
    create_default_actions,
)
from robot_agent.actions.registry import ActionRegistry
from robot_agent.application import AgentApplication
from robot_agent.conversation.agent import Agent
from robot_agent.conversation.memory import (
    ConversationMemory,
    RecentConversationMemory,
)
from robot_agent.conversation.provider import DashScopeProvider, Model
from robot_agent.offline_config import select_backend
from robot_agent.voice.live_input import LiveSpeechInput, SpeechInput
from robot_agent.voice.output import Playback, SpeechOutput
from robot_agent.voice.speech import DashScopeASR, DashScopeTTS
from robot_audio.async_pcm_input import AsyncPcmMicrophone
from robot_audio.async_playback import AsyncPcmPlayer

DEFAULT_ACTION_TIMEOUT = 5.0
DEFAULT_SHUTDOWN_TIMEOUT = 5.0


def shutdown_timeout(config: Dict) -> float:
    """退出预算在外部配置边缘统一验证，后代只接收绝对期限。"""
    timeout = float(config.get("shutdown_timeout", DEFAULT_SHUTDOWN_TIMEOUT))
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("shutdown_timeout 必须为正有限秒数")
    return timeout


def load_config(filename: Union[str, Path]) -> Dict:
    """读取JSON配置对象；文件、语法和形状错误直接向调用者显露。"""
    config = json.loads(
        Path(filename).expanduser().read_text(encoding="utf-8")
    )
    if not isinstance(config, dict):
        raise ValueError("在线配置必须是JSON对象")
    return config


def build_agent(
    config: Dict,
    actions: Optional[ActionRegistry] = None,
    *,
    model: Optional[Model] = None,
) -> Agent:
    """组装同一 Agent 并接管模型；未注入时沿用在线模型和记忆配置。"""
    if actions is None:
        actions = create_default_actions().registry
    if model is None:
        if config.get("backend") == "offline":
            raise ValueError("offline 后端必须注入本地 Model")
        model = DashScopeProvider(config)
    return Agent(
        model,
        actions,
        provider_timeout=float(config.get("provider_timeout", 60)),
        model_attempts=config.get("model_attempts", 3),
        action_timeout=float(
            config.get("action_timeout", DEFAULT_ACTION_TIMEOUT)
        ),
        memory=RecentConversationMemory(
            recent_turns=config.get("memory_recent_turns", 6),
            max_chars=config.get("memory_max_chars", 4096),
        )
        if config.get("backend") == "offline"
        else ConversationMemory(
            Path(
                config.get(
                    "memory_file",
                    "~/.local/state/ros-robot/conversation-summary.json",
                )
            ),
            recent_turns=config.get("memory_recent_turns", 6),
            summary_trigger=config.get("memory_summary_trigger", 6),
        ),
    )


def build_application(
    config: Dict,
    capabilities: Optional[ActionCapabilities] = None,
    speech_input: Optional[SpeechInput] = None,
    *,
    input_mode: str = "recording",
    model: Optional[Model] = None,
    speech_output: Optional[SpeechOutput] = None,
    playback: Optional[Playback] = None,
) -> AgentApplication:
    """接管注入的推理与播放资源；未注入的槽位按在线配置创建。

    显式播放器优先于 playback_enabled；返回应用负责所有依赖的关闭，
    共用 shutdown_timeout。输入已注入时不创建持续或文件识别依赖。
    """
    backend = select_backend(config)
    if backend == "offline" and any(
        item is None for item in (model, speech_input, speech_output)
    ):
        raise ValueError("offline 后端必须注入本地输入、Model 和输出")
    close_timeout = shutdown_timeout(config)
    save_reply_audio = config.get("save_reply_audio", False)
    save_turn_records = config.get("save_turn_records", True)
    for name, value in (
        ("save_reply_audio", save_reply_audio),
        ("save_turn_records", save_turn_records),
    ):
        if type(value) is not bool:
            raise ValueError(name + " 必须为 JSON 布尔值")
    directory = Path(config["output_dir"]).expanduser().resolve()
    checkout = Path(__file__).resolve().parents[4]
    if directory == checkout or checkout in directory.parents:
        raise ValueError("output_dir 必须在源码目录外")
    if capabilities is None:
        capabilities = create_default_actions()
    if playback is None and config.get("playback_enabled", False):
        playback = AsyncPcmPlayer(
            config.get("play_executable", "aplay"),
            config.get("play_device", "default"),
        )

    recording_input = None
    if speech_input is None:
        if input_mode == "microphone":
            speech_input = LiveSpeechInput(
                config,
                AsyncPcmMicrophone(
                    config.get("record_executable", "arecord"),
                    config.get("record_device", "default"),
                ),
            )
        elif input_mode == "recording":
            recording_input = DashScopeASR(config)
        else:
            raise ValueError("未知语音输入模式")

    if speech_output is None:
        speech_output = DashScopeTTS(config)
    voice = AgentApplication(
        build_agent(config, capabilities.registry, model=model),
        speech_input,
        speech_output,
        directory,
        music_playing=capabilities.music_playing,
        playback=playback,
        silence_timeout=float(config.get("silence_timeout", 120)),
        speech_timeout=float(config.get("speech_timeout", 60)),
        tts_attempts=int(config.get("tts_attempts", 3)),
        failure_threshold=int(config.get("tts_failure_threshold", 5)),
        retry_delay=float(config.get("tts_retry_delay", 1)),
        recording_input=recording_input,
        shutdown_timeout=close_timeout,
        save_reply_audio=save_reply_audio,
        save_turn_records=save_turn_records,
    )

    return voice
