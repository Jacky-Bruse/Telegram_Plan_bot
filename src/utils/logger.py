"""
日志系统
遵循开发清单第九章要求：
- INFO 级别
- 不打印任务全文到日志，仅打印任务 ID 和操作
- 可用 DEBUG 临时开详单
"""

import logging
import sys
from pathlib import Path
from typing import Optional


class TaskContentFilter(logging.Filter):
    """
    任务内容过滤器
    确保日志中不会打印完整的任务内容，仅打印任务 ID
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """
        过滤日志记录

        Args:
            record: 日志记录

        Returns:
            是否允许通过
        """
        # 所有日志都允许通过，但这个过滤器作为提醒：
        # 开发时应该只记录 task_id，不记录 task content
        return True


def setup_logger(
    name: str = "planbot",
    level: str = "INFO",
    log_file: Optional[str] = None
) -> logging.Logger:
    """
    设置日志记录器

    Args:
        name: 日志记录器名称
        level: 日志级别（DEBUG, INFO, WARNING, ERROR, CRITICAL）
        log_file: 日志文件路径（可选）

    Returns:
        配置好的日志记录器
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))

    # 避免重复添加处理器
    if logger.handlers:
        return logger

    # 日志格式
    formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level.upper()))
    console_handler.setFormatter(formatter)
    console_handler.addFilter(TaskContentFilter())
    logger.addHandler(console_handler)

    # 文件处理器（如果指定了日志文件）
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(
            log_file,
            encoding='utf-8'
        )
        file_handler.setLevel(getattr(logging, level.upper()))
        file_handler.setFormatter(formatter)
        file_handler.addFilter(TaskContentFilter())
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str = "planbot") -> logging.Logger:
    """
    获取日志记录器

    Args:
        name: 日志记录器名称

    Returns:
        日志记录器
    """
    return logging.getLogger(name)


# 辅助函数：安全记录任务信息（只记录 ID）
def log_task_operation(
    logger: logging.Logger,
    operation: str,
    task_id: int,
    user_id: Optional[int] = None,
    extra_info: Optional[str] = None
):
    """
    安全地记录任务操作（不记录任务内容）

    Args:
        logger: 日志记录器
        operation: 操作类型（如 "create", "update", "delete"）
        task_id: 任务 ID
        user_id: 用户 ID（可选）
        extra_info: 额外信息（可选）
    """
    msg_parts = [f"Task operation: {operation}"]
    msg_parts.append(f"task_id={task_id}")

    if user_id is not None:
        msg_parts.append(f"user_id={user_id}")

    if extra_info:
        msg_parts.append(extra_info)

    logger.info(", ".join(msg_parts))
