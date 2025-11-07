#!/usr/bin/env python3
"""
Telegram 计划提醒机器人 - 主程序入口
严格按照 docs/planbot-checklist.v1.0.md 实现

功能：
- 初始化数据库和Bot
- 注册命令和回调处理器
- 启动定时调度系统
- 处理停机恢复与补发逻辑
- 长轮询模式运行
"""

import asyncio
import signal
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytz
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from src.db.database import get_database
from src.core.scheduler import TaskScheduler
from src.bot.handlers import BotHandlers
from src.bot.callbacks import CallbackHandlers
from src.utils.config import get_config
from src.utils.logger import setup_logger, get_logger
from src.constants import STATUS_PENDING, STATUS_MISSED


# 全局变量
scheduler = None
application = None


def handle_shutdown(signum, frame):
    """处理关闭信号"""
    logger = get_logger(__name__)
    logger.info(f"Received signal {signum}, shutting down...")

    if scheduler:
        scheduler.shutdown()

    if application:
        # 停止轮询
        asyncio.create_task(application.stop())

    sys.exit(0)


async def check_and_send_makeup_reviews(scheduler_obj: TaskScheduler, db):
    """
    检查并发送补发的日终核对
    用于停机恢复后补发昨日未清任务
    严格按照文档第 6 和 8 章节

    Args:
        scheduler_obj: 调度器实例
        db: 数据库实例
    """
    logger = get_logger(__name__)
    logger.info("Checking for makeup reviews...")

    users = db.get_all_users()

    for user in users:
        try:
            # 获取用户时区的昨天日期
            tz = pytz.timezone(user.tz)
            yesterday = (datetime.now(tz) - timedelta(days=1)).strftime('%Y-%m-%d')

            # 获取昨天到期的 pending/missed 任务
            tasks = db.get_tasks_by_user_and_date(
                user.id,
                yesterday,
                statuses=[STATUS_PENDING, STATUS_MISSED]
            )

            if tasks:
                # 发送补发的日终核对
                await scheduler_obj.send_makeup_review(user.id)
                logger.info(
                    f"Makeup review sent: user_id={user.id}, "
                    f"chat_id={user.chat_id}, tasks_count={len(tasks)}"
                )

        except Exception as e:
            logger.error(f"Error sending makeup review for user {user.id}: {e}")

    logger.info("Makeup reviews check completed")


def main():
    """主函数"""
    global scheduler, application

    # 1. 加载配置
    try:
        config = get_config()
    except FileNotFoundError as e:
        print(f"错误：{e}")
        sys.exit(1)
    except Exception as e:
        print(f"配置加载失败：{e}")
        sys.exit(1)

    # 2. 设置日志
    logger = setup_logger(
        name="planbot",
        level=config.log_level,
        log_file=config.log_file
    )

    logger.info("=" * 60)
    logger.info("Telegram Plan Bot Starting...")
    logger.info("=" * 60)

    # 3. 初始化数据库
    try:
        db = get_database(config.db_path)
        db.init_db()
        logger.info(f"Database initialized: {config.db_path}")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        sys.exit(1)

    # 4. 创建 Telegram Bot Application
    try:
        application = Application.builder().token(config.bot_token).build()
        logger.info("Telegram Bot application created")
    except Exception as e:
        logger.error(f"Failed to create bot application: {e}")
        sys.exit(1)

    # 5. 创建处理器实例
    bot_handlers = BotHandlers(db)
    callback_handlers = CallbackHandlers(db)

    # 6. 注册命令处理器
    application.add_handler(CommandHandler("start", bot_handlers.cmd_start))
    application.add_handler(CommandHandler("add", bot_handlers.cmd_add))
    application.add_handler(CommandHandler("today", bot_handlers.cmd_today))
    application.add_handler(CommandHandler("week", bot_handlers.cmd_week))
    application.add_handler(CommandHandler("setevening", bot_handlers.cmd_setevening))
    application.add_handler(CommandHandler("setmorning", bot_handlers.cmd_setmorning))
    application.add_handler(CommandHandler("timezone", bot_handlers.cmd_timezone))
    logger.info("Command handlers registered")

    # 7. 注册回调查询处理器
    application.add_handler(CallbackQueryHandler(callback_handlers.handle_callback_query))
    logger.info("Callback query handler registered")

    # 8. 注册文本消息处理器（一次性输入模式）
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            bot_handlers.handle_text_message
        )
    )
    logger.info("Text message handler registered")

    # 9. 创建调度器
    try:
        scheduler = TaskScheduler(application.bot, db)
        logger.info("Scheduler created")
    except Exception as e:
        logger.error(f"Failed to create scheduler: {e}")
        sys.exit(1)

    # 10. 注册调度器重建回调（供命令处理器使用）
    def schedule_rebuild_callback(user):
        """调度器重建回调函数"""
        scheduler.rebuild_user_jobs(user)

    application.bot_data['schedule_rebuild_callback'] = schedule_rebuild_callback

    # 11. 启动调度器并重建所有 Job
    try:
        scheduler.start()
        scheduler.rebuild_all_jobs()
        logger.info("Scheduler started and jobs rebuilt")
        logger.info("🔔 Scheduler ready")
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")
        sys.exit(1)

    # 12. 检查并发送补发的日终核对（停机恢复逻辑）
    async def startup_tasks(application):
        """启动时执行的任务"""
        await check_and_send_makeup_reviews(scheduler, db)

    # 将启动任务添加到事件循环
    application.post_init = startup_tasks

    # 13. 注册信号处理器
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    # 14. 启动 Bot（长轮询模式）
    try:
        logger.info("Starting bot with long polling...")
        logger.info("=" * 60)
        logger.info("Bot is running. Press Ctrl+C to stop.")
        logger.info("=" * 60)

        # 使用 run_polling 启动长轮询
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=False  # 不丢弃挂起的更新
        )

    except Exception as e:
        logger.error(f"Bot runtime error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        # 清理资源
        if scheduler:
            scheduler.shutdown()
        logger.info("Bot stopped")


if __name__ == "__main__":
    main()
