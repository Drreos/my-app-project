import asyncio
import logging
from contextlib import suppress
from datetime import datetime, timezone, timedelta

from config import API_TOKEN, SUPPORT_CHAT_ID, TECH_SUPPORT_CHAT_ID, AUTO_CLOSE_ENABLED, AUTO_CLOSE_HOURS
from database import (
    init_db,
    get_open_tickets_for_reminders,
    mark_support_reminder_sent,
    mark_tech_reminder_sent,
    mark_close_reminder_sent,
    save_ticket_message,
    auto_close_ticket,
)
from handlers import dp, bot, setup_bot_commands

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

REMINDER_SUPPORT_TEXT = (
    "⏰ <b>Напоминание:</b> тикет открыт более часа без активности. "
    "Пожалуйста, проверьте и ответьте пользователю."
)

REMINDER_TECH_TEXT = (
    "⏰ <b>Напоминание:</b> технический тикет открыт более часа. "
    "Прошу обновить статус или дать ответ."
)

CLOSE_REMINDER_TEXT = (
    "📌 <b>Напоминание:</b> прошло 8 часов с последнего ответа поддержки. "
    "Если вопрос решён, пожалуйста, закройте тикет."
)

AUTO_CLOSE_SUPPORT_TEXT = (
    "🔒 <b>Тикет автоматически закрыт:</b> клиент не отвечал более {hours} час(а/ов). "
    "Если потребуется, клиент может создать новый тикет."
)

# ToDO: Стоит задача создать inlinekeyboards  в чате поддрежки при созалние кнопки для технического отдала Преоритетный тикер, Проблема вывода, Другие проблемы, Не пришел депозит
# ToDO: Тип будет покзаываться в название темы тикера!
async def main():
    logger.info("Starting bot...")
    if not API_TOKEN:
        logger.error("API_TOKEN is missing in .env")
        raise ValueError("API_TOKEN is missing")

    # Clear webhook and updates
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Webhook and updates cleared")

    # Initialize database
    await init_db()
    logger.info("Database initialized")

    # Set bot commands
    await setup_bot_commands()
    logger.info("Bot commands set")

    reminder_task = asyncio.create_task(reminder_worker())

    # Start polling
    logger.info("Starting polling...")
    try:
        await dp.start_polling(bot, skip_updates=True)
    finally:
        reminder_task.cancel()
        with suppress(asyncio.CancelledError):
            await reminder_task
        logger.info("Reminder task stopped")


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


