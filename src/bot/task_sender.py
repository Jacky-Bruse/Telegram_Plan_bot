"""任务列表发送辅助函数"""

import asyncio
from typing import Sequence

from telegram import Bot

from src.db.models import Task
from src.bot.messages import format_task_item
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
