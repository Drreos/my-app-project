#!/usr/bin/env python3
"""
Скрипт для закрытия всех открытых тикетов
Использование: python close_all_tickets.py
"""

import asyncio
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from config import API_TOKEN, SUPPORT_CHAT_ID
from database import get_db_pool
from datetime import datetime

bot = Bot(token=API_TOKEN)

async def close_all_tickets():
    """Закрывает все открытые тикеты"""
    
    print("=" * 60)
    print("🔒 ЗАКРЫТИЕ ВСЕХ ОТКРЫТЫХ ТИКЕТОВ")
    print("=" * 60)
    print()
    
    # Подключаемся к БД
    print("📊 Подключение к базе данных...")
    try:
        pool = await get_db_pool()
        print("✅ Подключено к БД")
    except Exception as e:
        print(f"❌ Ошибка подключения к БД: {e}")
        return
    
    try:
        # Получаем все открытые тикеты
        print("\n🔍 Поиск открытых тикетов...")
        async with pool.acquire() as conn:
            tickets = await conn.fetch(
                "SELECT user_id, thread_id, topic, tech_thread_id FROM tickets WHERE status = 'open'"
            )
        
        if not tickets:
            print("✅ Нет открытых тикетов!")
            return
        
        print(f"📋 Найдено открытых тикетов: {len(tickets)}")
        print()
        
        closed_count = 0
        failed_count = 0
        
        for ticket in tickets:
            user_id = ticket['user_id']
            thread_id = ticket['thread_id']
            topic = ticket['topic']
            tech_thread_id = ticket['tech_thread_id']
            
            print(f"🎫 Закрытие тикета: user_id={user_id}, thread_id={thread_id}")
            
            try:
                # 1. Закрываем основной тикет в support chat
                if thread_id:
                    try:
                        # Меняем название на ЗАКРЫТО
                        topic_display = topic or "Вопрос"
                        new_name = f"🔒 ЗАКРЫТО: {topic_display} - id{user_id}"
                        
                        await bot.edit_forum_topic(
                            chat_id=SUPPORT_CHAT_ID,
                            message_thread_id=thread_id,
                            name=new_name
                        )
                        print(f"  ✏️  Название изменено на: {new_name}")
                    except TelegramAPIError as e:
                        if "TOPIC_NOT_MODIFIED" not in str(e) and "FORUM_TOPIC_CLOSED" not in str(e):
                            print(f"  ⚠️  Не удалось изменить название: {e}")
                    
                    try:
                        # Закрываем тему
                        await bot.close_forum_topic(
                            chat_id=SUPPORT_CHAT_ID,
                            message_thread_id=thread_id
                        )
                        print(f"  ✅ Основной тикет закрыт")
                    except TelegramAPIError as e:
                        if "FORUM_TOPIC_CLOSED" not in str(e):
                            print(f"  ⚠️  Не удалось закрыть тему: {e}")
                        else:
                            print(f"  ✅ Тема уже была закрыта")
                
                # 2. Закрываем технический тикет если есть
                if tech_thread_id:
                    try:
                        from config import TECH_SUPPORT_CHAT_ID
                        if TECH_SUPPORT_CHAT_ID:
                            tech_name = f"🔒 ТЕХ: {topic or 'Вопрос'} - id{user_id}"
                            await bot.edit_forum_topic(
                                chat_id=TECH_SUPPORT_CHAT_ID,
                                message_thread_id=tech_thread_id,
                                name=tech_name
                            )
                            await bot.close_forum_topic(
                                chat_id=TECH_SUPPORT_CHAT_ID,
                                message_thread_id=tech_thread_id
                            )
                            print(f"  ✅ Технический тикет закрыт")
                    except TelegramAPIError as e:
                        if "FORUM_TOPIC_CLOSED" not in str(e):
                            print(f"  ⚠️  Не удалось закрыть тех. тикет: {e}")
                
                # 3. Обновляем статус в БД
                async with pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE tickets SET status = 'closed', tech_thread_id = NULL WHERE user_id = $1",
                        user_id
                    )
                print(f"  ✅ Статус обновлён в БД")
                
                closed_count += 1
                print()
                
            except Exception as e:
                print(f"  ❌ Ошибка при закрытии тикета user_id={user_id}: {e}")
                failed_count += 1
                print()
                continue
        
        print("=" * 60)
        print("📊 РЕЗУЛЬТАТЫ:")
        print(f"  ✅ Успешно закрыто: {closed_count}")
        print(f"  ❌ Ошибок: {failed_count}")
        print(f"  📋 Всего обработано: {len(tickets)}")
        print("=" * 60)
        
    finally:
        await bot.session.close()
        print("\n🔌 Бот отключён")

if __name__ == "__main__":
    print("\n⚠️  ВНИМАНИЕ: Этот скрипт закроет ВСЕ открытые тикеты!")
    print("⚠️  Убедитесь что вы действительно хотите это сделать!")
    print()
    
    response = input("Продолжить? (yes/no): ").strip().lower()
    
    if response == "yes":
        print("\n🚀 Запуск...\n")
        asyncio.run(close_all_tickets())
        print("\n✅ Готово!\n")
    else:
        print("\n❌ Отменено пользователем\n")

