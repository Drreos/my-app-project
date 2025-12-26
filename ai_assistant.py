import logging
from openai import AsyncOpenAI
from typing import Optional, Dict, Any
from config import (
    AI_API_KEY,
    AI_MODEL,
    AI_ENABLED,
    AI_MAX_TOKENS,
    AI_TEMPERATURE,
    FAQ_QUESTIONS,
    TRANSLATIONS,
)

logger = logging.getLogger(__name__)


def ai_wants_to_escalate(ai_response: str) -> bool:
    """
    Проверяет, хочет ли AI передать вопрос оператору.
    Если AI написал про передачу/уточнение - возвращает True.
    """
    response_lower = ai_response.lower()
    
    escalation_phrases = [
        "передаю",
        "передам",
        "уточню",
        "уточн",
        "коллег",
        "коллеге",
        "специалист",
        "оператор",
        "детальн",
        "рассмотр",
        "занимаемся",
        "изучением",
        "вернёмся",
        "решением"
    ]
    
    for phrase in escalation_phrases:
        if phrase in response_lower:
            logger.info(f"🔄 AI wants to escalate: detected '{phrase}' in response")
            return True
    
    return False


def detect_strong_emotion(message: str) -> bool:
    """
    Определяет наличие сильных негативных эмоций, мата или технических проблем.
    Если обнаружено - пользователя лучше передать оператору.
    """
    message_lower = message.lower()
    
    # Мат и грубая лексика
    profanity = [
        "блять", "бля", "блядь", "ебать", "ебал", "хуй", "пизд", "сука", 
        "гавно", "говно", "дерьм", "fuck", "shit", "damn", "asshole"
    ]
    
    # Сильные негативные эмоции
    strong_negative = [
        "ненавижу", "отвратительн", "ужасн", "кошмар", "отстой",
        "мошенник", "развод", "обман", "украл", "жалоб", "суд",
        "возмущён", "возмущен", "жду уже", "часов", "дней", "недел",
        "бред", "дебил"
    ]
    
    # Технические проблемы требующие оператора (ошибки из приложения)
    technical_issues = [
        "обратитесь в поддержку",
        "обратитесь в службу",
        "обратитесь к поддержке",
        "свяжитесь с поддержкой",
        "ошибка",
        "не могу вывести",
        "не могу поставить на вывод",
        "не выводится",
        "не работает вывод"
    ]
    
    # Вопросы про ожидание ответа оператора (пользователь хочет говорить с человеком)
    waiting_questions = [
        "как скоро проверят",
        "когда проверят",
        "сколько ждать",
        "когда ответ",
        "когда решат",
        "долго ждать",
        "когда рассмотрят"
    ]
    
    # Проверяем мат
    for word in profanity:
        if word in message_lower:
            logger.info(f"🔥 Обнаружен мат в сообщении: '{word}'")
            return True
    
    # Проверяем технические проблемы (требуют оператора)
    for phrase in technical_issues:
        if phrase in message_lower:
            logger.info(f"⚠️ Обнаружена техническая проблема: '{phrase}'")
            return True
    
    # Проверяем вопросы про ожидание (пользователь хочет человека)
    for phrase in waiting_questions:
        if phrase in message_lower:
            logger.info(f"⏰ Пользователь спрашивает про ожидание: '{phrase}'")
            return True
    
    # Проверяем сильные негативные эмоции (минимум 2 упоминания)
    negative_count = sum(1 for word in strong_negative if word in message_lower)
    if negative_count >= 2:
        logger.info(f"😡 Обнаружена сильная негативная эмоция (count={negative_count})")
        return True
    
    # Проверка на повторяющиеся сообщения (признак раздражения)
    if "уже" in message_lower and any(time_word in message_lower for time_word in ["час", "день", "недел", "сутки"]):
        logger.info(f"⏰ Пользователь долго ждет решения")
        return True
    
    return False


