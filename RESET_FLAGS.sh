#!/bin/bash
# Скрипт для сброса флагов ИИ/оператора для пользователя

if [ -z "$1" ]; then
    echo "❌ Использование: ./RESET_FLAGS.sh USER_ID"
    echo "Пример: ./RESET_FLAGS.sh 698471795"
    exit 1
fi

USER_ID=$1

echo "🔄 Сбрасываю флаги для пользователя $USER_ID..."

docker-compose exec bot python -c "
import asyncio
from database import get_db_pool

async def reset():
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute('UPDATE tickets SET human_responded = FALSE, ai_responded = FALSE WHERE user_id = $USER_ID')
        
        ticket = await conn.fetchrow('SELECT status, human_responded, ai_responded FROM tickets WHERE user_id = $USER_ID')
        if ticket:
            print(f'✅ Флаги сброшены для пользователя $USER_ID')
            print(f'Status: {ticket[\"status\"]}')
            print(f'Human responded: {ticket[\"human_responded\"]}')
            print(f'AI responded: {ticket[\"ai_responded\"]}')
        else:
            print(f'❌ Тикет не найден для пользователя $USER_ID')

asyncio.run(reset())
"

echo ""
echo "✅ Готово! Теперь ИИ будет отвечать этому пользователю."
echo "📝 Пользователь должен написать НОВОЕ сообщение."

