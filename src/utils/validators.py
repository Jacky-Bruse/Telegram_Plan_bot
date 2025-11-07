"""
输入验证工具
"""

import re
import pytz
from typing import Tuple, Optional


def validate_timezone(tz_name: str) -> bool:
    """
    验证时区名称是否有效

    Args:
        tz_name: IANA 时区名称

    Returns:
        是否有效
    """
    try:
        pytz.timezone(tz_name)
        return True
    except pytz.UnknownTimeZoneError:
        return False


def validate_time(time_str: str) -> Tuple[bool, Optional[int], Optional[int]]:
    """
    验证并解析时间字符串（HH:MM 格式）

    Args:
        time_str: 时间字符串，如 "22:00"

    Returns:
        (是否有效, 小时, 分钟)
    """
    # 匹配 HH:MM 格式
    match = re.match(r'^(\d{1,2}):(\d{2})$', time_str)

    if not match:
        return False, None, None

    hour = int(match.group(1))
    minute = int(match.group(2))

    # 验证范围
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return True, hour, minute

    return False, None, None


def truncate_text(text: str, max_length: int) -> Tuple[str, bool]:
    """
    截断文本到指定长度

    Args:
        text: 原始文本
        max_length: 最大长度

    Returns:
        (截断后的文本, 是否发生了截断)
    """
    if len(text) <= max_length:
        return text, False

    return text[:max_length], True


def validate_callback_data(data: str) -> bool:
    """
    验证 callback_data 格式和长度

    Args:
        data: callback_data 字符串

    Returns:
        是否有效（不超过 64 字节）
    """
    return len(data.encode('utf-8')) <= 64
