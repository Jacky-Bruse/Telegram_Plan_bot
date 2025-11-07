"""
日期解析引擎
严格按照开发清单第三章的确定性规则实现

优先级（从高到低）：
1. 显式日期：YYYY-MM-DD、MM-DD、MM/DD、MM.DD
2. 偏移：+Nd（天）、+Nw（周）
3. "下周 X"：落到下一周的对应星期几
4. "周 X"：解释为下一个对应星期几（不含今天）
5. 今天/明天/后天
6. 默认明天（未匹配任何模式）
"""

import re
from datetime import datetime, timedelta
from typing import Tuple, Optional
import pytz

from src.constants import (
    DATE_KEYWORD_TODAY,
    DATE_KEYWORD_TOMORROW,
    DATE_KEYWORD_DAY_AFTER_TOMORROW,
    WEEKDAY_KEYWORDS
)


class DateParser:
    """日期解析器"""

    def __init__(self, timezone: str = "Asia/Shanghai"):
        """
        初始化日期解析器

        Args:
            timezone: IANA 时区名称
        """
        self.tz = pytz.timezone(timezone)

    def get_today(self) -> datetime:
        """获取用户时区的今天（00:00:00）"""
        return datetime.now(self.tz).replace(hour=0, minute=0, second=0, microsecond=0)

    def parse_date(self, text: str) -> Tuple[str, str]:
        """
        解析文本中的日期
        按优先级规则匹配

        Args:
            text: 输入文本

        Returns:
            (解析后的日期 YYYY-MM-DD, 原始文本)
        """
        today = self.get_today()

        # 优先级 1: 显式日期
        # YYYY-MM-DD 格式
        match = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', text)
        if match:
            year, month, day = match.groups()
            return f"{year}-{int(month):02d}-{int(day):02d}", text

        # MM-DD 格式（默认当年）
        match = re.search(r'(\d{1,2})-(\d{1,2})(?!\d)', text)
        if match:
            month, day = match.groups()
            year = today.year
            return f"{year}-{int(month):02d}-{int(day):02d}", text

        # MM/DD 格式
        match = re.search(r'(\d{1,2})/(\d{1,2})', text)
        if match:
            month, day = match.groups()
            year = today.year
            return f"{year}-{int(month):02d}-{int(day):02d}", text

        # MM.DD 格式
        match = re.search(r'(\d{1,2})\.(\d{1,2})', text)
        if match:
            month, day = match.groups()
            year = today.year
            return f"{year}-{int(month):02d}-{int(day):02d}", text

        # 优先级 2: 偏移
        # +Nd 格式（N 天后）
        match = re.search(r'\+(\d+)d', text, re.IGNORECASE)
        if match:
            days = int(match.group(1))
            target_date = today + timedelta(days=days)
            return target_date.strftime('%Y-%m-%d'), text

        # +Nw 格式（N 周后）
        match = re.search(r'\+(\d+)w', text, re.IGNORECASE)
        if match:
            weeks = int(match.group(1))
            target_date = today + timedelta(weeks=weeks)
            return target_date.strftime('%Y-%m-%d'), text

        # 优先级 3: "下周 X"
        for keyword, weekday in WEEKDAY_KEYWORDS.items():
            if f"下周{keyword[-1]}" in text or f"下星期{keyword[-1]}" in text or f"下礼拜{keyword[-1]}" in text:
                # 下周对应的星期几
                target_date = self._get_next_week_weekday(today, weekday)
                return target_date.strftime('%Y-%m-%d'), text

        # 优先级 4: "周 X"（下一个对应星期几，不含今天）
        for keyword, weekday in WEEKDAY_KEYWORDS.items():
            if keyword in text:
                target_date = self._get_next_weekday(today, weekday)
                return target_date.strftime('%Y-%m-%d'), text

        # 优先级 5: 今天/明天/后天
        for keyword in DATE_KEYWORD_TODAY:
            if keyword in text:
                return today.strftime('%Y-%m-%d'), text

        for keyword in DATE_KEYWORD_TOMORROW:
            if keyword in text:
                tomorrow = today + timedelta(days=1)
                return tomorrow.strftime('%Y-%m-%d'), text

        for keyword in DATE_KEYWORD_DAY_AFTER_TOMORROW:
            if keyword in text:
                day_after_tomorrow = today + timedelta(days=2)
                return day_after_tomorrow.strftime('%Y-%m-%d'), text

        # 优先级 6: 默认明天
        tomorrow = today + timedelta(days=1)
        return tomorrow.strftime('%Y-%m-%d'), text

    def _get_next_weekday(self, today: datetime, target_weekday: int) -> datetime:
        """
        获取下一个对应星期几的日期（不含今天）

        Args:
            today: 今天的日期
            target_weekday: 目标星期几（0=周一, 6=周日）

        Returns:
            下一个对应星期几的日期
        """
        current_weekday = today.weekday()
        days_ahead = target_weekday - current_weekday

        # 如果目标是今天或之前，则跳到下周
        if days_ahead <= 0:
            days_ahead += 7

        return today + timedelta(days=days_ahead)

    def _get_next_week_weekday(self, today: datetime, target_weekday: int) -> datetime:
        """
        获取下周对应星期几的日期

        Args:
            today: 今天的日期
            target_weekday: 目标星期几（0=周一, 6=周日）

        Returns:
            下周对应星期几的日期
        """
        current_weekday = today.weekday()
        # 计算到下周对应星期几的天数
        # 例：周六(5)到下周一(0) = (7-5)+0 = 2天
        days_ahead = (7 - current_weekday) + target_weekday

        return today + timedelta(days=days_ahead)

    def parse_tasks(self, text: str) -> list[Tuple[str, str]]:
        """
        解析多行文本中的任务
        每行 = 1 个任务

        Args:
            text: 多行文本

        Returns:
            [(任务内容, 到期日期 YYYY-MM-DD), ...]
        """
        lines = text.strip().split('\n')
        tasks = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 解析日期
            due_date, content = self.parse_date(line)
            tasks.append((content, due_date))

        return tasks


def get_date_parser(timezone: str) -> DateParser:
    """
    获取日期解析器实例

    Args:
        timezone: IANA 时区名称

    Returns:
        DateParser 实例
    """
    return DateParser(timezone)
