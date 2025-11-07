"""
Bot 命令处理器
严格按照开发清单第二章的交互稿实现
"""

import re
from datetime import datetime, timedelta
from typing import Optional, List
import pytz

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
    format_task_item,
    get_no_tasks_message,
    format_week_tasks,
    get_timezone_updated_message,
    get_evening_time_updated_message,
    get_morning_time_updated_message,
    get_morning_time_disabled_message,
    get_invalid_timezone_message,
    get_invalid_time_format_message,
    get_input_truncated_message,
    get_text_truncated_warning,
)
from src.constants import (
    STATUS_PENDING, STATUS_MISSED,
    MAX_INPUT_LINES, MAX_CONTENT_LENGTH,
    DEFAULT_TIMEZONE, DEFAULT_EVENING_HOUR, DEFAULT_EVENING_MINUTE,
    DEFAULT_MORNING_HOUR, DEFAULT_MORNING_MINUTE,
)
from src.utils.logger import get_logger

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
        logger.info(f"User {chat_id} triggered /start")

        # 检查用户是否已存在
        user = self.db.get_user_by_chat_id(chat_id)

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
        await update.message.reply_text(message)

        # 通知调度器重建 Job（通过 context.bot_data）
        if 'schedule_rebuild_callback' in context.bot_data:
            context.bot_data['schedule_rebuild_callback'](user)

    async def cmd_add(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /add 命令处理器
        进入一次性输入模式
        严格按照文档 2.3 和 2.5 章节
        """
        chat_id = update.effective_chat.id
        user = self.db.get_user_by_chat_id(chat_id)

        if user is None:
            await update.message.reply_text("请先使用 /start 初始化。")
            return

        # 设置用户状态为等待输入
        self.db.set_user_awaiting_plans(user.id, True)
        logger.info(f"User {chat_id} entered input mode")

        # 发送输入说明
        await update.message.reply_text(get_input_mode_instructions())

    async def cmd_today(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /today 命令处理器
        输出当日 pending/missed 列表（不含 done/canceled）
        严格按照文档 2.5 章节
        """
        chat_id = update.effective_chat.id
        user = self.db.get_user_by_chat_id(chat_id)

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

        if not tasks:
            await update.message.reply_text(get_no_tasks_message())
            return

        # 格式化任务列表
        lines = [get_today_header()]
        for task in tasks:
            lines.append(format_task_item(task))

        await update.message.reply_text("\n".join(lines))

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

        # 查询7天内的任务（默认隐藏 done/canceled）
        tasks = self.db.get_tasks_by_user_and_date_range(
            user.id,
            start_date,
            end_date,
            statuses=[STATUS_PENDING, STATUS_MISSED]
        )

        if not tasks:
            await update.message.reply_text("未来 7 天没有待办事项 ✅")
            return

        # 按日期分组
        tasks_by_date = {}
        for task in tasks:
            if task.due_date not in tasks_by_date:
                tasks_by_date[task.due_date] = []
            tasks_by_date[task.due_date].append(task)

        # 格式化输出
        message = format_week_tasks(tasks_by_date)
        await update.message.reply_text(message)

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
        处理一次性输入模式的多行任务
        严格按照文档 2.3 章节和 8 章节（异常处理）
        """
        chat_id = update.effective_chat.id
        user = self.db.get_user_by_chat_id(chat_id)

        if user is None or not user.awaiting_plans:
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

        for i, line in enumerate(lines, start=1):
            line = line.strip()
            if not line:
                continue

            # 处理单行截断（最多512字符）
            if len(line) > MAX_CONTENT_LENGTH:
                line = line[:MAX_CONTENT_LENGTH]
                warnings.append(get_text_truncated_warning(i))

            # 解析日期
            due_date, content = parser.parse_date(line)

            # 创建任务
            task = self.db.create_task(user.id, content, due_date)

            if task:
                created_tasks.append((content, due_date))
            else:
                logger.error(f"Failed to create task for user {chat_id}: {content}")

        # 退出输入模式
        self.db.set_user_awaiting_plans(user.id, False)

        # 发送回执
        if created_tasks:
            receipt = format_task_creation_receipt(created_tasks)

            if truncated:
                receipt += f"\n{get_input_truncated_message(MAX_INPUT_LINES)}"

            if warnings:
                receipt += "\n" + "\n".join(warnings)

            await update.message.reply_text(receipt)
            logger.info(f"User {chat_id} created {len(created_tasks)} tasks")
        else:
            await update.message.reply_text("未能创建任何任务，请检查输入格式。")


def create_task_buttons(task_id: int) -> InlineKeyboardMarkup:
    """
    创建任务按钮（三键）
    严格按照文档 7 章节的按钮协议

    Args:
        task_id: 任务 ID

    Returns:
        按钮键盘
    """
    keyboard = [
        [
            InlineKeyboardButton("✅ 完成", callback_data=f"t:{task_id}:done"),
            InlineKeyboardButton("⏳ 未完成", callback_data=f"t:{task_id}:un"),
            InlineKeyboardButton("🗑 取消", callback_data=f"t:{task_id}:cancel"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def create_postpone_buttons(task_id: int) -> InlineKeyboardMarkup:
    """
    创建顺延按钮（两键）
    严格按照文档 7 章节的按钮协议

    Args:
        task_id: 任务 ID

    Returns:
        按钮键盘
    """
    keyboard = [
        [
            InlineKeyboardButton("顺延 +1 天", callback_data=f"t:{task_id}:p:1"),
            InlineKeyboardButton("顺延 +2 天", callback_data=f"t:{task_id}:p:2"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def create_new_plan_buttons() -> InlineKeyboardMarkup:
    """
    创建新计划征集按钮
    严格按照文档 7 章节的按钮协议

    Returns:
        按钮键盘
    """
    keyboard = [
        [
            InlineKeyboardButton("现在录入", callback_data="new:add"),
            InlineKeyboardButton("稍后再说", callback_data="new:skip"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)
