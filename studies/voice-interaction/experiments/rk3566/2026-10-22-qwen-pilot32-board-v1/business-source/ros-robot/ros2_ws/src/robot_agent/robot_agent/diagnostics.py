"""配置标准终端日志，以异步上下文关联同一轮处理阶段。"""

import logging
from contextvars import ContextVar
from urllib.parse import urlsplit, urlunsplit

TRACE_ID = ContextVar("robot_agent_trace_id", default="")


def get_logger(name: str) -> logging.Logger:
    """显式传播到包入口，兼容LaunchLogger默认关闭传播的行为。"""
    logger = logging.getLogger(name)
    logger.propagate = True
    return logger


class TraceFilter(logging.Filter):
    """日志记录只携带关联编号，不读取用户内容或设备状态。"""

    def filter(self, record: logging.LogRecord) -> bool:
        """在输出时附加当前任务继承的关联编号。"""
        record.trace_id = TRACE_ID.get() or "-"
        return True


def configure_logging(level: str = "INFO") -> None:
    """入口配置本包日志；不改变第三方HTTP或ROS日志等级。"""
    if level not in ("DEBUG", "INFO", "WARNING", "ERROR"):
        raise ValueError("log_level 必须为 DEBUG、INFO、WARNING 或 ERROR")
    logger = logging.getLogger("robot_agent")
    logger.setLevel(level)
    logger.propagate = False
    if not any(
        handler.name == "robot-agent-console" for handler in logger.handlers
    ):
        handler = logging.StreamHandler()
        handler.set_name("robot-agent-console")
        handler.addFilter(TraceFilter())
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s [%(name)s] "
                "[trace=%(trace_id)s] %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        logger.addHandler(handler)


def safe_url(value: str) -> str:
    """日志URL去掉用户密码、查询参数和片段。"""
    parts = urlsplit(value)
    host = parts.hostname or ""
    if ":" in host:
        host = "[" + host + "]"
    if parts.port is not None:
        host += ":" + str(parts.port)
    return urlunsplit((parts.scheme, host, parts.path, "", ""))


def redact_payload(value, secret: str):
    """仅用于日志副本：隐藏已知密钥和凭证字段，不改变实际请求。"""
    if isinstance(value, dict):
        return {
            key: "<REDACTED>"
            if key.lower()
            in {"authorization", "api_key", "password", "token", "secret"}
            else redact_payload(item, secret)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_payload(item, secret) for item in value]
    if isinstance(value, str) and secret:
        return value.replace(secret, "<REDACTED>")
    return value
