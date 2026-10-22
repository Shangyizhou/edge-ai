"""DashScope HTTP Adapter：拥有请求生命周期，协议校验委托私有解析器。"""

import asyncio
import json
import os
import time
from importlib import resources
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Optional, Protocol, Tuple
from urllib.request import getproxies

import httpx

from robot_agent.conversation._model_protocol import (
    MAX_MODEL_OUTPUT_BYTES,
    MAX_SSE_LINE_BYTES,
    ModelProtocolError,
    parse_model_reply,
)
from robot_agent.diagnostics import get_logger, redact_payload, safe_url
from robot_agent.results import ModelReply, _json_value
from robot_agent.shutdown import finish_tasks

LOGGER = get_logger(__name__)


DEFAULT_ENDPOINT = (
    "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
)
WAIT_LOG_INTERVAL = 5.0


class ModelTransportError(Exception):
    """已分类的外部模型故障，只有明确暂时故障允许有限重试。"""

    def __init__(self, code: str, *, transient: bool = False) -> None:
        """只保留脱敏错误代码和重试分类。"""
        super().__init__(code)
        self.code = code
        self.transient = transient


class Model(Protocol):
    """异步模型 Interface；deadline 是所有等待共用的绝对期限。"""

    async def complete(
        self,
        text: str,
        deadline: float,
        *,
        tools: Optional[Tuple[Dict[str, Any], ...]] = None,
    ) -> ModelReply:
        """tools 为空时禁用工具，用于只读摘要。"""
        ...

    async def aclose(self, deadline: Optional[float] = None) -> None:
        """释放模型连接和本地请求资源。"""
        ...


class IncrementalModel(Model, Protocol):
    """可选增量 Interface；旧在线 Implementation 只需完整 Model。"""

    incremental: bool

    async def complete_incremental(
        self,
        text: str,
        deadline: float,
        on_text: Callable[[str], Awaitable[None]],
        *,
        tools: Optional[Tuple[Dict[str, Any], ...]] = None,
    ) -> ModelReply:
        """仅交付资格已确立的增量；最终结果不重复构成另一份输出。"""
        ...


