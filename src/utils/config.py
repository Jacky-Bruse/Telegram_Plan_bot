"""
配置管理模块
从 config.json 读取配置，提供统一的配置访问接口
"""

import json
import os
from pathlib import Path
from typing import Optional


class Config:
    """配置管理类"""

    def __init__(self, config_path: Optional[str] = None):
        """
        初始化配置

        Args:
            config_path: 配置文件路径，默认为项目根目录的 config.json
        """
        if config_path is None:
            # 默认配置文件路径：项目根目录/config.json
            project_root = Path(__file__).parent.parent.parent
            config_path = project_root / "config.json"

        self.config_path = Path(config_path)
        self._config = self._load_config()

    def _load_config(self) -> dict:
        """
        加载配置文件

        Returns:
            配置字典

        Raises:
            FileNotFoundError: 配置文件不存在
            json.JSONDecodeError: 配置文件格式错误
        """
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"配置文件不存在: {self.config_path}\n"
                f"请创建 config.json 文件，参考 config.example.json"
            )

        with open(self.config_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def get(self, key: str, default=None):
        """
        获取配置项

        Args:
            key: 配置键，支持点号分隔的嵌套键（如 "database.path"）
            default: 默认值

        Returns:
            配置值，如果不存在则返回默认值
        """
        keys = key.split('.')
        value = self._config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    @property
    def bot_token(self) -> str:
        """获取 Telegram Bot Token"""
        token = self.get('bot.token')
        if not token:
            raise ValueError("配置项 'bot.token' 未设置")
        return token

    @property
    def db_path(self) -> str:
        """获取数据库路径"""
        return self.get('database.path', 'data/bot.db')

    @property
    def default_timezone(self) -> str:
        """获取默认时区"""
        return self.get('defaults.timezone', 'Asia/Shanghai')

    @property
    def default_evening_hour(self) -> int:
        """获取默认晚间小时"""
        return self.get('defaults.evening_hour', 22)

    @property
    def default_evening_minute(self) -> int:
        """获取默认晚间分钟"""
        return self.get('defaults.evening_minute', 0)

    @property
    def default_morning_hour(self) -> int:
        """获取默认早间小时"""
        return self.get('defaults.morning_hour', 8)

    @property
    def default_morning_minute(self) -> int:
        """获取默认早间分钟"""
        return self.get('defaults.morning_minute', 30)

    @property
    def log_level(self) -> str:
        """获取日志级别"""
        return self.get('logging.level', 'INFO')

    @property
    def log_file(self) -> Optional[str]:
        """获取日志文件路径"""
        return self.get('logging.file')


# 全局配置实例
_config_instance: Optional[Config] = None


def get_config(config_path: Optional[str] = None) -> Config:
    """
    获取全局配置实例（单例模式）

    Args:
        config_path: 配置文件路径（仅首次调用时有效）

    Returns:
        Config 实例
    """
    global _config_instance

    if _config_instance is None:
        _config_instance = Config(config_path)

    return _config_instance
