import logging
import asyncpg
from config import (
    POSTGRES_USER,
    POSTGRES_PASSWORD,
    POSTGRES_DB,
    POSTGRES_HOST,
    POSTGRES_PORT,
    SUPPORT_CHAT_ID,
    TECH_SUPPORT_CHAT_ID,
)

logger = logging.getLogger(__name__)

_pool = None


async def get_db_pool():
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            database=POSTGRES_DB,
            host=POSTGRES_HOST,
            port=POSTGRES_PORT
        )
    return _pool


async def init_db():
    logger.info("Initializing database...")
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                user_id BIGINT PRIMARY KEY,
                thread_id BIGINT,
                tech_thread_id BIGINT,
                status TEXT,
                topic TEXT,
                last_message_time TIMESTAMP,
                last_client_message_time TIMESTAMP,
                last_support_message_time TIMESTAMP,
                support_reminder_sent BOOLEAN DEFAULT FALSE,
                tech_reminder_sent BOOLEAN DEFAULT FALSE,
                close_reminder_sent BOOLEAN DEFAULT FALSE,
                human_responded BOOLEAN DEFAULT FALSE,
                ai_responded BOOLEAN DEFAULT FALSE,
                ai_response_count INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                lang TEXT
            );
            CREATE TABLE IF NOT EXISTS ticket_messages (
                user_id BIGINT,
                message_id BIGINT,
                chat_id BIGINT,
                thread_id BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, message_id)
            );
            ALTER TABLE tickets ADD COLUMN IF NOT EXISTS tech_thread_id BIGINT;
            ALTER TABLE tickets ADD COLUMN IF NOT EXISTS support_reminder_sent BOOLEAN DEFAULT FALSE;
            ALTER TABLE tickets ADD COLUMN IF NOT EXISTS tech_reminder_sent BOOLEAN DEFAULT FALSE;
            ALTER TABLE tickets ADD COLUMN IF NOT EXISTS last_client_message_time TIMESTAMP;
            ALTER TABLE tickets ADD COLUMN IF NOT EXISTS last_support_message_time TIMESTAMP;
            ALTER TABLE tickets ADD COLUMN IF NOT EXISTS close_reminder_sent BOOLEAN DEFAULT FALSE;
            ALTER TABLE tickets ADD COLUMN IF NOT EXISTS human_responded BOOLEAN DEFAULT FALSE;
            ALTER TABLE tickets ADD COLUMN IF NOT EXISTS ai_responded BOOLEAN DEFAULT FALSE;
            ALTER TABLE tickets ADD COLUMN IF NOT EXISTS ai_response_count INTEGER DEFAULT 0;
            ALTER TABLE ticket_messages ADD COLUMN IF NOT EXISTS thread_id BIGINT;
        """)
    logger.info("Database initialized")


async def get_ticket(user_id: int):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        ticket = await conn.fetchrow(
            """
            SELECT thread_id, status, topic, tech_thread_id, human_responded, ai_responded
            FROM tickets
            WHERE user_id = $1
            ORDER BY last_message_time DESC
            LIMIT 1
            """,
            user_id
        )
        if ticket:
            return (
                ticket["thread_id"], 
                ticket["status"], 
                ticket["topic"], 
                ticket["tech_thread_id"],
                ticket.get("human_responded", False),
                ticket.get("ai_responded", False)
            )
        return None, None, None, None, False, False


async def get_user_by_thread(thread_id: int):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        ticket = await conn.fetchrow(
            "SELECT user_id FROM tickets WHERE thread_id = $1", thread_id
        )
        return ticket["user_id"] if ticket else None


async def update_ticket_client_activity(user_id: int):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE tickets
            SET last_message_time = CURRENT_TIMESTAMP,
                last_client_message_time = CURRENT_TIMESTAMP,
                support_reminder_sent = FALSE,
                tech_reminder_sent = FALSE,
                close_reminder_sent = FALSE
            WHERE user_id = $1
            """,
            user_id
        )


