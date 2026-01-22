"""
日期时间解析引擎
支持日期解析和时间解析

日期优先级（从高到低）：
1. 显式日期：YYYY-MM-DD、MM-DD、MM/DD、MM.DD
2. 偏移：+Nd（天）、+Nw（周）
3. "下周 X"：落到下一周的对应星期几
4. "周 X"：解释为下一个对应星期几（包含今天）
5. 今天/明天/后天
6. 默认明天（未匹配任何模式）

时间格式支持：
- HH:MM、H:MM（如 20:00、8:30）
- H点、H点半（如 8点、8点半）
- H:MMam/pm（如 8:00pm）
- 中文时段词 + 数字（如 晚上八点、下午三点半）
"""

import re
from datetime import datetime, timedelta
from typing import Tuple, Optional, List
import pytz

from src.constants import (
    DATE_KEYWORD_TODAY,
    DATE_KEYWORD_TOMORROW,
    DATE_KEYWORD_DAY_AFTER_TOMORROW,
    WEEKDAY_KEYWORDS,
    TIME_PERIOD_KEYWORDS,
    CHINESE_NUMBERS
)


class DateParser:
    """日期时间解析器"""

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

    def get_now(self) -> datetime:
        """获取用户时区的当前时间"""
        return datetime.now(self.tz)

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

        # X月X日/号 格式（中文月日）
        match = re.search(r'(?<!\d)(\d{1,2})月(\d{1,2})(日|号)(?!\d)', text)
        if match:
            month, day = match.groups()[0], match.groups()[1]
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

        # 优先级 4: "周 X"（下一个对应星期几，包含今天）
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
        获取下一个对应星期几的日期（包含今天）

        Args:
            today: 今天的日期
            target_weekday: 目标星期几（0=周一, 6=周日）

        Returns:
            下一个对应星期几的日期
        """
        current_weekday = today.weekday()
        days_ahead = target_weekday - current_weekday

        # 如果目标是之前的日期，则跳到下周（包含今天）
        if days_ahead < 0:
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

    def _parse_chinese_number(self, text: str) -> Optional[int]:
        """
        解析中文数字

        Args:
            text: 中文数字文本

        Returns:
            数字或 None
        """
        # 先检查直接映射
        if text in CHINESE_NUMBERS:
            return CHINESE_NUMBERS[text]

        # 处理 "十X" 格式（如 "十一"）
        if text.startswith("十") and len(text) == 2:
            second = text[1]
            if second in CHINESE_NUMBERS:
                return 10 + CHINESE_NUMBERS[second]

        return None

    def _parse_chinese_minute(self, text: str) -> Optional[Tuple[int, int]]:
        """
        解析中文分钟（0-59）

        Args:
            text: 文本（如 "十分xxx" 或 "二十五分xxx"）

        Returns:
            (分钟值, 匹配的字符数) 或 None
        """
        # X十Y分 (如 二十五分、三十分)
        for cn1, val1 in CHINESE_NUMBERS.items():
            if val1 in [2, 3, 4, 5] and text.startswith(cn1 + "十"):
                rest = text[len(cn1) + 1:]
                # X十Y分
                for cn2, val2 in CHINESE_NUMBERS.items():
                    if 1 <= val2 <= 9 and rest.startswith(cn2 + "分"):
                        minute = val1 * 10 + val2
                        matched_len = len(cn1) + 1 + len(cn2) + 1
                        return minute, matched_len
                # X十分
                if rest.startswith("分"):
                    minute = val1 * 10
                    matched_len = len(cn1) + 2
                    return minute, matched_len

        # 十Y分 (如 十五分)
        if text.startswith("十"):
            rest = text[1:]
            for cn, val in CHINESE_NUMBERS.items():
                if 1 <= val <= 9 and rest.startswith(cn + "分"):
                    minute = 10 + val
                    matched_len = 1 + len(cn) + 1
                    return minute, matched_len
            # 十分
            if rest.startswith("分"):
                return 10, 2

        # 单个数字分 (如 五分)
        for cn, val in CHINESE_NUMBERS.items():
            if 1 <= val <= 9 and text.startswith(cn + "分"):
                return val, len(cn) + 1

        return None

    def parse_time(self, text: str) -> Optional[Tuple[int, int, str]]:
        """
        从文本开头解析时间

        Args:
            text: 输入文本

        Returns:
            (小时, 分钟, 匹配的时间表达式) 或 None
        """
        text = text.strip()

        # 模式 1: HH:MM 或 H:MM（必须在开头）
        match = re.match(r'^(\d{1,2}):(\d{2})', text)
        if match:
            hour, minute = int(match.group(1)), int(match.group(2))
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return hour, minute, match.group(0)

        # 模式 2: H:MMam/pm 或 H:MMpm（必须在开头）
        match = re.match(r'^(\d{1,2}):(\d{2})\s*(am|pm|AM|PM)', text)
        if match:
            hour, minute = int(match.group(1)), int(match.group(2))
            period = match.group(3).lower()
            if period == 'pm' and hour < 12:
                hour += 12
            elif period == 'am' and hour == 12:
                hour = 0
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return hour, minute, match.group(0)

        # 模式 3: 数字+点+分钟（必须在开头）
        # 优先匹配 X点Y分
        match = re.match(r'^(\d{1,2})点(\d{1,2})分', text)
        if match:
            hour, minute = int(match.group(1)), int(match.group(2))
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return hour, minute, match.group(0)

        # 再匹配 X点半 或 X点
        match = re.match(r'^(\d{1,2})点(半)?', text)
        if match:
            hour = int(match.group(1))
            minute = 30 if match.group(2) else 0
            if 0 <= hour <= 23:
                return hour, minute, match.group(0)

        # 模式 3.5: 中文数字 + 点（必须在开头）
        for cn_num in sorted(CHINESE_NUMBERS.keys(), key=len, reverse=True):
            if text.startswith(cn_num + "点"):
                hour = CHINESE_NUMBERS[cn_num]
                after_dian = text[len(cn_num) + 1:]
                minute_result = self._parse_chinese_minute(after_dian)
                if minute_result:
                    minute, minute_len = minute_result
                    matched_len = len(cn_num) + 1 + minute_len
                    if 0 <= hour <= 23:
                        return hour, minute, text[:matched_len]
                if after_dian.startswith("半"):
                    if 0 <= hour <= 23:
                        return hour, 30, text[:len(cn_num) + 2]
                if 0 <= hour <= 23:
                    return hour, 0, text[:len(cn_num) + 1]

        # 模式 4: 时段词 + 中文数字/阿拉伯数字 + 点（必须在开头）
        for period_name, (min_hour, max_hour) in TIME_PERIOD_KEYWORDS.items():
            if text.startswith(period_name):
                rest = text[len(period_name):]

                # 尝试匹配阿拉伯数字 + 点 + 分钟（优先）
                match = re.match(r'^(\d{1,2})点(\d{1,2})分', rest)
                if match:
                    hour, minute = int(match.group(1)), int(match.group(2))
                    hour = self._adjust_hour_by_period(hour, period_name)
                    if hour is not None and 0 <= minute <= 59:
                        return hour, minute, period_name + match.group(0)

                # 尝试匹配阿拉伯数字 + 点半/点
                match = re.match(r'^(\d{1,2})点(半)?', rest)
                if match:
                    hour = int(match.group(1))
                    minute = 30 if match.group(2) else 0
                    # 根据时段调整小时
                    hour = self._adjust_hour_by_period(hour, period_name)
                    if hour is not None:
                        return hour, minute, period_name + match.group(0)

                # 尝试匹配中文数字 + 点 + 中文分钟（优先）
                for cn_num, num_val in CHINESE_NUMBERS.items():
                    if rest.startswith(cn_num + "点"):
                        hour = num_val
                        after_dian = rest[len(cn_num) + 1:]
                        # 尝试解析中文分钟
                        minute_result = self._parse_chinese_minute(after_dian)
                        if minute_result:
                            minute, minute_len = minute_result
                            matched_len = len(cn_num) + 1 + minute_len
                            hour = self._adjust_hour_by_period(hour, period_name)
                            if hour is not None:
                                return hour, minute, period_name + rest[:matched_len]
                        # 检查是否有"半"
                        if after_dian.startswith("半"):
                            minute = 30
                            matched_len = len(cn_num) + 2
                            hour = self._adjust_hour_by_period(hour, period_name)
                            if hour is not None:
                                return hour, minute, period_name + rest[:matched_len]
                        # 仅 X点
                        minute = 0
                        matched_len = len(cn_num) + 1
                        hour = self._adjust_hour_by_period(hour, period_name)
                        if hour is not None:
                            return hour, minute, period_name + rest[:matched_len]

        # 模式 5: 今晚 + 时间（特殊处理）
        if text.startswith("今晚"):
            rest = text[2:]
            # 递归解析剩余部分的时间
            time_result = self.parse_time(rest)
            if time_result:
                hour, minute, matched = time_result
                # 今晚 = 晚上，调整小时
                if hour < 12:
                    hour += 12
                return hour, minute, "今晚" + matched

        return None

    def parse_time_at_end(self, text: str) -> Optional[Tuple[int, int, str]]:
        """
        从文本结尾解析时间

        Args:
            text: 输入文本

        Returns:
            (小时, 分钟, 匹配的时间表达式) 或 None
        """
        text = text.strip()

        # 模式 1: 今晚 + HH:MM（优先匹配，避免被通用 HH:MM 截断）
        match = re.search(r'今晚(\d{1,2}):(\d{2})$', text)
        if match:
            hour, minute = int(match.group(1)), int(match.group(2))
            if hour < 12:
                hour += 12
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return hour, minute, match.group(0)

        # 模式 2: 今晚 + 数字点（如 "今晚8点"、"今晚8点半"）
        match = re.search(r'今晚(\d{1,2})点(半)?$', text)
        if match:
            hour = int(match.group(1))
            minute = 30 if match.group(2) else 0
            if hour < 12:
                hour += 12
            if 0 <= hour <= 23:
                return hour, minute, match.group(0)

        # 模式 3: 今晚 + 中文数字（如 "今晚八点"）
        for cn_num, num_val in CHINESE_NUMBERS.items():
            pattern = r'今晚' + cn_num + r'点(半)?$'
            match = re.search(pattern, text)
            if match:
                hour = num_val
                minute = 30 if match.group(1) else 0
                if hour < 12:
                    hour += 12
                matched = "今晚" + cn_num + "点" + ("半" if minute == 30 else "")
                return hour, minute, matched

        # 模式 4: 通用 HH:MM 或 H:MM（必须在结尾）
        match = re.search(r'(\d{1,2}):(\d{2})$', text)
        if match:
            hour, minute = int(match.group(1)), int(match.group(2))
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return hour, minute, match.group(0)

        # 模式 5: H:MMam/pm（必须在结尾）
        match = re.search(r'(\d{1,2}):(\d{2})\s*(am|pm|AM|PM)$', text)
        if match:
            hour, minute = int(match.group(1)), int(match.group(2))
            period = match.group(3).lower()
            if period == 'pm' and hour < 12:
                hour += 12
            elif period == 'am' and hour == 12:
                hour = 0
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return hour, minute, match.group(0)

        # 模式 6: 时段词 + 阿拉伯数字 + 点 + 分钟（必须在结尾）
        for period_name, (min_hour, max_hour) in TIME_PERIOD_KEYWORDS.items():
            # 优先匹配 X点Y分
            pattern = period_name + r'(\d{1,2})点(\d{1,2})分$'
            match = re.search(pattern, text)
            if match:
                hour, minute = int(match.group(1)), int(match.group(2))
                hour = self._adjust_hour_by_period(hour, period_name)
                if hour is not None and 0 <= minute <= 59:
                    return hour, minute, match.group(0)

            # 再匹配 X点半/X点
            pattern = period_name + r'(\d{1,2})点(半)?$'
            match = re.search(pattern, text)
            if match:
                hour = int(match.group(1))
                minute = 30 if match.group(2) else 0
                hour = self._adjust_hour_by_period(hour, period_name)
                if hour is not None:
                    return hour, minute, match.group(0)

        # 模式 7: 时段词 + 中文数字 + 点 + 分钟（必须在结尾）
        for period_name, (min_hour, max_hour) in TIME_PERIOD_KEYWORDS.items():
            for cn_num, num_val in CHINESE_NUMBERS.items():
                prefix = period_name + cn_num + "点"
                if prefix in text:
                    # 检查是否在结尾位置
                    idx = text.rfind(prefix)
                    after_prefix = text[idx + len(prefix):]

                    # 尝试匹配中文分钟（如 十分、二十五分）
                    minute_result = self._parse_chinese_minute(after_prefix)
                    if minute_result:
                        minute, minute_len = minute_result
                        # 验证是否在结尾
                        if idx + len(prefix) + minute_len == len(text):
                            hour = num_val
                            hour = self._adjust_hour_by_period(hour, period_name)
                            if hour is not None:
                                matched = prefix + after_prefix[:minute_len]
                                return hour, minute, matched

                    # 匹配 X点半
                    if after_prefix == "半":
                        hour = num_val
                        minute = 30
                        hour = self._adjust_hour_by_period(hour, period_name)
                        if hour is not None:
                            matched = prefix + "半"
                            return hour, minute, matched

                    # 匹配 X点（结尾）
                    if after_prefix == "":
                        hour = num_val
                        minute = 0
                        hour = self._adjust_hour_by_period(hour, period_name)
                        if hour is not None:
                            return hour, minute, prefix

        # 模式 8: 纯数字+点+分钟（必须在结尾，最低优先级）
        # 优先匹配 X点Y分
        match = re.search(r'(\d{1,2})点(\d{1,2})分$', text)
        if match:
            hour, minute = int(match.group(1)), int(match.group(2))
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return hour, minute, match.group(0)

        # 再匹配 X点半/X点
        match = re.search(r'(\d{1,2})点(半)?$', text)
        if match:
            hour = int(match.group(1))
            minute = 30 if match.group(2) else 0
            if 0 <= hour <= 23:
                return hour, minute, match.group(0)

        return None

    def _adjust_hour_by_period(self, hour: int, period_name: str) -> Optional[int]:
        """
        根据时段调整小时数

        Args:
            hour: 原始小时（1-12）
            period_name: 时段名称

        Returns:
            调整后的小时（0-23）或 None（无效）
        """
        if period_name in ["凌晨"]:
            # 凌晨 0-5 点
            if hour == 12:
                return 0
            elif 1 <= hour <= 5:
                return hour
            return None
        elif period_name in ["早上", "上午"]:
            # 早上/上午 6-11 点
            if 6 <= hour <= 11:
                return hour
            elif 1 <= hour <= 5:
                # 早上1点-5点 也可能表示上午
                return hour
            return None
        elif period_name == "中午":
            # 中午 12 点
            if hour == 12:
                return 12
            return None
        elif period_name == "下午":
            # 下午 1-8 点 -> 13-20（口语中"下午"可延伸到傍晚）
            if 1 <= hour <= 8:
                return hour + 12
            elif hour == 12:
                return 12
            return None
        elif period_name == "晚上":
            # 晚上 6-11 点 -> 18-23
            # 晚上 1-5 点 -> 凌晨 01-05（夜间延续）
            # 晚上 12 点 -> 00:00（午夜）
            if 6 <= hour <= 11:
                return hour + 12  # 晚上6-11点 -> 18-23
            elif 1 <= hour <= 5:
                return hour  # 晚上1-5点 -> 凌晨01-05
            elif hour == 12:
                return 0  # 晚上12点 -> 午夜00:00
            return None

        return hour

    def parse_date_time(self, text: str) -> Tuple[str, Optional[str], str, bool]:
        """
        解析文本中的日期和时间

        Args:
            text: 输入文本

        Returns:
            (日期 YYYY-MM-DD, 时间 HH:MM 或 None, 原始文本, 是否时间已过)
        """
        # 先尝试解析开头时间
        time_result = self.parse_time(text)
        time_position = 'start' if time_result else None

        # 如果开头没有时间，尝试解析日期关键词后的时间
        if not time_result:
            time_result, date_prefix = self._parse_time_after_date(text)
            if time_result:
                time_position = 'after_date'

        # 如果还是没有时间，尝试解析结尾时间
        if not time_result:
            time_result = self.parse_time_at_end(text)
            if time_result:
                time_position = 'end'

        if time_result:
            hour, minute, time_expr = time_result

            # 根据时间位置确定日期解析的文本
            if time_position == 'start':
                # 去掉开头的时间表达式后用于日期解析
                text_for_date = text[len(time_expr):].strip()
            elif time_position == 'end':
                # 去掉结尾的时间表达式后用于日期解析
                text_for_date = text[:-len(time_expr)].strip()
            elif time_position == 'after_date':
                # 使用原文解析日期（日期关键词在时间之前）
                text_for_date = text

            # 检查是否有日期关键词
            has_date_keyword = False
            check_text = text_for_date if text_for_date else text
            for keyword in (DATE_KEYWORD_TODAY + DATE_KEYWORD_TOMORROW +
                           DATE_KEYWORD_DAY_AFTER_TOMORROW + list(WEEKDAY_KEYWORDS.keys())):
                if keyword in check_text:
                    has_date_keyword = True
                    break

            # 检查是否有显式日期
            if re.search(r'\d{4}-\d{1,2}-\d{1,2}', check_text) or \
               re.search(r'\d{1,2}-\d{1,2}', check_text) or \
               re.search(r'\d{1,2}/\d{1,2}', check_text) or \
               re.search(r'\d{1,2}\.\d{1,2}', check_text) or \
               re.search(r'\d{1,2}月\d{1,2}[日号]', check_text):
                has_date_keyword = True

            if has_date_keyword:
                # 使用去除时间后的文本解析日期
                date_str, _ = self.parse_date(check_text)
            else:
                # 默认今天（而不是明天）
                date_str = self.get_today().strftime('%Y-%m-%d')

            # 组合日期时间
            reminder_at = f"{date_str} {hour:02d}:{minute:02d}"

            # 检查时间是否已过
            now = self.get_now()
            reminder_dt = self.tz.localize(
                datetime.strptime(reminder_at, "%Y-%m-%d %H:%M")
            )
            is_passed = reminder_dt <= now

            return date_str, f"{hour:02d}:{minute:02d}", text, is_passed

        # 没有时间，只解析日期
        date_str, _ = self.parse_date(text)
        return date_str, None, text, False

    def _parse_time_after_date(self, text: str) -> Tuple[Optional[Tuple[int, int, str]], str]:
        """
        尝试解析日期关键词后紧跟的时间

        Args:
            text: 输入文本

        Returns:
            (时间解析结果, 日期前缀) 或 (None, "")
        """
        text = text.strip()

        # 检查星期关键词后的时间
        for keyword in WEEKDAY_KEYWORDS.keys():
            # 下周X
            prefix = "下" + keyword
            if text.startswith(prefix):
                rest = text[len(prefix):]
                time_result = self.parse_time(rest)
                if time_result:
                    return time_result, prefix
            # 周X
            if text.startswith(keyword):
                rest = text[len(keyword):]
                time_result = self.parse_time(rest)
                if time_result:
                    return time_result, keyword

        # 检查今天/明天/后天后的时间
        for keyword in DATE_KEYWORD_TODAY + DATE_KEYWORD_TOMORROW + DATE_KEYWORD_DAY_AFTER_TOMORROW:
            if text.startswith(keyword):
                rest = text[len(keyword):]
                time_result = self.parse_time(rest)
                if time_result:
                    return time_result, keyword

        # 检查显式日期后的时间（如 1-15 20:00）
        # YYYY-MM-DD
        match = re.match(r'^(\d{4}-\d{1,2}-\d{1,2})\s*', text)
        if match:
            rest = text[len(match.group(0)):]
            time_result = self.parse_time(rest)
            if time_result:
                return time_result, match.group(1)

        # MM-DD
        match = re.match(r'^(\d{1,2}-\d{1,2})\s*', text)
        if match:
            rest = text[len(match.group(0)):]
            time_result = self.parse_time(rest)
            if time_result:
                return time_result, match.group(1)

        return None, ""

    def strip_datetime_prefix(self, text: str) -> str:
        """
        去除文本开头和结尾的日期时间表达式

        Args:
            text: 输入文本

        Returns:
            去除日期时间后的文本
        """
        text = text.strip()
        original_text = text

        # 先尝试去除开头时间
        time_result = self.parse_time(text)
        if time_result:
            _, _, time_expr = time_result
            text = text[len(time_expr):].strip()

        # 尝试去除结尾时间（如果开头没有时间）
        if not time_result:
            time_result = self.parse_time_at_end(text)
            if time_result:
                _, _, time_expr = time_result
                text = text[:-len(time_expr)].strip()

        # 去除日期关键词（今天、明天、后天）
        for keyword in DATE_KEYWORD_TODAY + DATE_KEYWORD_TOMORROW + DATE_KEYWORD_DAY_AFTER_TOMORROW:
            if text.startswith(keyword):
                text = text[len(keyword):].strip()
                break

        # 去除星期关键词
        for keyword in WEEKDAY_KEYWORDS.keys():
            if text.startswith(keyword):
                text = text[len(keyword):].strip()
                break
            # 下周X
            if text.startswith("下" + keyword):
                text = text[len("下" + keyword):].strip()
                break

        # 去除显式日期格式
        # YYYY-MM-DD
        match = re.match(r'^\d{4}-\d{1,2}-\d{1,2}\s*', text)
        if match:
            text = text[len(match.group(0)):].strip()
        # MM-DD
        match = re.match(r'^\d{1,2}-\d{1,2}\s*', text)
        if match:
            text = text[len(match.group(0)):].strip()
        # MM/DD
        match = re.match(r'^\d{1,2}/\d{1,2}\s*', text)
        if match:
            text = text[len(match.group(0)):].strip()
        # X月X日/号
        match = re.match(r'^\d{1,2}月\d{1,2}[日号]\s*', text)
        if match:
            text = text[len(match.group(0)):].strip()

        # 去除日期后，再次检查开头是否有残留的时间表达式
        time_result = self.parse_time(text)
        if time_result:
            _, _, time_expr = time_result
            text = text[len(time_expr):].strip()

        # 如果去除后为空，返回原文
        if not text:
            return original_text

        return text

    def parse_tasks(self, text: str) -> List[Tuple[str, str, Optional[str], bool]]:
        """
        解析多行文本中的任务
        每行 = 1 个任务

        Args:
            text: 多行文本

        Returns:
            [(任务内容, 到期日期 YYYY-MM-DD, 提醒时间 YYYY-MM-DD HH:MM 或 None, 时间是否已过), ...]
        """
        lines = text.strip().split('\n')
        tasks = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 解析日期时间
            due_date, time_str, content, is_passed = self.parse_date_time(line)

            # 组合提醒时间
            reminder_at = f"{due_date} {time_str}" if time_str else None

            tasks.append((content, due_date, reminder_at, is_passed))

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
