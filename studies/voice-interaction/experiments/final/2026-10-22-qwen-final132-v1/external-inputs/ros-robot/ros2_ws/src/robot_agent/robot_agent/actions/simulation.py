"""缺失设备的状态模拟：只更新内存与日志，绝不连接硬件或修改系统。"""

import logging
import math
from copy import deepcopy
from typing import Any, Callable, List, Optional

from pydantic import Field, model_validator

from robot_agent.actions.contracts import (
    ActionDefinition,
    ActionInput,
    NoArguments,
    Number,
    StepNumber,
    Text,
)
from robot_agent.results import ActionReceipt


class LocationInput(ActionInput):
    """导航目标名称。"""

    location: Text = Field(description="已注册的导航位置名称")


class PoseInput(ActionInput):
    """地图位置与四元数，必须使用单位四元数。"""

    name: Text = Field(description="注册位置的名称")
    x: Number = Field(description="地图 X 坐标，单位米")
    y: Number = Field(description="地图 Y 坐标，单位米")
    z: Number = Field(default=0.0, description="地图 Z 坐标，单位米")
    qx: Number = Field(default=0.0, description="单位四元数 X 分量")
    qy: Number = Field(default=0.0, description="单位四元数 Y 分量")
    qz: Number = Field(default=0.0, description="单位四元数 Z 分量")
    qw: Number = Field(default=1.0, description="单位四元数 W 分量")

    @model_validator(mode="after")
    def require_unit_quaternion(self) -> "PoseInput":
        """地图姿态必须是单位四元数。"""
        if not math.isclose(
            math.hypot(self.qx, self.qy, self.qz, self.qw), 1.0, abs_tol=0.001
        ):
            raise ValueError("姿态必须为单位四元数")
        return self


class SongInput(ActionInput):
    """歌曲与队列接受非空名称。"""

    song_name: Text = Field(description="歌曲名称")


class RecommendationInput(ActionInput):
    """省略歌曲时按当前曲目推荐。"""

    song_name: Optional[Text] = Field(
        default=None, description="推荐依据歌曲；省略时使用当前歌曲"
    )


class StepInput(ActionInput):
    """非负音量步长，执行时按原契约饱和。"""

    step: StepNumber = Field(
        default=5, description="音量调整步长，非负，结果限制在0至100"
    )


class LevelInput(ActionInput):
    """音量执行时量化并按原契约饱和。"""

    level: Number = Field(
        default=50, description="音量，执行时取整并限制在0至100"
    )


LOGGER = logging.getLogger(__name__)


def simulated(detail: str, **data: Any) -> ActionReceipt:
    """返回独立的模拟快照，日志不含外部凭证或系统信息。"""
    LOGGER.info("模拟：%s", detail)
    return ActionReceipt(
        "simulated_success", "模拟：" + detail, deepcopy(data)
    )


class NavigationSimulation:
    """集中管理注册位置和导航任务；活动任务只由显式取消结束。"""

    def __init__(self) -> None:
        """复制源厨房坐标，每个 Agent 独立维护位置与任务。"""
        self.locations = {
            "厨房": dict(
                x=2.491, y=-0.331, z=0.0, qx=0.0, qy=0.0, qz=-0.389, qw=0.921
            ),
        }
        self.current_goal: Optional[str] = None
        self.state = "idle"

    async def add_location(
        self,
        name: str,
        x: float,
        y: float,
        z: float,
        qx: float,
        qy: float,
        qz: float,
        qw: float,
        *,
        deadline: float,
    ) -> ActionReceipt:
        """注册或替换位置，不发出地图或设备调用。"""
        self.locations[name] = dict(x=x, y=y, z=z, qx=qx, qy=qy, qz=qz, qw=qw)
        return simulated("注册位置 " + name, locations=self.locations)

    async def list_locations(self, *, deadline: float) -> ActionReceipt:
        """返回全部已注册位置的快照。"""
        return simulated("位置列表", locations=self.locations)

    async def navigate_to(
        self, location: str, *, deadline: float
    ) -> ActionReceipt:
        """模拟提交目标；未知目标或已有活动任务明确失败。"""
        if location not in self.locations:
            return ActionReceipt("failed", "模拟：未知位置 " + location)
        if self.state == "active":
            return ActionReceipt("failed", "模拟：请先取消当前导航")
        self.current_goal = location
        self.state = "active"
        return await self.navigation_status(deadline=deadline)

    async def cancel_navigation(self, *, deadline: float) -> ActionReceipt:
        """取消活动目标；无活动目标时保持状态，可重复查询和取消。"""
        if self.state == "active":
            self.state = "cancelled"
        return await self.navigation_status(deadline=deadline)

    async def navigation_status(self, *, deadline: float) -> ActionReceipt:
        """报告模拟任务状态，活动状态不宣称已到达目标。"""
        return simulated(
            f"导航 {self.state}，目标 {self.current_goal}",
            state=self.state,
            is_navigating=self.state == "active",
            current_goal=self.current_goal,
        )


