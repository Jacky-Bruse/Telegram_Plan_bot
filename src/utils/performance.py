"""
性能监控工具
用于诊断 Bot 响应延迟问题
"""

import time
import functools
from typing import Optional, Callable, Any
from contextlib import contextmanager

from src.utils.logger import get_logger

logger = get_logger(__name__)


class PerformanceTimer:
    """性能计时器"""

    def __init__(self, operation_name: str, chat_id: Optional[int] = None):
        """
        初始化计时器

        Args:
            operation_name: 操作名称
            chat_id: 用户 chat_id（可选）
        """
        self.operation_name = operation_name
        self.chat_id = chat_id
        self.start_time = None
        self.end_time = None

    def __enter__(self):
        """进入上下文管理器"""
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文管理器"""
        self.end_time = time.time()
        elapsed = (self.end_time - self.start_time) * 1000  # 转换为毫秒

        chat_info = f"chat_id={self.chat_id} " if self.chat_id else ""
        logger.info(f"⏱️ PERF | {chat_info}{self.operation_name} | {elapsed:.2f}ms")


@contextmanager
def perf_timer(operation_name: str, chat_id: Optional[int] = None):
    """
    性能计时上下文管理器

    用法:
        with perf_timer("database_query", chat_id=123):
            # your code here

    Args:
        operation_name: 操作名称
        chat_id: 用户 chat_id（可选）
    """
    timer = PerformanceTimer(operation_name, chat_id)
    with timer:
        yield timer


def perf_monitor(operation_name: Optional[str] = None):
    """
    性能监控装饰器

    用法:
        @perf_monitor("my_function")
        async def my_function():
            pass

    Args:
        operation_name: 操作名称（可选，默认使用函数名）
    """
    def decorator(func: Callable) -> Callable:
        name = operation_name or func.__name__

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            # 尝试提取 chat_id
            chat_id = None
            if args and hasattr(args[0], 'effective_chat'):
                # 从 Update 对象提取
                chat_id = args[0].effective_chat.id

            with perf_timer(name, chat_id):
                return await func(*args, **kwargs)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            with perf_timer(name):
                return func(*args, **kwargs)

        # 根据函数类型返回对应的包装器
        if functools.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


class PerformanceLogger:
    """性能日志记录器（用于更详细的分段计时）"""

    def __init__(self, operation_name: str, chat_id: Optional[int] = None):
        """
        初始化性能日志记录器

        Args:
            operation_name: 操作名称
            chat_id: 用户 chat_id（可选）
        """
        self.operation_name = operation_name
        self.chat_id = chat_id
        self.start_time = time.time()
        self.last_checkpoint = self.start_time
        self.checkpoints = []

    def checkpoint(self, name: str):
        """
        添加检查点

        Args:
            name: 检查点名称
        """
        now = time.time()
        elapsed_from_start = (now - self.start_time) * 1000
        elapsed_from_last = (now - self.last_checkpoint) * 1000

        self.checkpoints.append({
            'name': name,
            'from_start': elapsed_from_start,
            'from_last': elapsed_from_last
        })

        chat_info = f"chat_id={self.chat_id} " if self.chat_id else ""
        logger.info(
            f"⏱️ PERF | {chat_info}{self.operation_name} | "
            f"[{name}] +{elapsed_from_last:.2f}ms (total: {elapsed_from_start:.2f}ms)"
        )

        self.last_checkpoint = now

    def finish(self):
        """完成计时并输出总结"""
        total_elapsed = (time.time() - self.start_time) * 1000
        chat_info = f"chat_id={self.chat_id} " if self.chat_id else ""
        logger.info(
            f"⏱️ PERF | {chat_info}{self.operation_name} | "
            f"[TOTAL] {total_elapsed:.2f}ms"
        )
