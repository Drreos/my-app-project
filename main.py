import asyncio
import logging
from aiogram import Bot
from config import API_TOKEN
from database import init_db
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

    # Start polling
    logger.info("Starting polling...")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Error: {e}")