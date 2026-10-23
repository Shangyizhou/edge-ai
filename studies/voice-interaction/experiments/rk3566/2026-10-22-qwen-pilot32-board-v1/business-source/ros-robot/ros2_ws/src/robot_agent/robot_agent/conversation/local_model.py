"""已有 GGUF 的显式训练格式 Adapter；只解析数据，不执行模型代码。"""

import ast
import json
import re
import uuid
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

from robot_agent.conversation._model_protocol import ModelProtocolError
from robot_agent.results import ModelReply, ToolCall

MAX_LOCAL_OUTPUT_BYTES = 256 * 1024
TextConsumer = Callable[[str], Awaitable[None]]
StreamGenerate = Callable[[str, float, TextConsumer], Awaitable[str]]


def _object(pairs):
    """拒绝重复 JSON 字段，避免校验与执行观察不同含义。"""
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("重复字段")
        result[name] = value
    return result


def _parse_legacy_reply(raw: str, request_id: str, tools=()) -> ModelReply:
    """完整 res/fc 对象转换为相关调用；参数绑定留给 Registry。"""
    try:
        if len(raw.encode("utf-8")) > MAX_LOCAL_OUTPUT_BYTES:
            raise ValueError("输出过长")
        value = json.loads(raw, object_pairs_hook=_object)
        if (
            not isinstance(value, dict)
            or set(value) != {"res", "fc"}
            or not isinstance(value["res"], str)
            or not isinstance(value["fc"], list)
            or len(value["fc"]) > 64
        ):
            raise ValueError("对象形状无效")
        calls = []
        for index, source in enumerate(value["fc"]):
            if not isinstance(source, str) or len(source) > 8192:
                raise ValueError("调用形状无效")
            expression = ast.parse(source, mode="eval").body
            if isinstance(expression, ast.Name):
                expression = ast.Call(func=expression, args=[], keywords=[])
            if not isinstance(expression, ast.Call) or not isinstance(
                expression.func, ast.Name
            ):
                raise ValueError("只允许具名函数与字面参数")
            definitions = {item["name"]: item for item in tools}
            definition = definitions.get(expression.func.id)
            parameters = (
                []
                if definition is None
                else list(definition["parameters"].get("properties", {}))
            )
            if len(expression.args) > len(parameters):
                raise ValueError("位置参数无法绑定到目录声明")
            arguments = {
                parameters[index]: ast.literal_eval(node)
                for index, node in enumerate(expression.args)
            }
            for keyword in expression.keywords:
                if keyword.arg is None or keyword.arg in arguments:
                    raise ValueError("重复参数或展开参数")
                arguments[keyword.arg] = ast.literal_eval(keyword.value)
            # 所有位置与关键字实参均遵守 JSON 数据契约。
            arguments = json.loads(json.dumps(arguments, allow_nan=False))
            calls.append(
                ToolCall(
                    f"{request_id}_{index}", expression.func.id, arguments
                )
            )
        value["res"].encode("utf-8")
        return ModelReply(value["res"], tuple(calls))
    except (
        ValueError,
        TypeError,
        SyntaxError,
        RecursionError,
        UnicodeError,
    ) as error:
        raise ModelProtocolError("本地模型 res/fc 协议无效") from error


