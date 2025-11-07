"""
数据库初始化脚本
"""

from src.db.database import get_database
from src.utils.config import get_config
from src.utils.logger import setup_logger

logger = setup_logger()


def init_database():
    """初始化数据库"""
    config = get_config()
    db = get_database(config.db_path)
    db.init_db()
    logger.info("Database initialization completed")


if __name__ == '__main__':
    init_database()
