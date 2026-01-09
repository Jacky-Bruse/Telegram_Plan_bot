#!/usr/bin/env python3
"""
Telegram 璁″垝鎻愰啋鏈哄櫒浜?- 涓荤▼搴忓叆鍙?涓ユ牸鎸夌収 docs/planbot-checklist.v1.0.md 瀹炵幇

鍔熻兘锛?- 鍒濆鍖栨暟鎹簱鍜孊ot
- 娉ㄥ唽鍛戒护鍜屽洖璋冨鐞嗗櫒
- 鍚姩瀹氭椂璋冨害绯荤粺
- 澶勭悊鍋滄満鎭㈠涓庤ˉ鍙戦€昏緫
- 闀胯疆璇㈡ā寮忚繍琛?"""

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
from src.bot.messages import get_startup_notification
from src.utils.config import get_config
from src.utils.logger import setup_logger, get_logger
from src.constants import STATUS_PENDING, STATUS_MISSED


# 鍏ㄥ眬鍙橀噺
scheduler = None
application = None


def handle_shutdown(signum, frame):
    """澶勭悊鍏抽棴淇″彿"""
    logger = get_logger(__name__)
    logger.info(f"Received signal {signum}, shutting down...")

    if scheduler:
        scheduler.shutdown()

    if application:
        # 鍋滄杞
        asyncio.create_task(application.stop())

    sys.exit(0)


async def check_and_send_makeup_reviews(scheduler_obj: TaskScheduler, db):
    """
    妫€鏌ュ苟鍙戦€佽ˉ鍙戠殑鏃ョ粓鏍稿
    鐢ㄤ簬鍋滄満鎭㈠鍚庤ˉ鍙戞槰鏃ユ湭娓呬换鍔?    涓ユ牸鎸夌収鏂囨。绗?6 鍜?8 绔犺妭

    Args:
        scheduler_obj: 璋冨害鍣ㄥ疄渚?        db: 鏁版嵁搴撳疄渚?    """
    logger = get_logger(__name__)
    logger.info("Checking for makeup reviews...")

    users = db.get_all_users()

    for user in users:
        try:
            # 鑾峰彇鐢ㄦ埛鏃跺尯鐨勬槰澶╂棩鏈?            tz = pytz.timezone(user.tz)
            yesterday = (datetime.now(tz) - timedelta(days=1)).strftime('%Y-%m-%d')

            # 鑾峰彇鏄ㄥぉ鍒版湡鐨?pending/missed 浠诲姟
            tasks = db.get_tasks_by_user_and_date(
                user.id,
                yesterday,
                statuses=[STATUS_PENDING, STATUS_MISSED]
            )

            if tasks:
                # 鍙戦€佽ˉ鍙戠殑鏃ョ粓鏍稿
                await scheduler_obj.send_makeup_review(user.id)
                logger.info(
                    f"Makeup review sent: user_id={user.id}, "
                    f"chat_id={user.chat_id}, tasks_count={len(tasks)}"
                )

        except Exception as e:
            logger.error(f"Error sending makeup review for user {user.id}: {e}")

    logger.info("Makeup reviews check completed")


