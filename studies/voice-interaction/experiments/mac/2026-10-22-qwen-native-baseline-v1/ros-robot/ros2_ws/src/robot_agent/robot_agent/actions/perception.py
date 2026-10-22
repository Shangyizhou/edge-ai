"""感知动作流程：复用设备 Interface，不管理进程或输出运动命令。"""

import time
from typing import Dict, List, Optional, Protocol

from robot_agent.actions.contracts import ActionDefinition, NoArguments
from robot_agent.results import ActionReceipt


class PerceptionInterface(Protocol):
    """相机发布与已确认的跟随服务，传输在边缘变化。"""

    async def get_status(self, deadline: float) -> Dict:
        """读取tracker当前快照，不能用本入口缓存替代。"""
        ...

    async def aclose(self, deadline: Optional[float]) -> None:
        """原回执等待结束后释放设备Adapter。"""
        ...

    def camera(self, enabled: bool) -> Dict:
        """提交采集请求；成功只代表发布完成。"""
        ...

    async def set_enabled(
        self, kind: str, enabled: bool, deadline: float
    ) -> Dict:
        """等待服务最终回执；在途超时由交互 Interface 管理。"""
        ...


class PerceptionActions:
    """集中组织相机、融合和Follow；当前状态由设备查询。"""

    def __init__(self, interface: PerceptionInterface) -> None:
        """启动时不猜测其他入口控制的状态。"""
        self._interface = interface
        self._closed = False

    def stop(self) -> None:
        """立即禁止新步骤，但保留已提交请求的原回执等待。"""
        self._closed = True

    async def aclose(self, deadline: Optional[float]) -> None:
        """设备接收桥接由能力持有，执行收尾后才释放。"""
        self.stop()
        await self._interface.aclose(deadline)

    async def start_camera(self, *, deadline: float) -> ActionReceipt:
        """恢复采集，不把发布完成当作设备开启确认。"""
        if self._closed or time.monotonic() >= deadline:
            return ActionReceipt(
                "failed", "动作期限已过，未提交采集请求，不补执行"
            )
        return _receipt(self._interface.camera(True))

    async def stop_camera(self, *, deadline: float) -> ActionReceipt:
        """先确认 Follow standby，再暂停采集，失败则不继续。"""
        # 1. Follow 待机回执确认后，才提交无确认的相机开关。
        receipt = await self.disable_tracking(deadline=deadline)
        if receipt.status != "real_success":
            return receipt
        # 2. 只报告采集请求提交，不能声称相机硬件已停机。
        if self._closed or time.monotonic() >= deadline:
            return ActionReceipt(
                "failed",
                "Follow 已确认待机；入口退出或回执迟到，未提交相机暂停请求",
            )
        receipt = _receipt(self._interface.camera(False))
        return ActionReceipt(
            receipt.status, "Follow 已确认待机；" + receipt.detail
        )

    async def camera_status(self, *, deadline: float) -> ActionReceipt:
        """相机开关话题没有状态查询服务，不从本地意图推断状态。"""
        return ActionReceipt(
            "real_success", "相机采集状态未知：/enable_camera 无状态回执"
        )

    async def _set_state(
        self, kind: str, enabled: bool, deadline: float
    ) -> ActionReceipt:
        """成功服务回执更新记录，失败不推断设备当前状态。"""
        if self._closed:
            return ActionReceipt("failed", "入口退出，未提交后续设备请求")
        return _receipt(
            await self._interface.set_enabled(kind, enabled, deadline)
        )

    async def enable_lidar(self, *, deadline: float) -> ActionReceipt:
        """开启 tracker 扫描融合，保留服务端 TF/发布端检查。"""
        return await self._set_state("fusion", True, deadline)

    async def disable_lidar(self, *, deadline: float) -> ActionReceipt:
        """关闭融合，服务确认后记录其隐含的 Follow standby。"""
        return await self._set_state("fusion", False, deadline)

    async def start_following(self, *, deadline: float) -> ActionReceipt:
        """采集请求、融合确认、Follow 确认按序执行，不重试。"""
        # 1. 恢复相机采集，成功仅代表请求已发布。
        if self._closed or time.monotonic() >= deadline:
            return ActionReceipt(
                "failed", "动作期限已过，未提交采集或跟随请求"
            )
        receipt = await self.start_camera(deadline=deadline)
        if receipt.status != "real_success":
            return receipt
        # 2. 融合失败即停止，不越过 TF 和 LiDAR 前提。
        receipt = await self._set_state("fusion", True, deadline)
        if receipt.status != "real_success":
            return ActionReceipt(
                receipt.status,
                "采集请求已发布，无设备确认；融合：" + receipt.detail,
            )
        # 3. 服务端检查同步数据和近期扫描，不做相机跟随降级。
        if self._closed or time.monotonic() >= deadline:
            return ActionReceipt(
                "failed",
                "已确认融合；入口退出或回执迟到，未提交 Follow，不补执行",
            )
        fusion_detail = receipt.detail
        receipt = await self._set_state("follow", True, deadline)
        return ActionReceipt(
            receipt.status,
            "采集请求已发布，无设备确认；融合已确认："
            + fusion_detail
            + "；Follow："
            + receipt.detail,
        )

    async def enable_tracking(self, *, deadline: float) -> ActionReceipt:
        """仅启用 Follow，保留融合尚未开启时服务端拒绝的语义。"""
        return await self._set_state("follow", True, deadline)

    async def disable_tracking(self, *, deadline: float) -> ActionReceipt:
        """仅进入 Follow 待机，保持当前融合订阅。"""
        return await self._set_state("follow", False, deadline)

    async def stop_following(self, *, deadline: float) -> ActionReceipt:
        """按源动作先进入待机，再关闭融合；拒绝或超时不继续。"""
        # 1. 服务确认 Follow standby，不能把提交请求当作停止。
        receipt = await self._set_state("follow", False, deadline)
        if receipt.status != "real_success":
            return receipt
        # 2. 同一截止时间内关闭融合，不重试或补执行。
        follow_detail = receipt.detail
        if self._closed or time.monotonic() >= deadline:
            return ActionReceipt(
                "failed",
                "Follow 已确认待机；入口退出或回执迟到，未提交融合关闭请求",
            )
        receipt = await self._set_state("fusion", False, deadline)
        return ActionReceipt(
            receipt.status,
            "Follow 已确认待机："
            + follow_detail
            + "；融合："
            + receipt.detail,
        )

    async def toggle_following(self, *, deadline: float) -> ActionReceipt:
        """先读取设备当前状态再切换；跨入口不保证原子切换。"""
        receipt = await self.following_status(deadline=deadline)
        if receipt.status != "real_success":
            return receipt
        return (
            await self.stop_following(deadline=deadline)
            if receipt.data["state"]["follow"]
            else await self.start_following(deadline=deadline)
        )

    async def following_status(self, *, deadline: float) -> ActionReceipt:
        """读取ObjectTrack当前状态；不可用时不猜测或返回旧缓存。"""
        if self._closed or time.monotonic() >= deadline:
            return ActionReceipt("failed", "入口关闭或查询期限已过")
        return _receipt(await self._interface.get_status(deadline))


