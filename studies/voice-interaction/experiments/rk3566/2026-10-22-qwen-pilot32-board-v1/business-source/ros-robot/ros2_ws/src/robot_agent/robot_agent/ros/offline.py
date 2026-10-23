"""离线 ROS 组装资源：等待真实加载与传输发现，保留两阶段销毁。"""

import asyncio
import time
from typing import Dict

from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from std_msgs.msg import String

from robot_agent.ros.model import RosModel
from robot_agent.ros.speech_input import RosSpeechInput
from robot_agent.ros.speech_output import RosSpeechOutput
from robot_audio.async_pcm_input import AsyncPcmMicrophone


class RosInference:
    """拥有本地 Adapters；应用先关闭它们，executor 停止后才销毁实体。"""

    def __init__(self, node: Node, config: Dict) -> None:
        """接收入口已验证的配置；启动确认之前不打开采集。"""
        parameters = config["offline"]
        self.model = RosModel(node, max_tokens=config.get("max_tokens", 512))
        self.output = RosSpeechOutput(node)
        self.input = RosSpeechInput(
            node,
            AsyncPcmMicrophone(
                config.get("record_executable", "arecord"),
                config["record_device"],
            ),
            frame_samples=parameters["asr"].get("max_frame_samples", 1600),
            control_timeout=config.get("asr_control_timeout", 2.0),
            capture_timeout=config.get("capture_timeout", 10.0),
        )
        self._states = {"asr": "loading", "llm": "loading"}
        self._subscriptions = []
        for kind in self._states:
            self._subscriptions.append(
                node.create_subscription(
                    String,
                    "/inference/" + kind + "/status",
                    lambda message, name=kind: self._states.__setitem__(
                        name, message.data
                    ),
                    QoSProfile(
                        depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL
                    ),
                )
            )

    async def wait_ready(self, timeout: float) -> None:
        """加载状态与 Action 发现共同决定启动，失败或超时显式退出。"""
        deadline = time.monotonic() + timeout
        while True:
            states = dict(self._states, tts=self.output.state)
            if any(
                state in ("failed", "closing") for state in states.values()
            ):
                raise OSError("本地推理启动失败：" + str(states))
            if (
                all(state == "ready" for state in states.values())
                and self.model.ready
                and self.output.ready
            ):
                return
            if time.monotonic() >= deadline:
                raise asyncio.TimeoutError("本地推理未就绪：" + str(states))
            # 轮询发现状态，不以等待了固定时长代替可用性证明。
            await asyncio.sleep(0.01)

    def destroy_ros_entities(self) -> None:
        """调用者必须已停止并回收 executor，然后才能销毁 node。"""
        self.model.destroy_ros_entities()
        self.output.destroy_ros_entities()