class DashScopeProvider:
    """原生异步 HTTP Adapter，独占并关闭请求响应和连接池。"""

    def __init__(
        self, config: dict, *, client: Optional[httpx.AsyncClient] = None
    ) -> None:
        """加载非敏感配置，凭证只从环境读取，在线端点必须 HTTPS。"""
        if "api_key" in config:
            raise ValueError("配置使用 api_key_env，不允许明文 api_key")
        self._key = os.environ[config.get("api_key_env", "DASHSCOPE_API_KEY")]
        self._endpoint = config.get("endpoint", DEFAULT_ENDPOINT)
        if not self._endpoint.startswith("https://"):
            raise ValueError("在线端点必须使用 HTTPS")
        self._model = config.get("model", "qwen-plus")
        self._tool_examples = []
        prompt_file = config.get("system_prompt_file")
        if prompt_file is None:
            self._system_prompt = resources.read_text(
                "robot_agent.conversation",
                "online_system_prompt.txt",
                encoding="utf-8",
            )
            self._tool_examples = json.loads(
                resources.read_text(
                    "robot_agent.conversation",
                    "tool_call_examples.json",
                    encoding="utf-8",
                )
            )
        else:
            self._system_prompt = (
                Path(prompt_file).expanduser().read_text(encoding="utf-8")
            )
        if not self._system_prompt.strip():
            raise ValueError("system prompt 文件不能为空")
        self._network = config.get("model_network", "environment")
        if self._network not in ("direct", "environment"):
            raise ValueError("model_network 必须为 direct 或 environment")
        self._log_payload = config.get("log_http_payload", False)
        if type(self._log_payload) is not bool:
            raise ValueError("log_http_payload 必须为 JSON 布尔值")
        self._injected_client = client is not None
        self._client = client or httpx.AsyncClient(
            trust_env=self._network == "environment"
        )
        self._requests = set()
        self._cancelling = set()
        self._closed = False

    def _example_messages(
        self, tools: Optional[Tuple[Dict[str, Any], ...]]
    ) -> list:
        """示例只演示本次目录支持的动作；从不调用实现或冒充设备事实。"""
        if not tools or not self._tool_examples:
            return []
        supported = {definition["name"] for definition in tools}
        messages = []
        for index, example in enumerate(self._tool_examples):
            example_calls = example.get("calls")
            if example_calls is not None and not all(
                item["name"] in supported for item in example_calls
            ):
                continue
            messages.append({"role": "user", "content": example["user"]})
            if example_calls is None:
                messages.append(
                    {"role": "assistant", "content": example["reply"]}
                )
                continue
            calls = [
                {
                    "id": "example_call_{}_{}".format(index, call_index),
                    "type": "function",
                    "function": {
                        "name": action["name"],
                        "arguments": json.dumps(
                            action["arguments"], ensure_ascii=False
                        ),
                    },
                }
                for call_index, action in enumerate(example_calls)
            ]
            messages.append(
                {"role": "assistant", "content": "", "tool_calls": calls}
            )
            for call in calls:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "content": (
                            "协议示例回执：未实际执行设备，"
                            "仅演示工具消息关联。"
                        ),
                    }
                )
        return messages

    async def complete(
        self,
        text: str,
        deadline: float,
        *,
        tools: Optional[Tuple[Dict[str, Any], ...]] = None,
    ) -> ModelReply:
        """完整收齐请求后返回记录；不执行工具，也不请求措辞总结。"""
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": self._system_prompt},
                *self._example_messages(tools),
                {"role": "user", "content": text},
            ],
            "stream": True,
            "enable_thinking": False,
            "tool_choice": "auto" if tools else "none",
        }
        if tools:
            payload["tools"] = [
                {"type": "function", "function": definition}
                for definition in tools
            ]
            payload["parallel_tool_calls"] = True
        LOGGER.info(
            "[Model] 请求组装完成：model=%s tools=%s context_chars=%s",
            self._model,
            len(tools) if tools else "none",
            len(text),
        )
        if self._closed:
            raise ModelTransportError("closed")
        task = asyncio.create_task(
            self._request(payload, deadline, bool(tools))
        )
        self._requests.add(task)
        task.add_done_callback(self._retire_request)
        try:
            started = time.monotonic()
            while True:
                remaining = max(0.0, deadline - time.monotonic())
                done, _ = await asyncio.wait(
                    {task}, timeout=min(WAIT_LOG_INTERVAL, remaining)
                )
                if done:
                    return task.result()
                remaining = max(0.0, deadline - time.monotonic())
                if remaining <= 0:
                    LOGGER.warning(
                        "[HTTP] 请求总期限到期；elapsed=%.2fs remaining=0s",
                        time.monotonic() - started,
                    )
                    raise ModelTransportError("timeout", transient=True)
                LOGGER.info(
                    "[HTTP] 等待模型；elapsed=%.2fs remaining=%.2fs",
                    time.monotonic() - started,
                    remaining,
                )
        except asyncio.CancelledError:
            LOGGER.warning(
                "[HTTP] 等待被上层取消；remaining=%.2fs",
                max(0.0, deadline - time.monotonic()),
            )
            raise
        finally:
            self._cancel_request(task)
            # Agent 与 Adapter 的同一期限可能同时取消；清理只取消一次。
            while not task.done():
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    continue
            if not task.cancelled():
                task.result()

    def _cancel_request(self, task: asyncio.Task) -> None:
        """不把第二次取消传入正在释放响应的同一原请求。"""
        if not task.done() and task not in self._cancelling:
            self._cancelling.add(task)
            task.cancel()

    def _retire_request(self, task: asyncio.Task) -> None:
        """请求清理结束后才释放强引用，并领取尚未观察的异常。"""
        self._requests.discard(task)
        self._cancelling.discard(task)
        if not task.cancelled():
            task.exception()

    async def _request(self, payload, deadline, tools_enabled) -> ModelReply:
        """只在网络入口分类已知外部故障，不隐藏客户端编程错误。"""
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ModelTransportError("timeout", transient=True)
        started = time.monotonic()
        LOGGER.info("[Model] 开始发送请求，等待响应")
        LOGGER.info(
            "[HTTP] POST %s network=%s remaining=%.2fs "
            "headers={Content-Type: application/json, "
            "Authorization: <REDACTED>}",
            safe_url(self._endpoint),
            "injected-client" if self._injected_client else self._network,
            remaining,
        )
        proxies = getproxies()
        LOGGER.info(
            "[Network] 环境代理候选=%s；%s",
            {
                key: safe_url(value)
                for key, value in proxies.items()
                if key != "no"
            },
            "direct忽略环境代理"
            if self._network == "direct" and not self._injected_client
            else "实际TCP目标见连接事件；连接池复用时不会新建TCP",
        )
        if self._log_payload:
            LOGGER.info(
                "[HTTP] request_json=%s",
                json.dumps(
                    redact_payload(payload, self._key), ensure_ascii=False
                ),
            )

        async def trace(event, info):
            """只输出连接目标和阶段名，不打印请求对象或原始认证信息。"""
            if event == "connection.connect_tcp.started":
                LOGGER.info(
                    "[Network] TCP连接目标 host=%s port=%s timeout=%s",
                    info["host"],
                    info["port"],
                    info["timeout"],
                )
            elif event.endswith("start_tls.started"):
                LOGGER.info("[Network] TLS握手开始")
            elif event.endswith("send_request_body.complete"):
                LOGGER.info("[HTTP] 请求体发送完成，等待响应头")
            elif event.endswith(".failed") and not isinstance(
                info["exception"], (GeneratorExit, asyncio.CancelledError)
            ):
                LOGGER.warning(
                    "[Network] 阶段失败：%s error_type=%s elapsed=%.2fs",
                    event,
                    type(info["exception"]).__name__,
                    time.monotonic() - started,
                )

        try:
            async with self._client.stream(
                "POST",
                self._endpoint,
                json=payload,
                headers={"Authorization": "Bearer " + self._key},
                timeout=remaining,
                extensions={"trace": trace},
            ) as response:
                response.raise_for_status()
                LOGGER.info(
                    "[Model] 已收到HTTP响应头；status=%s elapsed=%.2fs",
                    response.status_code,
                    time.monotonic() - started,
                )
                raw = bytearray()
                line = bytearray()
                first_chunk = True
                async for chunk in response.aiter_bytes():
                    if first_chunk and chunk:
                        LOGGER.info(
                            "[Model] 收到首个响应数据；elapsed=%.2fs",
                            time.monotonic() - started,
                        )
                        first_chunk = False
                    raw.extend(chunk)
                    if len(raw) > MAX_MODEL_OUTPUT_BYTES:
                        raise ModelProtocolError("模型输出过长")
                    done = False
                    for byte in chunk:
                        line.append(byte)
                        if len(line) > MAX_SSE_LINE_BYTES:
                            raise ModelProtocolError("模型输出过长")
                        if byte == 10:
                            if (
                                line.startswith(b"data:")
                                and line[5:].strip() == b"[DONE]"
                            ):
                                done = True
                            line.clear()
                    if done:
                        break
                reply = parse_model_reply(bytes(raw), tools_enabled)
                self._log_reply(reply)
                LOGGER.info(
                    "[Model] 响应完整解析：kind=%s elapsed=%.2fs",
                    "tool" if reply.tool_calls else "text",
                    time.monotonic() - started,
                )
                return reply
        except httpx.HTTPStatusError as error:
            LOGGER.warning(
                "[HTTP] 服务返回失败状态：%s", error.response.status_code
            )
            status = error.response.status_code
            raise ModelTransportError(
                "http_" + str(status),
                transient=status in {408, 429, 500, 502, 503, 504},
            ) from error
        except httpx.TimeoutException as error:
            LOGGER.warning(
                "[HTTP] 传输超时：%s elapsed=%.2fs",
                type(error).__name__,
                time.monotonic() - started,
            )
            raise ModelTransportError("timeout", transient=True) from error
        except httpx.NetworkError as error:
            raise ModelTransportError("network", transient=True) from error
        except (httpx.RemoteProtocolError, httpx.DecodingError) as error:
            raise ModelProtocolError("模型传输协议无效") from error
        except (httpx.InvalidURL, httpx.UnsupportedProtocol) as error:
            raise ModelTransportError("configuration") from error

    def _log_reply(self, reply: ModelReply) -> None:
        """仅在显式开启时记录已校验响应，参数与文字统一脱敏。"""
        if not self._log_payload:
            return
        calls = [
            {
                "id": call.call_id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": json.dumps(
                        _json_value(call.arguments), ensure_ascii=False
                    ),
                },
            }
            for call in reply.tool_calls
        ]
        LOGGER.info(
            "[HTTP] response_tool_calls=%s response_content=%s",
            json.dumps(redact_payload(calls, self._key), ensure_ascii=False),
            redact_payload(reply.response, self._key),
        )

    async def aclose(self, deadline: Optional[float] = None) -> None:
        """先结束已拥有的请求，再释放连接池。"""
        self._closed = True
        requests = tuple(self._requests)
        for task in requests:
            self._cancel_request(task)
        try:
            if requests:
                await finish_tasks(requests, deadline)
        finally:
            await finish_tasks(
                [asyncio.create_task(self._client.aclose())], deadline
            )
