"""模型响应的私有协议解析：收齐 JSON/SSE 后统一校验，再交给业务层。"""

import io
import json
import math
from dataclasses import dataclass, field
from typing import Any, Dict, Tuple

from robot_agent.results import ModelReply, ToolCall

MAX_MODEL_OUTPUT_BYTES = 64 * 1024
MAX_SSE_LINE_BYTES = MAX_MODEL_OUTPUT_BYTES
MAX_JSON_DEPTH = 128
MAX_TOOL_CALLS = 64


class ModelProtocolError(ValueError):
    """模型响应不满足完整聊天或业务工具调用协议。"""


def _unique_object(pairs):
    """外部 JSON 禁止重复键，避免参数含义歧义。"""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ModelProtocolError("重复 JSON 键")
        result[key] = value
    return result


def _invalid_constant(value):
    """外部 JSON 不接受 NaN 和 Infinity。"""
    raise ModelProtocolError("非有限 JSON 数字")


def _finite_float(value: str) -> float:
    """合法 JSON 指数也不能溢出为非有限值。"""
    number = float(value)
    if not math.isfinite(number):
        raise ModelProtocolError("非有限 JSON 数字")
    return number


def _decode(raw):
    """JSON 解码仅留在传输入口。"""
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_unique_object,
            parse_constant=_invalid_constant,
            parse_float=_finite_float,
        )
    except RecursionError as error:
        raise ModelProtocolError("模型 JSON 嵌套过深") from error
    # 深度预算在外部入口统一检查，不依赖当前 Python 调用栈的剩余空间。
    pending = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if isinstance(item, (dict, list)):
            depth += 1
            if depth > MAX_JSON_DEPTH:
                raise ModelProtocolError("模型 JSON 嵌套过深")
            children = item.values() if isinstance(item, dict) else item
            pending.extend((child, depth) for child in children)
    return value


def _object(value) -> Dict[str, Any]:
    """协议对象在外部入口确认形状，再读取具名字段。"""
    if not isinstance(value, dict):
        raise ModelProtocolError("模型协议字段必须为对象")
    return value


@dataclass
class _CallFragments:
    """一个 SSE 索引独占的累计槽；只在响应完整后输出调用。"""

    call_id: str = ""
    name: str = ""
    arguments: str = ""
    call_type: str = ""

    def append(self, call: Dict[str, Any]) -> None:
        """名称和参数按片段拼接，标识只允许一次非空声明。"""
        function = _object(call.get("function", {}))
        if "id" in call:
            call_id = call["id"]
            if not isinstance(call_id, str):
                raise ModelProtocolError("工具标识片段无效")
            # Qwen 后续帧可以使用空 ID 延续同一槽。
            if call_id:
                if self.call_id:
                    raise ModelProtocolError("同一工具索引重复声明标识")
                self.call_id = call_id
        if "type" in call:
            if call["type"] != "function":
                raise ModelProtocolError("工具类型无效")
            self.call_type = "function"
        self.name += self._text_fragment(function, "name")
        self.arguments += self._text_fragment(function, "arguments")

    @staticmethod
    def _text_fragment(function: Dict[str, Any], field: str) -> str:
        """Qwen 空值表示无增量；其他非字符串类型仍是协议错误。"""
        value = function.get(field)
        if value is None:
            return ""
        if not isinstance(value, str):
            raise ModelProtocolError(
                f"工具名称或参数片段无效：function.{field} 类型为 "
                f"{type(value).__name__}，必须为字符串或 null"
            )
        return value

    def as_call(self) -> Dict[str, Any]:
        """恢复完整 JSON 的公共调用形状，统一执行最终协议校验。"""
        return {
            "id": self.call_id,
            "type": self.call_type,
            "function": {"name": self.name, "arguments": self.arguments},
        }


def _choices(event: Dict[str, Any]) -> list:
    """本版只接收一个选择，SSE 用量统计允许空列表。"""
    choices = event["choices"]
    if not isinstance(choices, list) or len(choices) > 1:
        raise ModelProtocolError("模型必须返回一个选择")
    if choices:
        index = _object(choices[0]).get("index", 0)
        if type(index) is not int or index != 0:
            raise ModelProtocolError("模型必须返回一个选择")
    return choices


def _validate_tool_calls(calls: list) -> Tuple[ToolCall, ...]:
    """校验完整调用的字段、唯一标识和 JSON 参数，不校验业务工具名。"""
    tool_calls = []
    call_ids = set()
    for raw_call in calls:
        call = _object(raw_call)
        function = _object(call["function"])
        call_id = call["id"]
        name = function["name"]
        raw_arguments = function["arguments"]
        if (
            call["type"] != "function"
            or not isinstance(name, str)
            or not name.strip()
            or not isinstance(call_id, str)
            or not call_id.strip()
            or call_id in call_ids
            or not isinstance(raw_arguments, str)
        ):
            raise ModelProtocolError("工具类型、名称、标识或参数字符串无效")
        call_ids.add(call_id)
        arguments = _decode(raw_arguments)
        if not isinstance(arguments, dict):
            raise ModelProtocolError("工具参数必须为对象")
        try:
            tool_calls.append(ToolCall(call_id, name, arguments))
        except RecursionError as error:
            raise ModelProtocolError("工具参数嵌套过深") from error
    return tuple(tool_calls)


