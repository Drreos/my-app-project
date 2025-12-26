# 📊 Руководство по детальным логам ИИ

## ✅ ЧТО ДОБАВЛЕНО

### Детальные логи во всех ключевых местах:

#### 1. **ai_assistant.py** - Работа ИИ
```
📥 get_ai_response called - входящий запрос
🔨 Building system prompt - создание промпта
✅ System prompt built - промпт готов
📌 Added topic context - добавлен контекст
🌐 Requesting AI response from OpenAI - запрос к API
💬 AI response preview - предпросмотр ответа
✅ AI response received - ответ получен
❌ Error messages - ошибки
```

#### 2. **handlers.py** - Обработка сообщений
```
🤖 ========== AI AUTO-RESPONSE START ==========
🤖 User ID, Message, Language, Topic
🔍 Checking if human already responded
👨‍💼 Human responded status
📞 Calling ai_assistant.get_ai_response
📨 AI response received status
💬 AI response length and preview
📤 Sending AI response to user
✅ Message sent
🏷️  Marking AI responded flag
🎉 AI AUTO-RESPONSE SUCCESS
🤖 ========== AI AUTO-RESPONSE END ==========
```

#### 3. **Создание тикетов**
```
🎯 Creating AI response task
✅ AI response task created
```

## 📺 КАК СМОТРЕТЬ ЛОГИ

### Все логи в реальном времени:
```bash
docker-compose logs -f bot
```

### Только логи ИИ:
```bash
docker-compose logs -f bot | grep -E "🤖|📥|🌐|✅|❌|💬|🎉"
```

### Фильтр по конкретному пользователю:
```bash
docker-compose logs -f bot | grep "698471795"
```

### Последние 100 строк:
```bash
docker-compose logs --tail=100 bot
```

### Поиск ошибок:
```bash
docker-compose logs bot | grep -E "ERROR|Error|❌"
```

## 🧪 ТЕСТИРОВАНИЕ С ЛОГАМИ

### Шаг 1: Откройте логи
```bash
docker-compose logs -f bot
```

### Шаг 2: Напишите боту

Создайте новый тикет или напишите сообщение.

### Шаг 3: Смотрите детальные логи

Вы увидите **каждый шаг** работы ИИ:

```
🤖 ========== AI AUTO-RESPONSE START ==========
🤖 User ID: 698471795
🤖 Message: Как пополнить баланс?
🤖 Language: ru
🤖 Topic: balance
🤖 AI_ENABLED: True
🤖 AI_AUTO_RESPOND: True
🔍 Checking if human already responded to user 698471795...
🔍 Human responded: False
📞 Calling ai_assistant.get_ai_response...
📥 get_ai_response called: message='Как пополнить баланс?', lang=ru
🔨 Building system prompt for lang=ru...
✅ System prompt built, length=2543
📌 Added topic context: 💰 Баланс
🌐 Requesting AI response from OpenAI (model=gpt-4o-mini)...
📝 User message: Как пополнить баланс?
✅ AI response received! Length=456
💬 AI response preview: Чтобы пополнить баланс, перейдите в раздел...
📨 AI response received: True
💬 AI response length: 456
💬 AI response preview: Чтобы пополнить баланс...
📤 Sending AI response to user 698471795...
✅ Message sent to user 698471795
🏷️  Marking AI responded for user 698471795...
✅ AI responded flag set
🎉 AI AUTO-RESPONSE SUCCESS for user 698471795
🤖 ========== AI AUTO-RESPONSE END ==========
```

## 🔍 ЧТО ОЗНАЧАЮТ ЛОГИ

### ✅ Успешная работа:
```
🤖 AI AUTO-RESPONSE START
🔍 Human responded: False ← Оператор не ответил, ИИ может работать
📞 Calling ai_assistant
🌐 Requesting AI response from OpenAI ← Запрос к API
✅ AI response received ← Ответ получен
📤 Sending AI response ← Отправка клиенту
🎉 SUCCESS ← Всё работает!
```

### 👨‍💼 Оператор уже ответил:
```
🤖 AI AUTO-RESPONSE START
🔍 Human responded: True ← Оператор ответил
👨‍💼 Human already responded, skipping AI ← ИИ не вмешивается
```

### ⚠️  AI отключен:
```
🤖 AI AUTO-RESPONSE START
⚠️  AI is disabled globally
```

### ❌ Ошибка API:
```
🌐 Requesting AI response from OpenAI
❌ Error in get_ai_response: ...
🔑 OpenAI Authentication failed ← Проверьте API ключ
```

## 📊 МОНИТОРИНГ В РЕАЛЬНОМ ВРЕМЕНИ

### Терминал 1 - Все логи:
```bash
docker-compose logs -f bot
```

### Терминал 2 - Только ИИ:
```bash
docker-compose logs -f bot | grep "🤖"
```

### Терминал 3 - Только ошибки:
```bash
docker-compose logs -f bot | grep "❌"
```

## 🎯 ПРИМЕРЫ КОМАНД

### Найти все успешные ответы ИИ:
```bash
docker-compose logs bot | grep "🎉 AI AUTO-RESPONSE SUCCESS"
```

### Найти когда оператор вмешался:
```bash
docker-compose logs bot | grep "👨‍💼 Human already responded"
```

### Посмотреть все вызовы ИИ:
```bash
docker-compose logs bot | grep "🤖 ========== AI AUTO-RESPONSE START"
```

### Найти ошибки OpenAI:
```bash
docker-compose logs bot | grep -A5 "Error in get_ai_response"
```

## 💡 TIPS

### 1. Цветные логи (если терминал поддерживает):
```bash
docker-compose logs -f bot | grep --color=always -E "✅|❌|🎉|⚠️"
```

### 2. Сохранить логи в файл:
```bash
docker-compose logs bot > bot_logs.txt
```

### 3. Следить за конкретным пользователем:
```bash
docker-compose logs -f bot | grep "User ID: 698471795"
```

### 4. Только важные события:
```bash
docker-compose logs -f bot | grep -E "START|SUCCESS|ERROR"
```

## 🎊 ГОТОВО!

Теперь вы видите **каждый шаг** работы ИИ!

**Просто откройте логи и напишите боту - увидите всё в деталях!** 📊✨

---

## 📞 Быстрый тест

```bash
# Откройте логи
docker-compose logs -f bot | grep "🤖"

# Напишите боту: "Как пополнить баланс?"
# Смотрите как ИИ обрабатывает запрос шаг за шагом!
```

