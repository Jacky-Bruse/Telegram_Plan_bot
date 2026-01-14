"""
Bot 回调查询处理器
处理按钮点击事件
严格按照文档第 7 章的按钮协议

性能优化：
- 使用批量数据库操作减少事务次数
- 利用唯一约束去重，省去预查询
- 使用 run_in_executor 包装同步 DB 调用，避免阻塞事件循环
- back 操作使用 edit_message_reply_markup 减少网络传输
"""

import asyncio
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Optional, Callable, Any
import pytz

from telegram import Update
from telegram.ext import ContextTypes

from src.db.database import Database
from src.core.state_machine import TaskStateMachine
from src.bot.messages import (
    get_task_done_message,
    get_task_canceled_message,
    get_task_already_processed_message,
    get_postpone_prompt,
    get_postpone_confirmation_days,
    get_input_mode_instructions,
    get_confirm_complete_prompt,
    get_confirm_cancel_prompt,
    get_edit_time_prompt,
    get_reminder_message,
)
from src.bot.keyboards import (
    create_postpone_buttons,
    create_task_buttons,
    create_confirm_complete_buttons,
    create_confirm_cancel_buttons,
    create_cancel_edit_button,
    create_reminder_buttons,
)
from src.constants import (
    ACTION_DONE, ACTION_UNDONE, ACTION_CANCEL, ACTION_POSTPONE,
    ACTION_EDIT_TIME, ACTION_CANCEL_EDIT,
    STATUS_DONE, STATUS_CANCELED,
    REMINDER_STATUS_CANCELED,
)
from src.utils.logger import get_logger
from src.utils.performance import PerformanceLogger

logger = get_logger(__name__)

# 线程池用于执行同步数据库操作
_db_executor: Optional[ThreadPoolExecutor] = None


def get_db_executor() -> ThreadPoolExecutor:
    """获取数据库线程池（懒加载单例）"""
    global _db_executor
    if _db_executor is None:
        # 使用较小的线程池，避免数据库连接过多
        _db_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="db_")
    return _db_executor


async def run_in_executor(func: Callable, *args, **kwargs) -> Any:
    """
    在线程池中执行同步函数，避免阻塞事件循环

    Args:
        func: 同步函数
        *args: 位置参数
        **kwargs: 关键字参数

    Returns:
        函数返回值
    """
    loop = asyncio.get_event_loop()
    if kwargs:
        func = partial(func, **kwargs)
    return await loop.run_in_executor(get_db_executor(), func, *args)


