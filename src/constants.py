"""
常量定义
"""

# 任务状态
STATUS_PENDING = "pending"
STATUS_DONE = "done"
STATUS_CANCELED = "canceled"
STATUS_MISSED = "missed"

# 回调数据前缀
CALLBACK_TASK_PREFIX = "t"
CALLBACK_NEW_PLAN = "new"

# 回调动作
ACTION_DONE = "done"
ACTION_UNDONE = "un"
ACTION_CANCEL = "cancel"
ACTION_POSTPONE = "p"
ACTION_ADD = "add"
ACTION_SKIP = "skip"

# 限制
MAX_TASKS_PER_MESSAGE = 10  # 每条消息最多显示的任务数
MAX_INPUT_LINES = 100       # 一次性输入模式最多接收行数
MAX_CONTENT_LENGTH = 512    # 单行任务内容最大长度

# 分批发送延迟（秒）
BATCH_SEND_DELAY = 1.5

# 默认配置
DEFAULT_TIMEZONE = "Asia/Shanghai"
DEFAULT_EVENING_HOUR = 22
DEFAULT_EVENING_MINUTE = 0
DEFAULT_MORNING_HOUR = 8
DEFAULT_MORNING_MINUTE = 30

# 中文日期关键词
DATE_KEYWORD_TODAY = ["今天", "今日"]
DATE_KEYWORD_TOMORROW = ["明天", "明日"]
DATE_KEYWORD_DAY_AFTER_TOMORROW = ["后天"]

# 星期关键词
WEEKDAY_KEYWORDS = {
    "周一": 0, "星期一": 0, "礼拜一": 0,
    "周二": 1, "星期二": 1, "礼拜二": 1,
    "周三": 2, "星期三": 2, "礼拜三": 2,
    "周四": 3, "星期四": 3, "礼拜四": 3,
    "周五": 4, "星期五": 4, "礼拜五": 4,
    "周六": 5, "星期六": 5, "礼拜六": 5,
    "周日": 6, "星期日": 6, "礼拜日": 6,
    "周天": 6, "星期天": 6, "礼拜天": 6,
}
