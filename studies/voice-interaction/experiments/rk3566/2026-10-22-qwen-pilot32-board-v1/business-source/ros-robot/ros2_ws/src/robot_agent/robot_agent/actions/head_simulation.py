"""头部和 LCD 的可观察模拟；源动作序列使用虚拟时间，不创建驱动。"""

from functools import partial
from typing import Callable, Dict, List, Literal, Optional, Sequence, Tuple

from pydantic import Field, StrictInt, create_model, model_validator
from typing_extensions import Annotated

from robot_agent.actions.contracts import (
    ActionDefinition,
    ActionInput,
    NoArguments,
    PitchNumber,
    PositiveNumber,
    YawNumber,
)
from robot_agent.actions.simulation import simulated
from robot_agent.results import ActionReceipt


class PositionInput(ActionInput):
    """头部角度范围；至少指定一轴。"""

    pitch: Optional[PitchNumber] = Field(
        default=None, description="俯仰角，单位度"
    )
    yaw: Optional[YawNumber] = Field(
        default=None, description="偏航角，单位度"
    )

    @model_validator(mode="after")
    def require_axis(self) -> "PositionInput":
        """至少提供需要改变的一轴。"""
        if self.pitch is None and self.yaw is None:
            raise ValueError("必须指定 pitch 或 yaw")
        return self


class DurationInput(ActionInput):
    """动作持续时间使用正有限秒数。"""

    duration: PositiveNumber = Field(description="虚拟动作时长，单位秒")


class BreathingInput(ActionInput):
    """呼吸周期限制资源，保留既有默认值。"""

    cycles: Annotated[StrictInt, Field(ge=1, le=64)] = Field(
        default=5, description="呼吸周期数，1至64"
    )
    duration: PositiveNumber = Field(
        default=0.5, description="每个呼吸周期时长，单位秒"
    )


class AttentionInput(ActionInput):
    """注意方向与时间。"""

    direction: Literal["left", "right", "up", "down", "center"] = Field(
        default="center", description="注意方向"
    )
    duration: PositiveNumber = Field(
        default=1.0, description="虚拟动作时长，单位秒"
    )


class EmotionalInput(ActionInput):
    """情感类别与时间。"""

    emotion: Literal["happy", "sad", "angry", "excited", "calm"] = Field(
        default="happy", description="表现的情感"
    )
    duration: PositiveNumber = Field(
        default=3.0, description="虚拟动作时长，单位秒"
    )


# 旧注册函数仅改变 LCD，不能把这些表情宣称为真实舵机点头或跳舞。
EXPRESSIONS = {
    "head_smile": "兴奋",
    "head_nod": "兴奋",
    "head_shake": "正常",
    "head_dance": "兴奋",
    "excited": "兴奋",
    "normal": "正常",
    "sleep": "good_night",
    "wake_up": "苏醒",
}
BASIC_POSES = {
    "head_forward": (90, 90),
    "head_reset": (90, 90),
    "head_down": (65, None),
    "head_up": (120, None),
    "head_left": (None, 130),
    "head_right": (None, 50),
}
# 元组为 pitch/yaw；None 保留当前轴。
# 以源姿态顺序为准，duration 均分虚拟时间。
GESTURES = {
    "head_think": (
        2.0,
        [(80, 90), (82, 75), (90, 90), (85, 105), (100, 90), (90, 90)],
    ),
    "head_confused": (1.5, [(None, 80), (None, 100), (None, 90)]),
    "head_surprised": (1.0, [(105, None), (85, None), (90, None)]),
    "head_look_around": (
        3.0,
        [
            (100, 90),
            (105, 65),
            (80, 60),
            (90, 90),
            (105, 115),
            (80, 120),
            (110, 90),
            (75, 90),
            (90, 90),
        ],
    ),
    "head_greet": (
        2.0,
        [
            (100, 90),
            (82, 90),
            (95, 90),
            (90, 75),
            (90, 105),
            (90, 90),
            (80, 90),
            (90, 90),
        ],
    ),
    "head_goodbye": (1.5, [(65, None), (90, 90), (85, None), (90, None)]),
    "head_refuse": (
        1.0,
        [(None, 130), (None, 50)] * 2 + [(90, 90), (85, None), (90, None)],
    ),
    "head_listen": (
        2.0,
        [
            (82, 90),
            (85, 75),
            (85, 105),
            (82, 90),
            (78, 90),
            (82, 90),
            (90, 90),
        ],
    ),
    "head_interest": (
        1.5,
        [(100, 90), (85, 90), (88, 75), (88, 105), (100, 90), (90, 90)],
    ),
    "head_concern": (
        2.0,
        [
            (80, 90),
            (82, 75),
            (82, 105),
            (80, 90),
            (75, 90),
            (80, 90),
            (90, 90),
        ],
    ),
    "head_agree": (
        1.0,
        [(82, 90), (95, 90), (80, 90), (90, 90), (100, 90), (90, 90)],
    ),
    "head_disagree": (
        1.0,
        [(90, 75), (90, 105), (90, 70), (90, 110), (90, 90)],
    ),
}
Pose = Tuple[Optional[float], Optional[float]]


