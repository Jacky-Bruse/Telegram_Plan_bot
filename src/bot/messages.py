"""
Bot 消息文案模板
严格按照开发清单第二章的交互稿
"""

import re
from datetime import datetime, timedelta
from typing import List, Optional
import pytz

from src.db.models import Task
from src.constants import (
    DATE_KEYWORD_TODAY,
    DATE_KEYWORD_TOMORROW,
    DATE_KEYWORD_DAY_AFTER_TOMORROW,
    WEEKDAY_KEYWORDS
)
from src.core.date_parser import DateParser


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


def get_relative_date_label(date_str: str, timezone: str = "Asia/Shanghai") -> str:
    """
    获取日期的相对时间标签

    Args:
        date_str: 日期字符串 YYYY-MM-DD
        timezone: 时区名称

    Returns:
        相对时间标签，如 " (今天)", " (明天)", " (后天)"，或空字符串
    """
    try:
        tz = pytz.timezone(timezone)
        today = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)

        # 解析目标日期
        target_date = datetime.strptime(date_str, '%Y-%m-%d')
        target_date = tz.localize(target_date)

        # 计算天数差
        days_diff = (target_date - today).days

        if days_diff == 0:
            return " (今天)"
        elif days_diff == 1:
            return " (明天)"
        elif days_diff == 2:
            return " (后天)"
        else:
            return ""
    except Exception:
        return ""


def _strip_date_keywords(content: str) -> str:
    """
    去掉任务内容开头的日期关键词

    Args:
        content: 任务内容

    Returns:
        去掉日期关键词后的内容
    """
    content = content.strip()

    # 构建所有需要去掉的日期关键词列表
    keywords_to_strip = []

    # 今天/明天/后天
    keywords_to_strip.extend(DATE_KEYWORD_TODAY)
    keywords_to_strip.extend(DATE_KEYWORD_TOMORROW)
    keywords_to_strip.extend(DATE_KEYWORD_DAY_AFTER_TOMORROW)

    # 周X、星期X、礼拜X、下周X、下星期X、下礼拜X
    for keyword in WEEKDAY_KEYWORDS.keys():
        keywords_to_strip.append(keyword)
        # 下周X、下星期X、下礼拜X
        keywords_to_strip.append(f"下{keyword}")
        if keyword.startswith("星期"):
            keywords_to_strip.append(f"下{keyword}")
        if keyword.startswith("礼拜"):
            keywords_to_strip.append(f"下{keyword}")

    # 尝试去掉开头的日期关键词
    for keyword in keywords_to_strip:
        if content.startswith(keyword):
            # 去掉关键词，并去掉后面可能的空格
            content = content[len(keyword):].strip()
            break

    # 去掉常见的日期格式（YYYY-MM-DD, MM-DD, MM/DD, MM.DD, X月X日/号, +Nd, +Nw）
    # 这些通常在开头
    content = re.sub(r'^\d{4}-\d{1,2}-\d{1,2}\s*', '', content)
    content = re.sub(r'^\d{1,2}-\d{1,2}\s*', '', content)
    content = re.sub(r'^\d{1,2}/\d{1,2}\s*', '', content)
    content = re.sub(r'^\d{1,2}\.\d{1,2}\s*', '', content)
    content = re.sub(r'^\d{1,2}月\d{1,2}(日|号)\s*', '', content)
    content = re.sub(r'^\+\d+[dDwW]\s*', '', content)

    return content.strip()


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


def format_task_item(task: Task, index: int = None, timezone: str = "Asia/Shanghai") -> str:
    """
    格式化单个任务条目

    Args:
        task: 任务对象
        index: 显示序号（如果为None则使用task.id，用于向后兼容）
        timezone: 时区名称

    Returns:
        格式化后的文本，如 "• #1 备份 NAS 配置" 或 "• #1 备份 NAS 配置（20:00）"
    """
    # 使用 DateParser 去掉任务内容开头的日期时间关键词
    parser = DateParser(timezone)
    clean_content = parser.strip_datetime_prefix(task.content)
    display_id = index if index is not None else task.id

    # 如果有提醒时间，显示时间
    if task.reminder_at:
        # reminder_at 格式为 "YYYY-MM-DD HH:MM"，取时间部分
        time_part = task.reminder_at.split(" ")[1] if " " in task.reminder_at else ""
        if time_part:
            return f"• #{display_id} {clean_content}（{time_part}）"

    return f"• #{display_id} {clean_content}"


def get_new_plan_prompt() -> str:
    """获取新计划征集提示"""
    return "要不要录入「明天 + 一周内」的新计划？"


def get_input_mode_instructions() -> str:
    """获取一次性输入模式的说明"""
    return """请发送多行文本，每行 = 1 个任务

📝 示例：
今天 买菜
明天 去银行
周五 下午开会
11月15日 还信用卡
+3d 检查服务器

💡 提示：
• 行首写日期，后面跟任务内容
• 不写日期默认为「明天」
• 支持：今天/明天/后天/周X/下周X/日期/+Nd"""


