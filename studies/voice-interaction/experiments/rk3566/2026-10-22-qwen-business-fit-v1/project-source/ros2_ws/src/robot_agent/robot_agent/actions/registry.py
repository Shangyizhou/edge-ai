"""单一目录导出原生工具 Schema，整表绑定后才允许调用设备。"""

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from pydantic import ValidationError

from robot_agent.actions.contracts import (
    ActionDefinition,
)
from robot_agent.actions.perception import (
    PerceptionActions,
    perception_actions,
)
from robot_agent.results import ActionReceipt, ToolCall, _freeze, _json_value

CONFIRMED_SUCCESS = frozenset({"simulated_success", "real_success"})
DEVICE_OUTCOMES = CONFIRMED_SUCCESS | {"failed", "unknown"}
MAX_ACTIONS = 64


class PlanValidationError(ValueError):
    """本批首处输入错误，保留来源而不泄露原参数。"""

    def __init__(
        self,
        call_index: int,
        tool_call_id: str,
        name: str,
        field_path: str,
        reason: str,
    ) -> None:
        """记录动作序号、字段和可显示原因。"""
        self.call_index = call_index
        self.tool_call_id = tool_call_id
        self.name = name
        self.field_path = field_path
        self.reason = reason
        super().__init__(
            f"第{call_index + 1}项 {name} {field_path}：{reason}；"
            "本批全部未执行"
        )


@dataclass(frozen=True)
class ActionCommand:
    """输入校验完成后的动作与不可变参数快照。"""

    name: str
    parameters: Mapping[str, Any]
    tool_call_id: str

    def __post_init__(self) -> None:
        """复制参数，调用者不能在执行前改写计划。"""
        object.__setattr__(self, "parameters", _freeze(self.parameters))


@dataclass(frozen=True)
class ActionPlan:
    """已完整绑定的计划，保留原顺序和有意重复。"""

    commands: Tuple[ActionCommand, ...]

    def __post_init__(self) -> None:
        """脱离调用者的可变序列。"""
        object.__setattr__(self, "commands", tuple(self.commands))


class ActionRegistry:
    """Schema、默认值绑定、业务校验和实现查找共享同一目录。"""

    def __init__(self) -> None:
        """创建空目录，能力在组装时注册。"""
        self._handlers: Dict[str, ActionDefinition] = {}
        self._definitions: List[ActionDefinition] = []
        self._perception: Optional[PerceptionActions] = None

    def register(self, definition: ActionDefinition) -> None:
        """组装时检查规范名和别名冲突，禁止覆盖已有能力。"""
        names = (definition.name,) + definition.aliases
        if len(set(names)) != len(names) or any(
            name in self._handlers for name in names
        ):
            raise ValueError("重复动作名称或别名：" + definition.name)
        for name in names:
            self._handlers[name] = definition
        self._definitions.append(definition)

    def register_many(self, definitions: Sequence[ActionDefinition]) -> None:
        """按声明顺序组装能力目录。"""
        for definition in definitions:
            self.register(definition)

    def register_perception(self, perception: PerceptionActions) -> None:
        """注册感知能力并接管其设备准入和回执桥接生命周期。"""
        self.register_many(perception_actions(perception))
        self._perception = perception

    def stop(self) -> None:
        """关闭时阻止组合动作的新设备步骤。"""
        if self._perception is not None:
            self._perception.stop()

    async def aclose(self, deadline: Optional[float]) -> None:
        """执行已停止等待原回执之后，才释放感知Adapter。"""
        if self._perception is not None:
            await self._perception.aclose(deadline)

    def schemas(self) -> Tuple[Dict[str, Any], ...]:
        """每个工具拥有独立参数根，嵌套引用留在本工具内。"""
        return tuple(
            {
                "name": definition.name,
                "description": definition.description,
                "parameters": definition.inputs.model_json_schema(),
            }
            for definition in self._definitions
        )

    def validate_calls(self, calls: Sequence[ToolCall]) -> ActionPlan:
        """完整校验本次响应，任何错误都不执行动作。"""
        if not 1 <= len(calls) <= MAX_ACTIONS:
            raise PlanValidationError(0, "", "", "", "每批必须有1至64项调用")
        return ActionPlan(
            tuple(
                self._validate_call(index, call)
                for index, call in enumerate(calls)
            )
        )

    def _validate_call(self, index: int, call: ToolCall) -> ActionCommand:
        """按声明校验单项并补默认值；错误携带原调用序号、标识和字段。"""
        definition = self._handlers.get(call.name)
        if definition is None:
            raise PlanValidationError(
                index, call.call_id, call.name, "name", "动作未实现"
            )
        try:
            parameters = definition.inputs.model_validate(
                _json_value(call.arguments)
            ).model_dump()
        except ValidationError as error:
            first = error.errors(include_input=False)[0]
            raise PlanValidationError(
                index,
                call.call_id,
                call.name,
                ".".join(str(part) for part in first["loc"]),
                first["msg"],
            ) from error
        return ActionCommand(call.name, parameters, call.call_id)

    async def invoke(
        self, command: ActionCommand, deadline: float
    ) -> ActionReceipt:
        """调用已校验动作，设备字典转换由能力 Adapter 完成。"""
        definition = self._handlers[command.name]
        return await definition.handler(
            **_json_value(command.parameters), deadline=deadline
        )
