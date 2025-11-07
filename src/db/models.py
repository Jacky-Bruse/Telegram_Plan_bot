"""
数据库模型定义
严格按照开发清单第五章字段级定义
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey,
    Index, CheckConstraint, Boolean
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

from src.constants import (
    STATUS_PENDING, STATUS_DONE, STATUS_CANCELED, STATUS_MISSED
)

Base = declarative_base()


class User(Base):
    """
    用户表
    存储用户配置和状态
    """
    __tablename__ = 'users'

    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Telegram chat_id（唯一）
    chat_id = Column(Integer, unique=True, nullable=False, index=True)

    # 时区（默认 Asia/Shanghai）
    tz = Column(String(64), nullable=False, default='Asia/Shanghai')

    # 晚间例行时间（默认 22:00）
    evening_hour = Column(Integer, nullable=False, default=22)
    evening_min = Column(Integer, nullable=False, default=0)

    # 早间清单时间（默认 08:30；关闭时为 -1）
    morning_hour = Column(Integer, nullable=True, default=8)
    morning_min = Column(Integer, nullable=True, default=30)

    # 一次性输入模式开关（0/1）
    awaiting_plans = Column(Boolean, nullable=False, default=False)

    # 是否已跳过当晚新计划征集（每天重置）
    skipped_tonight = Column(Boolean, nullable=False, default=False)

    # 创建时间
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # 关联任务
    tasks = relationship('Task', back_populates='user', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<User(id={self.id}, chat_id={self.chat_id}, tz={self.tz})>"


class Task(Base):
    """
    任务表
    存储用户的任务计划
    """
    __tablename__ = 'tasks'

    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)

    # 用户 ID（外键）
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)

    # 任务内容（原文）
    content = Column(String(512), nullable=False)

    # 到期日期（YYYY-MM-DD）
    due_date = Column(String(10), nullable=False)

    # 状态（pending/done/canceled/missed）
    status = Column(
        String(16),
        nullable=False,
        default=STATUS_PENDING
    )

    # 创建时间（ISO8601）
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # 更新时间（ISO8601）
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # 完成时间（可空）
    completed_at = Column(DateTime, nullable=True)

    # 取消时间（可空）
    canceled_at = Column(DateTime, nullable=True)

    # 关联用户
    user = relationship('User', back_populates='tasks')

    # 约束：状态必须是有效值
    __table_args__ = (
        CheckConstraint(
            f"status IN ('{STATUS_PENDING}', '{STATUS_DONE}', "
            f"'{STATUS_CANCELED}', '{STATUS_MISSED}')",
            name='check_status'
        ),
        # 复合索引：(user_id, due_date)
        Index('idx_user_due', 'user_id', 'due_date'),
        # 复合索引：(user_id, status, due_date)
        Index('idx_user_status_due', 'user_id', 'status', 'due_date'),
    )

    def __repr__(self):
        return (
            f"<Task(id={self.id}, user_id={self.user_id}, "
            f"status={self.status}, due_date={self.due_date})>"
        )


class Callback(Base):
    """
    回调记录表（可选）
    用于去重和审计
    """
    __tablename__ = 'callbacks'

    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)

    # callback_id（Telegram 回调 ID）
    callback_id = Column(String(128), unique=True, nullable=False, index=True)

    # 任务 ID
    task_id = Column(Integer, nullable=False)

    # 动作类型
    action = Column(String(32), nullable=False)

    # 处理时间
    processed_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return (
            f"<Callback(callback_id={self.callback_id}, "
            f"task_id={self.task_id}, action={self.action})>"
        )
