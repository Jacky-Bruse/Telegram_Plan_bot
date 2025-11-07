"""任务列表发送辅助函数"""

import asyncio
from typing import Sequence, Dict, List

from telegram import Bot

from src.db.models import Task
from src.bot.messages import format_task_item, get_week_header, _get_relative_date_label
from src.bot.keyboards import create_task_buttons
from src.constants import MAX_TASKS_PER_MESSAGE, BATCH_SEND_DELAY


async def send_tasks_with_buttons(
    bot: Bot,
    chat_id: int,
    tasks: Sequence[Task],
    header: str,
) -> None:
    """发送带按钮的任务列表。"""
    if not tasks:
        return

    await bot.send_message(chat_id=chat_id, text=header)

    for i in range(0, len(tasks), MAX_TASKS_PER_MESSAGE):
        batch = tasks[i : i + MAX_TASKS_PER_MESSAGE]

        for task in batch:
            await bot.send_message(
                chat_id=chat_id,
                text=format_task_item(task),
                reply_markup=create_task_buttons(task.id),
            )

        if i + MAX_TASKS_PER_MESSAGE < len(tasks):
            await asyncio.sleep(BATCH_SEND_DELAY)


async def send_week_tasks_with_buttons(
    bot: Bot,
    chat_id: int,
    tasks_by_date: Dict[str, List[Task]],
    timezone: str = "Asia/Shanghai",
) -> None:
    """
    发送按日期分组的任务列表（带按钮）

    Args:
        bot: Telegram Bot 实例
        chat_id: 用户 chat_id
        tasks_by_date: {日期: [任务列表], ...}
        timezone: 时区名称，用于计算相对时间标签
    """
    if not tasks_by_date:
        return

    # 发送标题
    header = get_week_header()
    await bot.send_message(chat_id=chat_id, text=header)

    # 遍历每个日期（按日期排序）
    for date_str, tasks in sorted(tasks_by_date.items()):
        # 获取相对时间标签（今天、明天、后天）
        relative_label = _get_relative_date_label(date_str, timezone)
        date_header = f"\n【{date_str}{relative_label}】"

        # 发送日期标题
        await bot.send_message(chat_id=chat_id, text=date_header)

        # 发送该日期的所有任务（每个任务带按钮）
        for task in tasks:
            await bot.send_message(
                chat_id=chat_id,
                text=format_task_item(task),
                reply_markup=create_task_buttons(task.id),
            )

        # 添加小延迟避免发送过快
        await asyncio.sleep(0.1)
