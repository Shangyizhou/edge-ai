"""本地 LLM ROS Action Adapter；事件循环拥有请求准入和最终交付。"""

import asyncio
import threading
import time
import uuid
from collections import deque
from typing import Optional

from action_msgs.msg import GoalStatus
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.qos import QoSProfile
from robot_interfaces.action import GenerateReply
from unique_identifier_msgs.msg import UUID

from robot_agent.conversation.local_model import LocalModel
from robot_agent.conversation.provider import (
    ModelProtocolError,
    ModelTransportError,
)


class RosModel(LocalModel):
    """每次只拥有一个 Action Goal，取消后仍等待原生终态。"""

    def __init__(
        self,
        node: Node,
        *,
        action_name: str = "/inference/llm/generate",
        max_tokens: int = 512,
    ) -> None:
        """沿用应用 ROS node；不创建额外 executor 或模型进程。"""
        if type(max_tokens) is not int or not 1 <= max_tokens <= 4096:
            raise ValueError("LLM max_tokens 必须为 1..4096 整数")
        self._client = ActionClient(
            node,
            GenerateReply,
            action_name,
            feedback_sub_qos_profile=QoSProfile(depth=256),
        )
        self._feedback_callback = None
        self._feedback_goal_id = None
        # Foxy 在 Result 到达时删除反馈回调，需独立订阅标准通道。
        # 按 final_sequence 收齐，不能假定跨通道到达顺序。
        self._feedback_subscription = node.create_subscription(
            GenerateReply.Impl.FeedbackMessage,
            action_name.rstrip("/") + "/_action/feedback",
            self._receive_feedback,
            QoSProfile(depth=256),
        )
        self._node = node
        self._max_tokens = max_tokens
        self._active = None
        self._closed = False
        self._retirements = set()
        self._retirement_error = None
        super().__init__(
            self._generate_action,
            stream_generate=self._generate_action,
            close=self._close_action,
        )

    def _receive_feedback(self, message):
        """发送前确定 Goal UUID；早于 GoalResponse 的反馈也有归属。"""
        callback = self._feedback_callback
        if (
            callback is not None
            and bytes(message.goal_id.uuid) == self._feedback_goal_id
        ):
            callback(message)

    @property
    def idle(self) -> bool:
        """原生请求和退役均结束后，应用才可重新开放普通输入。"""
        return (
            self._retirement_error is None
            and (self._active is None or self._active.done())
            and all(task.done() for task in self._retirements)
        )

    @property
    def ready(self) -> bool:
        """公开 Action 发现事实；原生加载事实由启动状态另行确认。"""
        return not self._closed and self._client.server_is_ready()

    async def _bridge(self, original):
        """executor 仅线程安全交接，迟到结果不完成已取消等待。"""
        loop = asyncio.get_running_loop()
        destination = loop.create_future()

        def deliver():
            """在业务循环中领取 ROS 结果。"""
            if destination.done():
                return
            error = original.exception()
            if error is not None:
                destination.set_exception(error)
            else:
                destination.set_result(original.result())

        def receive(_):
            """应用关闭前保持原请求生命周期。"""
            if not loop.is_closed():
                loop.call_soon_threadsafe(deliver)

        original.add_done_callback(receive)
        return await destination

    async def _generate_action(self, prompt, deadline, consume=None):
        """期限结束请求取消，但资源忙碌持续到原 Goal 终态。"""
        if self._closed:
            raise ModelTransportError("closed")
        if self._retirement_error is not None:
            raise self._retirement_error
        if self._active is not None:
            raise ModelTransportError("busy")
        if not self._client.server_is_ready():
            raise ModelTransportError("not_ready")
        goal = GenerateReply.Goal()
        goal.request_id = uuid.uuid4().hex
        goal.prompt = prompt
        goal.budget_seconds = max(0.0, deadline - time.monotonic())
        goal.max_tokens = self._max_tokens
        if goal.budget_seconds <= 0:
            raise ModelTransportError("timeout")
        task = asyncio.create_task(
            self._run_stream_goal(goal, deadline, consume)
            if consume is not None
            else self._run_goal(goal, deadline)
        )
        self._active = task
        task.add_done_callback(self._finished)
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            task.cancel()
            raise
        finally:
            if task.done() and self._active is task:
                self._active = None

    def _finished(self, task):
        """发送前取消也须退役；已发送 Goal 由清理任务接管。"""
        if self._active is task:
            self._active = None
        if not task.cancelled():
            task.exception()

    async def _run_stream_goal(self, goal, deadline, consume):
        """Feedback 失败取消原 Goal；有界缓存不能静默丢掉协议片段。"""
        loop = asyncio.get_running_loop()
        queue = asyncio.Queue(maxsize=256)
        overflow = loop.create_future()
        accepting = True
        sequence = 0
        received = asyncio.Event()
        incoming = deque()
        handoff_lock = threading.Lock()
        scheduled = False
        admitted = 0
        handoff_error = None

        def deliver():
            """至多一个待调度回调；线程缓存和异步消费共同占用256份额度。"""
            nonlocal sequence, scheduled
            with handoff_lock:
                batch = tuple(incoming)
                incoming.clear()
                error = handoff_error
                scheduled = False
            if not accepting or overflow.done():
                return
            if error is not None:
                overflow.set_exception(error)
                return
            for feedback in batch:
                if (
                    feedback.request_id != goal.request_id
                    or feedback.sequence != sequence + 1
                    or feedback.output_contract != "fc-first-v1"
                ):
                    overflow.set_exception(
                        ModelProtocolError("LLM Feedback 契约无效")
                    )
                    return
                queue.put_nowait(feedback.text_delta)
                sequence += 1
                received.set()

        def receive(message):
            """ROS 线程先限流，避免事件循环待执行回调无界增长。"""
            nonlocal admitted, scheduled, handoff_error
            with handoff_lock:
                if not accepting or handoff_error is not None:
                    return
                if (
                    admitted >= 256
                    or len(message.feedback.text_delta.encode("utf-8")) > 4096
                ):
                    handoff_error = ModelProtocolError(
                        "LLM Feedback 线程交接溢出"
                    )
                else:
                    incoming.append(message.feedback)
                    admitted += 1
                if scheduled:
                    return
                scheduled = True
            if not loop.is_closed():
                loop.call_soon_threadsafe(deliver)

        async def drain():
            """单消费者保留协议顺序，并向上层传播合成或播放失败。"""
            nonlocal admitted
            while True:
                delta = await queue.get()
                if delta is None:
                    return
                await consume(delta)
                with handoff_lock:
                    admitted -= 1

        goal_uuid = UUID(uuid=list(uuid.uuid4().bytes))
        self._feedback_goal_id = bytes(goal_uuid.uuid)
        self._feedback_callback = receive
        generation = asyncio.create_task(
            self._run_goal(goal, deadline, goal_uuid)
        )
        consumer = asyncio.create_task(drain())
        try:
            await asyncio.wait(
                {generation, consumer, overflow},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if overflow.done():
                overflow.result()
            if consumer.done():
                consumer.result()
            response = await generation
            while sequence < response.final_sequence:
                received.clear()
                arrival = asyncio.create_task(received.wait())
                try:
                    done, _ = await asyncio.wait(
                        {arrival, consumer, overflow},
                        timeout=max(0, deadline - time.monotonic()),
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if not done:
                        raise ModelTransportError("feedback_seal_timeout")
                    if overflow.done():
                        overflow.result()
                    if consumer.done():
                        consumer.result()
                finally:
                    arrival.cancel()
                    await asyncio.gather(arrival, return_exceptions=True)
            if sequence != response.final_sequence:
                raise ModelProtocolError("LLM Feedback 封口序号无效")
            raw = response.output
            accepting = False

            async def finish():
                """最终封口也受原回合期限约束，包括合成和播放消费者。"""
                await queue.put(None)
                await consumer

            await asyncio.wait_for(
                finish(), max(0, deadline - time.monotonic())
            )
            return raw
        finally:
            accepting = False
            self._feedback_callback = None
            self._feedback_goal_id = None
            for task in (generation, consumer):
                if not task.done():
                    task.cancel()
            await asyncio.gather(generation, consumer, return_exceptions=True)
            if not overflow.done():
                overflow.cancel()
            elif not overflow.cancelled():
                overflow.exception()
            # 回调失败先取消原生请求，尚有回合预算时等待其真实终态。
            retirement = self._active
            if retirement in self._retirements:
                done, _ = await asyncio.wait(
                    {retirement}, timeout=max(0, deadline - time.monotonic())
                )
                if done:
                    retirement.result()

    async def _run_goal(self, goal, deadline, goal_uuid=None):
        """取消可能早于 Goal 接收；仍领取句柄并取消原请求。"""
        handle = None
        acceptance = asyncio.create_task(
            self._bridge(
                self._client.send_goal_async(goal, goal_uuid=goal_uuid)
            )
        )
        result = None
        try:
            handle = await asyncio.wait_for(
                asyncio.shield(acceptance), max(0, deadline - time.monotonic())
            )
            if not handle.accepted:
                raise ModelTransportError("rejected")
            result = asyncio.create_task(
                self._bridge(handle.get_result_async())
            )
            response = await asyncio.wait_for(
                asyncio.shield(result), max(0, deadline - time.monotonic())
            )
            if (
                response.status != GoalStatus.STATUS_SUCCEEDED
                or not response.result.success
            ):
                raise ModelTransportError(
                    response.result.error_code or "failed"
                )
            return (
                response.result
                if goal_uuid is not None
                else response.result.output
            )
        except (asyncio.TimeoutError, asyncio.CancelledError) as error:
            # 取消接受不代表 native 停止；终态前仍保持忙碌。
            cleanup = asyncio.create_task(
                self._retire(acceptance, handle, result)
            )
            self._active = cleanup
            self._retirements.add(cleanup)
            cleanup.add_done_callback(self._retired)
            if isinstance(error, asyncio.TimeoutError):
                raise ModelTransportError("timeout") from error
            raise

    async def _retire(self, acceptance, handle, result):
        """无论接收回执早晚，都只取消原 Goal 并等待其最终退出。"""
        if handle is None:
            handle = await acceptance
        if handle.accepted:
            await self._bridge(handle.cancel_goal_async())
            if result is None:
                result = asyncio.create_task(
                    self._bridge(handle.get_result_async())
                )
            await result

    def _retired(self, task):
        """领取异步收尾错误；下一次调用不复用尚未退役的原请求。"""
        self._retirements.discard(task)
        error = (
            ModelTransportError("retirement_cancelled")
            if task.cancelled()
            else task.exception()
        )
        if error is not None:
            self._retirement_error = error
            return
        if self._active is task:
            self._active = None

    async def _close_action(self, deadline: Optional[float] = None):
        """关闭准入并在共享期限内结束本地等待，不拥有 node 生命周期。"""
        self._closed = True
        task = self._active
        if task is not None and task not in self._retirements:
            task.cancel()
        while self._active is not None:
            if self._retirement_error is not None:
                raise self._retirement_error
            task = self._active
            done, _ = await asyncio.wait(
                {task},
                timeout=max(
                    0, (deadline or time.monotonic()) - time.monotonic()
                ),
            )
            if not done:
                raise asyncio.TimeoutError("LLM 原生请求尚未退役")
            if self._active is task:
                self._active = None
        # Foxy wait-set 可能仍引用 Action entity；实体由停止 executor
        # 后通过 destroy_ros_entities 释放，避免并发销毁段错误。

    def destroy_ros_entities(self) -> None:
        """executor 停止后销毁 Action 实体，必须先于 node 销毁。"""
        self._client.destroy()
        self._node.destroy_subscription(self._feedback_subscription)
