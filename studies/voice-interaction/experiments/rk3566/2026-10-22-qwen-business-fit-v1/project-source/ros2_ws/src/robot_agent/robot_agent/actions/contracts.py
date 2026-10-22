"""动作输入模型是 Schema、默认值和类型校验的共同声明。"""

from dataclasses import dataclass
from typing import Awaitable, Callable, Tuple, Type, Union

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictFloat,
    StrictInt,
)
from typing_extensions import Annotated

from robot_agent.results import ActionReceipt


def _number(value):
    """保持原数值契约，仅接受 Python/JSON 的整数和浮点数。"""
    if type(value) not in (int, float):
        raise ValueError("数值必须为整数或浮点数")
    return value


# strict float 仍可接收 Decimal 等可转换对象，因此先限定原始类型。
FiniteFloat = Annotated[StrictFloat, Field(allow_inf_nan=False)]
Number = Annotated[Union[StrictInt, FiniteFloat], BeforeValidator(_number)]
# 约束放在数值分支，避免联合外层生成非标准 gt/ge/le。
POSITIVE_BOUNDS = Field(gt=0)
PITCH_BOUNDS = Field(ge=65, le=120)
YAW_BOUNDS = Field(ge=50, le=130)
STEP_BOUNDS = Field(ge=0)
PositiveNumber = Annotated[
    Union[
        Annotated[StrictInt, POSITIVE_BOUNDS],
        Annotated[FiniteFloat, POSITIVE_BOUNDS],
    ],
    BeforeValidator(_number),
]
PitchNumber = Annotated[
    Union[
        Annotated[StrictInt, PITCH_BOUNDS],
        Annotated[FiniteFloat, PITCH_BOUNDS],
    ],
    BeforeValidator(_number),
]
YawNumber = Annotated[
    Union[
        Annotated[StrictInt, YAW_BOUNDS], Annotated[FiniteFloat, YAW_BOUNDS]
    ],
    BeforeValidator(_number),
]
StepNumber = Annotated[
    Union[
        Annotated[StrictInt, STEP_BOUNDS], Annotated[FiniteFloat, STEP_BOUNDS]
    ],
    BeforeValidator(_number),
]
Text = Annotated[str, Field(min_length=1, max_length=2048, pattern=r"\S")]


class ActionInput(BaseModel):
    """外部工具参数严格校验，未知字段不能成为内部执行参数。"""

    model_config = ConfigDict(extra="forbid", strict=True)


class NoArguments(ActionInput):
    """无模型参数的动作。"""


@dataclass(frozen=True)
class ActionDefinition:
    """连接动作的公开输入和本地执行函数。"""

    name: str
    description: str
    inputs: Type[ActionInput]
    handler: Callable[..., Awaitable[ActionReceipt]]
    aliases: Tuple[str, ...] = ()