@dataclass(frozen=True)
class _ResponseMessage:
    """传输已收齐但尚未信任的消息；校验成功才能输出 ModelReply。"""

    content: Any
    calls: Any
    finish: Any

    def validate(self, tools_enabled: bool) -> ModelReply:
        """校验文字、批次和结束原因，业务参数仍留给 Registry。"""
        if self.content is not None and not isinstance(self.content, str):
            raise ModelProtocolError("模型文字无效")
        if (
            not isinstance(self.calls, list)
            or len(self.calls) > MAX_TOOL_CALLS
        ):
            raise ModelProtocolError("工具调用列表无效或超过64项")
        if self.calls:
            if not tools_enabled or self.finish != "tool_calls":
                raise ModelProtocolError("工具调用未完成或已被禁用")
            return ModelReply(
                self.content or "", _validate_tool_calls(self.calls)
            )
        if (
            self.finish != "stop"
            or not self.content
            or not self.content.strip()
        ):
            raise ModelProtocolError("聊天响应未完成或为空")
        return ModelReply(self.content)


def _read_json_message(raw: bytes) -> _ResponseMessage:
    """完整 JSON 用调用数组顺序，统一转成待校验消息。"""
    if len(raw) > MAX_MODEL_OUTPUT_BYTES:
        raise ModelProtocolError("模型输出过长")
    event = _object(_decode(raw))
    choices = _choices(event)
    if len(choices) != 1:
        raise ModelProtocolError("模型必须返回一个选择")
    choice = _object(choices[0])
    message = _object(choice["message"])
    return _ResponseMessage(
        message.get("content"),
        message.get("tool_calls", []),
        choice["finish_reason"],
    )


@dataclass
class _SseResponse:
    """持有一次流式响应的累计状态，片段只能经 append 校验后写入。"""

    content: str = ""
    slots: Dict[int, _CallFragments] = field(default_factory=dict)
    finish: Any = None

    def append(self, data: bytes) -> None:
        """接收单帧，拒绝结束后的片段及无效文字、调用索引。"""
        event = _object(_decode(data))
        choices = _choices(event)
        # 部分端点在最后发送空 choices 的用量统计。
        if not choices:
            return
        choice = _object(choices[0])
        delta = _object(choice["delta"])
        if self.finish is not None:
            raise ModelProtocolError("结束后仍有模型片段")
        fragment = delta.get("content")
        if fragment is not None:
            if not isinstance(fragment, str):
                raise ModelProtocolError("文字片段无效")
            self.content += fragment
        fragments = delta.get("tool_calls", [])
        if not isinstance(fragments, list):
            raise ModelProtocolError("工具片段必须为列表")
        for raw_call in fragments:
            call = _object(raw_call)
            index = call["index"]
            if type(index) is not int or not 0 <= index < MAX_TOOL_CALLS:
                raise ModelProtocolError("工具调用索引无效或超过64项")
            if index not in self.slots:
                self.slots[index] = _CallFragments()
            self.slots[index].append(call)
        self.finish = choice.get("finish_reason")

    def message(self) -> _ResponseMessage:
        """结束时检查索引连续性，按协议索引恢复完整调用顺序。"""
        if sorted(self.slots) != list(range(len(self.slots))):
            raise ModelProtocolError("工具调用索引不连续")
        calls = [
            self.slots[index].as_call() for index in range(len(self.slots))
        ]
        return _ResponseMessage(self.content, calls, self.finish)


def _read_message(raw: bytes) -> _ResponseMessage:
    """识别 JSON 或 SSE；读取流程不承担消息字段的校验细节。"""
    response = io.BytesIO(raw)
    stream = _SseResponse()
    size = 0
    while True:
        line = response.readline(MAX_SSE_LINE_BYTES + 1)
        size += len(line)
        if len(line) > MAX_SSE_LINE_BYTES or size > MAX_MODEL_OUTPUT_BYTES:
            raise ModelProtocolError("模型输出过长")
        if not line:
            raise ModelProtocolError("模型响应未正常结束")
        if line.lstrip().startswith(b"{"):
            return _read_json_message(
                line + response.read(MAX_MODEL_OUTPUT_BYTES + 1)
            )
        if not line.startswith(b"data:"):
            continue
        data = line[5:].strip()
        if data == b"[DONE]":
            return stream.message()
        stream.append(data)


def parse_model_reply(raw: bytes, tools_enabled: bool) -> ModelReply:
    """在不可信响应入口完成协议校验，分类已知解码故障。"""
    try:
        return _read_message(raw).validate(tools_enabled)
    except (KeyError, UnicodeError, json.JSONDecodeError) as error:
        raise ModelProtocolError("模型协议无效") from error
