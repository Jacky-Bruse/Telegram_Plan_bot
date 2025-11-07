"""键盘构建工具"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def create_task_buttons(task_id: int) -> InlineKeyboardMarkup:
    """创建任务操作按钮（三键）"""
    keyboard = [
        [
            InlineKeyboardButton("✅ 完成", callback_data=f"t:{task_id}:done"),
            InlineKeyboardButton("⏳ 未完成", callback_data=f"t:{task_id}:un"),
            InlineKeyboardButton("🗑 取消", callback_data=f"t:{task_id}:cancel"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def create_postpone_buttons(task_id: int) -> InlineKeyboardMarkup:
    """创建顺延按钮（两键）"""
    keyboard = [
        [
            InlineKeyboardButton("顺延 +1 天", callback_data=f"t:{task_id}:p:1"),
            InlineKeyboardButton("顺延 +2 天", callback_data=f"t:{task_id}:p:2"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def create_confirm_complete_buttons(task_id: int) -> InlineKeyboardMarkup:
    """创建完成确认按钮"""
    keyboard = [
        [
            InlineKeyboardButton("✔️ 确认完成", callback_data=f"t:{task_id}:done:cf"),
            InlineKeyboardButton("↩️ 返回", callback_data=f"t:{task_id}:back"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def create_confirm_cancel_buttons(task_id: int) -> InlineKeyboardMarkup:
    """创建取消确认按钮"""
    keyboard = [
        [
            InlineKeyboardButton("✔️ 确认取消", callback_data=f"t:{task_id}:cancel:cf"),
            InlineKeyboardButton("↩️ 返回", callback_data=f"t:{task_id}:back"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def create_new_plan_buttons() -> InlineKeyboardMarkup:
    """创建新计划征集按钮"""
    keyboard = [
        [
            InlineKeyboardButton("现在录入", callback_data="new:add"),
            InlineKeyboardButton("稍后再说", callback_data="new:skip"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)