class CallbackHandlers:
    """回调查询处理器"""

    def __init__(self, db: Database):
        """
        初始化处理器

        Args:
            db: 数据库实例
        """
        self.db = db
        self.state_machine = TaskStateMachine(db)

    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        处理回调查询（按钮点击）
        严格按照文档第 2.2、2.3、7 章节实现

        回调数据格式：
        - 任务操作：t:<task_id>:<action>
        - 任务顺延：t:<task_id>:p:<days>
        - 新计划征集：new:<action>

        性能优化：
        - 不再预查询 is_callback_processed，改为写入时捕获唯一约束冲突
        - 数据库操作使用 run_in_executor 避免阻塞
        """
        query = update.callback_query
        chat_id = update.effective_chat.id
        perf = PerformanceLogger("handle_callback_query", chat_id)

        await query.answer()  # 确认收到回调
        perf.checkpoint("Telegram确认回调")

        callback_id = query.id
        callback_data = query.data

        logger.info(f"Callback received: chat_id={chat_id}, data={callback_data}")

        # 解析回调数据（不再预查询去重，由后续操作的唯一约束处理）
        parts = callback_data.split(':')

        if parts[0] == 't':
            # 任务操作
            await self._handle_task_callback(query, parts, callback_id, context, perf)
        elif parts[0] == 'new':
            # 新计划征集
            await self._handle_new_plan_callback(query, parts, callback_id, context, perf)
        elif parts[0] == 'ovr':
            # 逾期提醒暂停
            await self._handle_overdue_callback(query, parts, callback_id, perf)
        else:
            logger.warning(f"Unknown callback data: {callback_data}")

        perf.finish()

    async def _handle_task_callback(self, query, parts: list, callback_id: str, context: ContextTypes.DEFAULT_TYPE, perf: PerformanceLogger):
        """
        处理任务相关的回调（性能优化版）

        优化点：
        - 使用 run_in_executor 包装同步 DB 调用
        - 利用唯一约束去重，减少查询
        - back 操作使用 edit_message_reply_markup

        Args:
            query: 回调查询对象
            parts: 回调数据分割后的列表
            callback_id: 回调 ID
            context: 上下文
            perf: 性能日志记录器
        """
        try:
            task_id = int(parts[1])
            action = parts[2]

            # 获取任务（异步执行，不阻塞事件循环）
            task = await run_in_executor(self.db.get_task_by_id, task_id)
            perf.checkpoint("DB查询任务(async)")

            if not task:
                await query.edit_message_text("任务不存在。")
                perf.checkpoint("Telegram响应(任务不存在)")
                return

            if task.status in (STATUS_DONE, STATUS_CANCELED):
                await query.edit_message_reply_markup(reply_markup=None)
                perf.checkpoint("Telegram移除按钮(已处理)")
                return

            # 根据动作执行操作
            if action == ACTION_DONE:
                await self._handle_done_action(query, task, task_id, parts, callback_id, perf, context)

            elif action == ACTION_UNDONE:
                await self._handle_undone_action(query, task_id, callback_id, perf)

            elif action == ACTION_CANCEL:
                await self._handle_cancel_action(query, task, task_id, parts, callback_id, perf, context)

            elif action == 'back':
                await self._handle_back_action(query, task_id, perf)

            elif action == 'p':
                await self._handle_postpone_action(query, task, task_id, parts, callback_id, perf)

            elif action == ACTION_EDIT_TIME:
                await self._handle_edit_time_action(query, task, task_id, callback_id, context, perf)

            elif action == ACTION_CANCEL_EDIT:
                await self._handle_cancel_edit_action(query, task, task_id, callback_id, perf)

            else:
                logger.warning(f"Unknown task action: {action}")

        except (ValueError, IndexError) as e:
            logger.error(f"Invalid callback data format: {parts}, error: {e}")
            await query.edit_message_text("无效的操作。")
            perf.checkpoint("Telegram响应(无效操作)")

    async def _handle_done_action(self, query, task, task_id: int, parts: list, callback_id: str, perf: PerformanceLogger, context=None):
        """处理完成任务操作"""
        # 判断是否有第四个参数（确认标志）
        if len(parts) > 3 and parts[3] == 'cf':
            # 确认完成 - 使用批量操作（包含去重）
            result = await run_in_executor(
                self.db.complete_task_with_callback,
                task_id=task_id,
                status=STATUS_DONE,
                callback_id=callback_id,
                action=ACTION_DONE
            )
            perf.checkpoint("DB批量操作(完成+回调,async)")

            if result == "ok":
                # 清理提醒 Job 并更新提醒状态
                if task.reminder_at and context and 'scheduler' in context.bot_data:
                    context.bot_data['scheduler'].remove_reminder_job(task_id)
                    await run_in_executor(
                        self.db.update_reminder_status,
                        task_id, REMINDER_STATUS_CANCELED
                    )
                    perf.checkpoint("清理提醒Job(async)")

                await query.edit_message_text(get_task_done_message(task.content))
                perf.checkpoint("Telegram响应")
            elif result == "duplicate":
                await query.edit_message_text(get_task_already_processed_message())
                perf.checkpoint("Telegram响应(重复点击)")
            else:
                await query.edit_message_text(get_task_already_processed_message())
                perf.checkpoint("Telegram响应(失败)")
        else:
            # 第一次点击完成 - 显示确认界面
            buttons = create_confirm_complete_buttons(task_id)
            await query.edit_message_text(
                get_confirm_complete_prompt(task.content),
                reply_markup=buttons
            )
            perf.checkpoint("Telegram显示确认界面")

    async def _handle_undone_action(self, query, task_id: int, callback_id: str, perf: PerformanceLogger):
        """处理未完成操作 - 显示顺延按钮"""
        # 记录回调（异步）
        result = await run_in_executor(
            self.db.mark_callback_processed,
            callback_id, task_id, ACTION_UNDONE
        )
        perf.checkpoint("DB记录回调(async)")

        if result == "duplicate":
            await query.edit_message_text(get_task_already_processed_message())
            perf.checkpoint("Telegram响应(重复点击)")
            return

        if result == "error":
            logger.warning(f"DB error when marking undone callback: task_id={task_id}")
            await query.edit_message_text("操作失败，请稍后重试。")
            perf.checkpoint("Telegram响应(DB错误)")
            return

        # 替换为顺延按钮（严格按照文档 2.2）
        buttons = create_postpone_buttons(task_id)
        await query.edit_message_text(
            get_postpone_prompt(),
            reply_markup=buttons
        )
        perf.checkpoint("Telegram显示顺延按钮")

    async def _handle_cancel_action(self, query, task, task_id: int, parts: list, callback_id: str, perf: PerformanceLogger, context=None):
        """处理取消任务操作"""
        # 判断是否有第四个参数（确认标志）
        if len(parts) > 3 and parts[3] == 'cf':
            # 确认取消 - 使用批量操作（包含去重）
            result = await run_in_executor(
                self.db.complete_task_with_callback,
                task_id=task_id,
                status=STATUS_CANCELED,
                callback_id=callback_id,
                action=ACTION_CANCEL
            )
            perf.checkpoint("DB批量操作(取消+回调,async)")

            if result == "ok":
                # 清理提醒 Job 并更新提醒状态
                if task.reminder_at and context and 'scheduler' in context.bot_data:
                    context.bot_data['scheduler'].remove_reminder_job(task_id)
                    await run_in_executor(
                        self.db.update_reminder_status,
                        task_id, REMINDER_STATUS_CANCELED
                    )
                    perf.checkpoint("清理提醒Job(async)")

                await query.edit_message_text(get_task_canceled_message(task.content))
                perf.checkpoint("Telegram响应")
            elif result == "duplicate":
                await query.edit_message_text(get_task_already_processed_message())
                perf.checkpoint("Telegram响应(重复点击)")
            else:
                await query.edit_message_text(get_task_already_processed_message())
                perf.checkpoint("Telegram响应(失败)")
        else:
            # 第一次点击取消 - 显示确认界面
            buttons = create_confirm_cancel_buttons(task_id)
            await query.edit_message_text(
                get_confirm_cancel_prompt(task.content),
                reply_markup=buttons
            )
            perf.checkpoint("Telegram显示确认界面")

    async def _handle_back_action(self, query, task_id: int, perf: PerformanceLogger):
        """
        处理返回操作 - 仅切换按钮

        优化：使用 edit_message_reply_markup 而非 edit_message_text
        因为只需要切换按钮，消息内容不变
        """
        buttons = create_task_buttons(task_id)
        await query.edit_message_reply_markup(reply_markup=buttons)
        perf.checkpoint("Telegram切换按钮(reply_markup)")

    async def _handle_postpone_action(self, query, task, task_id: int, parts: list, callback_id: str, perf: PerformanceLogger):
        """处理顺延任务操作"""
        days = int(parts[3])

        # 获取用户（异步，用于时区计算）
        user = await run_in_executor(self.db.get_user_by_id, task.user_id)
        perf.checkpoint("DB查询用户(async)")

        # 计算新日期（纯计算，无 DB 操作）
        new_due_date = self.state_machine.calculate_postpone_date(days, user)

        # 单事务完成：更新日期/状态 + 记录回调（包含去重）
        result = await run_in_executor(
            self.db.postpone_task_with_callback,
            task_id=task_id,
            new_due_date=new_due_date,
            callback_id=callback_id,
            action=f"{ACTION_POSTPONE}:{days}"
        )
        perf.checkpoint("DB批量操作(顺延+回调,async)")

        if result == "ok":
            await query.edit_message_text(
                get_postpone_confirmation_days(days, new_due_date)
            )
            perf.checkpoint("Telegram响应")
        elif result == "duplicate":
            await query.edit_message_text(get_task_already_processed_message())
            perf.checkpoint("Telegram响应(重复点击)")
        else:
            await query.edit_message_text("顺延失败，请稍后重试。")
            perf.checkpoint("Telegram响应(失败)")

    async def _handle_overdue_callback(self, query, parts: list, callback_id: str, perf: PerformanceLogger):
        """处理逾期提醒暂停回调"""
        action = parts[1] if len(parts) > 1 else None
        if action != 'snooze':
            logger.warning(f"Unknown overdue action: {action}")
            return

        if not query.message:
            return

        chat_id = query.message.chat_id
        user = await run_in_executor(self.db.get_user_by_chat_id, chat_id)
        perf.checkpoint("DB查询用户(async)")

        if not user:
            await query.edit_message_reply_markup(reply_markup=None)
            return

        tz = pytz.timezone(user.tz)
        today = datetime.now(tz).strftime('%Y-%m-%d')

        result = await run_in_executor(
            self.db.mark_callback_processed,
            callback_id, 0, 'overdue_snooze'
        )
        perf.checkpoint("DB记录回调(async)")

        if result == 'error':
            logger.warning(f"DB error when marking overdue_snooze callback: chat_id={chat_id}")
            return

        await run_in_executor(
            self.db.set_user_overdue_snooze_date,
            user.id, today
        )
        perf.checkpoint("DB设置snooze(async)")

        await query.edit_message_reply_markup(reply_markup=None)
        perf.checkpoint("Telegram移除按钮")

    async def _handle_new_plan_callback(
        self,
        query,
        parts: list,
        callback_id: str,
        context: ContextTypes.DEFAULT_TYPE,
        perf: PerformanceLogger
    ):
        """
        处理新计划征集的回调

        Args:
            query: 回调查询对象
            parts: 回调数据分割后的列表
            callback_id: 回调 ID
            context: 上下文对象
            perf: 性能日志记录器
        """
        chat_id = query.message.chat_id
        user = await run_in_executor(self.db.get_user_by_chat_id, chat_id)
        perf.checkpoint("DB查询用户(async)")

        if not user:
            await query.edit_message_text("用户不存在，请使用 /start 初始化。")
            perf.checkpoint("Telegram响应(用户不存在)")
            return

        action = parts[1]

        if action == 'add':
            # 现在录入 - 进入一次性输入模式（异步执行）
            result = await run_in_executor(
                self.db.mark_callback_processed,
                callback_id, 0, 'new_add'
            )

            if result == "duplicate":
                await query.edit_message_text(get_task_already_processed_message())
                perf.checkpoint("Telegram响应(重复点击)")
                return

            if result == "error":
                logger.warning(f"DB error when marking new_add callback: chat_id={chat_id}")
                await query.edit_message_text("操作失败，请稍后重试。")
                perf.checkpoint("Telegram响应(DB错误)")
                return

            await run_in_executor(
                self.db.set_user_awaiting_plans,
                user.id, True
            )
            perf.checkpoint("DB记录回调+设置状态(async)")

            await query.edit_message_text(get_input_mode_instructions())
            perf.checkpoint("Telegram响应")
            logger.info(f"User {chat_id} entered input mode via new plan prompt")

        elif action == 'skip':
            # 稍后再说 - 设置当晚已跳过标记（异步执行）
            result = await run_in_executor(
                self.db.mark_callback_processed,
                callback_id, 0, 'new_skip'
            )

            if result == "duplicate":
                await query.edit_message_text(get_task_already_processed_message())
                perf.checkpoint("Telegram响应(重复点击)")
                return

            if result == "error":
                logger.warning(f"DB error when marking new_skip callback: chat_id={chat_id}")
                await query.edit_message_text("操作失败，请稍后重试。")
                perf.checkpoint("Telegram响应(DB错误)")
                return

            await run_in_executor(
                self.db.set_user_skipped_tonight,
                user.id, True
            )
            perf.checkpoint("DB记录回调+设置状态(async)")

            await query.edit_message_text("已跳过，当晚不再询问。")
            perf.checkpoint("Telegram响应")
            logger.info(f"User {chat_id} skipped new plan prompt")

        else:
            logger.warning(f"Unknown new plan action: {action}")

    # ==================== 提醒时间修改回调 ====================

    async def _handle_edit_time_action(
        self,
        query,
        task,
        task_id: int,
        callback_id: str,
        context: ContextTypes.DEFAULT_TYPE,
        perf: PerformanceLogger
    ):
        """
        处理修改时间操作

        Args:
            query: 回调查询对象
            task: 任务对象
            task_id: 任务 ID
            callback_id: 回调 ID
            context: 上下文
            perf: 性能日志记录器
        """
        chat_id = query.message.chat_id

        # 获取用户
        user = await run_in_executor(self.db.get_user_by_chat_id, chat_id)
        perf.checkpoint("DB查询用户(async)")

        if not user:
            await query.edit_message_text("用户不存在。")
            return

        # 记录回调
        result = await run_in_executor(
            self.db.mark_callback_processed,
            callback_id, task_id, ACTION_EDIT_TIME
        )
        perf.checkpoint("DB记录回调(async)")

        if result == "duplicate":
            await query.edit_message_text(get_task_already_processed_message())
            perf.checkpoint("Telegram响应(重复点击)")
            return

        # 设置等待输入状态（保存原消息 ID 用于后续编辑）
        message_id = query.message.message_id
        await run_in_executor(
            self.db.set_user_awaiting_reminder_time,
            user.id, True, task_id, message_id
        )
        perf.checkpoint("DB设置等待状态(async)")

        # 显示输入提示
        buttons = create_cancel_edit_button(task_id)
        await query.edit_message_text(
            get_edit_time_prompt(),
            reply_markup=buttons
        )
        perf.checkpoint("Telegram显示输入提示")

        logger.info(f"User {chat_id} started editing reminder time for task_id={task_id}")

    async def _handle_cancel_edit_action(
        self,
        query,
        task,
        task_id: int,
        callback_id: str,
        perf: PerformanceLogger
    ):
        """
        处理取消修改操作

        Args:
            query: 回调查询对象
            task: 任务对象
            task_id: 任务 ID
            callback_id: 回调 ID
            perf: 性能日志记录器
        """
        chat_id = query.message.chat_id

        # 获取用户
        user = await run_in_executor(self.db.get_user_by_chat_id, chat_id)
        perf.checkpoint("DB查询用户(async)")

        if not user:
            await query.edit_message_text("用户不存在。")
            return

        # 清除等待状态
        await run_in_executor(
            self.db.clear_user_reminder_waiting,
            user.id
        )
        perf.checkpoint("DB清除等待状态(async)")

        # 恢复提醒消息（显示三键）
        message = get_reminder_message(task.content, task.reminder_at, user.tz)
        buttons = create_reminder_buttons(task_id)
        await query.edit_message_text(message, reply_markup=buttons)
        perf.checkpoint("Telegram恢复提醒消息")

        logger.info(f"User {chat_id} canceled editing reminder time for task_id={task_id}")