def navigation_actions(
    navigation: NavigationSimulation,
) -> List[ActionDefinition]:
    """连接本能力输入模型和异步执行入口。"""
    return [
        ActionDefinition(
            name="navigate_to",
            description="模拟提交目标；未知目标或已有活动任务明确失败。",
            inputs=LocationInput,
            handler=navigation.navigate_to,
            aliases=("go_to",),
        ),
        ActionDefinition(
            name="add_location",
            description="注册或替换位置，不发出地图或设备调用。",
            inputs=PoseInput,
            handler=navigation.add_location,
        ),
        ActionDefinition(
            name="cancel_navigation",
            description="取消活动目标；无活动目标时保持状态，可重复查询和取消。",
            inputs=NoArguments,
            handler=navigation.cancel_navigation,
        ),
        ActionDefinition(
            name="navigation_status",
            description="报告模拟任务状态，活动状态不宣称已到达目标。",
            inputs=NoArguments,
            handler=navigation.navigation_status,
        ),
        ActionDefinition(
            name="list_locations",
            description="返回全部已注册位置的快照。",
            inputs=NoArguments,
            handler=navigation.list_locations,
        ),
    ]


RECOMMENDATIONS = {
    "小幸运": ["青花瓷", "稻香", "夜曲", "告白气球"],
    "青花瓷": ["小幸运", "稻香", "夜曲", "东风破"],
    "稻香": ["小幸运", "青花瓷", "夜曲", "听妈妈的话"],
    "夜曲": ["小幸运", "青花瓷", "稻香", "七里香"],
    "告白气球": ["小幸运", "青花瓷", "稻香", "等你下课"],
    "东风破": ["青花瓷", "小幸运", "稻香", "夜曲"],
    "七里香": ["夜曲", "小幸运", "青花瓷", "稻香"],
    "听妈妈的话": ["稻香", "小幸运", "青花瓷", "夜曲"],
    "等你下课": ["告白气球", "小幸运", "青花瓷", "稻香"],
}


class MusicSimulation:
    """歌曲、队列和播放状态共同归属音乐模拟，不启动播放器。"""

    def __init__(self, display: Callable[[str], ActionReceipt]) -> None:
        """初始化独立队列；is_playing 可供语音会话过滤读取。"""
        self._display = display
        self.current_song = ""
        self.queue: List[str] = []
        self.is_playing = False

    async def play_music(
        self, song_name: str, *, deadline: float
    ) -> ActionReceipt:
        """模拟切换当前歌曲，保留等待队列。"""
        self.current_song = song_name
        self.is_playing = True
        self._display("兴奋")
        return await self.music_status(deadline=deadline)

    async def stop_music(self, *, deadline: float) -> ActionReceipt:
        """停止播放但保留当前歌曲与队列，遵循旧音乐状态契约。"""
        self.is_playing = False
        self._display("正常")
        return await self.music_status(deadline=deadline)

    async def next_song(self, *, deadline: float) -> ActionReceipt:
        """优先按序消费队列，空队列使用源推荐表的首首歌曲。"""
        song = (
            self.queue.pop(0) if self.queue else self._recommendations(None)[0]
        )
        return await self.play_music(song, deadline=deadline)

    async def add_to_queue(
        self, song_name: str, *, deadline: float
    ) -> ActionReceipt:
        """保留重复歌曲和入队顺序，不自动开始播放。"""
        self.queue.append(song_name)
        return await self.music_status(deadline=deadline)

    async def recommend_songs(
        self, song_name: Optional[str], *, deadline: float
    ) -> ActionReceipt:
        """返回源静态推荐，不拉取在线歌曲或修改播放状态。"""
        songs = self._recommendations(song_name)
        return simulated("推荐歌曲 " + "、".join(songs), songs=songs)

    def _recommendations(self, song_name: Optional[str]) -> List[str]:
        """未指定歌曲时使用当前曲目，排除作为推荐依据的歌曲。"""
        seed = self.current_song if song_name is None else song_name
        songs = RECOMMENDATIONS.get(seed, ["小幸运", "青花瓷", "稻香", "夜曲"])
        return [song for song in songs if song != seed]

    async def music_status(self, *, deadline: float) -> ActionReceipt:
        """返回播放快照，保持会话过滤所需的 is_playing 字段。"""
        return simulated(
            f"音乐 {'播放中' if self.is_playing else '已停止'}，"
            f"当前歌曲 {self.current_song}，队列 {self.queue}",
            is_playing=self.is_playing,
            current_song=self.current_song,
            queue=self.queue,
        )