async def update_ticket_support_activity(user_id: int):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE tickets
            SET last_message_time = CURRENT_TIMESTAMP,
                last_support_message_time = CURRENT_TIMESTAMP,
                close_reminder_sent = FALSE,
                human_responded = TRUE
            WHERE user_id = $1
            """,
            user_id
        )


async def update_user_language(user_id: int, lang: str):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (user_id, lang) VALUES ($1, $2) ON CONFLICT (user_id) DO UPDATE SET lang = $2",
            user_id, lang
        )


async def get_user_language(user_id: int):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        user = await conn.fetchrow("SELECT lang FROM users WHERE user_id = $1", user_id)
        return user["lang"] if user else None


async def close_ticket(bot, user_id: int, thread_id: int, topic: str):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE tickets SET status = 'closed' WHERE user_id = $1", user_id
        )

    await bot.close_forum_topic(
        chat_id=SUPPORT_CHAT_ID,
        message_thread_id=thread_id
    )

    async with pool.acquire() as conn:
        tech_thread_id = await conn.fetchval(
            "SELECT tech_thread_id FROM tickets WHERE user_id = $1",
            user_id
        )

    if tech_thread_id:
        try:
            await bot.close_forum_topic(
                chat_id=TECH_SUPPORT_CHAT_ID,
                message_thread_id=tech_thread_id
            )
        except Exception as exc:
            logger.error(f"Failed to close tech topic for user {user_id}: {exc}")


async def update_ticket_tech_thread(user_id: int, tech_thread_id: int):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE tickets
            SET tech_thread_id = $2,
                tech_reminder_sent = FALSE
            WHERE user_id = $1
            """,
            user_id,
            tech_thread_id
        )


async def save_ticket_message(user_id: int, message_id: int, chat_id: int, thread_id: int | None):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO ticket_messages (user_id, message_id, chat_id, thread_id)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (user_id, message_id) DO NOTHING
            """,
            user_id,
            message_id,
            chat_id,
            thread_id
        )


async def get_ticket_messages(user_id: int, thread_id: int):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        records = await conn.fetch(
            """
            SELECT message_id
            FROM ticket_messages
            WHERE user_id = $1 AND chat_id = $2 AND (thread_id = $3 OR $3 IS NULL)
            ORDER BY created_at ASC
            """,
            user_id,
            SUPPORT_CHAT_ID,
            thread_id
        )
        return [record["message_id"] for record in records]


async def get_open_tickets_for_reminders():
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        records = await conn.fetch(
            """
            SELECT user_id,
                   thread_id,
                   tech_thread_id,
                   support_reminder_sent,
                   tech_reminder_sent,
                   close_reminder_sent,
                   last_client_message_time,
                   last_support_message_time
            FROM tickets
            WHERE status = 'open'
            """,
        )
        return records


async def mark_support_reminder_sent(user_id: int):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE tickets SET support_reminder_sent = TRUE WHERE user_id = $1",
            user_id
        )


async def mark_tech_reminder_sent(user_id: int):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE tickets SET tech_reminder_sent = TRUE WHERE user_id = $1",
            user_id
        )


async def mark_close_reminder_sent(user_id: int):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE tickets SET close_reminder_sent = TRUE WHERE user_id = $1",
            user_id
        )


async def mark_ai_responded(user_id: int):
    """Отмечает, что ИИ ответил на тикет и увеличивает счетчик"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE tickets 
            SET ai_responded = TRUE, 
                ai_response_count = ai_response_count + 1 
            WHERE user_id = $1
            """,
            user_id
        )


async def check_if_human_responded(user_id: int) -> bool:
    """Проверяет, ответил ли оператор (человек) на тикет"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchval(
            "SELECT human_responded FROM tickets WHERE user_id = $1",
            user_id
        )
        return result if result is not None else False


async def get_ai_response_count(user_id: int) -> int:
    """Получает количество ответов ИИ для пользователя"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchval(
            "SELECT ai_response_count FROM tickets WHERE user_id = $1",
            user_id
        )
        return result if result is not None else 0


async def mark_human_responded(user_id: int):
    """Отмечает, что человек (оператор) ответил на тикет"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE tickets SET human_responded = TRUE WHERE user_id = $1",
            user_id
        )


async def auto_close_ticket(user_id: int):
    """Автоматически закрывает тикет (без закрытия форума)"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE tickets SET status = 'closed' WHERE user_id = $1",
            user_id
        )
        logger.info(f"🔒 Ticket auto-closed for user {user_id} due to inactivity")
