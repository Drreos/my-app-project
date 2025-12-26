# Исправление ошибок устаревших Callback Query

## Проблема

После перезапуска бота возникали ошибки при обработке устаревших callback query (нажатия кнопок):

```
TelegramBadRequest: Telegram server says - Bad Request: query is too old and response timeout expired or query ID is invalid
```

Ошибка возникала в функции `close_ticket_button` и других обработчиках callback query, когда бот пытался отправить ответ (`callback.answer()`) на устаревшие запросы.

## Причина

Telegram API имеет таймаут для callback query. После перезапуска бота, он пытался обработать старые callback query из очереди, но эти запросы уже истекли. При попытке отправить ответ на такой запрос, Telegram API возвращал ошибку.

Проблема усугублялась тем, что в блоке обработки ошибок (`except`) также был вызов `callback.answer()`, который тоже падал с той же ошибкой, создавая цепочку исключений.

## Решение

Создана вспомогательная функция `safe_callback_answer()` в файле `handlers.py`:

```python
async def safe_callback_answer(callback: CallbackQuery, text: str = "", show_alert: bool = False) -> bool:
    """
    Безопасно отвечает на callback query, игнорируя ошибки устаревших запросов.
    Возвращает True если ответ был отправлен успешно, False в противном случае.
    """
    try:
        await callback.answer(text, show_alert=show_alert)
        return True
    except TelegramBadRequest as exc:
        error_msg = str(exc).lower()
        if "query is too old" in error_msg or "query id is invalid" in error_msg:
            logger.info(f"Ignoring old/invalid callback query: {exc}")
            return False
        else:
            logger.error(f"Callback answer failed: {exc}")
            raise
    except Exception as exc:
        logger.error(f"Unexpected error in callback answer: {exc}")
        raise
```

### Изменения в коде

Заменены все вызовы `callback.answer()` на `safe_callback_answer()` в следующих функциях:

1. **close_ticket_button** - закрытие тикета пользователем
2. **prompt_tech_ticket** - создание технического тикета
3. **confirm_tech_ticket** - подтверждение технического тикета
4. **cancel_tech_ticket** - отмена создания тикета
5. **close_tech_ticket** - закрытие технического тикета
6. И других обработчиках callback query

## Результат

- ✅ Бот больше не падает при обработке устаревших callback query
- ✅ Ошибки "query is too old" корректно игнорируются
- ✅ Логируются информационные сообщения о пропущенных устаревших запросах
- ✅ Другие типы ошибок обрабатываются как раньше
- ✅ Бот стабильно работает после перезапусков

## Тестирование

После применения изменений:
1. Бот успешно перезапустился
2. База данных инициализирована
3. Polling запущен без ошибок
4. Auto-close функционал работает корректно

## Дата исправления

26 декабря 2025

