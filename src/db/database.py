"""
数据库操作模块
提供数据库连接和CRUD操作
"""

from datetime import datetime, date
from pathlib import Path
from typing import List, Optional, Tuple
from sqlalchemy import create_engine, and_
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError

from src.db.models import Base, User, Task, Callback
from src.constants import (
    STATUS_PENDING, STATUS_DONE, STATUS_CANCELED, STATUS_MISSED
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


class Database:
    """数据库管理类"""

    def __init__(self, db_path: str):
        """
        初始化数据库连接

        Args:
            db_path: 数据库文件路径
        """
        # 确保数据目录存在
        db_file = Path(db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)

        # 创建引擎
        self.engine = create_engine(
            f'sqlite:///{db_path}',
            echo=False,  # 生产环境不输出 SQL
            pool_pre_ping=True  # 连接池预检测
        )

        # 创建会话工厂
        # expire_on_commit=False 确保 commit 后对象仍可访问
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine,
            expire_on_commit=False
        )

        logger.info(f"Database initialized: {db_path}")

    def init_db(self):
        """创建所有表"""
        Base.metadata.create_all(bind=self.engine)
        logger.info("Database tables created")

    def get_session(self) -> Session:
        """获取数据库会话"""
        return self.SessionLocal()

    # ==================== User CRUD ====================

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """
        根据用户 ID 获取用户

        Args:
            user_id: 用户 ID（数据库主键）

        Returns:
            User 对象或 None
        """
        try:
            with self.get_session() as session:
                return session.query(User).filter(User.id == user_id).first()
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_user_by_id: {e}")
            return None

    def get_user_by_chat_id(self, chat_id: int) -> Optional[User]:
        """
        根据 chat_id 获取用户

        Args:
            chat_id: Telegram chat_id

        Returns:
            User 对象或 None
        """
        try:
            with self.get_session() as session:
                return session.query(User).filter(User.chat_id == chat_id).first()
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_user_by_chat_id: {e}")
            return None

    def create_user(
        self,
        chat_id: int,
        tz: str,
        evening_hour: int,
        evening_min: int,
        morning_hour: int,
        morning_min: int
    ) -> Optional[User]:
        """
        创建新用户

        Args:
            chat_id: Telegram chat_id
            tz: 时区
            evening_hour: 晚间小时
            evening_min: 晚间分钟
            morning_hour: 早间小时
            morning_min: 早间分钟

        Returns:
            创建的 User 对象，失败返回 None
        """
        try:
            with self.get_session() as session:
                user = User(
                    chat_id=chat_id,
                    tz=tz,
                    evening_hour=evening_hour,
                    evening_min=evening_min,
                    morning_hour=morning_hour,
                    morning_min=morning_min
                )
                session.add(user)
                session.commit()
                session.refresh(user)
                logger.info(f"User created: chat_id={chat_id}")
                return user
        except SQLAlchemyError as e:
            logger.error(f"Database error in create_user: {e}")
            return None

    def update_user_timezone(self, user_id: int, tz: str) -> bool:
        """更新用户时区

        Returns:
            是否成功
        """
        try:
            with self.get_session() as session:
                user = session.query(User).filter(User.id == user_id).first()
                if user:
                    user.tz = tz
                    session.commit()
                    logger.info(f"User timezone updated: user_id={user_id}, tz={tz}")
                    return True
                return False
        except SQLAlchemyError as e:
            logger.error(f"Database error in update_user_timezone: {e}")
            return False

    def update_user_evening_time(self, user_id: int, hour: int, minute: int) -> bool:
        """更新用户晚间时间

        Returns:
            是否成功
        """
        try:
            with self.get_session() as session:
                user = session.query(User).filter(User.id == user_id).first()
                if user:
                    user.evening_hour = hour
                    user.evening_min = minute
                    session.commit()
                    logger.info(
                        f"User evening time updated: user_id={user_id}, "
                        f"time={hour:02d}:{minute:02d}"
                    )
                    return True
                return False
        except SQLAlchemyError as e:
            logger.error(f"Database error in update_user_evening_time: {e}")
            return False

    def update_user_morning_time(
        self,
        user_id: int,
        hour: Optional[int],
        minute: Optional[int]
    ) -> bool:
        """
        更新用户早间时间

        Args:
            user_id: 用户 ID
            hour: 小时（None 表示关闭）
            minute: 分钟（None 表示关闭）

        Returns:
            是否成功
        """
        try:
            with self.get_session() as session:
                user = session.query(User).filter(User.id == user_id).first()
                if user:
                    user.morning_hour = hour if hour is not None else -1
                    user.morning_min = minute if minute is not None else -1
                    session.commit()
                    logger.info(
                        f"User morning time updated: user_id={user_id}, "
                        f"hour={hour}, minute={minute}"
                    )
                    return True
                return False
        except SQLAlchemyError as e:
            logger.error(f"Database error in update_user_morning_time: {e}")
            return False

    def set_user_awaiting_plans(self, user_id: int, awaiting: bool) -> bool:
        """设置用户是否在等待输入计划

        Returns:
            是否成功
        """
        try:
            with self.get_session() as session:
                user = session.query(User).filter(User.id == user_id).first()
                if user:
                    user.awaiting_plans = awaiting
                    session.commit()
                    return True
                return False
        except SQLAlchemyError as e:
            logger.error(f"Database error in set_user_awaiting_plans: {e}")
            return False

    def set_user_skipped_tonight(self, user_id: int, skipped: bool) -> bool:
        """设置用户是否已跳过当晚新计划征集

        Returns:
            是否成功
        """
        try:
            with self.get_session() as session:
                user = session.query(User).filter(User.id == user_id).first()
                if user:
                    user.skipped_tonight = skipped
                    session.commit()
                    return True
                return False
        except SQLAlchemyError as e:
            logger.error(f"Database error in set_user_skipped_tonight: {e}")
            return False

    def get_all_users(self) -> List[User]:
        """获取所有用户"""
        try:
            with self.get_session() as session:
                return session.query(User).all()
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_all_users: {e}")
            return []

    # ==================== Task CRUD ====================

    def create_task(
        self,
        user_id: int,
        content: str,
        due_date: str
    ) -> Optional[Task]:
        """
        创建任务

        Args:
            user_id: 用户 ID
            content: 任务内容
            due_date: 到期日期（YYYY-MM-DD）

        Returns:
            创建的 Task 对象，失败返回 None
        """
        try:
            with self.get_session() as session:
                task = Task(
                    user_id=user_id,
                    content=content,
                    due_date=due_date,
                    status=STATUS_PENDING
                )
                session.add(task)
                session.commit()
                session.refresh(task)
                logger.info(f"Task created: task_id={task.id}, user_id={user_id}")
                return task
        except SQLAlchemyError as e:
            logger.error(f"Database error in create_task: {e}")
            return None

    def get_task_by_id(self, task_id: int) -> Optional[Task]:
        """根据 ID 获取任务"""
        try:
            with self.get_session() as session:
                return session.query(Task).filter(Task.id == task_id).first()
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_task_by_id: {e}")
            return None

    def get_tasks_by_user_and_date(
        self,
        user_id: int,
        due_date: str,
        statuses: Optional[List[str]] = None
    ) -> List[Task]:
        """
        获取用户指定日期的任务

        Args:
            user_id: 用户 ID
            due_date: 到期日期（YYYY-MM-DD）
            statuses: 状态列表（可选，默认所有状态）

        Returns:
            任务列表
        """
        try:
            with self.get_session() as session:
                query = session.query(Task).filter(
                    and_(
                        Task.user_id == user_id,
                        Task.due_date == due_date
                    )
                )

                if statuses:
                    query = query.filter(Task.status.in_(statuses))

                return query.order_by(Task.id).all()
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_tasks_by_user_and_date: {e}")
            return []

    def get_tasks_by_user_and_date_range(
        self,
        user_id: int,
        start_date: str,
        end_date: str,
        statuses: Optional[List[str]] = None
    ) -> List[Task]:
        """
        获取用户指定日期范围的任务

        Args:
            user_id: 用户 ID
            start_date: 开始日期（YYYY-MM-DD）
            end_date: 结束日期（YYYY-MM-DD）
            statuses: 状态列表（可选）

        Returns:
            任务列表
        """
        try:
            with self.get_session() as session:
                query = session.query(Task).filter(
                    and_(
                        Task.user_id == user_id,
                        Task.due_date >= start_date,
                        Task.due_date <= end_date
                    )
                )

                if statuses:
                    query = query.filter(Task.status.in_(statuses))

                return query.order_by(Task.due_date, Task.id).all()
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_tasks_by_user_and_date_range: {e}")
            return []

    def update_task_status(
        self,
        task_id: int,
        status: str,
        timestamp: Optional[datetime] = None
    ) -> bool:
        """
        更新任务状态

        Args:
            task_id: 任务 ID
            status: 新状态
            timestamp: 时间戳（可选）

        Returns:
            是否成功
        """
        try:
            with self.get_session() as session:
                task = session.query(Task).filter(Task.id == task_id).first()
                if task:
                    task.status = status

                    if status == STATUS_DONE:
                        task.completed_at = timestamp or datetime.utcnow()
                    elif status == STATUS_CANCELED:
                        task.canceled_at = timestamp or datetime.utcnow()

                    session.commit()
                    logger.info(f"Task status updated: task_id={task_id}, status={status}")
                    return True
                return False
        except SQLAlchemyError as e:
            logger.error(f"Database error in update_task_status: {e}")
            return False

    def update_task_due_date(self, task_id: int, new_due_date: str) -> bool:
        """
        更新任务到期日期

        Args:
            task_id: 任务 ID
            new_due_date: 新到期日期（YYYY-MM-DD）

        Returns:
            是否成功
        """
        try:
            with self.get_session() as session:
                task = session.query(Task).filter(Task.id == task_id).first()
                if task:
                    task.due_date = new_due_date
                    session.commit()
                    logger.info(
                        f"Task due date updated: task_id={task_id}, "
                        f"new_due_date={new_due_date}"
                    )
                    return True
                return False
        except SQLAlchemyError as e:
            logger.error(f"Database error in update_task_due_date: {e}")
            return False

    # ==================== Callback CRUD ====================

    def is_callback_processed(self, callback_id: str) -> bool:
        """检查回调是否已处理（防重复点击）"""
        try:
            with self.get_session() as session:
                return session.query(Callback).filter(
                    Callback.callback_id == callback_id
                ).first() is not None
        except SQLAlchemyError as e:
            logger.error(f"Database error in is_callback_processed: {e}")
            return False

    def mark_callback_processed(
        self,
        callback_id: str,
        task_id: int,
        action: str
    ) -> bool:
        """标记回调已处理

        Returns:
            是否成功
        """
        try:
            with self.get_session() as session:
                callback = Callback(
                    callback_id=callback_id,
                    task_id=task_id,
                    action=action
                )
                session.add(callback)
                session.commit()
                return True
        except SQLAlchemyError as e:
            logger.error(f"Database error in mark_callback_processed: {e}")
            return False


# 全局数据库实例
_db_instance: Optional[Database] = None


def get_database(db_path: Optional[str] = None) -> Database:
    """
    获取全局数据库实例（单例模式）

    Args:
        db_path: 数据库路径（仅首次调用时有效）

    Returns:
        Database 实例
    """
    global _db_instance

    if _db_instance is None:
        if db_path is None:
            raise ValueError("首次调用必须提供 db_path")
        _db_instance = Database(db_path)

    return _db_instance
