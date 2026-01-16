"""
Bot 命令处理器
严格按照开发清单第二章的交互稿实现
"""

import asyncio
import re
from datetime import datetime, timedelta
from typing import Optional, List
import pytz

from telegram import Update
from telegram.ext import ContextTypes

from src.db.database import Database
from src.db.models import User, Task
from src.core.date_parser import DateParser
from src.core.state_machine import TaskStateMachine
from src.bot.messages import (
    get_start_message,
    get_input_mode_instructions,
    format_task_creation_receipt,
    get_today_header,
    get_week_header,
    format_task_item,
    get_no_tasks_message,
    get_relative_date_label,
    get_timezone_updated_message,
    get_evening_time_updated_message,
    get_morning_time_updated_message,
    get_morning_time_disabled_message,
    get_invalid_timezone_message,
    get_invalid_time_format_message,
    get_input_truncated_message,
    get_text_truncated_warning,
    get_time_passed_create_message,
    get_time_passed_edit_message,
    get_reminder_message,
    get_reminder_updated_message,
    get_reminder_time_changed_message,
)
from src.bot.task_sender import send_tasks_with_buttons
from src.bot.keyboards import create_task_buttons, create_reminder_buttons
from src.constants import (
    STATUS_PENDING, STATUS_MISSED,
    MAX_INPUT_LINES, MAX_CONTENT_LENGTH,
    DEFAULT_TIMEZONE, DEFAULT_EVENING_HOUR, DEFAULT_EVENING_MINUTE,
    DEFAULT_MORNING_HOUR, DEFAULT_MORNING_MINUTE,
)
from src.utils.logger import get_logger
from src.utils.performance import PerformanceLogger

logger = get_logger(__name__)