def _receipt(raw: Dict) -> ActionReceipt:
    """在设备边界转换回执，并保留查询状态快照。"""
    data = dict(raw.get("data") or {})
    if "state" in raw:
        data["state"] = raw["state"]
    return ActionReceipt(raw["status"], raw.get("detail", ""), data or None)


def perception_actions(
    perception: PerceptionActions,
) -> List[ActionDefinition]:
    """声明感知业务入口；别名集中到规范声明。"""
    return [
        ActionDefinition(
            name="start_camera",
            description="恢复采集，不把发布完成当作设备开启确认。",
            inputs=NoArguments,
            handler=perception.start_camera,
            aliases=("start_receiving_image",),
        ),
        ActionDefinition(
            name="stop_camera",
            description="先确认 Follow standby，再暂停采集，失败则不继续。",
            inputs=NoArguments,
            handler=perception.stop_camera,
            aliases=("stop_camera_collection",),
        ),
        ActionDefinition(
            name="query_camera_status",
            description="相机开关话题没有状态查询服务，不从本地意图推断状态。",
            inputs=NoArguments,
            handler=perception.camera_status,
        ),
        ActionDefinition(
            name="start_following",
            description="采集请求、融合确认、Follow 确认按序执行，不重试。",
            inputs=NoArguments,
            handler=perception.start_following,
            aliases=("start_tracking",),
        ),
        ActionDefinition(
            name="enable_tracking",
            description="仅启用 Follow，保留融合尚未开启时服务端拒绝的语义。",
            inputs=NoArguments,
            handler=perception.enable_tracking,
        ),
        ActionDefinition(
            name="stop_following",
            description="按源动作先进入待机，再关闭融合；拒绝或超时不继续。",
            inputs=NoArguments,
            handler=perception.stop_following,
        ),
        ActionDefinition(
            name="disable_tracking",
            description="仅进入 Follow 待机，保持当前融合订阅。",
            inputs=NoArguments,
            handler=perception.disable_tracking,
        ),
        ActionDefinition(
            name="toggle_following",
            description="先读取设备当前状态再切换；跨入口不保证原子切换。",
            inputs=NoArguments,
            handler=perception.toggle_following,
        ),
        ActionDefinition(
            name="following_status",
            description="读取ObjectTrack当前状态；不可用时不猜测或返回旧缓存。",
            inputs=NoArguments,
            handler=perception.following_status,
            aliases=("query_person_tracking_status",),
        ),
        ActionDefinition(
            name="enable_lidar",
            description="开启 tracker 扫描融合，保留服务端 TF/发布端检查。",
            inputs=NoArguments,
            handler=perception.enable_lidar,
        ),
        ActionDefinition(
            name="disable_lidar",
            description="关闭融合，服务确认后记录其隐含的 Follow standby。",
            inputs=NoArguments,
            handler=perception.disable_lidar,
        ),
    ]