def format_task_creation_receipt(
    tasks: List[tuple],
    timezone: str = "Asia/Shanghai",
    skipped_count: int = 0
) -> str:
    """
    格式化任务创建回执

    Args:
        tasks: [(任务内容, 到期日期, 提醒时间或None), ...] 或旧格式 [(任务内容, 到期日期), ...]
        timezone: 时区名称，用于计算相对时间标签
        skipped_count: 因时间已过跳过的任务数

    Returns:
        回执文本
    """
    lines = [f"✅ 已创建 {len(tasks)} 项："]
    parser = DateParser(timezone)

    for item in tasks:
        # 兼容新旧格式
        if len(item) == 3:
            content, due_date, reminder_at = item
        else:
            content, due_date = item
            reminder_at = None

        # 去掉任务内容中的日期时间关键词
        clean_content = parser.strip_datetime_prefix(content)

        # 如果有提醒时间，显示完整的日期时间
        if reminder_at:
            lines.append(f"• {clean_content} → {reminder_at}")
        else:
            # 获取相对时间标签
            relative_label = get_relative_date_label(due_date, timezone)
            # 格式：• 任务内容 → 日期 (相对时间)
            lines.append(f"• {clean_content} → {due_date}{relative_label}")

    # 添加跳过提示
    if skipped_count > 0:
        lines.append(f"\n⚠️ 其中 {skipped_count} 条因时间已过未创建")

    return "\n".join(lines)


def get_morning_checklist_header() -> str:
    """获取早间清单的标题"""
    return "🌅 今日待办："


def get_overdue_review_header() -> str:
    """获取逾期任务区块的标题"""
    return "⚠️ 逾期未清（需要处理）："


def get_overdue_warning(count: int) -> str:
    """
    获取早间清单的逾期任务提示（仅数量，无按钮）

    Args:
        count: 逾期任务数量

    Returns:
        提示文本
    """
    return f"⚠️ 有 {count} 项逾期任务需要处理"


def get_overdue_snooze_hint() -> str:
    """获取逾期任务暂停提示（今日不再提醒）"""
    return "点击下方按钮可暂停今日的逾期提醒"


def format_overdue_task_item(task: Task, index: int = None) -> str:
    """
    格式化逾期任务条目（带原定日期）

    Args:
        task: 任务对象
        index: 显示序号（如果为None则使用task.id）

    Returns:
        格式化后的文本，如 "• #1 备份 NAS 配置（原定 11-08）"
    """
    clean_content = _strip_date_keywords(task.content)
    display_id = index if index is not None else task.id
    # 将 YYYY-MM-DD 转换为 MM-DD 格式
    due_date_short = task.due_date[5:]  # 去掉年份，只保留 MM-DD
    return f"• #{display_id} {clean_content}（原定 {due_date_short}）"


def get_no_tasks_message() -> str:
    """获取无任务时的提示"""
    return "今天没有待办 ✅"


def get_today_header() -> str:
    """获取 /today 命令的标题"""
    return "📋 今日待办："


def get_week_header() -> str:
    """获取 /week 命令的标题"""
    return "📅 未来 7 天："


def get_confirm_complete_prompt(task_content: str) -> str:
    """
    获取完成确认提示

    Args:
        task_content: 任务内容

    Returns:
        确认提示消息
    """
    clean_content = _strip_date_keywords(task_content)
    return f"确认要完成这个计划吗？\n📝 {clean_content}"


def get_confirm_cancel_prompt(task_content: str) -> str:
    """
    获取取消确认提示

    Args:
        task_content: 任务内容

    Returns:
        确认提示消息
    """
    clean_content = _strip_date_keywords(task_content)
    return f"确认要取消这个计划吗？\n📝 {clean_content}"


def get_task_done_message(task_content: str) -> str:
    """
    任务完成的确认消息

    Args:
        task_content: 任务内容

    Returns:
        确认消息
    """
    clean_content = _strip_date_keywords(task_content)
    return f"✅ 已完成：{clean_content}"


def get_task_canceled_message(task_content: str) -> str:
    """
    任务取消的确认消息

    Args:
        task_content: 任务内容

    Returns:
        确认消息
    """
    clean_content = _strip_date_keywords(task_content)
    return f"🗑 已取消：{clean_content}"


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


def get_startup_notification(startup_time: str, timezone: str, user_count: int) -> str:
    """
    获取启动通知消息

    Args:
        startup_time: 启动时间字符串 (YYYY-MM-DD HH:MM:SS)
        timezone: 时区名称
        user_count: 注册用户数量

    Returns:
        启动通知消息文本
    """
    return f"""🤖 Telegram Plan Bot 已启动

📅 时间：{startup_time} ({timezone})
👥 用户数：{user_count}"""


# ==================== 提醒相关消息 ====================

def get_reminder_message(task_content: str, reminder_at: str, timezone: str = "Asia/Shanghai") -> str:
    """
    获取提醒消息

    Args:
        task_content: 任务内容（原文）
        reminder_at: 提醒时间（YYYY-MM-DD HH:MM）
        timezone: 时区名称

    Returns:
        提醒消息文本
    """
    parser = DateParser(timezone)
    clean_content = parser.strip_datetime_prefix(task_content)
    return f"⏰ 提醒：{clean_content}\n时间：{reminder_at}"


def get_time_passed_create_message() -> str:
    """时间已过（创建时）提示"""
    return "时间已过，未创建该任务"


def get_time_passed_edit_message() -> str:
    """时间已过（修改时）提示"""
    return "时间已过，请重新输入"


def get_edit_time_prompt() -> str:
    """修改时间输入提示"""
    return """请输入新的提醒时间
支持格式：今晚8点 / 今天20:00 / 周五20:00 / 周五晚上八点 / 20:00"""


def get_reminder_updated_message(new_reminder_at: str) -> str:
    """
    提醒时间更新确认

    Args:
        new_reminder_at: 新提醒时间（YYYY-MM-DD HH:MM）

    Returns:
        确认消息
    """
    return f"✅ 提醒时间已更新为：{new_reminder_at}"


def get_edit_canceled_message() -> str:
    """取消修改确认"""
    return "已取消修改"


