"""
Bot 消息文案模板
严格按照开发清单第二章的交互稿
"""

from typing import List
from src.db.models import Task


def get_start_message(tz: str, evening_time: str, morning_time: str) -> str:
    """
    获取 /start 命令的欢迎消息

    Args:
        tz: 时区
        evening_time: 晚间时间（HH:MM）
        morning_time: 早间时间（HH:MM 或 "关闭"）

    Returns:
        欢迎消息文本
    """
    return f"""✅ 已就绪！
当前时区：{tz}
晚间例行时间：{evening_time}
早间清单时间：{morning_time}

常用指令：
/add 录入计划（多行=多任务）
/today 查看今日清单
/week 查看未来 7 天
/setevening HH:MM 设置晚间时间
/setmorning HH:MM 设置早间时间（08:30 为默认，可关闭）
/timezone <IANA 名称> 设置时区（如 Asia/Shanghai）"""


def get_daily_review_header(is_makeup: bool = False) -> str:
    """
    获取日终核对的标题

    Args:
        is_makeup: 是否是补发（含昨日未清）

    Returns:
        标题文本
    """
    if is_makeup:
        return "🧾 日终核对（含昨日未清）："
    return "🧾 日终核对（今天应完成）："


def format_task_item(task: Task) -> str:
    """
    格式化单个任务条目

    Args:
        task: 任务对象

    Returns:
        格式化后的文本，如 "• #12 备份 NAS 配置"
    """
    return f"• #{task.id} {task.content}"


def get_new_plan_prompt() -> str:
    """获取新计划征集提示"""
    return "要不要录入「明天 + 一周内」的新计划？"


def get_input_mode_instructions() -> str:
    """获取一次性输入模式的说明"""
    return """请发送多行文本，每行=1 个任务。
行内可写日期：今天/明天/后天/周三/下周一/11-15/2025-11-15/+2d/+1w。
未写日期默认归档到「明天」。"""


def format_task_creation_receipt(tasks: List[tuple]) -> str:
    """
    格式化任务创建回执

    Args:
        tasks: [(任务内容, 到期日期), ...]

    Returns:
        回执文本
    """
    lines = [f"已创建 {len(tasks)} 项："]

    for content, due_date in tasks:
        # 提取任务描述（不含日期标记）
        display_content = content
        lines.append(f"• {display_content}  →  {due_date}")

    return "\n".join(lines)


def get_morning_checklist_header() -> str:
    """获取早间清单的标题"""
    return "🌅 今日待办："


def get_no_tasks_message() -> str:
    """获取无任务时的提示"""
    return "今天没有待办 ✅"


def get_today_header() -> str:
    """获取 /today 命令的标题"""
    return "📋 今日待办："


def get_week_header() -> str:
    """获取 /week 命令的标题"""
    return "📅 未来 7 天："


def format_week_tasks(tasks_by_date: dict) -> str:
    """
    格式化一周任务

    Args:
        tasks_by_date: {日期: [任务列表], ...}

    Returns:
        格式化后的文本
    """
    if not tasks_by_date:
        return "未来 7 天没有待办事项 ✅"

    lines = [get_week_header()]

    for date_str, tasks in sorted(tasks_by_date.items()):
        lines.append(f"\n【{date_str}】")
        for task in tasks:
            lines.append(format_task_item(task))

    return "\n".join(lines)


def get_task_done_message() -> str:
    """任务完成的确认消息"""
    return "已标记完成。"


def get_task_canceled_message() -> str:
    """任务取消的确认消息"""
    return "已取消任务。"


def get_task_already_processed_message() -> str:
    """任务已处理的提示"""
    return "该任务已处理。"


def get_postpone_prompt() -> str:
    """顺延选择提示"""
    return "请选择顺延天数："


def get_postpone_confirmation(new_due_date: str) -> str:
    """
    顺延确认消息

    Args:
        new_due_date: 新的到期日期

    Returns:
        确认消息
    """
    return f"已顺延 1 天（新到期日：{new_due_date}）。"


def get_postpone_confirmation_days(days: int, new_due_date: str) -> str:
    """
    顺延确认消息（多天）

    Args:
        days: 顺延天数
        new_due_date: 新的到期日期

    Returns:
        确认消息
    """
    return f"已顺延 {days} 天（新到期日：{new_due_date}）。"


def get_timezone_updated_message(tz: str) -> str:
    """时区更新确认"""
    return f"时区已更新为：{tz}"


def get_evening_time_updated_message(time_str: str) -> str:
    """晚间时间更新确认"""
    return f"晚间例行时间已更新为：{time_str}"


def get_morning_time_updated_message(time_str: str) -> str:
    """早间时间更新确认"""
    return f"早间清单时间已更新为：{time_str}"


def get_morning_time_disabled_message() -> str:
    """早间清单关闭确认"""
    return "早间清单已关闭。"


def get_invalid_timezone_message() -> str:
    """无效时区提示"""
    return "无效时区名，请使用 IANA 名称，如 Asia/Shanghai"


def get_invalid_time_format_message() -> str:
    """无效时间格式提示"""
    return "无效时间格式，请使用 HH:MM 格式，如 22:00"


def get_input_truncated_message(limit: int) -> str:
    """输入截断提示"""
    return f"（已截断到 {limit} 条）"


def get_text_truncated_warning(line_num: int) -> str:
    """文本截断警告"""
    return f"第 {line_num} 行内容过长，已截断到 512 字符。"
