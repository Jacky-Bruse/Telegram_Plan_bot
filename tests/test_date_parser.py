"""
日期解析器单元测试
验证修复后的日期匹配逻辑
"""

import unittest
from datetime import datetime
from unittest.mock import patch
import pytz

from src.core.date_parser import DateParser


class TestDateParser(unittest.TestCase):
    """日期解析器测试类"""

    def setUp(self):
        """测试前准备"""
        self.parser = DateParser("Asia/Shanghai")

    def test_next_week_weekday_fix(self):
        """测试 _get_next_week_weekday 修复：周六到下周一应该是2天"""
        # 模拟 2025-11-08（周六）
        mock_today = datetime(2025, 11, 8, 0, 0, 0, tzinfo=pytz.timezone("Asia/Shanghai"))

        # 下周一（weekday=0）
        result = self.parser._get_next_week_weekday(mock_today, 0)

        # 应该是 2025-11-10（2天后）
        expected = datetime(2025, 11, 10, 0, 0, 0, tzinfo=pytz.timezone("Asia/Shanghai"))
        self.assertEqual(result.date(), expected.date())

    def test_next_week_weekday_same_day(self):
        """测试 _get_next_week_weekday：周一到下周一应该是7天"""
        # 模拟 2025-11-10（周一）
        mock_today = datetime(2025, 11, 10, 0, 0, 0, tzinfo=pytz.timezone("Asia/Shanghai"))

        # 下周一（weekday=0）
        result = self.parser._get_next_week_weekday(mock_today, 0)

        # 应该是 2025-11-17（7天后）
        expected = datetime(2025, 11, 17, 0, 0, 0, tzinfo=pytz.timezone("Asia/Shanghai"))
        self.assertEqual(result.date(), expected.date())

    @patch.object(DateParser, 'get_today')
    def test_parse_next_week_monday_from_saturday(self, mock_get_today):
        """测试解析"下周一"（从周六）"""
        # 模拟 2025-11-08（周六）
        mock_get_today.return_value = datetime(2025, 11, 8, 0, 0, 0, tzinfo=pytz.timezone("Asia/Shanghai"))

        # 测试"下周一"
        date_str, _ = self.parser.parse_date("下周一 开会")
        self.assertEqual(date_str, "2025-11-10")

    @patch.object(DateParser, 'get_today')
    def test_parse_next_week_with_libai(self, mock_get_today):
        """测试解析"下礼拜X"支持"""
        # 模拟 2025-11-08（周六）
        mock_get_today.return_value = datetime(2025, 11, 8, 0, 0, 0, tzinfo=pytz.timezone("Asia/Shanghai"))

        # 测试"下礼拜一"
        date_str, _ = self.parser.parse_date("下礼拜一 开会")
        self.assertEqual(date_str, "2025-11-10")

        # 测试"下礼拜五"
        date_str, _ = self.parser.parse_date("下礼拜五 聚餐")
        self.assertEqual(date_str, "2025-11-14")

    @patch.object(DateParser, 'get_today')
    def test_doc_example_parsing(self, mock_get_today):
        """测试文档示例（2025-11-08周六）的解析"""
        # 模拟 2025-11-08（周六）
        mock_get_today.return_value = datetime(2025, 11, 8, 0, 0, 0, tzinfo=pytz.timezone("Asia/Shanghai"))

        # 文档示例测试
        test_cases = [
            ("明天 买菜", "2025-11-09"),
            ("周五 下午 3 点开会", "2025-11-14"),
            ("+2d 跑 RAID 校验", "2025-11-10"),
            ("下周一 客户回访", "2025-11-10"),
            ("11-15 NAS 固件更新", "2025-11-15"),
        ]

        for text, expected_date in test_cases:
            with self.subTest(text=text):
                date_str, _ = self.parser.parse_date(text)
                self.assertEqual(date_str, expected_date, f"解析'{text}'失败")

    @patch.object(DateParser, 'get_today')
    def test_weekday_keywords(self, mock_get_today):
        """测试各种星期关键词"""
        # 模拟 2025-11-08（周六）
        mock_get_today.return_value = datetime(2025, 11, 8, 0, 0, 0, tzinfo=pytz.timezone("Asia/Shanghai"))

        # 测试"周X"（下一个对应星期几，不含今天）
        test_cases = [
            ("周一 开会", "2025-11-10"),  # 下周一
            ("星期一 开会", "2025-11-10"),
            ("礼拜一 开会", "2025-11-10"),
            ("周日 休息", "2025-11-09"),  # 明天周日
        ]

        for text, expected_date in test_cases:
            with self.subTest(text=text):
                date_str, _ = self.parser.parse_date(text)
                self.assertEqual(date_str, expected_date, f"解析'{text}'失败")

    @patch.object(DateParser, 'get_today')
    def test_priority_order(self, mock_get_today):
        """测试优先级顺序：显式日期 > 偏移 > "下周X" > "周X" > 今天/明天/后天 > 默认明天"""
        # 模拟 2025-11-08（周六）
        mock_get_today.return_value = datetime(2025, 11, 8, 0, 0, 0, tzinfo=pytz.timezone("Asia/Shanghai"))

        # 显式日期优先
        date_str, _ = self.parser.parse_date("2025-12-25 圣诞节 周一")
        self.assertEqual(date_str, "2025-12-25")  # 不应该被"周一"覆盖

        # 偏移优先于周X
        date_str, _ = self.parser.parse_date("+3d 周一开会")
        self.assertEqual(date_str, "2025-11-11")  # +3d，不是周一

        # "下周X"优先于"周X"
        date_str, _ = self.parser.parse_date("下周一")
        self.assertEqual(date_str, "2025-11-10")

    @patch.object(DateParser, 'get_today')
    def test_default_tomorrow(self, mock_get_today):
        """测试默认日期为明天"""
        # 模拟 2025-11-08（周六）
        mock_get_today.return_value = datetime(2025, 11, 8, 0, 0, 0, tzinfo=pytz.timezone("Asia/Shanghai"))

        # 没有任何日期关键词
        date_str, _ = self.parser.parse_date("买菜做饭")
        self.assertEqual(date_str, "2025-11-09")  # 明天

    @patch.object(DateParser, 'get_today')
    def test_parse_tasks_multiline(self, mock_get_today):
        """测试多行任务解析"""
        # 模拟 2025-11-08（周六）
        mock_get_today.return_value = datetime(2025, 11, 8, 0, 0, 0, tzinfo=pytz.timezone("Asia/Shanghai"))

        text = """明天 买菜
周五 下午 3 点开会
+2d 跑 RAID 校验
下周一 客户回访
11-15 NAS 固件更新"""

        tasks = self.parser.parse_tasks(text)

        expected = [
            ("明天 买菜", "2025-11-09"),
            ("周五 下午 3 点开会", "2025-11-14"),
            ("+2d 跑 RAID 校验", "2025-11-10"),
            ("下周一 客户回访", "2025-11-10"),
            ("11-15 NAS 固件更新", "2025-11-15"),
        ]

        self.assertEqual(len(tasks), 5)
        for (content, date), (exp_content, exp_date) in zip(tasks, expected):
            self.assertEqual(content, exp_content)
            self.assertEqual(date, exp_date)

    @patch.object(DateParser, 'get_today')
    def test_edge_cases(self, mock_get_today):
        """测试边界情况"""
        # 模拟 2025-11-08（周六）
        mock_get_today.return_value = datetime(2025, 11, 8, 0, 0, 0, tzinfo=pytz.timezone("Asia/Shanghai"))

        # 空行应该被忽略
        tasks = self.parser.parse_tasks("明天 买菜\n\n周一 开会\n")
        self.assertEqual(len(tasks), 2)

        # 只有空白的行
        tasks = self.parser.parse_tasks("   \n  ")
        self.assertEqual(len(tasks), 0)

    @patch.object(DateParser, 'get_today')
    def test_chinese_month_day_format(self, mock_get_today):
        """测试中文月日格式"""
        mock_get_today.return_value = datetime(2025, 11, 8, 0, 0, 0, tzinfo=pytz.timezone("Asia/Shanghai"))

        test_cases = [
            ("11月5日 写日记", "2025-11-05"),
            ("1月1日 新年", "2025-01-01"),
            ("12月31号 跨年", "2025-12-31"),
            ("11月5日 周一", "2025-11-05"),  # 优先级测试：显式日期优先于"周一"
        ]

        for text, expected_date in test_cases:
            with self.subTest(text=text):
                date_str, _ = self.parser.parse_date(text)
                self.assertEqual(date_str, expected_date, f"解析'{text}'失败")


if __name__ == '__main__':
    unittest.main()