class LocalModel:
    """用已有 Model Interface 接入本地生成并集中训练模板契约。"""

    def __init__(
        self,
        generate: Callable[[str, float], Awaitable[str]],
        *,
        stream_generate: Optional[StreamGenerate] = None,
        close: Optional[Callable[[Optional[float]], Awaitable[None]]] = None,
    ) -> None:
        """接管生成与关闭；增量传输必须安装 fc-first-v1 grammar。

        任意旧生成器不能仅因有分块数据就获准提前说；未提供受约束传输时
        只开放 complete 路径，保留完整旧格式兼容。
        """
        self._generate = generate
        self._close = close
        self._stream_generate = stream_generate
        self.incremental = stream_generate is not None

    async def complete(
        self,
        text: str,
        deadline: float,
        *,
        tools: Optional[Tuple[Dict[str, Any], ...]] = None,
    ) -> ModelReply:
        """使用核实过的模板，工具来自当前 Registry 的唯一声明。"""
        raw = await self._generate(self._prompt(text, tools), deadline)
        return self._reply(raw, tools)

    def _prompt(self, text, tools):
        """固定字段顺序与 native 非懒加载 grammar 契约一致。"""
        system = (
            '你是小沫机器人。只输出 JSON 对象 {"fc":[], "res":"回复"}。'
            "fc 是函数调用字符串数组，只允许下列工具及关键字参数。"
            "不要执行代码；没有动作时 fc 为空。不要声称设备已经成功。"
            "\n工具：" + json.dumps(tools or [], ensure_ascii=False)
        )
        # 已核实此 GGUF 的具体模板，不能交给预置模板猜测。
        prompt = (
            "System: "
            + system
            + "<|im_end|>\nHuman: "
            + text
            + "<|im_end|>\nAssistant:"
        )
        return prompt

    def _reply(self, raw, tools):
        """最终完整验证始终在工具准入之前。"""
        reply = _parse_legacy_reply(raw, uuid.uuid4().hex, tools or ())
        if not tools and reply.tool_calls:
            raise ModelProtocolError("已禁用工具")
        return reply

    async def complete_incremental(
        self,
        text: str,
        deadline: float,
        on_text: TextConsumer,
        *,
        tools: Optional[Tuple[Dict[str, Any], ...]] = None,
    ) -> ModelReply:
        """固定 fc-first 原生传输才能授权空 fc 后的文字增量。"""
        parser = _IncrementalReply()

        async def consume(chunk):
            """先验证与解码，只有具备资格的文字进入上层。"""
            delta = parser.feed(chunk)
            if delta:
                await on_text(delta)

        raw = await self._stream_generate(
            self._prompt(text, tools), deadline, consume
        )
        if not parser.raw:
            # 无 Feedback 不能授予前缀资格；完整旧协议只能走最终回复。
            return self._reply(raw, tools)
        if raw != parser.raw:
            raise ModelProtocolError("增量与最终结果不一致")
        return self._reply(raw, tools)

    async def aclose(self, deadline: Optional[float] = None) -> None:
        """关闭传输拥有者，不创建模型或设备进程。"""
        if self._close is not None:
            await self._close(deadline)


class _IncrementalReply:
    """只识别固定顺序空 fc；非空或旧顺序只在最终结果处理。"""

    def __init__(self):
        """缓存受协议预算约束，字符串游标不重放前缀。"""
        self.raw = ""
        self.position = None
        self.finished = False

    def feed(self, chunk):
        """JSON 转义与代理对完整后才交付一个 Unicode 字符。"""
        self.raw += chunk
        if len(self.raw.encode("utf-8")) > MAX_LOCAL_OUTPUT_BYTES:
            raise ModelProtocolError("本地增量超过输出预算")
        if self.finished:
            return ""
        if self.position is None:
            prefix = re.match(
                r'\A[ \t\r\n]*\{[ \t\r\n]*"fc"[ \t\r\n]*:[ \t\r\n]*', self.raw
            )
            if prefix is None:
                return ""
            try:
                calls, end = json.JSONDecoder().raw_decode(
                    self.raw, prefix.end()
                )
            except ValueError:
                return ""
            if calls != []:
                return ""
            following = re.match(
                r'[ \t\r\n]*,[ \t\r\n]*"res"[ \t\r\n]*:[ \t\r\n]*"',
                self.raw[end:],
            )
            if following is None:
                return ""
            self.position = end + following.end()
        result = []
        while self.position < len(self.raw):
            start = self.position
            char = self.raw[start]
            if char == '"':
                self.finished = True
                break
            width = 1
            if char == "\\":
                if start + 1 >= len(self.raw):
                    break
                width = 6 if self.raw[start + 1] == "u" else 2
                if start + width > len(self.raw):
                    break
                if width == 6:
                    try:
                        code = int(self.raw[start + 2 : start + 6], 16)
                    except ValueError as error:
                        raise ModelProtocolError(
                            "无效 Unicode 转义"
                        ) from error
                    if 0xD800 <= code <= 0xDBFF:
                        width = 12
                        if start + width > len(self.raw):
                            break
            token = self.raw[start : start + width]
            try:
                decoded = json.loads('"' + token + '"')
                decoded.encode("utf-8")
            except (ValueError, UnicodeError) as error:
                raise ModelProtocolError("无效增量 JSON 字符串") from error
            result.append(decoded)
            self.position += width
        return "".join(result)