class BotHandlers:
    """Bot 命令处理器"""

    def __init__(self, db: Database):
        """
        初始化处理器

        Args:
            db: 数据库实例
        """
        self.db = db
        self.state_machine = TaskStateMachine(db)

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /start 命令处理器
        严格按照文档 2.1 章节实现
        """
        chat_id = update.effective_chat.id
        perf = PerformanceLogger("cmd_start", chat_id)
        logger.info(f"User {chat_id} triggered /start")

        # 检查用户是否已存在
        user = self.db.get_user_by_chat_id(chat_id)
        perf.checkpoint("DB查询用户")

        if user is None:
            # 创建新用户
            user = self.db.create_user(
                chat_id=chat_id,
                tz=DEFAULT_TIMEZONE,
                evening_hour=DEFAULT_EVENING_HOUR,
                evening_min=DEFAULT_EVENING_MINUTE,
                morning_hour=DEFAULT_MORNING_HOUR,
                morning_min=DEFAULT_MORNING_MINUTE
            )
            perf.checkpoint("DB创建用户")

            if user is None:
                await update.message.reply_text("初始化失败，请稍后重试。")
                return

            logger.info(f"New user created: chat_id={chat_id}, user_id={user.id}")

        # 格式化时间
        evening_time = f"{user.evening_hour:02d}:{user.evening_min:02d}"

        if user.morning_hour is None or user.morning_hour < 0:
            morning_time = "关闭"
        else:
            morning_time = f"{user.morning_hour:02d}:{user.morning_min:02d}"

        # 发送欢迎消息（严格按照文档格式）
        message = get_start_message(user.tz, evening_time, morning_time)
        perf.checkpoint("准备消息")

        await update.message.reply_text(message)
        perf.checkpoint("Telegram发送消息")

        # 通知调度器重建 Job（通过 context.bot_data）
        if 'schedule_rebuild_callback' in context.bot_data:
            context.bot_data['schedule_rebuild_callback'](user)
            perf.checkpoint("重建调度任务")

        perf.finish()

    async def cmd_add(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /add 命令处理器
        进入一次性输入模式
        严格按照文档 2.3 和 2.5 章节
        """
        chat_id = update.effective_chat.id
        perf = PerformanceLogger("cmd_add", chat_id)

        user = self.db.get_user_by_chat_id(chat_id)
        perf.checkpoint("DB查询用户")

        if user is None:
            await update.message.reply_text("请先使用 /start 初始化。")
            return

        # 设置用户状态为等待输入
        self.db.set_user_awaiting_plans(user.id, True)
        perf.checkpoint("DB更新用户状态")
        logger.info(f"User {chat_id} entered input mode")

        # 发送输入说明
        await update.message.reply_text(get_input_mode_instructions())
        perf.checkpoint("Telegram发送消息")
        perf.finish()

    async def cmd_today(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /today 命令处理器
        输出当日 pending/missed 列表（不含 done/canceled）
        严格按照文档 2.5 章节
        """
        chat_id = update.effective_chat.id
        perf = PerformanceLogger("cmd_today", chat_id)

        user = self.db.get_user_by_chat_id(chat_id)
        perf.checkpoint("DB查询用户")

        if user is None:
            await update.message.reply_text("请先使用 /start 初始化。")
            return

        # 获取用户时区的今天日期
        tz = pytz.timezone(user.tz)
        today = datetime.now(tz).strftime('%Y-%m-%d')

        # 查询当日 pending/missed 任务
        tasks = self.db.get_tasks_by_user_and_date(
            user.id,
            today,
            statuses=[STATUS_PENDING, STATUS_MISSED]
        )
        perf.checkpoint("DB查询任务列表")

        if not tasks:
            await update.message.reply_text(get_no_tasks_message())
            perf.checkpoint("Telegram发送消息")
            perf.finish()
            return

        # 格式化任务列表
        header = get_today_header()
        await send_tasks_with_buttons(context.bot, chat_id, tasks, header)
        perf.checkpoint("Telegram发送任务列表")
        perf.finish()

    async def cmd_week(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /week 命令处理器
        输出从今日起 7 天内的任务（按日聚合）
        严格按照文档 2.5 章节
        """
        chat_id = update.effective_chat.id
        user = self.db.get_user_by_chat_id(chat_id)

        if user is None:
            await update.message.reply_text("请先使用 /start 初始化。")
            return

        # 获取用户时区的日期范围
        tz = pytz.timezone(user.tz)
        today = datetime.now(tz)
        start_date = today.strftime('%Y-%m-%d')
        end_date = (today + timedelta(days=6)).strftime('%Y-%m-%d')

        # 查询7天内的任务（数据库已按 due_date, id 排序）
        tasks = self.db.get_tasks_by_user_and_date_range(
            user.id,
            start_date,
            end_date,
            statuses=[STATUS_PENDING, STATUS_MISSED]
        )

        if not tasks:
            await update.message.reply_text("未来 7 天没有待办事项 ✅")
            return

        # 流式处理：直接按日期分组发送，无需构建 dict
        await self._send_tasks_by_date_stream(
            context.bot,
            chat_id,
            tasks,
            timezone=user.tz
        )

    async def _send_tasks_by_date_stream(
        self,
        bot,
        chat_id: int,
        tasks: List[Task],
        timezone: str
    ):
        """
        流式发送按日期分组的任务

        Args:
            bot: Telegram Bot 实例
            chat_id: 用户 chat_id
            tasks: 已按 due_date 排序的任务列表
            timezone: 时区名称
        """
        # 发送标题
        await bot.send_message(chat_id=chat_id, text=get_week_header())

        current_date = None
        current_tasks = []

        for task in tasks:
            if task.due_date != current_date:
                # 日期变化，发送之前的任务组
                if current_tasks:
                    await self._send_date_group(bot, chat_id, current_date, current_tasks, timezone)
                current_date = task.due_date
                current_tasks = [task]
            else:
                current_tasks.append(task)

        # 发送最后一组
        if current_tasks:
            await self._send_date_group(bot, chat_id, current_date, current_tasks, timezone)

    async def _send_date_group(
        self,
        bot,
        chat_id: int,
        date_str: str,
        tasks: List[Task],
        timezone: str
    ):
        """
        发送单个日期的任务组

        Args:
            bot: Telegram Bot 实例
            chat_id: 用户 chat_id
            date_str: 日期字符串 YYYY-MM-DD
            tasks: 该日期的任务列表
            timezone: 时区名称
        """
        # 发送日期标题
        relative_label = get_relative_date_label(date_str, timezone)
        date_header = f"\n【{date_str}{relative_label}】"
        await bot.send_message(chat_id=chat_id, text=date_header)

        # 发送该日期的所有任务（每个任务带按钮和序号）
        for index, task in enumerate(tasks, start=1):
            await bot.send_message(
                chat_id=chat_id,
                text=format_task_item(task, index),
                reply_markup=create_task_buttons(task.id),
            )

        # 添加小延迟避免发送过快
        await asyncio.sleep(0.1)

    async def cmd_setevening(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /setevening HH:MM 命令处理器
        更新晚间时间并立刻重建调度
        严格按照文档 2.5 章节
        """
        chat_id = update.effective_chat.id
        user = self.db.get_user_by_chat_id(chat_id)

        if user is None:
            await update.message.reply_text("请先使用 /start 初始化。")
            return

        # 解析时间参数
        if not context.args or len(context.args) != 1:
            await update.message.reply_text(get_invalid_time_format_message())
            return

        time_str = context.args[0]
        match = re.match(r'^(\d{1,2}):(\d{2})$', time_str)

        if not match:
            await update.message.reply_text(get_invalid_time_format_message())
            return

        hour, minute = int(match.group(1)), int(match.group(2))

        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            await update.message.reply_text(get_invalid_time_format_message())
            return

        # 更新数据库
        success = self.db.update_user_evening_time(user.id, hour, minute)

        if not success:
            await update.message.reply_text("更新失败，请稍后重试。")
            return

        logger.info(f"User {chat_id} updated evening time to {hour:02d}:{minute:02d}")

        # 发送确认消息
        await update.message.reply_text(get_evening_time_updated_message(f"{hour:02d}:{minute:02d}"))

        # 通知调度器重建 Job
        if 'schedule_rebuild_callback' in context.bot_data:
            # 重新获取用户对象
            user = self.db.get_user_by_chat_id(chat_id)
            context.bot_data['schedule_rebuild_callback'](user)

    async def cmd_setmorning(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /setmorning HH:MM 或 /setmorning off 命令处理器
        设置时间或关闭早间清单，并立刻重建调度
        严格按照文档 2.5 章节
        """
        chat_id = update.effective_chat.id
        user = self.db.get_user_by_chat_id(chat_id)

        if user is None:
            await update.message.reply_text("请先使用 /start 初始化。")
            return

        # 解析参数
        if not context.args or len(context.args) != 1:
            await update.message.reply_text("用法：/setmorning HH:MM 或 /setmorning off")
            return

        arg = context.args[0].lower()

        # 处理关闭
        if arg == "off":
            success = self.db.update_user_morning_time(user.id, None, None)

            if not success:
                await update.message.reply_text("更新失败，请稍后重试。")
                return

            logger.info(f"User {chat_id} disabled morning checklist")
            await update.message.reply_text(get_morning_time_disabled_message())

            # 通知调度器重建 Job（取消早间 Job）
            if 'schedule_rebuild_callback' in context.bot_data:
                user = self.db.get_user_by_chat_id(chat_id)
                context.bot_data['schedule_rebuild_callback'](user)

            return

        # 解析时间
        match = re.match(r'^(\d{1,2}):(\d{2})$', arg)

        if not match:
            await update.message.reply_text(get_invalid_time_format_message())
            return

        hour, minute = int(match.group(1)), int(match.group(2))

        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            await update.message.reply_text(get_invalid_time_format_message())
            return

        # 更新数据库
        success = self.db.update_user_morning_time(user.id, hour, minute)

        if not success:
            await update.message.reply_text("更新失败，请稍后重试。")
            return

        logger.info(f"User {chat_id} updated morning time to {hour:02d}:{minute:02d}")

        # 发送确认消息
        await update.message.reply_text(get_morning_time_updated_message(f"{hour:02d}:{minute:02d}"))

        # 通知调度器重建 Job
        if 'schedule_rebuild_callback' in context.bot_data:
            user = self.db.get_user_by_chat_id(chat_id)
            context.bot_data['schedule_rebuild_callback'](user)

    async def cmd_timezone(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /timezone <IANA名称> 命令处理器
        更新时区并立刻重建调度
        严格按照文档 2.5 和 8 章节
        """
        chat_id = update.effective_chat.id
        user = self.db.get_user_by_chat_id(chat_id)

        if user is None:
            await update.message.reply_text("请先使用 /start 初始化。")
            return

        # 解析时区参数
        if not context.args or len(context.args) != 1:
            await update.message.reply_text("用法：/timezone <IANA名称>，如 /timezone Asia/Shanghai")
            return

        tz_name = context.args[0]

        # 验证时区
        try:
            pytz.timezone(tz_name)
        except pytz.exceptions.UnknownTimeZoneError:
            await update.message.reply_text(get_invalid_timezone_message())
            return

        # 更新数据库
        success = self.db.update_user_timezone(user.id, tz_name)

        if not success:
            await update.message.reply_text("更新失败，请稍后重试。")
            return

        logger.info(f"User {chat_id} updated timezone to {tz_name}")

        # 发送确认消息
        await update.message.reply_text(get_timezone_updated_message(tz_name))

        # 通知调度器重建 Job
        if 'schedule_rebuild_callback' in context.bot_data:
            user = self.db.get_user_by_chat_id(chat_id)
            context.bot_data['schedule_rebuild_callback'](user)

    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        文本消息处理器
        处理一次性输入模式的多行任务和修改时间输入
        严格按照文档 2.3 章节和 8 章节（异常处理）
        """
        chat_id = update.effective_chat.id
        perf = PerformanceLogger("handle_text_message", chat_id)

        user = self.db.get_user_by_chat_id(chat_id)
        perf.checkpoint("DB查询用户")

        if user is None:
            return

        # 优先处理修改时间输入
        if user.awaiting_reminder_time and user.awaiting_reminder_task_id:
            await self._handle_reminder_time_input(update, context, user)
            perf.finish()
            return

        # 处理任务输入
        if not user.awaiting_plans:
            # 不在输入模式，忽略
            return

        text = update.message.text
        lines = text.strip().split('\n')

        # 处理输入截断（最多100行）
        truncated = False
        if len(lines) > MAX_INPUT_LINES:
            lines = lines[:MAX_INPUT_LINES]
            truncated = True

        # 解析任务
        parser = DateParser(user.tz)
        created_tasks = []
        warnings = []
        skipped_count = 0

        for i, line in enumerate(lines, start=1):
            line = line.strip()
            if not line:
                continue

            # 处理单行截断（最多512字符）
            if len(line) > MAX_CONTENT_LENGTH:
                line = line[:MAX_CONTENT_LENGTH]
                warnings.append(get_text_truncated_warning(i))

            # 解析日期时间
            due_date, time_str, content, is_passed = parser.parse_date_time(line)

            # 如果时间已过，跳过
            if is_passed:
                skipped_count += 1
                logger.info(f"Skipped task (time passed): {content}")
                continue

            # 组合提醒时间
            reminder_at = f"{due_date} {time_str}" if time_str else None

            # 创建任务
            task = self.db.create_task(user.id, content, due_date, reminder_at)

            if task:
                created_tasks.append((content, due_date, reminder_at))

                # 如果有提醒时间，创建提醒 Job
                if reminder_at and 'scheduler' in context.bot_data:
                    context.bot_data['scheduler'].schedule_reminder_job(task, user.tz)
            else:
                logger.error(f"Failed to create task for user {chat_id}: {content}")

        perf.checkpoint(f"DB创建{len(created_tasks)}个任务")

        # 退出输入模式
        self.db.set_user_awaiting_plans(user.id, False)
        perf.checkpoint("DB更新用户状态")

        # 发送回执
        if created_tasks:
            receipt = format_task_creation_receipt(
                created_tasks,
                timezone=user.tz,
                skipped_count=skipped_count
            )

            if truncated:
                receipt += f"\n{get_input_truncated_message(MAX_INPUT_LINES)}"

            if warnings:
                receipt += "\n" + "\n".join(warnings)

            await update.message.reply_text(receipt)
            perf.checkpoint("Telegram发送回执")
            logger.info(f"User {chat_id} created {len(created_tasks)} tasks, skipped {skipped_count}")
        elif skipped_count > 0:
            await update.message.reply_text(f"⚠️ 全部 {skipped_count} 条任务因时间已过未创建")
            perf.checkpoint("Telegram发送跳过消息")
        else:
            await update.message.reply_text("未能创建任何任务，请检查输入格式。")
            perf.checkpoint("Telegram发送错误消息")

        perf.finish()

    async def _handle_reminder_time_input(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        user: User
    ):
        """
        处理修改时间的输入

        Args:
            update: Telegram Update
            context: 上下文
            user: 用户对象
        """
        chat_id = update.effective_chat.id
        text = update.message.text.strip()
        task_id = user.awaiting_reminder_task_id
        original_message_id = user.awaiting_reminder_message_id

        # 获取任务
        task = self.db.get_task_by_id(task_id)
        if not task:
            await update.message.reply_text("任务不存在。")
            self.db.clear_user_reminder_waiting(user.id)
            return

        # 解析新时间
        parser = DateParser(user.tz)
        due_date, time_str, _, is_passed = parser.parse_date_time(text)

        # 如果没有解析到时间，提示错误
        if not time_str:
            await update.message.reply_text("无法解析时间，请重新输入。\n支持格式：今晚8点 / 今天20:00 / 周五20:00 / 20:00")
            return

        # 如果时间已过，提示重输
        if is_passed:
            await update.message.reply_text(get_time_passed_edit_message())
            return

        # 组合新的提醒时间
        new_reminder_at = f"{due_date} {time_str}"

        # 更新任务提醒
        success = self.db.update_task_reminder(task_id, new_reminder_at, due_date)
        if not success:
            await update.message.reply_text("更新失败，请稍后重试。")
            return

        # 更新提醒 Job
        if 'scheduler' in context.bot_data:
            scheduler = context.bot_data['scheduler']
            # 移除旧 Job
            scheduler.remove_reminder_job(task_id)
            # 重新获取任务对象
            task = self.db.get_task_by_id(task_id)
            # 创建新 Job
            scheduler.schedule_reminder_job(task, user.tz)

        # 清除等待状态
        self.db.clear_user_reminder_waiting(user.id)

        # 回复用户输入消息，确认修改成功
        confirm_msg = get_reminder_time_changed_message(task.content, new_reminder_at, user.tz)
        try:
            await update.message.reply_text(confirm_msg, quote=True)
        except Exception as e:
            logger.warning(f"Failed to send confirmation reply: {e}")
            # 兜底：如果回复失败，尝试直接发送消息
            try:
                await context.bot.send_message(chat_id=chat_id, text=confirm_msg)
            except Exception as e2:
                logger.warning(f"Failed to send confirmation message: {e2}")

        # 编辑原消息（显示更新后的提醒消息）
        message = get_reminder_message(task.content, new_reminder_at, user.tz)
        buttons = create_reminder_buttons(task_id)

        if original_message_id:
            # 编辑原消息
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=original_message_id,
                    text=message,
                    reply_markup=buttons
                )
            except Exception as e:
                # 如果编辑失败，发送新消息
                logger.warning(f"Failed to edit original message: {e}")
                await update.message.reply_text(message, reply_markup=buttons)
        else:
            # 没有保存 message_id，发送新消息
            await update.message.reply_text(message, reply_markup=buttons)

        logger.info(f"User {chat_id} updated reminder time: task_id={task_id}, new_reminder_at={new_reminder_at}")
