"""本地 ASR Adapter：采集归 Python，ROS worker 只拥有识别流。"""

import asyncio
import math
import threading
import time
import uuid
from collections import deque
from typing import Optional

from rclpy.node import Node
from robot_interfaces.msg import AsrAudio, AsrEvent
from robot_interfaces.srv import SetAsrInput

from robot_agent.voice.live_input import PcmInput

MAX_PENDING_EVENTS = 16


class RosSpeechInput:
    """本地门禁立即关闭；只有新流实际确认后才发布 PCM、交付 final。"""

    def __init__(
        self,
        node: Node,
        source: PcmInput,
        *,
        sample_rate: int = 16000,
        frame_samples: int = 1600,
        control_timeout: float = 2.0,
        capture_timeout: float = 10.0,
    ) -> None:
        """创建 ROS 边缘资源；不在构造期间打开声卡。"""
        if sample_rate != 16000 or not 0 < frame_samples <= 1600:
            raise ValueError("本地 ASR 仅支持 16kHz、至多 1600 采样帧")
        if (
            not 0 < control_timeout <= 5
            or not math.isfinite(capture_timeout)
            or capture_timeout <= 0
        ):
            raise ValueError("ASR 控制期限必须在 0–5 秒，采集期限必须为正")
        self._node = node
        self._source = source
        self._sample_rate = sample_rate
        self._frame_bytes = frame_samples * 2
        self._control_timeout = control_timeout
        self._capture_timeout = capture_timeout
        self._audio = node.create_publisher(
            AsrAudio, "/inference/asr/audio", 10
        )
        self._control = node.create_client(
            SetAsrInput, "/inference/asr/set_input"
        )
        self._subscription = node.create_subscription(
            AsrEvent, "/inference/asr/events", self._receive, 10
        )
        self._loop = None
        self._runner = None
        self._closing = None
        self._source_closing = None
        self._changed = None
        self._control_changed = None
        self._generation = 0
        self._wanted = True
        self._ready = False
        self._closed = False
        self._started = False
        self._stream = ""
        self._sequence = 0
        self._last_final = -1
        self._text = None
        self._error = None
        self._pending = set()
        self._handoff = threading.Lock()
        self._callbacks_open = True
        self._events = deque()
        self._events_scheduled = False
        self._events_overflow = False
        self._deadline = None

    async def listen(self, timeout: float = 0.2) -> Optional[str]:
        """等待单次最终句；正常等待超时不改变会话或识别流。"""
        if self._closed:
            return None
        if self._runner is None:
            self._loop = asyncio.get_running_loop()
            self._changed = asyncio.Event()
            self._control_changed = asyncio.Event()
            self._control_changed.set()
            self._runner = asyncio.create_task(self._run())
            self._runner.add_done_callback(lambda _: self._changed.set())
        try:
            if self._text is None and self._error is None:
                try:
                    await asyncio.wait_for(self._changed.wait(), timeout)
                except asyncio.TimeoutError:
                    return None
            self._changed.clear()
            if self._runner.done():
                self._runner.result()
            if self._error is not None:
                raise self._error
            text, self._text = self._text, None
            return text
        except asyncio.CancelledError:
            await self.aclose()
            raise

    def pause(self) -> None:
        """同步封闭交付，再通知后台控制；在途应答不能重新开启旧流。"""
        self._request(False)

    def resume(self) -> None:
        """新流确认之前持续丢弃音频，包括控制应答前读取的半帧。"""
        if not self._closed:
            self._request(True)

    def _request(self, enabled: bool) -> None:
        """事件循环独占门禁和代数；同状态请求仍使旧读取失效。"""
        self._ready = False
        self._text = None
        self._wanted = enabled
        self._generation += 1
        if self._started:
            self._source.discard()
        if self._control_changed is not None:
            self._control_changed.set()

    def _receive(self, message: AsrEvent) -> None:
        """ROS executor 仅跨线程交接，业务状态由应用循环串行更新。"""
        with self._handoff:
            if (
                self._loop is None
                or self._closed
                or not self._callbacks_open
                or self._error is not None
            ):
                return
            if not self._events_overflow:
                if len(self._events) >= MAX_PENDING_EVENTS:
                    self._events.clear()
                    self._events_overflow = True
                else:
                    self._events.append(message)
            if not self._events_scheduled:
                self._events_scheduled = True
                self._loop.call_soon_threadsafe(self._drain_events)

    def _drain_events(self) -> None:
        """最多交接一批十六条；溢出使输入失效，不静默保留某个 final。"""
        with self._handoff:
            events = tuple(self._events)
            overflow = self._events_overflow
            self._events.clear()
            self._events_overflow = False
            self._events_scheduled = False
        if self._closed:
            return
        if overflow:
            self.pause()
            self._error = OSError("本地 ASR 事件积压，输入不可用")
            self._changed.set()
            return
        for message in events:
            self._accept(message)

    def _accept(self, message: AsrEvent) -> None:
        """partial 不交付；final 只接纳一次，旧流结果丢弃。"""
        if (
            self._closed
            or not self._ready
            or message.stream_id != self._stream
        ):
            return
        if message.kind == "error":
            self._ready = False
            self._error = OSError("本地 ASR 输入不可用：" + message.detail)
            self._changed.set()
            return
        if message.kind not in ("partial", "final"):
            self._error = OSError("本地 ASR 事件类型无效")
            self._ready = False
            self._changed.set()
            return
        if (
            message.kind != "final"
            or message.utterance_id <= self._last_final
            or not message.text.strip()
        ):
            return
        self._last_final = message.utterance_id
        text = message.text
        self.pause()
        self._text = text
        self._changed.set()

    async def _call_control(self, enabled: bool, stream: str):
        """超时不宣称控制成功；迟到应答仍被领取，不重新打开门禁。"""
        expires = time.monotonic() + self._control_timeout
        while not self._control.service_is_ready():
            if time.monotonic() >= expires:
                raise OSError("本地 ASR 控制 Service 就绪超时")
            await asyncio.sleep(0.02)
        request = SetAsrInput.Request()
        request.stream_id = stream
        request.enabled = enabled
        request.timeout_ms = max(1, int((expires - time.monotonic()) * 1000))
        original = self._control.call_async(request)
        destination = self._loop.create_future()
        self._pending.add(original)

        def deliver():
            """原 ROS Future 先回收，即使本地已取消等待。"""
            self._pending.discard(original)
            error = original.exception()
            if destination.done():
                return
            if error is not None:
                destination.set_exception(OSError("ASR 控制传输失败"))
            else:
                destination.set_result(original.result())

        def receive(_):
            """只向仍运行的应用循环交接。"""
            with self._handoff:
                if self._callbacks_open:
                    self._loop.call_soon_threadsafe(deliver)
                else:
                    original.exception()

        original.add_done_callback(receive)
        try:
            response = await asyncio.wait_for(
                destination, max(0.001, expires - time.monotonic())
            )
        except asyncio.TimeoutError as error:
            raise OSError("本地 ASR 控制超时，输入不可用") from error
        if not response.applied or response.stream_id != stream:
            raise OSError("本地 ASR 控制未应用：" + response.detail)
        return response

    async def _controls(self) -> None:
        """逐次控制，只有最新代且实际启用成功才重新接纳音频。"""
        while not self._closed:
            await self._control_changed.wait()
            self._control_changed.clear()
            generation = self._generation
            enabled = self._wanted
            stream = uuid.uuid4().hex
            await self._call_control(enabled, stream)
            if self._closed or generation != self._generation:
                continue
            self._stream = stream
            self._sequence = 0
            self._last_final = -1
            self._generation += 1
            self._source.discard()
            self._ready = enabled

    async def _capture(self) -> None:
        """持续排空采集；暂停发言不保留，恢复应答前的帧不发布。"""
        last_frame = time.monotonic()
        while not self._closed:
            generation = self._generation
            frame = await self._source.read(self._frame_bytes, 0.2)
            if frame is None:
                if time.monotonic() - last_frame >= self._capture_timeout:
                    raise OSError("本地 ASR PCM 采集超时")
                continue
            last_frame = time.monotonic()
            if len(frame) != self._frame_bytes:
                raise OSError("本地 ASR PCM 帧不完整")
            if (
                self._closed
                or not self._ready
                or generation != self._generation
            ):
                continue
            message = AsrAudio()
            message.stream_id = self._stream
            message.sequence = self._sequence
            message.captured_at_ns = time.time_ns()
            message.sample_rate = self._sample_rate
            message.pcm = list(frame)
            self._audio.publish(message)
            self._sequence += 1

    async def _run(self) -> None:
        """输入失败先清理采集资源，再通过 listen 暴露错误。"""
        tasks = []
        try:
            await self._source.start()
            self._started = True
            tasks = [
                asyncio.create_task(self._controls()),
                asyncio.create_task(self._capture()),
            ]
            done, _ = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_COMPLETED
            )
            for task in done:
                await task
        except OSError as error:
            self._error = error
        finally:
            self._ready = False
            for task in tasks:
                if not task.done():
                    task.cancel()
            try:
                await asyncio.gather(*tasks, return_exceptions=True)
            finally:
                await self._close_source(self._deadline)
                self._changed.set()

    def stop(self) -> None:
        """立即关闭音频和结果门禁；异步关闭负责回收持有资源。"""
        self._closed = True
        self._ready = False
        self._generation += 1
        self._text = None
        if self._changed is not None:
            self._changed.set()

    async def aclose(self, deadline: Optional[float] = None) -> None:
        """共享关闭任务；停止 native 输入失败仍释放本地资源。"""
        if self._closing is None:
            self._deadline = deadline
            self.stop()
            self._closing = asyncio.create_task(self._close(deadline))
        await asyncio.shield(self._closing)

    async def _close(self, deadline: Optional[float]) -> None:
        """关闭不重启控制，不将无法确认的 native 停止说成成功。"""
        failure = None
        try:
            if self._runner is not None:
                self._runner.cancel()
                results = await asyncio.gather(
                    self._runner, return_exceptions=True
                )
                if isinstance(results[0], Exception) and not isinstance(
                    results[0], OSError
                ):
                    failure = results[0]
                try:
                    remaining = self._control_timeout
                    if deadline is not None:
                        remaining = min(
                            remaining, max(0, deadline - time.monotonic())
                        )
                    if remaining > 0:
                        await asyncio.wait_for(
                            self._call_control(False, uuid.uuid4().hex),
                            remaining,
                        )
                except (OSError, asyncio.TimeoutError):
                    pass
        finally:
            try:
                await self._close_source(deadline)
            finally:
                with self._handoff:
                    self._callbacks_open = False
                    self._events.clear()
                self._pending.clear()
        # Foxy executor 仍可能读取实体，由 node 在 executor 停止后销毁。
        if failure is not None:
            raise failure

    async def _close_source(self, deadline: Optional[float]) -> None:
        """采集只关闭一次；重复取消不遗失正在回收的采集资源。"""
        if self._source_closing is None:
            self._source_closing = asyncio.create_task(
                self._source.aclose(deadline)
            )
        await asyncio.shield(self._source_closing)