async def reminder_worker(
    interval_minutes: int = 5,
    client_overdue_minutes: int = 60,
    close_overdue_hours: int = 8
):
    logger.info("Reminder worker started")
    logger.info(f"⚙️  Auto-close enabled: {AUTO_CLOSE_ENABLED}, timeout: {AUTO_CLOSE_HOURS} hour(s)")
    sleep_seconds = max(interval_minutes, 1) * 60
    while True:
        try:
            tickets = await get_open_tickets_for_reminders()
            now = datetime.now(timezone.utc)
            client_delta = timedelta(minutes=client_overdue_minutes)
            close_delta = timedelta(hours=close_overdue_hours)
            auto_close_delta = timedelta(hours=AUTO_CLOSE_HOURS)

            for ticket in tickets:
                user_id = ticket["user_id"]
                thread_id = ticket["thread_id"]
                tech_thread_id = ticket["tech_thread_id"]
                support_sent = ticket["support_reminder_sent"]
                tech_sent = ticket["tech_reminder_sent"]
                close_sent = ticket["close_reminder_sent"]
                last_client = _as_utc(ticket["last_client_message_time"])
                last_support = _as_utc(ticket["last_support_message_time"])

                if (
                    thread_id
                    and last_client
                    and not support_sent
                    and now - last_client >= client_delta
                ):
                    try:
                        message = await bot.send_message(
                            chat_id=SUPPORT_CHAT_ID,
                            text=REMINDER_SUPPORT_TEXT,
                            message_thread_id=thread_id,
                            parse_mode="HTML"
                        )
                        await save_ticket_message(user_id, message.message_id, SUPPORT_CHAT_ID, thread_id)
                        await mark_support_reminder_sent(user_id)
                    except Exception as exc:
                        logger.error(f"Failed to send support reminder for user {user_id}: {exc}")

                if (
                    tech_thread_id
                    and TECH_SUPPORT_CHAT_ID
                    and last_client
                    and not tech_sent
                    and now - last_client >= client_delta
                ):
                    try:
                        await bot.send_message(
                            chat_id=TECH_SUPPORT_CHAT_ID,
                            text=REMINDER_TECH_TEXT,
                            message_thread_id=tech_thread_id,
                            parse_mode="HTML"
                        )
                        await mark_tech_reminder_sent(user_id)
                    except Exception as exc:
                        logger.error(f"Failed to send tech reminder for user {user_id}: {exc}")

                if (
                    thread_id
                    and last_support
                    and not close_sent
                    and now - last_support >= close_delta
                ):
                    try:
                        message = await bot.send_message(
                            chat_id=SUPPORT_CHAT_ID,
                            text=CLOSE_REMINDER_TEXT,
                            message_thread_id=thread_id,
                            parse_mode="HTML"
                        )
                        await save_ticket_message(user_id, message.message_id, SUPPORT_CHAT_ID, thread_id)
                        await mark_close_reminder_sent(user_id)
                    except Exception as exc:
                        logger.error(f"Failed to send close reminder for user {user_id}: {exc}")
                
                # Автоматическое закрытие тикета если клиент не отвечает
                if (
                    AUTO_CLOSE_ENABLED
                    and thread_id
                    and last_support  # Поддержка ответила
                    and (not last_client or last_support > last_client)  # Последнее сообщение от поддержки
                    and now - last_support >= auto_close_delta  # Прошло N часов
                ):
                    try:
                        # Закрываем тикет в БД (клиент НЕ получает уведомления - тихое закрытие)
                        await auto_close_ticket(user_id)
                        
                        # Пытаемся отправить уведомление в чат поддержки
                        try:
                            message = await bot.send_message(
                                chat_id=SUPPORT_CHAT_ID,
                                text=AUTO_CLOSE_SUPPORT_TEXT.format(hours=AUTO_CLOSE_HOURS),
                                message_thread_id=thread_id,
                                parse_mode="HTML"
                            )
                            await save_ticket_message(user_id, message.message_id, SUPPORT_CHAT_ID, thread_id)
                        except Exception as exc:
                            # Тема форума не найдена - значит уже закрыта вручную, это нормально
                            if "message thread not found" in str(exc).lower():
                                logger.debug(f"Thread {thread_id} not found for user {user_id} (already closed manually)")
                            else:
                                logger.warning(f"Failed to send auto-close message for user {user_id}: {exc}")
                        
                        # Пытаемся закрыть тему форума
                        try:
                            await bot.close_forum_topic(
                                chat_id=SUPPORT_CHAT_ID,
                                message_thread_id=thread_id
                            )
                            logger.info(f"✅ Ticket auto-closed successfully for user {user_id}")
                        except Exception as exc:
                            # Тема форума не найдена - значит уже закрыта, это нормально
                            if "message thread not found" in str(exc).lower():
                                logger.debug(f"Thread {thread_id} already closed for user {user_id}")
                            else:
                                logger.warning(f"Failed to close forum topic for user {user_id}: {exc}")
                            
                    except Exception as exc:
                        logger.error(f"Failed to auto-close ticket for user {user_id}: {exc}")

        except asyncio.CancelledError:
            logger.info("Reminder worker cancelled")
            raise
        except Exception as exc:
            logger.error(f"Reminder worker error: {exc}", exc_info=True)

        await asyncio.sleep(sleep_seconds)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Error: {e}")