class HeadSimulation:
    """持有姿态、LCD 和本动作虚拟轨迹，不保留无限历史队列。"""

    def __init__(self) -> None:
        """初始化源中心姿态和正常表情。"""
        self.pitch = 90.0
        self.yaw = 90.0
        self.display = "正常"

    def expression(self, display: str) -> ActionReceipt:
        """更新 LCD 模拟状态，保留头部姿态。"""
        self.display = display
        return simulated("LCD " + display, **self._state())

    async def show_expression(
        self, display: str, *, deadline: float
    ) -> ActionReceipt:
        """动作入口复用同步 LCD 更新，供音乐共享同一状态。"""
        return self.expression(display)

    async def basic_position(
        self, pose: Pose, *, deadline: float
    ) -> ActionReceipt:
        """动作入口执行预先声明的基础姿态。"""
        return self._perform([pose], 0.0)

    async def head_position(
        self,
        pitch: Optional[float],
        yaw: Optional[float],
        *,
        deadline: float,
    ) -> ActionReceipt:
        """更新指定轴，未指定轴保留当前角度。"""
        return self._perform([(pitch, yaw)], 0.0)

    def gesture_handler(self, name: str) -> Callable:
        """相同参数契约的组合姿态共用实现，保留各动作默认时间。"""

        async def execute(
            duration: float, *, deadline: float
        ) -> ActionReceipt:
            """完成一个组合动作的完整虚拟轨迹后返回快照。"""
            return self._perform(GESTURES[name][1], duration)

        return execute

    async def head_breathing(
        self, cycles: int, duration: float, *, deadline: float
    ) -> ActionReceipt:
        """按周期展开吸气和呼气，并回到中心俯仰角。"""
        poses = [(92, None), (88, None)] * cycles + [(90, None)]
        return self._perform(poses, cycles * duration)

    async def head_attention(
        self,
        direction: str,
        duration: float,
        *,
        deadline: float,
    ) -> ActionReceipt:
        """转向注意方向后回到中心，全部步骤均为模拟。"""
        poses = {
            "left": (None, 130),
            "right": (None, 50),
            "up": (120, None),
            "down": (65, None),
            "center": (90, 90),
        }
        return self._perform([poses[direction], (90, 90)], duration)

    async def head_emotional(
        self,
        emotion: str,
        duration: float,
        *,
        deadline: float,
    ) -> ActionReceipt:
        """按源情感组合展开姿态，按序执行而非创建子动作线程。"""
        nod = [(65, None), (90, 90)]
        shake = [(None, 130), (None, 50), (90, 90)]
        poses = {
            "happy": nod * 2 + [(None, 85), (None, 95), (None, 90)],
            "sad": [(85, None)] + shake + [(90, None)],
            "angry": GESTURES["head_confused"][1] + [(95, None), (90, None)],
            "excited": nod * 3 + GESTURES["head_look_around"][1],
            "calm": [(92, None), (88, None)] * 3 + [(90, None)],
        }
        return self._perform(poses[emotion], duration)

    def _perform(
        self, poses: Sequence[Pose], duration: float
    ) -> ActionReceipt:
        """按序更新姿态并返回有界轨迹；duration 不影响真实时间。"""
        # 1. 本动作独占轨迹，保留每步姿态与有意重复。
        steps = []
        for pitch, yaw in poses:
            if pitch is not None:
                self.pitch = pitch
            if yaw is not None:
                self.yaw = yaw
            steps.append(
                dict(
                    pitch=self.pitch,
                    yaw=self.yaw,
                    duration=duration / len(poses),
                )
            )

        # 2. 只有完整虚拟序列结束才返回模拟成功。
        return simulated(
            "头部姿态与轨迹", **self._state(), steps=steps, duration=duration
        )

    def _state(self) -> Dict:
        """返回当前姿态和 LCD 显示字段。"""
        return dict(pitch=self.pitch, yaw=self.yaw, display=self.display)


def head_actions(head: HeadSimulation) -> List[ActionDefinition]:
    """声明 LCD、基础姿态及组合动作，参数规则位于本能力。"""
    definitions = [
        ActionDefinition(
            name=name,
            description="模拟 LCD 表情：" + display,
            inputs=NoArguments,
            handler=partial(head.show_expression, display),
        )
        for name, display in EXPRESSIONS.items()
    ]
    definitions.extend(
        ActionDefinition(
            name=name,
            description="模拟头部基础姿态：" + name,
            inputs=NoArguments,
            handler=partial(head.basic_position, pose),
        )
        for name, pose in BASIC_POSES.items()
    )
    for name, (default, _) in GESTURES.items():
        inputs = create_model(
            name + "Input",
            __base__=DurationInput,
            duration=(
                PositiveNumber,
                Field(default=default, description="虚拟动作时长，单位秒"),
            ),
        )
        definitions.append(
            ActionDefinition(
                name=name,
                description="模拟头部组合姿态：" + name,
                inputs=inputs,
                handler=head.gesture_handler(name),
            )
        )
    definitions.extend(
        [
            ActionDefinition(
                name="head_position",
                description="模拟指定头部角度，省略轴保持原位",
                inputs=PositionInput,
                handler=head.head_position,
            ),
            ActionDefinition(
                name="head_breathing",
                description="模拟头部呼吸轨迹",
                inputs=BreathingInput,
                handler=head.head_breathing,
            ),
            ActionDefinition(
                name="head_attention",
                description="模拟转向注意方向后回中",
                inputs=AttentionInput,
                handler=head.head_attention,
            ),
            ActionDefinition(
                name="head_emotional",
                description="模拟情感对应的头部轨迹",
                inputs=EmotionalInput,
                handler=head.head_emotional,
            ),
        ]
    )
    return definitions