class AIAssistant:
    """ИИ-ассистент для автоматических ответов клиентам"""
    
    def __init__(self):
        print(f"[DEBUG] Initializing AI Assistant... AI_ENABLED={AI_ENABLED}, API_KEY={'SET' if AI_API_KEY else 'EMPTY'}")
        self.enabled = AI_ENABLED
        self.client = None
        if self.enabled and AI_API_KEY:
            self.client = AsyncOpenAI(api_key=AI_API_KEY)
            logger.info(f"✅ AI Assistant initialized with model: {AI_MODEL}")
            print(f"[DEBUG] AI Assistant initialized successfully with model: {AI_MODEL}")
        else:
            logger.warning(f"⚠️  AI Assistant is disabled (enabled={AI_ENABLED}, api_key={'set' if AI_API_KEY else 'empty'})")
            print(f"[DEBUG] AI Assistant NOT initialized: enabled={AI_ENABLED}, api_key={'set' if AI_API_KEY else 'empty'}")
    
    def _build_system_prompt(self, lang: str = "ru") -> str:
        """Создает системный промпт с базой знаний"""
        
        # Базовая инструкция
        system_prompt = f"""Ты - оператор службы поддержки Majestic Game Bot. Общайся как живой человек.

КРИТИЧЕСКИ ВАЖНО - ЗАПРЕЩЕННЫЕ ФРАЗЫ:
🚫 "Я здесь, чтобы помочь"
🚫 "Постараюсь помочь"
🚫 "Уточните пожалуйста"
🚫 "Какая именно ошибка"
🚫 "Напишите подробнее"
🚫 "Какой именно подарок"
🚫 НЕ задавай уточняющих вопросов если проблема ОЧЕВИДНА!

ТВОЯ РОЛЬ:
- Ты ПЕРВАЯ линия поддержки
- Отвечай ТОЛЬКО на простые вопросы из FAQ
- Пиши максимально коротко (1-2 предложения)
- Язык: {lang}

ПРАВИЛА ОТВЕТОВ:
1. Простой вопрос из FAQ → дай короткий ответ
2. Вопросы "как скоро", "когда проверят" → объясни что заявка уже в обработке
3. НЕ задавай уточняющих вопросов - отвечай по сути!
4. Эмодзи: НЕ используй совсем
5. Если не знаешь ответа → напиши: "Занимаемся изучением вашей проблемы. Скоро вернёмся с решением."

БАЗА ЗНАНИЙ:
"""
        
        # Добавляем FAQ в промпт
        for topic, questions in FAQ_QUESTIONS.items():
            if lang in questions:
                topic_name = TRANSLATIONS[lang]["topics"].get(topic, topic)
                system_prompt += f"\n\n📌 {topic_name.upper()}:\n"
                
                lang_questions = questions[lang]
                for i in range(1, 10):
                    q_key = f"question{i}"
                    a_key = f"answer{i}"
                    if q_key in lang_questions and a_key in lang_questions:
                        question = lang_questions[q_key]
                        answer = lang_questions[a_key]
                        if answer:  # Только если есть ответ
                            system_prompt += f"\nВопрос: {question}\nОтвет: {answer}\n"
        
        system_prompt += """

ПРИМЕРЫ ОТВЕТОВ:
- Пользователь: "Как пополнить?" → Дай инструкцию из базы знаний
- Пользователь: "Не пришли деньги" → "Транзакции могут занять до 15 минут. Проверьте позже."
- Пользователь: "Как скоро проверят мой вопрос?" → "Ваше обращение уже в обработке. Время ответа зависит от загрузки поддержки."
- Пользователь: "its wrong me have 2 accounts only" → "Занимаемся изучением вашей проблемы. Скоро вернёмся с решением."

ВАЖНО: Когда пишешь про изучение проблемы - система реально передаст вопрос оператору!
"""
        
        return system_prompt
    
    async def get_ai_response(
        self,
        user_message: str,
        lang: str = "ru",
        context: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Получает ответ от ИИ на вопрос пользователя
        
        Args:
            user_message: сообщение пользователя
            lang: язык пользователя
            context: дополнительный контекст (тема, история и т.д.)
        
        Returns:
            Ответ ИИ или None в случае ошибки
        """
        logger.info(f"📥 get_ai_response called: message='{user_message[:50]}...', lang={lang}, context={context}")
        
        if not self.enabled:
            logger.warning("⚠️  AI is disabled, skipping response generation")
            return None
        
        if not AI_API_KEY:
            logger.error("❌ AI API key is not configured")
            return None
        
        if not self.client:
            logger.error("❌ OpenAI client is not initialized")
            return None
        
        try:
            logger.info(f"🔨 Building system prompt for lang={lang}...")
            system_prompt = self._build_system_prompt(lang)
            logger.info(f"✅ System prompt built, length={len(system_prompt)}")
            
            # Добавляем контекст если есть
            if context:
                topic = context.get("topic")
                if topic:
                    topic_name = TRANSLATIONS[lang]["topics"].get(topic, topic)
                    system_prompt += f"\n\nТекущая тема обращения: {topic_name}"
                    logger.info(f"📌 Added topic context: {topic_name}")
            
            # Создаем запрос к API
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ]
            
            logger.info(f"🌐 Requesting AI response from OpenAI (model={AI_MODEL})...")
            logger.info(f"📝 User message: {user_message}")
            
            response = await self.client.chat.completions.create(
                model=AI_MODEL,
                messages=messages,
                max_tokens=AI_MAX_TOKENS,
                temperature=AI_TEMPERATURE,
            )
            
            ai_message = response.choices[0].message.content.strip()
            logger.info(f"✅ AI response received! Length={len(ai_message)}")
            logger.info(f"💬 AI response preview: {ai_message[:100]}...")
            
            return ai_message
        
        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ Error in get_ai_response: {e}", exc_info=True)
            if "authentication" in error_msg.lower() or "api_key" in error_msg.lower():
                logger.error("🔑 OpenAI Authentication failed - check your API key")
            elif "rate" in error_msg.lower() or "limit" in error_msg.lower():
                logger.warning("⏱️  OpenAI rate limit exceeded")
            else:
                logger.error(f"💥 OpenAI API error: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in AI response generation: {e}", exc_info=True)
            return None
    
    def should_escalate_to_human(self, ai_response: str) -> bool:
        """
        Определяет, нужно ли передать вопрос оператору
        
        Args:
            ai_response: ответ ИИ
        
        Returns:
            True если нужно передать оператору
        """
        escalation_keywords = [
            "оператор",
            "специалист",
            "поддержк",
            "свяж",
            "не могу помочь",
            "не уверен",
            "рекомендую обратиться",
        ]
        
        ai_response_lower = ai_response.lower()
        return any(keyword in ai_response_lower for keyword in escalation_keywords)
    
    async def analyze_sentiment(self, user_message: str, lang: str = "ru") -> str:
        """
        Анализирует тональность сообщения пользователя
        
        Args:
            user_message: сообщение пользователя
            lang: язык
        
        Returns:
            Тональность: "positive", "neutral", "negative"
        """
        if not self.enabled or not AI_API_KEY or not self.client:
            return "neutral"
        
        try:
            prompt = f"""Проанализируй тональность следующего сообщения пользователя.
Ответь одним словом: positive, neutral или negative.

Сообщение: {user_message}

Тональность:"""
            
            response = await self.client.chat.completions.create(
                model=AI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=10,
                temperature=0.3,
            )
            
            sentiment = response.choices[0].message.content.strip().lower()
            if sentiment in ["positive", "neutral", "negative"]:
                return sentiment
            return "neutral"
        
        except Exception as e:
            logger.error(f"Error analyzing sentiment: {e}")
            return "neutral"
    
    async def generate_thread_title(self, user_message: str, topic: str, lang: str = "ru") -> str:
        """
        Генерирует краткое название темы на основе сообщения пользователя
        
        Args:
            user_message: первое сообщение пользователя
            topic: тема тикета
            lang: язык
            
        Returns:
            Краткое название с эмодзи (максимум 50 символов)
        """
        if not self.enabled or not AI_API_KEY or not self.client:
            # Fallback названия с эмодзи
            emoji_map = {
                "balance": "💰",
                "withdrop": "🎁",
                "bugs": "🐛",
                "donate": "💎",
                "cooperation": "🤝"
            }
            emoji = emoji_map.get(topic, "📝")
            return f"{emoji} Новый вопрос"
        
        try:
            prompt = f"""Создай ОЧЕНЬ КРАТКОЕ название для тикета поддержки (максимум 5-6 слов) на основе вопроса клиента.
Начни с подходящего эмодзи.
Язык: {lang}

Примеры:
- "не могу пополнить баланс" → "💰 Проблема с пополнением"
- "как вывести подарки" → "🎁 Вопрос про вывод"
- "ошибка при входе" → "🐛 Ошибка входа"
- "хочу стать партнером" → "🤝 Партнерство"

Вопрос клиента: {user_message[:200]}

Название (максимум 50 символов):"""
            
            response = await self.client.chat.completions.create(
                model=AI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=30,
                temperature=0.7,
            )
            
            title = response.choices[0].message.content.strip()
            
            # Ограничиваем длину
            if len(title) > 50:
                title = title[:47] + "..."
            
            logger.info(f"✨ Generated thread title: '{title}'")
            return title
        
        except Exception as e:
            logger.error(f"Error generating thread title: {e}")
            # Fallback
            emoji_map = {
                "balance": "💰",
                "withdrop": "🎁",
                "bugs": "🐛",
                "donate": "💎",
                "cooperation": "🤝"
            }
            emoji = emoji_map.get(topic, "📝")
            return f"{emoji} Новый вопрос"


# Глобальный экземпляр ассистента
ai_assistant = AIAssistant()

