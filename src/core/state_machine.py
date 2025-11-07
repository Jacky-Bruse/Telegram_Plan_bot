"""
任务状态机
管理任务的生命周期状态转换

状态流转：
pending → (done | canceled | missed)

事件：
- 点「✅ 完成」→ done
- 点「🗑 取消」→ canceled
- 点「⏳ 未完成」+ 顺延 → 回到 pending（更新 due_date）
- 过期未处理 → missed（可选标记）
"""

from datetime import datetime, timedelta
from typing import Optional

from src.constants import (
    STATUS_PENDING, STATUS_DONE, STATUS_CANCELED, STATUS_MISSED
)
from src.db.database import Database
from src.utils.logger import get_logger, log_task_operation

logger = get_logger(__name__)


class TaskStateMachine:
    """任务状态机"""

    def __init__(self, db: Database):
        """
        初始化状态机

        Args:
            db: 数据库实例
        """
        self.db = db

    def mark_as_done(self, task_id: int) -> bool:
        """
        标记任务为完成

        Args:
            task_id: 任务 ID

        Returns:
            是否成功
        """
        task = self.db.get_task_by_id(task_id)
        if not task:
            logger.warning(f"Task not found: task_id={task_id}")
            return False

        if task.status == STATUS_DONE:
            logger.info(f"Task already done: task_id={task_id}")
            return False

        self.db.update_task_status(task_id, STATUS_DONE, datetime.utcnow())
        log_task_operation(logger, "mark_as_done", task_id, task.user_id)
        return True

    def mark_as_canceled(self, task_id: int) -> bool:
        """
        标记任务为取消

        Args:
            task_id: 任务 ID

        Returns:
            是否成功
        """
        task = self.db.get_task_by_id(task_id)
        if not task:
            logger.warning(f"Task not found: task_id={task_id}")
            return False

        if task.status == STATUS_CANCELED:
            logger.info(f"Task already canceled: task_id={task_id}")
            return False

        self.db.update_task_status(task_id, STATUS_CANCELED, datetime.utcnow())
        log_task_operation(logger, "mark_as_canceled", task_id, task.user_id)
        return True

    def postpone_task(self, task_id: int, days: int) -> Optional[str]:
        """
        顺延任务

        Args:
            task_id: 任务 ID
            days: 顺延天数

        Returns:
            新的到期日期（YYYY-MM-DD），失败返回 None
        """
        task = self.db.get_task_by_id(task_id)
        if not task:
            logger.warning(f"Task not found: task_id={task_id}")
            return None

        # 解析当前到期日期
        try:
            current_due = datetime.strptime(task.due_date, '%Y-%m-%d')
        except ValueError:
            logger.error(f"Invalid due_date format: task_id={task_id}, due_date={task.due_date}")
            return None

        # 计算新的到期日期
        new_due = current_due + timedelta(days=days)
        new_due_str = new_due.strftime('%Y-%m-%d')

        # 更新数据库
        self.db.update_task_due_date(task_id, new_due_str)

        # 确保状态回到 pending
        if task.status != STATUS_PENDING:
            self.db.update_task_status(task_id, STATUS_PENDING)

        log_task_operation(
            logger,
            "postpone_task",
            task_id,
            task.user_id,
            f"days={days}, new_due_date={new_due_str}"
        )

        return new_due_str

    def mark_as_missed(self, task_id: int) -> bool:
        """
        标记任务为逾期未处理

        Args:
            task_id: 任务 ID

        Returns:
            是否成功
        """
        task = self.db.get_task_by_id(task_id)
        if not task:
            logger.warning(f"Task not found: task_id={task_id}")
            return False

        if task.status != STATUS_PENDING:
            logger.info(f"Task not in pending status: task_id={task_id}, status={task.status}")
            return False

        self.db.update_task_status(task_id, STATUS_MISSED)
        log_task_operation(logger, "mark_as_missed", task_id, task.user_id)
        return True

    def can_transition(self, task_id: int, target_status: str) -> bool:
        """
        检查是否可以转换到目标状态

        Args:
            task_id: 任务 ID
            target_status: 目标状态

        Returns:
            是否可以转换
        """
        task = self.db.get_task_by_id(task_id)
        if not task:
            return False

        current_status = task.status

        # 已完成或已取消的任务不能再转换
        if current_status in (STATUS_DONE, STATUS_CANCELED):
            return False

        # pending 和 missed 可以转换到任何状态
        return True


def get_state_machine(db: Database) -> TaskStateMachine:
    """
    获取状态机实例

    Args:
        db: 数据库实例

    Returns:
        TaskStateMachine 实例
    """
    return TaskStateMachine(db)
