"""
定时调度系统
使用 APScheduler 为每个用户管理晚间例行、早间清单和定时提醒任务
严格按照文档第 6 章的 Job 规则
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional, List
import pytz

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from telegram import Bot

from src.db.database import Database
from src.db.models import User, Task
from src.bot.messages import (
    get_daily_review_header,
    format_task_item,
    get_new_plan_prompt,
    get_morning_checklist_header,
    get_overdue_review_header,
    get_overdue_warning,
    get_overdue_snooze_hint,
    format_overdue_task_item,
    get_reminder_message,
)
from src.bot.keyboards import (
    create_new_plan_buttons,
    create_overdue_snooze_buttons,
    create_reminder_buttons,
)
from src.bot.task_sender import send_tasks_with_buttons
from src.constants import (
    STATUS_PENDING, STATUS_MISSED, STATUS_DONE, STATUS_CANCELED,
    REMINDER_STATUS_SENT, REMINDER_STATUS_CANCELED,
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
        self.scheduler = AsyncIOScheduler(timezone='UTC', event_loop=asyncio.get_running_loop())

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
        重建用户的所有 Job（包括提醒 Job）
        用于初始化或配置更新后立即生效
        严格按照文档第 6 章

        Args:
            user: 用户对象
        """
        # 移除旧的定时 Job（不移除提醒 Job，提醒 Job 单独管理）
        self._remove_user_scheduled_jobs(user.id)

        # 创建晚间例行 Job
        self._schedule_evening_job(user)

        # 创建早间清单 Job（如果未关闭）
        if user.morning_hour is not None and user.morning_hour >= 0:
            self._schedule_morning_job(user)

        self._schedule_midnight_job(user)

        # 重建用户的提醒 Job（用于时区变更）
        self._rebuild_user_reminder_jobs(user)

        logger.info(
            f"Jobs rebuilt for user {user.chat_id}: "
            f"evening={user.evening_hour:02d}:{user.evening_min:02d}, "
            f"morning={user.morning_hour if user.morning_hour else 'off'}"
        )

    def rebuild_all_jobs(self) -> List[int]:
        """
        重建所有用户的 Job
        进程启动时调用
        严格按照文档第 6 章

        Returns:
            需要补发的任务 ID 列表（24小时内的过期提醒）
        """
        users = self.db.get_all_users()

        for user in users:
            self.rebuild_user_jobs(user)

        # 重建所有提醒 Job，返回需要补发的任务
        catchup_task_ids = self._rebuild_all_reminder_jobs()

        logger.info(f"All jobs rebuilt for {len(users)} users")
        return catchup_task_ids

    def _remove_user_scheduled_jobs(self, user_id: int):
        """移除用户的定时 Job（不包括提醒 Job）"""
        evening_job_id = f"evening_{user_id}"
        morning_job_id = f"morning_{user_id}"
        midnight_job_id = f"midnight_{user_id}"

        if self.scheduler.get_job(evening_job_id):
            self.scheduler.remove_job(evening_job_id)

        if self.scheduler.get_job(morning_job_id):
            self.scheduler.remove_job(morning_job_id)

        if self.scheduler.get_job(midnight_job_id):
            self.scheduler.remove_job(midnight_job_id)

    def _rebuild_user_reminder_jobs(self, user: User):
        """
        重建用户的所有提醒 Job
        用于时区变更后重建

        Args:
            user: 用户对象
        """
        # 获取用户所有待发送的提醒
        pending_reminders = self.db.get_pending_reminders_for_user(user.id)
        tz = pytz.timezone(user.tz)
        now = datetime.now(tz)

        for task in pending_reminders:
            if not task.reminder_at:
                continue

            # 解析提醒时间
            try:
                reminder_dt = datetime.strptime(task.reminder_at, "%Y-%m-%d %H:%M")
                reminder_dt = tz.localize(reminder_dt)

                # 只重建未来的提醒
                if reminder_dt > now:
                    self.schedule_reminder_job(task, user.tz)
            except ValueError as e:
                logger.error(f"Invalid reminder_at format: {task.reminder_at}, error: {e}")

    def _rebuild_all_reminder_jobs(self) -> List[int]:
        """
        重建所有待发送的提醒 Job（启动时调用）

        处理逻辑：
        - reminder_at > now：正常调度 DateTrigger
        - now - reminder_at <= 24h：返回任务ID，由调用方统一补发
        - now - reminder_at > 24h：标记为 canceled 并记录日志

        Returns:
            需要补发的任务 ID 列表
        """
        pending_reminders = self.db.get_all_pending_reminders()
        rebuilt_count = 0
        catchup_task_ids = []
        expired_count = 0

        for task in pending_reminders:
            if not task.reminder_at:
                continue

            # 获取任务对应的用户
            user = self.db.get_user_by_id(task.user_id)
            if not user:
                continue

            tz = pytz.timezone(user.tz)
            now = datetime.now(tz)

            # 解析提醒时间
            try:
                reminder_dt = datetime.strptime(task.reminder_at, "%Y-%m-%d %H:%M")
                reminder_dt = tz.localize(reminder_dt)

                if reminder_dt > now:
                    # 未来的提醒：正常调度
                    self.schedule_reminder_job(task, user.tz)
                    rebuilt_count += 1
                elif (now - reminder_dt) <= timedelta(hours=24):
                    # 24小时内的过期提醒：收集任务ID，稍后统一补发
                    catchup_task_ids.append(task.id)
                    logger.info(
                        f"Pending catch-up reminder: task_id={task.id}, "
                        f"original_time={task.reminder_at}, overdue_by={(now - reminder_dt)}"
                    )
                else:
                    # 超过24小时的过期提醒：标记为 canceled
                    self.db.update_reminder_status(task.id, REMINDER_STATUS_CANCELED)
                    expired_count += 1
                    logger.info(
                        f"Expired reminder canceled: task_id={task.id}, "
                        f"original_time={task.reminder_at}, overdue_by={(now - reminder_dt)}"
                    )
            except ValueError as e:
                logger.error(f"Invalid reminder_at format: {task.reminder_at}, error: {e}")

        logger.info(
            f"Reminder jobs rebuilt: scheduled={rebuilt_count}, "
            f"pending_catchup={len(catchup_task_ids)}, expired={expired_count}"
        )
        return catchup_task_ids

    async def send_catchup_reminders(self, task_ids: List[int]):
        """
        发送补发的提醒消息（启动完成后调用）

        Args:
            task_ids: 需要补发的任务 ID 列表
        """
        if not task_ids:
            return

        logger.info(f"Sending {len(task_ids)} catch-up reminders")
        sent_count = 0

        for task_id in task_ids:
            try:
                await self._send_reminder(task_id)
                sent_count += 1
            except Exception as e:
                logger.error(f"Failed to send catch-up reminder: task_id={task_id}, error: {e}")

        logger.info(f"Catch-up reminders sent: {sent_count}/{len(task_ids)}")

    # ==================== 提醒 Job 管理 ====================

    def schedule_reminder_job(self, task: Task, timezone: str):
        """
        创建提醒 Job

        Args:
            task: 任务对象
            timezone: 用户时区
        """
        if not task.reminder_at:
            return

        job_id = f"remind_{task.id}"
        tz = pytz.timezone(timezone)

        try:
            # 解析提醒时间
            reminder_dt = datetime.strptime(task.reminder_at, "%Y-%m-%d %H:%M")
            reminder_dt = tz.localize(reminder_dt)

            # 使用 DateTrigger 创建一次性 Job
            trigger = DateTrigger(run_date=reminder_dt)

            self.scheduler.add_job(
                self._send_reminder,
                trigger=trigger,
                id=job_id,
                args=[task.id],
                replace_existing=True
            )

            logger.info(f"Reminder job scheduled: task_id={task.id}, reminder_at={task.reminder_at}")
        except ValueError as e:
            logger.error(f"Failed to schedule reminder: task_id={task.id}, error: {e}")

    def remove_reminder_job(self, task_id: int):
        """
        移除提醒 Job

        Args:
            task_id: 任务 ID
        """
        job_id = f"remind_{task_id}"

        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
            logger.info(f"Reminder job removed: task_id={task_id}")

    async def _send_reminder(self, task_id: int):
        """
        发送提醒消息

        Args:
            task_id: 任务 ID
        """
        logger.info(f"Reminder triggered for task_id={task_id}")

        # 获取任务
        task = self.db.get_task_by_id(task_id)
        if not task:
            logger.warning(f"Task not found: task_id={task_id}")
            return

        # 前置校验：任务是否已完成或取消
        if task.status in (STATUS_DONE, STATUS_CANCELED):
            # 不发送提醒，标记为已取消
            self.db.update_reminder_status(task_id, REMINDER_STATUS_CANCELED)
            logger.info(f"Reminder skipped (task already {task.status}): task_id={task_id}")
            return

        # 获取用户
        user = self.db.get_user_by_id(task.user_id)
        if not user:
            logger.warning(f"User not found: user_id={task.user_id}")
            return

        chat_id = user.chat_id

        # 发送提醒消息
        message = get_reminder_message(task.content, task.reminder_at, user.tz)
        buttons = create_reminder_buttons(task.id)

        try:
            await self.bot.send_message(
                chat_id=chat_id,
                text=message,
                reply_markup=buttons
            )

            # 更新提醒状态为已发送
            self.db.update_reminder_status(task_id, REMINDER_STATUS_SENT)
            logger.info(f"Reminder sent: task_id={task_id}, chat_id={chat_id}")
        except Exception as e:
            logger.error(f"Failed to send reminder: task_id={task_id}, error: {e}")

    # ==================== 定时任务 ====================

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

    def _schedule_midnight_job(self, user: User):
        """创建午夜滚动 Job，每天 00:00 触发"""
        job_id = f"midnight_{user.id}"
        tz = pytz.timezone(user.tz)

        trigger = CronTrigger(
            hour=0,
            minute=0,
            timezone=tz
        )

        self.scheduler.add_job(
            self._midnight_rollover,
            trigger=trigger,
            id=job_id,
            args=[user.id],
            replace_existing=True
        )

    async def _midnight_rollover(self, user_id: int):
        """午夜滚动：将过期的 pending 任务标记为 missed"""
        logger.info(f"Midnight rollover triggered for user_id={user_id}")

        user = self.db.get_user_by_id(user_id)
        if not user:
            logger.warning(f"User not found: user_id={user_id}")
            return

        tz = pytz.timezone(user.tz)
        today = datetime.now(tz).strftime('%Y-%m-%d')

        updated = self.db.mark_overdue_tasks_as_missed(user.id, today)
        logger.info(
            f"Midnight rollover completed: user_id={user.id}, updated={updated}"
        )

    async def _evening_routine(self, user_id: int):
        """
        晚间例行任务
        1. 推送逾期未清任务（如有）
        2. 推送日终核对（当日到期任务）
        3. 推送新计划征集（当晚只问1次）
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
        snoozed = user.overdue_snooze_date == today

        # 1. 逾期未清：获取 due_date < today 的 pending 任务
        overdue_tasks = self.db.get_overdue_tasks(user.id, today)
        if overdue_tasks and not snoozed:
            await self._send_overdue_review(chat_id, overdue_tasks)

        # 2. 日终核对：获取当日到期的 pending/missed 任务
        tasks = self.db.get_tasks_by_user_and_date(
            user.id,
            today,
            statuses=[STATUS_PENDING, STATUS_MISSED]
        )

        if tasks:
            # 发送日终核对（分批发送，每批最多 MAX_TASKS_PER_MESSAGE 项）
            await self._send_daily_review(chat_id, tasks, is_makeup=False)

        # 3. 新计划征集（当晚只问 1 次）
        # 重新获取用户对象，因为 skipped_tonight 可能在按钮回调中被修改
        user = self.db.get_user_by_id(user_id)
        if user and not user.skipped_tonight:
            await self._send_new_plan_prompt(chat_id)

        logger.info(f"Evening routine completed for user_id={user_id}, chat_id={chat_id}")

    async def _morning_checklist(self, user_id: int):
        """
        早间清单任务
        1. 显示逾期任务数量提示（如有）
        2. 推送当日 pending/missed 任务
        若无任何任务则不发（静默）
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
        snoozed = user.overdue_snooze_date == today

        # 获取逾期任务数量
        overdue_count = self.db.count_overdue_tasks(user.id, today)

        # 获取当日 pending/missed 任务
        tasks = self.db.get_tasks_by_user_and_date(
            user.id,
            today,
            statuses=[STATUS_PENDING, STATUS_MISSED]
        )

        # 若无逾期任务也无今日任务，静默
        if not tasks and (overdue_count == 0 or snoozed):
            logger.info(f"No tasks for morning checklist: user_id={user_id}")
            return

        # 构建消息
        lines = []
        show_overdue = overdue_count > 0 and not snoozed

        # 1. 逾期任务提示（如有）
        if show_overdue:
            lines.append(get_overdue_warning(overdue_count))
            lines.append(get_overdue_snooze_hint())
            lines.append("")  # 空行分隔

        # 2. 今日待办（如有）
        if tasks:
            lines.append(get_morning_checklist_header())
            for task in tasks:
                lines.append(format_task_item(task))

        message = "\n".join(lines)
        buttons = create_overdue_snooze_buttons() if show_overdue else None
        await self.bot.send_message(chat_id=chat_id, text=message, reply_markup=buttons)

        logger.info(
            f"Morning checklist sent to user_id={user_id}, "
            f"overdue_count={overdue_count}, today_tasks_count={len(tasks)}"
        )

    async def _send_overdue_review(self, chat_id: int, tasks: list):
        """
        发送逾期未清任务
        使用与日终核对相同的分批策略，带完整交互按钮

        Args:
            chat_id: Telegram chat_id
            tasks: 逾期任务列表
        """
        header = get_overdue_review_header()
        await send_tasks_with_buttons(
            self.bot, chat_id, tasks, header,
            format_func=format_overdue_task_item
        )

        logger.info(f"Overdue review sent to chat_id={chat_id}, tasks_count={len(tasks)}")

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
        header = get_daily_review_header(is_makeup)
        await send_tasks_with_buttons(self.bot, chat_id, tasks, header)

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
