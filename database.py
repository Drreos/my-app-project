import logging
import asyncpg
from config import POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, POSTGRES_HOST, POSTGRES_PORT, SUPPORT_CHAT_ID, TOPICS

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
                status TEXT,
                topic TEXT,
                last_message_time TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                lang TEXT
            );
        """)
    logger.info("Database initialized")


async def get_ticket(user_id: int):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        ticket = await conn.fetchrow(
            "SELECT thread_id, status, topic FROM tickets WHERE user_id = $1 ORDER BY last_message_time DESC LIMIT 1",
            user_id
        )
        if ticket:
            return ticket["thread_id"], ticket["status"], ticket["topic"]
        return None, None, None


async def get_user_by_thread(thread_id: int):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        ticket = await conn.fetchrow(
            "SELECT user_id FROM tickets WHERE thread_id = $1", thread_id
        )
        return ticket["user_id"] if ticket else None


async def update_ticket_time(user_id: int):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE tickets SET last_message_time = CURRENT_TIMESTAMP WHERE user_id = $1",
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

    forum_topic = await bot.get_forum_topic(chat_id=SUPPORT_CHAT_ID, message_thread_id=thread_id)
    current_name = forum_topic.name
    if not current_name.startswith("[CLOSED] "):
        new_name = f"[CLOSED] {current_name}"
        await bot.edit_forum_topic(
            chat_id=SUPPORT_CHAT_ID,
            message_thread_id=thread_id,
            name=new_name
        )

    await bot.close_forum_topic(chat_id=SUPPORT_CHAT_ID, message_thread_id=thread_id)