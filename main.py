#!/usr/bin/env python3
"""
Telegram ??????? - ????????? docs/planbot-checklist.v1.0.md ???

???
- ??????? Bot
- ??????????
- ????????
- ???????????
- ???????
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
from src.bot.messages import get_startup_notification
from src.utils.config import get_config
from src.utils.logger import setup_logger, get_logger
from src.constants import STATUS_PENDING, STATUS_MISSED


# ????
scheduler = None
application = None


def handle_shutdown(signum, frame):
    """??????"""
    logger = get_logger(__name__)
    logger.info(f"Received signal {signum}, shutting down...")

    # ????
    if scheduler:
        scheduler.shutdown()

    if application:
        asyncio.create_task(application.stop())

    sys.exit(0)


async def check_and_send_makeup_reviews(scheduler_obj: TaskScheduler, db):
    """????????????
    ?????????????????????? 6 ? 8 ??
    
    Args:
        scheduler_obj: ?????
        db: ?????
    """
    
    logger = get_logger(__name__)
    logger.info("Checking for makeup reviews...")

    users = db.get_all_users()

    for user in users:
        try:
            # ???????????
            tz = pytz.timezone(user.tz)
            yesterday = (datetime.now(tz) - timedelta(days=1)).strftime('%Y-%m-%d')

            # ??????? pending/missed ??
            tasks = db.get_tasks_by_user_and_date(
                user.id,
                yesterday,
                statuses=[STATUS_PENDING, STATUS_MISSED]
            )

            if tasks:
                # ?????????
                await scheduler_obj.send_makeup_review(user.id)
                logger.info(
                    f"Makeup review sent: user_id={user.id}, "
                    f"chat_id={user.chat_id}, tasks_count={len(tasks)}"
                )

        except Exception as e:
            logger.error(f"Error sending makeup review for user {user.id}: {e}")

    logger.info("Makeup reviews check completed")


def main():
    """???"""
    global scheduler, application

    try:
        # 1. ????
        config = get_config()
    except FileNotFoundError as e:
        print(f"错误：{e}")
        sys.exit(1)
    except Exception as e:
        print(f"配置加载失败：{e}")
        sys.exit(1)

    # 2. ????
    logger = setup_logger(
        name="planbot",
        level=config.log_level,
        log_file=config.log_file
    )

    logger.info("=" * 60)
    logger.info("Telegram Plan Bot Starting...")
    logger.info("=" * 60)

    try:
        # 3. ??????
        db = get_database(config.db_path)
        db.init_db()
        logger.info(f"Database initialized: {config.db_path}")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        sys.exit(1)

    try:
        # 4. ?? Telegram Bot Application
        application = Application.builder().token(config.bot_token).build()
        logger.info("Telegram Bot application created")
    except Exception as e:
        logger.error(f"Failed to create bot application: {e}")
        sys.exit(1)

    # 5. ???????
    bot_handlers = BotHandlers(db)
    callback_handlers = CallbackHandlers(db)

    # 6. ???????
    application.add_handler(CommandHandler("start", bot_handlers.cmd_start))
    application.add_handler(CommandHandler("add", bot_handlers.cmd_add))
    application.add_handler(CommandHandler("today", bot_handlers.cmd_today))
    application.add_handler(CommandHandler("week", bot_handlers.cmd_week))
    application.add_handler(CommandHandler("setevening", bot_handlers.cmd_setevening))
    application.add_handler(CommandHandler("setmorning", bot_handlers.cmd_setmorning))
    application.add_handler(CommandHandler("timezone", bot_handlers.cmd_timezone))
    logger.info("Command handlers registered")

    # 7. ?????????
    application.add_handler(CallbackQueryHandler(callback_handlers.handle_callback_query))
    logger.info("Callback query handler registered")

    application.add_handler(
        # 8. ??????????????????
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            bot_handlers.handle_text_message
        )
    )
    logger.info("Text message handler registered")

    async def startup_tasks(application):
        """????????"""
        global scheduler

        try:
            # 1. ??????????????????
            scheduler = TaskScheduler(application.bot, db)
            logger.info("Scheduler created")
        except Exception as e:
            logger.error(f"Failed to create scheduler: {e}")
            raise

        # 2. ???????????????????
        def schedule_rebuild_callback(user):
            """?????????"""
            scheduler.rebuild_user_jobs(user)

        application.bot_data['schedule_rebuild_callback'] = schedule_rebuild_callback

        try:
            # 3. 启动调度器并重建 Job
            scheduler.start()
            catchup_task_ids = scheduler.rebuild_all_jobs()
            logger.info("Scheduler started and jobs rebuilt")
            logger.info("Scheduler ready")
        except Exception as e:
            logger.error(f"Failed to start scheduler: {e}")
            raise

        # 4. 补发昨日未清任务
        await check_and_send_makeup_reviews(scheduler, db)

        # 5. 补发24小时内的过期提醒
        if catchup_task_ids:
            try:
                await scheduler.send_catchup_reminders(catchup_task_ids)
            except Exception as e:
                logger.error(f"Failed to send catch-up reminders: {e}")

        try:
            # ??????????
            enabled = config.get('notifications.startup_alert.enabled', False)
            admin_chat_id = config.get('notifications.startup_alert.admin_chat_id')

            if enabled and admin_chat_id:
                # ??????????????
                tz = pytz.timezone(config.default_timezone)
                now = datetime.now(tz)
                startup_time = now.strftime('%Y-%m-%d %H:%M:%S')

                # ??????
                users = db.get_all_users()
                user_count = len(users)

                # ????????
                message = get_startup_notification(
                    startup_time=startup_time,
                    timezone=config.default_timezone,
                    user_count=user_count
                )

                # ????
                await application.bot.send_message(
                    chat_id=admin_chat_id,
                    text=message
                )

                logger.info(f"Startup notification sent to admin: {admin_chat_id}")

        except Exception as e:
            logger.error(f"Failed to send startup notification: {e}")

    # ????????????
    application.post_init = startup_tasks

    # 13. ???????
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    # 14. ?? Bot???????
    try:
        logger.info("Starting bot with long polling...")
        logger.info("=" * 60)
        logger.info("Bot is running. Press Ctrl+C to stop.")
        logger.info("=" * 60)

        # ?? run_polling ?????
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=False  # ????????
        )

    except Exception as e:
        logger.error(f"Bot runtime error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        if scheduler:
            scheduler.shutdown()
        logger.info("Bot stopped")


if __name__ == "__main__":
    main()