def music_actions(music: MusicSimulation) -> List[ActionDefinition]:
    """连接本能力输入模型和异步执行入口。"""
    return [
        ActionDefinition(
            name="play_music",
            description="模拟切换当前歌曲，保留等待队列。",
            inputs=SongInput,
            handler=music.play_music,
            aliases=("play_song",),
        ),
        ActionDefinition(
            name="stop_music",
            description="停止播放但保留当前歌曲与队列，遵循旧音乐状态契约。",
            inputs=NoArguments,
            handler=music.stop_music,
        ),
        ActionDefinition(
            name="next_song",
            description="优先按序消费队列，空队列使用源推荐表的首首歌曲。",
            inputs=NoArguments,
            handler=music.next_song,
        ),
        ActionDefinition(
            name="add_to_queue",
            description="保留重复歌曲和入队顺序，不自动开始播放。",
            inputs=SongInput,
            handler=music.add_to_queue,
        ),
        ActionDefinition(
            name="recommend_songs",
            description="返回源静态推荐，不拉取在线歌曲或修改播放状态。",
            inputs=RecommendationInput,
            handler=music.recommend_songs,
        ),
        ActionDefinition(
            name="music_status",
            description="返回播放快照，保持会话过滤所需的 is_playing 字段。",
            inputs=NoArguments,
            handler=music.music_status,
        ),
    ]


class VolumeSimulation:
    """独立管理音量和静音状态，不调用 amixer 或系统混音器。"""

    def __init__(self) -> None:
        """初始模拟音量为50，未静音。"""
        self.level = 50
        self.is_muted = False

    async def volume_up(
        self, step: float, *, deadline: float
    ) -> ActionReceipt:
        """增加音量，保留静音开关。"""
        self.level = min(100, self.level + step)
        return await self.volume_status(deadline=deadline)

    async def volume_down(
        self, step: float, *, deadline: float
    ) -> ActionReceipt:
        """减少音量，保留静音开关。"""
        self.level = max(0, self.level - step)
        return await self.volume_status(deadline=deadline)

    async def volume_set(
        self, level: float, *, deadline: float
    ) -> ActionReceipt:
        """模拟源 level 的整数转换与0至100饱和。"""
        self.level = max(0, min(100, int(level)))
        return await self.volume_status(deadline=deadline)

    async def volume_mute(self, *, deadline: float) -> ActionReceipt:
        """静音但保留原音量。"""
        self.is_muted = True
        return await self.volume_status(deadline=deadline)

    async def volume_unmute(self, *, deadline: float) -> ActionReceipt:
        """取消静音，不重置音量。"""
        self.is_muted = False
        return await self.volume_status(deadline=deadline)

    async def volume_status(self, *, deadline: float) -> ActionReceipt:
        """返回模拟音量与静音快照。"""
        return simulated(
            f"音量 {self.level}，静音 {self.is_muted}",
            level=self.level,
            is_muted=self.is_muted,
        )


def volume_actions(volume: VolumeSimulation) -> List[ActionDefinition]:
    """连接本能力输入模型和异步执行入口。"""
    return [
        ActionDefinition(
            name="volume_up",
            description="增加音量，保留静音开关。",
            inputs=StepInput,
            handler=volume.volume_up,
        ),
        ActionDefinition(
            name="volume_down",
            description="减少音量，保留静音开关。",
            inputs=StepInput,
            handler=volume.volume_down,
        ),
        ActionDefinition(
            name="volume_set",
            description="模拟源 level 的整数转换与0至100饱和。",
            inputs=LevelInput,
            handler=volume.volume_set,
        ),
        ActionDefinition(
            name="volume_mute",
            description="静音但保留原音量。",
            inputs=NoArguments,
            handler=volume.volume_mute,
        ),
        ActionDefinition(
            name="volume_unmute",
            description="取消静音，不重置音量。",
            inputs=NoArguments,
            handler=volume.volume_unmute,
        ),
        ActionDefinition(
            name="volume_status",
            description="返回模拟音量与静音快照。",
            inputs=NoArguments,
            handler=volume.volume_status,
        ),
    ]


def wifi_status() -> ActionReceipt:
    """查询固定模拟网络，文档专用IP不代表主机真实连接。"""
    return simulated(
        "WiFi 已连接 simulated-network，IP 192.0.2.2",
        connected=True,
        ssid="simulated-network",
        ip="192.0.2.2",
    )


def show_wifi_info(display: Callable[[str], ActionReceipt]) -> ActionReceipt:
    """模拟LCD显示WiFi信息，不查询主机网络或创建屏幕驱动。"""
    display("wifi_info")
    return wifi_status()


def wifi_actions(
    display: Callable[[str], ActionReceipt],
) -> List[ActionDefinition]:
    """绑定共享 LCD，不查询主机网络。"""

    async def status(*, deadline: float) -> ActionReceipt:
        """返回模拟网络状态。"""
        return wifi_status()

    async def show(*, deadline: float) -> ActionReceipt:
        """更新 LCD 并返回模拟网络状态。"""
        return show_wifi_info(display)

    return [
        ActionDefinition(
            name="wifi_status",
            description="查询模拟 WiFi 连接及 IP",
            inputs=NoArguments,
            handler=status,
            aliases=("get_wifi_ip",),
        ),
        ActionDefinition(
            name="show_wifi_info",
            description="在模拟 LCD 显示 WiFi 信息",
            inputs=NoArguments,
            handler=show,
        ),
    ]


def simulate_cue(kind: str) -> ActionReceipt:
    """启动及错误提示音只输出日志，无播放器和音频产物。"""
    if kind not in ("startup", "error"):
        raise ValueError("未知提示音")
    return simulated("提示音 " + kind + "，不播放", cue=kind)