def main():
    """涓诲嚱鏁?""
    global scheduler, application

    # 1. 鍔犺浇閰嶇疆
    try:
        config = get_config()
    except FileNotFoundError as e:
        print(f"閿欒锛歿e}")
        sys.exit(1)
    except Exception as e:
        print(f"閰嶇疆鍔犺浇澶辫触锛歿e}")
        sys.exit(1)

    # 2. 璁剧疆鏃ュ織
    logger = setup_logger(
        name="planbot",
        level=config.log_level,
        log_file=config.log_file
    )

    logger.info("=" * 60)
    logger.info("Telegram Plan Bot Starting...")
    logger.info("=" * 60)

    # 3. 鍒濆鍖栨暟鎹簱
    try:
        db = get_database(config.db_path)
        db.init_db()
        logger.info(f"Database initialized: {config.db_path}")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        sys.exit(1)

    # 4. 鍒涘缓 Telegram Bot Application
    try:
        application = Application.builder().token(config.bot_token).build()
        logger.info("Telegram Bot application created")
    except Exception as e:
        logger.error(f"Failed to create bot application: {e}")
        sys.exit(1)

    # 5. 鍒涘缓澶勭悊鍣ㄥ疄渚?    bot_handlers = BotHandlers(db)
    callback_handlers = CallbackHandlers(db)

    # 6. 娉ㄥ唽鍛戒护澶勭悊鍣?    application.add_handler(CommandHandler("start", bot_handlers.cmd_start))
    application.add_handler(CommandHandler("add", bot_handlers.cmd_add))
    application.add_handler(CommandHandler("today", bot_handlers.cmd_today))
    application.add_handler(CommandHandler("week", bot_handlers.cmd_week))
    application.add_handler(CommandHandler("setevening", bot_handlers.cmd_setevening))
    application.add_handler(CommandHandler("setmorning", bot_handlers.cmd_setmorning))
    application.add_handler(CommandHandler("timezone", bot_handlers.cmd_timezone))
    logger.info("Command handlers registered")

    # 7. 娉ㄥ唽鍥炶皟鏌ヨ澶勭悊鍣?    application.add_handler(CallbackQueryHandler(callback_handlers.handle_callback_query))
    logger.info("Callback query handler registered")

    # 8. 娉ㄥ唽鏂囨湰娑堟伅澶勭悊鍣紙涓€娆℃€ц緭鍏ユā寮忥級
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            bot_handlers.handle_text_message
        )
    )
    logger.info("Text message handler registered")

    # 启动任务（调度器初始化/补发/通知）
    async def startup_tasks(application):
        """启动时执行的任务"""
        global scheduler

        # 1. 初始化调度器（绑定运行中的事件循环）
        try:
            scheduler = TaskScheduler(application.bot, db)
            logger.info("Scheduler created")
        except Exception as e:
            logger.error(f"Failed to create scheduler: {e}")
            raise

        # 2. 注册调度器重建回调（供命令处理器使用）
        def schedule_rebuild_callback(user):
            """调度器重建回调函数"""
            scheduler.rebuild_user_jobs(user)

        application.bot_data['schedule_rebuild_callback'] = schedule_rebuild_callback

        # 3. 启动调度器并重建所有 Job
        try:
            scheduler.start()
            scheduler.rebuild_all_jobs()
            logger.info("Scheduler started and jobs rebuilt")
            logger.info("Scheduler ready")
        except Exception as e:
            logger.error(f"Failed to start scheduler: {e}")
            raise

        # 4. 检查并发送补发的日终核对
        await check_and_send_makeup_reviews(scheduler, db)

        # 5. 发送启动通知（如果已配置）
        try:
            # 检查是否启用启动通知
            enabled = config.get('notifications.startup_alert.enabled', False)
            admin_chat_id = config.get('notifications.startup_alert.admin_chat_id')

            if enabled and admin_chat_id:
                # 获取当前时间（使用默认时区）
                tz = pytz.timezone(config.default_timezone)
                now = datetime.now(tz)
                startup_time = now.strftime('%Y-%m-%d %H:%M:%S')

                # 获取用户数量
                users = db.get_all_users()
                user_count = len(users)

                # 生成启动通知消息
                message = get_startup_notification(
                    startup_time=startup_time,
                    timezone=config.default_timezone,
                    user_count=user_count
                )

                # 发送通知
                await application.bot.send_message(
                    chat_id=admin_chat_id,
                    text=message
                )

                logger.info(f"Startup notification sent to admin: {admin_chat_id}")

        except Exception as e:
            logger.error(f"Failed to send startup notification: {e}")

    application.post_init = startup_tasks

    # 13. 娉ㄥ唽淇″彿澶勭悊鍣?    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    # 14. 鍚姩 Bot锛堥暱杞妯″紡锛?    try:
        logger.info("Starting bot with long polling...")
        logger.info("=" * 60)
        logger.info("Bot is running. Press Ctrl+C to stop.")
        logger.info("=" * 60)

        # 浣跨敤 run_polling 鍚姩闀胯疆璇?        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=False  # 涓嶄涪寮冩寕璧风殑鏇存柊
        )

    except Exception as e:
        logger.error(f"Bot runtime error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        # 娓呯悊璧勬簮
        if scheduler:
            scheduler.shutdown()
        logger.info("Bot stopped")


if __name__ == "__main__":
    main()
