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
    """创建顺延按钮（三键：+1天、+2天、返回）"""
    keyboard = [
        [
            InlineKeyboardButton("顺延 +1 天", callback_data=f"t:{task_id}:p:1"),
            InlineKeyboardButton("顺延 +2 天", callback_data=f"t:{task_id}:p:2"),
            InlineKeyboardButton("↩️ 返回", callback_data=f"t:{task_id}:back"),
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


def create_overdue_snooze_buttons() -> InlineKeyboardMarkup:
    """创建逾期任务暂停按钮"""
    keyboard = [
        [
            InlineKeyboardButton("今日不再提醒", callback_data="ovr:snooze"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


# ==================== 提醒相关按钮 ====================

def create_reminder_buttons(task_id: int) -> InlineKeyboardMarkup:
    """创建提醒消息按钮（三键：完成、取消、修改时间）"""
    keyboard = [
        [
            InlineKeyboardButton("✅ 完成", callback_data=f"t:{task_id}:done"),
            InlineKeyboardButton("🗑 取消", callback_data=f"t:{task_id}:cancel"),
            InlineKeyboardButton("🕒 修改时间", callback_data=f"t:{task_id}:edit_time"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def create_cancel_edit_button(task_id: int) -> InlineKeyboardMarkup:
    """创建取消修改按钮"""
    keyboard = [
        [
            InlineKeyboardButton("❌ 取消修改", callback_data=f"t:{task_id}:cancel_edit"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)
