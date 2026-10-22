"""无需 ROS、云端凭证或硬件的完整模拟演示，输入固定模型响应。"""

import asyncio
import json
from typing import Any, Dict, List, Optional

from robot_agent.actions.capabilities import create_default_actions
from robot_agent.actions.simulation import simulate_cue
from robot_agent.conversation.agent import Agent
from robot_agent.results import ModelReply, ToolCall, result_to_json


class FixedDemoProvider:
    """演示专用固定模型，不能作为真实在线验收证据。"""

    def __init__(self) -> None:
        """初始化本轮动作建议。"""
        self.actions: List[Dict[str, Any]] = []
        self.turn = 0

    async def complete(
        self, text: str, deadline: float, *, tools=None
    ) -> ModelReply:
        """按在线契约返回固定动作列表。"""
        self.turn += 1
        return ModelReply(
            response="模拟建议",
            tool_calls=tuple(
                ToolCall(
                    call_id="demo_{}_{}".format(self.turn, index),
                    name=action["name"],
                    arguments=action["arguments"],
                )
                for index, action in enumerate(self.actions)
            ),
        )

    async def aclose(self, deadline: Optional[float] = None) -> None:
        """固定模型没有本地连接资源。"""
        pass


def _cue_json(kind: str) -> Dict[str, Any]:
    """将模拟提示回执投影成终端可读 JSON，不输出内部对象。"""
    receipt = simulate_cue(kind)
    return {
        "status": receipt.status,
        "detail": receipt.detail,
        "data": dict(receipt.data),
    }


async def _run_demo() -> None:
    """逐轮展示动作、状态、查询、重复及失败停止，始终保持模拟。"""
    # 1. 固定 provider 只用于演示；缺失设备使用默认模拟注册表。
    provider = FixedDemoProvider()
    agent = Agent(provider, create_default_actions().registry)
    print(json.dumps(_cue_json("startup"), ensure_ascii=False))
    scenarios = [
        (
            "设置头部并两次呼吸后苏醒",
            [
                {
                    "name": "head_position",
                    "arguments": {"pitch": 80, "yaw": 100},
                },
                {"name": "head_breathing", "arguments": {"cycles": 2}},
                {"name": "head_breathing", "arguments": {"cycles": 2}},
                {"name": "wake_up", "arguments": {}},
            ],
        ),
        (
            "注册书房并导航、查询、取消",
            [
                {
                    "name": "add_location",
                    "arguments": {"name": "书房", "x": 1, "y": 2},
                },
                {"name": "list_locations", "arguments": {}},
                {"name": "navigate_to", "arguments": {"location": "书房"}},
                {"name": "navigation_status", "arguments": {}},
                {"name": "cancel_navigation", "arguments": {}},
                {"name": "navigation_status", "arguments": {}},
            ],
        ),
        (
            "播放音乐、队列切歌、推荐与停止",
            [
                {"name": "play_music", "arguments": {"song_name": "小幸运"}},
                {"name": "add_to_queue", "arguments": {"song_name": "夜曲"}},
                {"name": "next_song", "arguments": {}},
                {"name": "recommend_songs", "arguments": {}},
                {"name": "music_status", "arguments": {}},
                {"name": "stop_music", "arguments": {}},
                {"name": "music_status", "arguments": {}},
            ],
        ),
        (
            "音量、静音与模拟WiFi显示",
            [
                {"name": "volume_set", "arguments": {"level": 80}},
                {"name": "volume_down", "arguments": {}},
                {"name": "volume_mute", "arguments": {}},
                {"name": "volume_status", "arguments": {}},
                {"name": "volume_unmute", "arguments": {}},
                {"name": "show_wifi_info", "arguments": {}},
                {"name": "wifi_status", "arguments": {}},
                {"name": "wifi_status", "arguments": {}},
            ],
        ),
        (
            "未知目标失败后不能继续动作",
            [
                {"name": "navigate_to", "arguments": {"location": "不存在"}},
                {"name": "head_smile", "arguments": {}},
            ],
        ),
    ]

    # 2. 始终从交互输入提交，观察可信回执，不调用私有执行器。
    for text, functions in scenarios:
        provider.actions = functions
        result = await agent.submit(text)
        print(
            json.dumps(
                {"input": text, "result": result_to_json(result)},
                ensure_ascii=False,
            )
        )
        if result.status == "failed":
            print(json.dumps(_cue_json("error"), ensure_ascii=False))


def main() -> None:
    """命令入口统一启动异步演示回合。"""
    asyncio.run(_run_demo())


if __name__ == "__main__":
    main()
