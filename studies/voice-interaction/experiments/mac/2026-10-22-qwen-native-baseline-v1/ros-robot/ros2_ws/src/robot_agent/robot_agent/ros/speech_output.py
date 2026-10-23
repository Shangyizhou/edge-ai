"""完整单句 PCM 的 ROS Action Adapter；不创建播放器或推理子进程。"""

import asyncio
import math
import threading
import time
import uuid
from typing import Optional

from action_msgs.msg import GoalStatus
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from robot_interfaces.action import SynthesizeSpeech
from std_msgs.msg import String

from robot_audio.pcm import PcmAudio


class RosSpeechOutput:
    """事件循环拥有请求；取消等待后仍持有原 Goal 到原生计算终态。"""

    def __init__(self, node: Node) -> None:
        """复用业务 ROS node，在 executor 与 asyncio 之间交接回执。"""
        self._client = ActionClient(
            node, SynthesizeSpeech, "/inference/tts/synthesize"
        )
        self._state = "loading"
        self._state_subscription = node.create_subscription(
            String,
            "/inference/tts/state",
            self._receive_state,
            QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL),
        )
        self._active = None
        self._handle = None
        self._cancel_requested = False
        self._closed = False
        self._admitting = True
        self._handoff = threading.Lock()
        self._destinations = set()

    @property
    def idle(self) -> bool:
        """原 Goal 终态交付后才允许新一轮输入；取消接受不算完成。"""
        return self._active is None

    @property
    def ready(self) -> bool:
        """模型公布可用且 Action 可发现；最终准入仍由 Goal 决定。"""
        return (
            self._admitting
            and self._state == "ready"
            and self._client.server_is_ready()
        )

    @property
    def state(self) -> str:
        """返回最近的原生状态；只作观察，不推断在途 Goal 已结束。"""
        return self._state

    def _receive_state(self, message: String) -> None:
        """状态快照由 executor 原子替换，业务等待仍由 asyncio 拥有。"""
        if message.data in ("loading", "ready", "busy", "failed", "closing"):
            self._state = message.data

    async def synthesize(self, text: str, timeout: float) -> PcmAudio:
        """只交付完整成功结果；超时／取消请求撤销，迟到结果不复用。"""
        if not self._admitting:
            raise OSError("TTS Adapter 已关闭")
        if self._active is not None:
            raise OSError("TTS 原 Goal 尚未结束")
        if not self._client.server_is_ready():
            raise OSError("TTS Action 不可用")
        if not text or "\0" in text or len(text.encode("utf-8")) > 4096:
            raise ValueError("TTS 单句必须为 1–4096 UTF-8 字节")
        if not math.isfinite(timeout) or timeout <= 0 or timeout > 300:
            raise ValueError("TTS timeout 必须为 (0, 300] 秒")
        self._cancel_requested = False
        deadline = time.monotonic() + timeout
        self._active = asyncio.create_task(self._run(text, deadline))
        self._active.add_done_callback(self._finished)
        try:
            return await asyncio.wait_for(
                asyncio.shield(self._active), timeout
            )
        except (asyncio.CancelledError, asyncio.TimeoutError):
            self._request_cancel()
            raise

    async def _run(self, text: str, deadline: float) -> PcmAudio:
        """保留接受和结果 Future，拒绝、错误及非成功终态均显式失败。"""
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise asyncio.TimeoutError("TTS 预算已过，未发送 Goal")
        goal = SynthesizeSpeech.Goal()
        goal.request_id = uuid.uuid4().hex
        goal.text = text
        goal.budget_ms = max(1, math.ceil(remaining * 1000))
        handle = await self._wait_ros(self._client.send_goal_async(goal))
        if not handle.accepted:
            raise OSError("TTS Goal 被拒绝：模型未就绪、繁忙或请求无效")
        self._handle = handle
        if self._cancel_requested:
            self._request_cancel()
        response = await self._wait_ros(handle.get_result_async())
        result = response.result
        if self._cancel_requested:
            raise OSError("TTS 原 Goal 已取消，本地不接收迟到音频")
        if result.request_id != goal.request_id:
            raise OSError("TTS Result 请求归属错误")
        if (
            response.status != GoalStatus.STATUS_SUCCEEDED
            or not result.success
        ):
            raise OSError(
                "TTS 合成失败：" + result.error_code + " " + result.detail
            )
        pcm = bytes(result.pcm)
        if (
            result.encoding != "pcm_s16le"
            or result.channels != 1
            or not 0 < result.sample_rate <= 192000
            or not pcm
            or len(pcm) % 2
            or len(pcm) > 8388608
        ):
            raise OSError("TTS Result PCM 格式或长度无效")
        return PcmAudio(pcm, result.sample_rate, result.channels)

    async def _wait_ros(self, original):
        """executor 不直接修改 asyncio Future；关闭后只领取传输异常。"""
        loop = asyncio.get_running_loop()
        destination = loop.create_future()
        self._destinations.add(destination)
        retired = False

        def deliver():
            """只在请求所属事件循环交付一次结果。"""
            if destination.done():
                return
            error = original.exception()
            if error is None:
                destination.set_result(original.result())
            else:
                destination.set_exception(error)

        def receive(_):
            """锁保证关闭与跨线程交接不会交错写入已关闭循环。"""
            with self._handoff:
                if not self._closed and not retired:
                    loop.call_soon_threadsafe(deliver)
                else:
                    original.exception()

        original.add_done_callback(receive)
        try:
            return await destination
        finally:
            # 等待取消即退役交接，不依赖稍后的 Adapter 关闭。
            with self._handoff:
                retired = True
            self._destinations.discard(destination)

    def _finished(self, task) -> None:
        """领取迟到失败并在实际结果到达后才释放本地准入槽位。"""
        if not task.cancelled():
            task.exception()
        if self._active is task:
            self._active = None
            self._handle = None

    def _request_cancel(self) -> None:
        """取消只请求停止；继续等待原 Action 终态而不开放并发推理。"""
        self._cancel_requested = True
        if self._handle is not None:
            future = self._handle.cancel_goal_async()
            future.add_done_callback(lambda response: response.exception())

    def stop(self) -> None:
        """同步关闭新请求入口，接受延迟返回时仍补发原 Goal 取消。"""
        self._admitting = False
        self._request_cancel()

    async def aclose(self, deadline: Optional[float] = None) -> None:
        """保留回执直到共享退出期限，随后断开本地交接并释放 client。"""
        self.stop()
        if self._active is not None:
            await asyncio.wait(
                {self._active},
                timeout=0
                if deadline is None
                else max(0, deadline - time.monotonic()),
            )
        with self._handoff:
            if self._closed:
                return
            self._closed = True
        for destination in self._destinations:
            destination.cancel()
        if self._active is not None:
            self._active.cancel()
            await asyncio.gather(self._active, return_exceptions=True)
        # executor 停止后再销毁 ROS 实体，避免 wait-set 竞态。

    def destroy_ros_entities(self) -> None:
        """仅由已停止 executor 的 ROS 所有者在销毁 node 前调用。"""
        self._client.destroy()
