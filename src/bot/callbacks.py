"""
Bot 回调查询处理器
处理按钮点击事件
严格按照文档第 7 章的按钮协议
"""

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
)
from src.bot.keyboards import create_postpone_buttons
from src.constants import ACTION_DONE, ACTION_UNDONE, ACTION_CANCEL, ACTION_POSTPONE
from src.utils.logger import get_logger

logger = get_logger(__name__)


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
        """
        query = update.callback_query
        await query.answer()  # 确认收到回调

        callback_id = query.id
        callback_data = query.data
        chat_id = update.effective_chat.id

        logger.info(f"Callback received: chat_id={chat_id}, data={callback_data}")

        # 检查是否已处理（防重复点击）
        if self.db.is_callback_processed(callback_id):
            await query.edit_message_text(get_task_already_processed_message())
            return

        # 解析回调数据
        parts = callback_data.split(':')

        if parts[0] == 't':
            # 任务操作
            await self._handle_task_callback(query, parts, callback_id)
        elif parts[0] == 'new':
            # 新计划征集
            await self._handle_new_plan_callback(query, parts, callback_id, context)
        else:
            logger.warning(f"Unknown callback data: {callback_data}")

    async def _handle_task_callback(self, query, parts: list, callback_id: str):
        """
        处理任务相关的回调

        Args:
            query: 回调查询对象
            parts: 回调数据分割后的列表
            callback_id: 回调 ID
        """
        try:
            task_id = int(parts[1])
            action = parts[2]

            # 获取任务
            task = self.db.get_task_by_id(task_id)

            if not task:
                await query.edit_message_text("任务不存在。")
                return

            # 根据动作执行操作
            if action == ACTION_DONE:
                # 完成任务
                success = self.state_machine.mark_as_done(task_id)

                if success:
                    # 记录回调
                    self.db.mark_callback_processed(callback_id, task_id, ACTION_DONE)
                    await query.edit_message_text(get_task_done_message())
                else:
                    await query.edit_message_text(get_task_already_processed_message())

            elif action == ACTION_UNDONE:
                # 未完成 - 弹出顺延按钮
                self.db.mark_callback_processed(callback_id, task_id, ACTION_UNDONE)

                # 替换为顺延按钮（严格按照文档 2.2）
                buttons = create_postpone_buttons(task_id)
                await query.edit_message_text(
                    get_postpone_prompt(),
                    reply_markup=buttons
                )

            elif action == ACTION_CANCEL:
                # 取消任务
                success = self.state_machine.mark_as_canceled(task_id)

                if success:
                    self.db.mark_callback_processed(callback_id, task_id, ACTION_CANCEL)
                    await query.edit_message_text(get_task_canceled_message())
                else:
                    await query.edit_message_text(get_task_already_processed_message())

            elif action == 'p':
                # 顺延任务
                days = int(parts[3])
                new_due_date = self.state_machine.postpone_task(task_id, days)

                if new_due_date:
                    self.db.mark_callback_processed(callback_id, task_id, f"{ACTION_POSTPONE}:{days}")
                    await query.edit_message_text(
                        get_postpone_confirmation_days(days, new_due_date)
                    )
                else:
                    await query.edit_message_text("顺延失败，请稍后重试。")

            else:
                logger.warning(f"Unknown task action: {action}")

        except (ValueError, IndexError) as e:
            logger.error(f"Invalid callback data format: {parts}, error: {e}")
            await query.edit_message_text("无效的操作。")

    async def _handle_new_plan_callback(
        self,
        query,
        parts: list,
        callback_id: str,
        context: ContextTypes.DEFAULT_TYPE
    ):
        """
        处理新计划征集的回调

        Args:
            query: 回调查询对象
            parts: 回调数据分割后的列表
            callback_id: 回调 ID
            context: 上下文对象
        """
        chat_id = query.message.chat_id
        user = self.db.get_user_by_chat_id(chat_id)

        if not user:
            await query.edit_message_text("用户不存在，请使用 /start 初始化。")
            return

        action = parts[1]

        if action == 'add':
            # 现在录入 - 进入一次性输入模式
            self.db.mark_callback_processed(callback_id, 0, 'new_add')
            self.db.set_user_awaiting_plans(user.id, True)

            await query.edit_message_text(get_input_mode_instructions())
            logger.info(f"User {chat_id} entered input mode via new plan prompt")

        elif action == 'skip':
            # 稍后再说 - 设置当晚已跳过标记
            self.db.mark_callback_processed(callback_id, 0, 'new_skip')
            self.db.set_user_skipped_tonight(user.id, True)

            await query.edit_message_text("已跳过，当晚不再询问。")
            logger.info(f"User {chat_id} skipped new plan prompt")

        else:
            logger.warning(f"Unknown new plan action: {action}")
