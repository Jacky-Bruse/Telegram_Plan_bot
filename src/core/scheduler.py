"""
定时调度系统
使用 APScheduler 为每个用户管理晚间例行和早间清单任务
严格按照文档第 6 章的 Job 规则
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional
import pytz

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import Bot

from src.db.database import Database
from src.db.models import User
from src.bot.messages import (
    get_daily_review_header,
    format_task_item,
    get_new_plan_prompt,
    get_morning_checklist_header,
)
from src.bot.handlers import create_task_buttons, create_new_plan_buttons
from src.constants import (
    STATUS_PENDING, STATUS_MISSED,
    MAX_TASKS_PER_MESSAGE, BATCH_SEND_DELAY,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


class TaskScheduler:
    """任务调度器"""

    def __init__(self, bot: Bot, db: Database):
        """
        初始化调度器

        Args:
            bot: Telegram Bot 实例
            db: 数据库实例
        """
        self.bot = bot
        self.db = db
        self.scheduler = AsyncIOScheduler(timezone='UTC')

        logger.info("Scheduler initialized")

    def start(self):
        """启动调度器"""
        self.scheduler.start()
        logger.info("Scheduler started")

    def shutdown(self):
        """关闭调度器"""
        self.scheduler.shutdown()
        logger.info("Scheduler shut down")

    def rebuild_user_jobs(self, user: User):
        """
        重建用户的所有 Job
        用于初始化或配置更新后立即生效
        严格按照文档第 6 章

        Args:
            user: 用户对象
        """
        # 移除旧 Job
        self._remove_user_jobs(user.id)

        # 创建晚间例行 Job
        self._schedule_evening_job(user)

        # 创建早间清单 Job（如果未关闭）
        if user.morning_hour is not None and user.morning_hour >= 0:
            self._schedule_morning_job(user)

        logger.info(
            f"Jobs rebuilt for user {user.chat_id}: "
            f"evening={user.evening_hour:02d}:{user.evening_min:02d}, "
            f"morning={user.morning_hour if user.morning_hour else 'off'}"
        )

    def rebuild_all_jobs(self):
        """
        重建所有用户的 Job
        进程启动时调用
        严格按照文档第 6 章
        """
        users = self.db.get_all_users()

        for user in users:
            self.rebuild_user_jobs(user)

        logger.info(f"All jobs rebuilt for {len(users)} users")

    def _remove_user_jobs(self, user_id: int):
        """移除用户的所有 Job"""
        evening_job_id = f"evening_{user_id}"
        morning_job_id = f"morning_{user_id}"

        if self.scheduler.get_job(evening_job_id):
            self.scheduler.remove_job(evening_job_id)

        if self.scheduler.get_job(morning_job_id):
            self.scheduler.remove_job(morning_job_id)

    def _schedule_evening_job(self, user: User):
        """
        创建晚间例行 Job（22:00 或用户设定时间）
        严格按照文档第 2.2-2.3 章节
        """
        job_id = f"evening_{user.id}"
        tz = pytz.timezone(user.tz)

        # 使用 CronTrigger，在用户时区的指定时间触发
        trigger = CronTrigger(
            hour=user.evening_hour,
            minute=user.evening_min,
            timezone=tz
        )

        self.scheduler.add_job(
            self._evening_routine,
            trigger=trigger,
            id=job_id,
            args=[user.id],
            replace_existing=True
        )

    def _schedule_morning_job(self, user: User):
        """
        创建早间清单 Job（08:30 或用户设定时间）
        严格按照文档第 2.4 章节
        """
        job_id = f"morning_{user.id}"
        tz = pytz.timezone(user.tz)

        # 使用 CronTrigger
        trigger = CronTrigger(
            hour=user.morning_hour,
            minute=user.morning_min,
            timezone=tz
        )

        self.scheduler.add_job(
            self._morning_checklist,
            trigger=trigger,
            id=job_id,
            args=[user.id],
            replace_existing=True
        )

    async def _evening_routine(self, user_id: int):
        """
        晚间例行任务
        1. 推送日终核对（当日到期任务）
        2. 推送新计划征集（当晚只问1次）
        严格按照文档第 2.2-2.3 章节
        """
        logger.info(f"Evening routine triggered for user_id={user_id}")

        # 根据 user_id 获取用户
        user = self.db.get_user_by_id(user_id)
        if not user:
            logger.warning(f"User not found: user_id={user_id}")
            return

        chat_id = user.chat_id

        # 重置 skipped_tonight 标记（每天晚间例行开始时重置，为当晚的征集做准备）
        # 这样无论用户是否开启早间清单，都能确保"每天重置"的效果
        self.db.set_user_skipped_tonight(user.id, False)

        # 获取用户时区的今天日期
        tz = pytz.timezone(user.tz)
        today = datetime.now(tz).strftime('%Y-%m-%d')

        # 1. 日终核对：获取当日到期的 pending/missed 任务
        tasks = self.db.get_tasks_by_user_and_date(
            user.id,
            today,
            statuses=[STATUS_PENDING, STATUS_MISSED]
        )

        if tasks:
            # 发送日终核对（分批发送，每批最多 MAX_TASKS_PER_MESSAGE 项）
            await self._send_daily_review(chat_id, tasks, is_makeup=False)

        # 2. 新计划征集（当晚只问 1 次）
        # 重新获取用户对象，因为 skipped_tonight 可能在按钮回调中被修改
        user = self.db.get_user_by_id(user_id)
        if user and not user.skipped_tonight:
            await self._send_new_plan_prompt(chat_id)

        logger.info(f"Evening routine completed for user_id={user_id}, chat_id={chat_id}")

    async def _morning_checklist(self, user_id: int):
        """
        早间清单任务
        推送当日 pending/missed 任务
        若无则不发（静默）
        严格按照文档第 2.4 章节
        """
        logger.info(f"Morning checklist triggered for user_id={user_id}")

        # 根据 user_id 获取用户
        user = self.db.get_user_by_id(user_id)
        if not user:
            logger.warning(f"User not found: user_id={user_id}")
            return

        chat_id = user.chat_id

        # 获取用户时区的今天日期
        tz = pytz.timezone(user.tz)
        today = datetime.now(tz).strftime('%Y-%m-%d')

        # 获取当日 pending/missed 任务
        tasks = self.db.get_tasks_by_user_and_date(
            user.id,
            today,
            statuses=[STATUS_PENDING, STATUS_MISSED]
        )

        if not tasks:
            # 若无任务，不发送（静默）
            logger.info(f"No tasks for morning checklist: user_id={user_id}")
            return

        # 发送早间清单
        lines = [get_morning_checklist_header()]
        for task in tasks:
            lines.append(format_task_item(task))

        message = "\n".join(lines)
        await self.bot.send_message(chat_id=chat_id, text=message)

        logger.info(f"Morning checklist sent to user_id={user_id}, tasks_count={len(tasks)}")

    async def _send_daily_review(self, chat_id: int, tasks: list, is_makeup: bool):
        """
        发送日终核对
        分批发送，每批最多 MAX_TASKS_PER_MESSAGE 项
        严格按照文档第 2.2 和 8 章节（分批策略）

        Args:
            chat_id: Telegram chat_id
            tasks: 任务列表
            is_makeup: 是否是补发
        """
        # 先发送标题
        header = get_daily_review_header(is_makeup)
        await self.bot.send_message(chat_id=chat_id, text=header)

        # 分批发送任务
        for i in range(0, len(tasks), MAX_TASKS_PER_MESSAGE):
            batch = tasks[i:i + MAX_TASKS_PER_MESSAGE]

            for task in batch:
                # 每条任务单独发送，附带三键按钮
                message = f"{format_task_item(task)}"
                buttons = create_task_buttons(task.id)

                await self.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    reply_markup=buttons
                )

            # 批间延迟（避免429限流）
            if i + MAX_TASKS_PER_MESSAGE < len(tasks):
                await asyncio.sleep(BATCH_SEND_DELAY)

        logger.info(f"Daily review sent to chat_id={chat_id}, tasks_count={len(tasks)}")

    async def _send_new_plan_prompt(self, chat_id: int):
        """
        发送新计划征集提示
        严格按照文档第 2.3 章节
        """
        message = get_new_plan_prompt()
        buttons = create_new_plan_buttons()

        await self.bot.send_message(
            chat_id=chat_id,
            text=message,
            reply_markup=buttons
        )

        logger.info(f"New plan prompt sent to chat_id={chat_id}")

    async def send_makeup_review(self, user_id: int):
        """
        发送补发的日终核对
        用于停机恢复后补发昨日未清任务
        严格按照文档第 6 和 8 章节

        Args:
            user_id: 用户 ID
        """
        logger.info(f"Makeup review triggered for user_id={user_id}")

        # 根据 user_id 获取用户
        user = self.db.get_user_by_id(user_id)
        if not user:
            logger.warning(f"User not found: user_id={user_id}")
            return

        chat_id = user.chat_id

        # 获取用户时区的昨天日期
        tz = pytz.timezone(user.tz)
        yesterday = (datetime.now(tz) - timedelta(days=1)).strftime('%Y-%m-%d')

        # 获取昨天到期的 pending/missed 任务
        tasks = self.db.get_tasks_by_user_and_date(
            user.id,
            yesterday,
            statuses=[STATUS_PENDING, STATUS_MISSED]
        )

        if tasks:
            # 发送补发的日终核对
            await self._send_daily_review(chat_id, tasks, is_makeup=True)
            logger.info(f"Makeup review sent to user_id={user_id}, tasks_count={len(tasks)}")
