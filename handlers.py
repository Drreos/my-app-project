import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeChat
from aiogram.types import Sticker, Animation
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from typing import Optional  # Добавлен импорт для extract_reply_markup
from config import API_TOKEN, SUPPORT_CHAT_ID, TRANSLATIONS, DEFAULT_LANGUAGE, MEDIA_GROUP_TIMEOUT, FAQ_QUESTIONS, TOPICS
from database import get_ticket, get_user_by_thread, update_ticket_time, close_ticket, get_db_pool, update_user_language, get_user_language
from utils import MessageToHtmlConverter, generate_ticket_id
import asyncio

logger = logging.getLogger(__name__)

router = Router()
bot = Bot(token=API_TOKEN)
dp = Dispatcher()
dp.include_router(router)
user_languages = {}
ticket_creation_locks = {}

class TicketStates(StatesGroup):
    waiting_for_topic = State()
    waiting_for_subtopic = State()
    waiting_for_faq_answer = State()
    waiting_for_description = State()
    active_ticket = State()

async def setup_bot_commands():
    for lang in TRANSLATIONS.keys():
        commands = [
            BotCommand(command="/start", description=TRANSLATIONS[lang].get("command_start", "Start the bot")),
            BotCommand(command="/lang", description=TRANSLATIONS[lang].get("command_lang", "Change language")),
        ]
        await bot.set_my_commands(
            commands=commands,
            scope=BotCommandScopeAllPrivateChats(),
            language_code=lang
        )
        logger.debug(f"Set bot commands for language: {lang}")

    default_commands = [
        BotCommand(command="/start", description=TRANSLATIONS[DEFAULT_LANGUAGE]["command_start"]),
        BotCommand(command="/lang", description=TRANSLATIONS[DEFAULT_LANGUAGE]["command_lang"]),
    ]
    await bot.set_my_commands(
        commands=default_commands,
        scope=BotCommandScopeAllPrivateChats()
    )
    logger.debug("Set default bot commands")

async def update_user_commands(user_id: int, lang: str):
    try:
        await bot.delete_my_commands(
            scope=BotCommandScopeChat(chat_id=user_id)
        )
        commands = [
            BotCommand(command="/start", description=TRANSLATIONS[lang]["command_start"]),
            BotCommand(command="/lang", description=TRANSLATIONS[lang]["command_lang"]),
        ]
        await bot.set_my_commands(
            commands=commands,
            scope=BotCommandScopeChat(chat_id=user_id)
        )
        logger.debug(f"Updated commands for user {user_id} to language {lang}")
    except TelegramAPIError as e:
        logger.error(f"Failed to update commands for user {user_id}: {e}")

async def get_language(user_id: int, default_lang: str = DEFAULT_LANGUAGE, language_code: str = None) -> str:
    logger.debug(f"Getting language for user {user_id}, language_code={language_code}")
    if user_id in user_languages:
        return user_languages[user_id]

    lang = await get_user_language(user_id)
    if lang:
        user_languages[user_id] = lang
        logger.debug(f"Retrieved language from DB: {lang}")
        return lang

    if language_code and language_code in ("en", "ru"):
        lang = language_code
        logger.debug(f"Using Telegram language_code: {lang}")
    else:
        lang = default_lang
        logger.debug(f"Falling back to default language: {lang}")

    await update_user_language(user_id, lang)
    user_languages[user_id] = lang
    return lang

def create_language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇺🇸 English", callback_data="lang_en"),
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru")
        ],
    ])

def create_topics_keyboard(lang: str) -> InlineKeyboardMarkup:
    topics = TRANSLATIONS[lang]["topics"]
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=topics["balance"], callback_data="topic_balance"),
            InlineKeyboardButton(text=topics["bugs"], callback_data="topic_bugs"),
        ],
        [
            InlineKeyboardButton(text=topics["withdrop"], callback_data="topic_withdrop"),
            InlineKeyboardButton(text=topics["other"], callback_data="topic_other"),
        ],
        [
            InlineKeyboardButton(text=topics["cooperation"], callback_data="topic_cooperation")
        ]
    ])
    logger.debug(f"Created topics keyboard: {markup}")
    return markup

def create_topic_subpage(topic: str, lang: str) -> tuple[str, InlineKeyboardMarkup]:
    logger.debug(f"Creating subpage for topic: {topic}, lang: {lang}")
    if topic not in FAQ_QUESTIONS:
        logger.error(f"Invalid topic in FAQ_QUESTIONS: {topic}")
        text = TRANSLATIONS[lang]["error"]
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=TRANSLATIONS[lang]["back"],
                callback_data="back_to_topics"
            )]
        ])
        return text, markup

    try:
        faq = FAQ_QUESTIONS[topic][lang]
        subpage_text = TRANSLATIONS[lang]["select_topic"]
        faq_buttons = []
        if topic == "bugs":
            faq_buttons = [
                [InlineKeyboardButton(
                    text=faq[f"question{i}"],
                    callback_data=f"contact_{topic}_subtopic{i}"
                )] for i in range(1, 10) if f"question{i}" in faq
            ]
        else:
            faq_buttons = [
                [InlineKeyboardButton(
                    text=faq[f"question{i}"],
                    callback_data=f"faq_{topic}_question{i}"
                )] for i in range(1, 10) if f"question{i}" in faq
            ]
        action_buttons = [
            [InlineKeyboardButton(
                text=TRANSLATIONS[lang].get("back", "Back"),
                callback_data="back_to_topics"
            )]
        ]
        markup = InlineKeyboardMarkup(inline_keyboard=faq_buttons + action_buttons)
        return subpage_text, markup
    except Exception as e:
        logger.error(f"Error creating subpage for topic {topic}, lang {lang}: {e}")
        text = TRANSLATIONS[lang]["error"]
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=TRANSLATIONS[lang]["back"],
                callback_data="back_to_topics"
            )]
        ])
        return text, markup

def create_faq_answer_keyboard(lang: str, topic: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=TRANSLATIONS[lang].get("contact_operator", "Contact operator"),
            callback_data=f"contact_{topic}"
        )],
        [InlineKeyboardButton(
            text=TRANSLATIONS[lang].get("back", "Back"),
            callback_data="back_to_subpage"
        )]
    ])

def create_back_to_topics_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=TRANSLATIONS[lang]["back"], callback_data="back_to_topics")]
    ])

def create_close_ticket_keyboard(user_id: int, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🔒 Закрыть тикет",
                callback_data=f"close_ticket_{user_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="🦄 Информация о пользователе",
                url=f"https://t.me/MajesticGameBot?start=open_user_information_{user_id}"
            )
        ]
    ])

async def create_forum_thread(user_id: int, topic: str, subtopic: str, lang: str) -> int:
    try:
        user_info = await bot.get_chat(user_id)
        username = f"@{user_info.username}" if user_info.username else f"user{user_id}"
        first_name = user_info.first_name or "N/A"
        last_name = user_info.last_name or "N/A"

        topic_name_ru = TRANSLATIONS["ru"]["topics"][topic]
        subtopic_text = subtopic or "Не указан"

        title = f"🟢 ОТКРЫТО: {topic_name_ru} - id{user_id}"
        user_details = (
            f"<b>👤 Пользователь:</b> <code>{first_name} {last_name}</code>\n"
            f"<b>🆔 ID:</b> <code>{user_id}</code>\n"
            f"<b>📧 Username:</b> <code>{username}</code>\n"
            f"<b>📌 Тема:</b> <code>{topic_name_ru}</code>\n"
            f"<b>📍 Подтема:</b> <code>{subtopic_text}</code>\n"
            f"<b>⏰ Создан:</b> <code>{datetime.now().strftime('%Y-%m-%d %H:%M')}</code>\n"
            f"────────────────────"
        )

        forum_topic = await bot.create_forum_topic(
            chat_id=SUPPORT_CHAT_ID,
            name=title
        )

        await bot.send_message(
            chat_id=SUPPORT_CHAT_ID,
            text=user_details,
            message_thread_id=forum_topic.message_thread_id,
            reply_markup=create_close_ticket_keyboard(user_id, "ru"),
            parse_mode="HTML"
        )

        return forum_topic.message_thread_id
    except TelegramAPIError as e:
        logger.error(f"Error creating forum topic: {e}")
        raise

async def extract_reply_markup(message: Message) -> Optional[InlineKeyboardMarkup]:
    """Извлекает inline-клавиатуру из сообщения, если она есть."""
    if message.reply_markup and isinstance(message.reply_markup, InlineKeyboardMarkup):
        logger.debug(f"Extracted reply_markup from message {message.message_id}: {message.reply_markup}")
        return message.reply_markup
    logger.debug(f"No reply_markup found in message {message.message_id}")
    return None

@router.message(Command("lang"), F.chat.type == "private")
async def cmd_lang(message: Message, state: FSMContext):
    user_id = message.from_user.id
    lang = await get_language(user_id, language_code=message.from_user.language_code)
    await message.answer(
        TRANSLATIONS[lang]["select_language"],
        reply_markup=create_language_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(TicketStates.waiting_for_topic)

@router.callback_query(F.data.startswith("lang_"))
async def process_language_selection(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    lang = callback.data.split("_")[1]

    try:
        await update_user_language(user_id, lang)
        user_languages[user_id] = lang
        await update_user_commands(user_id, lang)
        logger.debug(f"Language set to {lang} for user {user_id}")
        converter = MessageToHtmlConverter(TRANSLATIONS[lang]["start_screen"], None)
        await callback.message.edit_text(
            converter.html,
            reply_markup=create_topics_keyboard(lang),
            parse_mode="HTML"
        )
        await state.set_state(TicketStates.waiting_for_topic)


    except TelegramBadRequest as e:
        logger.warning(f"Message not modified for lang selection: {e}")
        await state.set_state(TicketStates.waiting_for_topic)
    except Exception as e:
        logger.error(f"Error updating language: {e}")
        converter = MessageToHtmlConverter(TRANSLATIONS[lang]["start_screen"], None)
        await callback.message.edit_text(
            converter.html,
            reply_markup=create_topics_keyboard(lang),
            parse_mode="HTML"
        )
        await callback.answer("Please try again.")
    await callback.answer()

@router.message(CommandStart(), F.chat.type == "private")
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    language_code = message.from_user.language_code
    lang = await get_language(user_id, language_code=language_code)

    converter = MessageToHtmlConverter(TRANSLATIONS[lang]["start_screen"], None)
    await message.answer(
        converter.html,
        reply_markup=create_topics_keyboard(lang),
        parse_mode="HTML"
    )
    await state.set_state(TicketStates.waiting_for_topic)

    thread_id, status, _ = await get_ticket(user_id)
    if status == "open":
        await state.update_data(thread_id=thread_id)

@router.callback_query(F.data == "back_to_topics")
async def back_to_topics(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    lang = await get_language(user_id)
    try:
        converter = MessageToHtmlConverter(TRANSLATIONS[lang]["start_screen"], None)
        await callback.message.edit_text(
            converter.html,
            reply_markup=create_topics_keyboard(lang),
            parse_mode="HTML"
        )
        await state.set_state(TicketStates.waiting_for_topic)
    except TelegramBadRequest as e:
        logger.warning(f"Message not modified for back_to_topics: {e}")
        await state.set_state(TicketStates.waiting_for_topic)
    await callback.answer()

@router.callback_query(F.data == "back_to_subpage")
async def back_to_subpage(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    lang = await get_language(user_id)
    data = await state.get_data()
    topic = data.get("topic")

    if not topic:
        logger.error(f"No topic found in state for user {user_id}")
        try:
            converter = MessageToHtmlConverter(TRANSLATIONS[lang]["start_screen"], None)
            await callback.message.edit_text(
                converter.html,
                reply_markup=create_topics_keyboard(lang),
                parse_mode="HTML"
            )
            await state.set_state(TicketStates.waiting_for_topic)
        except TelegramBadRequest as e:
            logger.warning(f"Message not modified for back_to_subpage: {e}")
            await state.set_state(TicketStates.waiting_for_topic)
        await callback.answer()
        return

    try:
        subpage_text, subpage_markup = create_topic_subpage(topic, lang)
        converter = MessageToHtmlConverter(subpage_text, None)
        await callback.message.edit_text(
            converter.html,
            reply_markup=subpage_markup,
            parse_mode="HTML"
        )
        await state.set_state(TicketStates.waiting_for_subtopic)
    except TelegramBadRequest as e:
        logger.warning(f"Message not modified for subpage {topic}: {e}")
        await state.set_state(TicketStates.waiting_for_subtopic)
    except Exception as e:
        logger.error(f"Error returning to subpage for topic {topic}: {e}")
        try:
            converter = MessageToHtmlConverter(TRANSLATIONS[lang]["start_screen"], None)
            await callback.message.edit_text(
                converter.html,
                reply_markup=create_topics_keyboard(lang),
                parse_mode="HTML"
            )
            await state.set_state(TicketStates.waiting_for_topic)
        except TelegramBadRequest as e:
            logger.warning(f"Message not modified for error fallback: {e}")
            await state.set_state(TicketStates.waiting_for_topic)
    await callback.answer()

@router.callback_query(F.data.startswith("topic_"))
async def select_topic(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    lang = await get_language(user_id)
    logger.debug(f"Received callback data: {callback.data}")
    topic = callback.data.split("_")[1]

    if topic not in TOPICS:
        logger.error(f"Invalid topic selected: {topic}")
        try:
            current_text = callback.message.text or ""
            converter = MessageToHtmlConverter(TRANSLATIONS[lang]["start_screen"], None)
            if current_text != converter.html:
                await callback.message.edit_text(
                    converter.html,
                    reply_markup=create_topics_keyboard(lang),
                    parse_mode="HTML"
                )
            await state.set_state(TicketStates.waiting_for_topic)
            await callback.answer("Please select a valid topic.")
        except TelegramBadRequest as e:
            logger.warning(f"Message not modified for invalid topic {topic}: {e}")
            await state.set_state(TicketStates.waiting_for_topic)
            await callback.answer()
        return

    try:
        if topic == "cooperation":
            buttons = [
                [InlineKeyboardButton(
                    text=TRANSLATIONS[lang].get("contact_operator", "Contact operator"),
                    callback_data=f"contact_{topic}"
                )],
                [InlineKeyboardButton(
                    text=TRANSLATIONS[lang].get("back", "Back"),
                    callback_data="back_to_topics"
                )]
            ]
            cooperation_text = TRANSLATIONS[lang].get("cooperation_message", "Please provide details about your cooperation proposal.")
            converter = MessageToHtmlConverter(cooperation_text, None, buttons=buttons)
            await callback.message.edit_text(
                converter.html,
                reply_markup=converter.get_reply_markup(),
                parse_mode="HTML"
            )
            await state.clear()
        else:
            await state.update_data(topic=topic)
            subpage_text, subpage_markup = create_topic_subpage(topic, lang)
            converter = MessageToHtmlConverter(subpage_text, None)
            await callback.message.edit_text(
                converter.html,
                reply_markup=subpage_markup,
                parse_mode="HTML"
            )
            await state.set_state(TicketStates.waiting_for_subtopic)
    except TelegramBadRequest as e:
        logger.warning(f"Message not modified for topic {topic}: {e}")
        await state.set_state(TicketStates.waiting_for_subtopic if topic != "cooperation" else TicketStates.waiting_for_topic)
    except Exception as e:
        logger.error(f"Error in select_topic for topic {topic}: {e}")
        try:
            converter = MessageToHtmlConverter(TRANSLATIONS[lang]["start_screen"], None)
            await callback.message.edit_text(
                converter.html,
                reply_markup=create_topics_keyboard(lang),
                parse_mode="HTML"
            )
            await state.set_state(TicketStates.waiting_for_topic)
        except TelegramBadRequest as e:
            logger.warning(f"Message not modified for error fallback: {e}")
            await state.set_state(TicketStates.waiting_for_topic)
    await callback.answer()

@router.callback_query(F.data.startswith("faq_"))
async def show_faq_answer(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    lang = await get_language(user_id)
    try:
        _, topic, question_key = callback.data.split("_")
        question_num = question_key.replace("question", "")
        faq = FAQ_QUESTIONS[topic][lang]
        answer_text = f"📩 <b>{faq[f'question{question_num}']}</b>\n\n{faq[f'answer{question_num}']}"
        converter = MessageToHtmlConverter(answer_text, None)
        await callback.message.edit_text(
            converter.html,
            reply_markup=create_faq_answer_keyboard(lang, topic),
            parse_mode="HTML"
        )
        await state.set_state(TicketStates.waiting_for_faq_answer)
    except TelegramBadRequest as e:
        logger.warning(f"Message not modified for FAQ answer {callback.data}: {e}")
        await state.set_state(TicketStates.waiting_for_faq_answer)
    except Exception as e:
        logger.error(f"Error showing FAQ answer for {callback.data}: {e}")
        try:
            converter = MessageToHtmlConverter(TRANSLATIONS[lang]["error"], None)
            await callback.message.edit_text(
                converter.html,
                reply_markup=create_back_to_topics_keyboard(lang),
                parse_mode="HTML"
            )
            await state.set_state(TicketStates.waiting_for_topic)
        except TelegramBadRequest as e:
            logger.warning(f"Message not modified for FAQ error: {e}")
            await state.set_state(TicketStates.waiting_for_topic)
    await callback.answer()

@router.callback_query(F.data.startswith("contact_"))
async def contact_operator(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    lang = await get_language(user_id)
    data = callback.data.split("_")
    topic = data[1]
    subtopic = None

    if len(data) > 2 and data[2].startswith("subtopic"):
        subtopic_key = data[2].replace("subtopic", "question")
        subtopic = FAQ_QUESTIONS[topic][lang].get(subtopic_key, "Unknown subtopic")

    try:
        thread_id, status, _ = await get_ticket(user_id)
        if status == "open":
            converter = MessageToHtmlConverter(TRANSLATIONS[lang]["ticket_already_open"], None)
            await callback.message.edit_text(
                converter.html,
                reply_markup=create_back_to_topics_keyboard(lang),
                parse_mode="HTML"
            )
            await state.set_state(TicketStates.waiting_for_topic)
            await callback.answer()
            return

        await state.update_data(topic=topic, subtopic=subtopic)
        converter = MessageToHtmlConverter(TRANSLATIONS[lang]["describe_issue"], None)
        await callback.message.edit_text(
            converter.html,
            reply_markup=create_back_to_topics_keyboard(lang),
            parse_mode="HTML"
        )
        await state.set_state(TicketStates.waiting_for_description)
    except TelegramBadRequest as e:
        logger.warning(f"Message not modified in contact_operator: {e}")
        await state.set_state(TicketStates.waiting_for_description)
    except Exception as e:
        logger.error(f"Error in contact_operator: {e}")
        converter = MessageToHtmlConverter(TRANSLATIONS[lang]["start_screen"], None)
        await callback.message.edit_text(
            converter.html,
            reply_markup=create_topics_keyboard(lang),
            parse_mode="HTML"
        )
        await state.set_state(TicketStates.waiting_for_topic)
    await callback.answer()

@router.message(TicketStates.waiting_for_description, F.chat.type == "private")
async def create_ticket(message: Message, state: FSMContext):
    user_id = message.from_user.id
    lang = await get_language(user_id, language_code=message.from_user.language_code)
    data = await state.get_data()
    topic = data.get("topic")
    subtopic = data.get("subtopic", None)

    if user_id not in ticket_creation_locks:
        ticket_creation_locks[user_id] = asyncio.Lock()

    async with ticket_creation_locks[user_id]:
        try:
            existing_thread_id, status, _ = await get_ticket(user_id)
            reply_markup = await extract_reply_markup(message)  # Извлечение клавиатуры
            if status == "open" and existing_thread_id:
                await state.set_state(TicketStates.active_ticket)
                await state.update_data(thread_id=existing_thread_id)
                if message.text:
                    converter = MessageToHtmlConverter(message.text, message.entities)
                    await bot.send_message(
                        SUPPORT_CHAT_ID,
                        converter.html,
                        message_thread_id=existing_thread_id,
                        reply_markup=reply_markup,  # Передача клавиатуры
                        parse_mode="HTML"
                    )
                elif message.sticker:
                    await bot.send_sticker(
                        SUPPORT_CHAT_ID,
                        message.sticker.file_id,
                        message_thread_id=existing_thread_id,
                        reply_markup=reply_markup  # Передача клавиатуры
                    )
                elif message.animation:
                    await bot.send_animation(
                        SUPPORT_CHAT_ID,
                        message.animation.file_id,
                        message_thread_id=existing_thread_id,
                        reply_markup=reply_markup  # Передача клавиатуры
                    )
                elif message.photo:
                    converter = MessageToHtmlConverter(message.caption, message.caption_entities)
                    await bot.send_photo(
                        SUPPORT_CHAT_ID,
                        message.photo[-1].file_id,
                        caption=converter.html,
                        message_thread_id=existing_thread_id,
                        reply_markup=reply_markup,  # Передача клавиатуры
                        parse_mode="HTML"
                    )
                await update_ticket_time(user_id)
                return

            thread_id = await create_forum_thread(user_id, topic, subtopic, "ru")

            async with (await get_db_pool()).acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO tickets (user_id, thread_id, status, topic, last_message_time) 
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (user_id) DO UPDATE 
                    SET thread_id = $2, status = $3, topic = $4, last_message_time = $5
                    """,
                    user_id, thread_id, "open", topic, datetime.now()
                )

            if message.text:
                converter = MessageToHtmlConverter(message.text, message.entities)
                await bot.send_message(
                    SUPPORT_CHAT_ID,
                    converter.html,
                    message_thread_id=thread_id,
                    reply_markup=reply_markup,  # Передача клавиатуры
                    parse_mode="HTML"
                )
            elif message.sticker:
                await bot.send_sticker(
                    SUPPORT_CHAT_ID,
                    message.sticker.file_id,
                    message_thread_id=thread_id,
                    reply_markup=reply_markup  # Передача клавиатуры
                )
            elif message.animation:
                await bot.send_animation(
                    SUPPORT_CHAT_ID,
                    message.animation.file_id,
                    message_thread_id=thread_id,
                    reply_markup=reply_markup  # Передача клавиатуры
                )
            elif message.photo:
                converter = MessageToHtmlConverter(message.caption, message.caption_entities)
                await bot.send_photo(
                    SUPPORT_CHAT_ID,
                    message.photo[-1].file_id,
                    caption=converter.html,
                    message_thread_id=thread_id,
                    reply_markup=reply_markup,  # Передача клавиатуры
                    parse_mode="HTML"
                )

            converter = MessageToHtmlConverter(TRANSLATIONS[lang]["ticket_submitted"], None)
            await message.answer(
                converter.html,
                parse_mode="HTML"
            )

            await state.set_state(TicketStates.active_ticket)
            await state.update_data(thread_id=thread_id)

        except Exception as e:
            logger.error(f"Error creating ticket: {e}", exc_info=True)
            converter = MessageToHtmlConverter(TRANSLATIONS[lang]["error"], None)
            await message.answer(
                converter.html,
                parse_mode="HTML"
            )

@router.message(TicketStates.active_ticket, F.chat.type == "private")
async def forward_to_support(message: Message, state: FSMContext):
    user_id = message.from_user.id
    lang = await get_language(user_id, language_code=message.from_user.language_code)
    data = await state.get_data()
    thread_id = data.get("thread_id")

    if not thread_id:
        converter = MessageToHtmlConverter(TRANSLATIONS[lang]["error"], None)
        await message.answer(
            converter.html,
            parse_mode="HTML"
        )
        await state.clear()
        converter = MessageToHtmlConverter(TRANSLATIONS[lang]["start_screen"], None)
        await message.answer(
            converter.html,
            reply_markup=create_topics_keyboard(lang),
            parse_mode="HTML"
        )
        return

    try:
        _, status, _ = await get_ticket(user_id)
        if status != "open":
            converter = MessageToHtmlConverter(TRANSLATIONS[lang]["ticket_closed_message"], None)
            await message.answer(
                converter.html,
                parse_mode="HTML"
            )
            converter = MessageToHtmlConverter(TRANSLATIONS[lang]["start_screen"], None)
            await message.answer(
                converter.html,
                reply_markup=create_topics_keyboard(lang),
                parse_mode="HTML"
            )
            await state.clear()
            return

        reply_markup = await extract_reply_markup(message)  # Извлечение клавиатуры

        if message.text:
            converter = MessageToHtmlConverter(message.text, message.entities)
            await bot.send_message(
                SUPPORT_CHAT_ID,
                converter.html,
                message_thread_id=thread_id,
                reply_markup=reply_markup,  # Передача клавиатуры
                parse_mode="HTML"
            )
        elif message.sticker:
            await bot.send_sticker(
                SUPPORT_CHAT_ID,
                message.sticker.file_id,
                message_thread_id=thread_id,
                reply_markup=reply_markup  # Передача клавиатуры
            )
        elif message.animation:
            await bot.send_animation(
                SUPPORT_CHAT_ID,
                message.animation.file_id,
                message_thread_id=thread_id,
                reply_markup=reply_markup  # Передача клавиатуры
            )
        elif message.photo:
            converter = MessageToHtmlConverter(message.caption, message.caption_entities)
            await bot.send_photo(
                SUPPORT_CHAT_ID,
                message.photo[-1].file_id,
                caption=converter.html,
                message_thread_id=thread_id,
                reply_markup=reply_markup,  # Передача клавиатуры
                parse_mode="HTML"
            )

        await update_ticket_time(user_id)

    except Exception as e:
        logger.error(f"Error forwarding message: {e}")
        converter = MessageToHtmlConverter(TRANSLATIONS[lang]["error"], None)
        await message.answer(
            converter.html,
            parse_mode="HTML"
        )

@router.message(F.chat.type == "private")
async def handle_random_message(message: Message, state: FSMContext):
    user_id = message.from_user.id
    lang = await get_language(user_id, language_code=message.from_user.language_code)

    thread_id, status, _ = await get_ticket(user_id)

    if status == "open":
        await state.set_state(TicketStates.active_ticket)
        await state.update_data(thread_id=thread_id)
        await forward_to_support(message, state)
    else:
        async with (await get_db_pool()).acquire() as conn:
            ticket_exists = await conn.fetchval(
                "SELECT EXISTS (SELECT 1 FROM tickets WHERE user_id = $1)",
                user_id
            )
        if ticket_exists:
            converter = MessageToHtmlConverter(TRANSLATIONS[lang]["ticket_closed_message"], None)
            await message.answer(
                converter.html,
                parse_mode="HTML"
            )

        converter = MessageToHtmlConverter(TRANSLATIONS[lang]["start_screen"], None)
        await message.answer(
            converter.html,
            reply_markup=create_topics_keyboard(lang),
            parse_mode="HTML"
        )
        await state.clear()

@router.callback_query(F.data.startswith("close_ticket_"))
async def close_ticket_button(callback: CallbackQuery, state: FSMContext):
    user_id = int(callback.data.split("_")[-1])
    thread_id = callback.message.message_thread_id

    try:
        _, status, topic = await get_ticket(user_id)
        if status != "open":
            await callback.answer("Тикет уже закрыт")
            return

        async with (await get_db_pool()).acquire() as conn:
            await conn.execute(
                "UPDATE tickets SET status = 'closed' WHERE user_id = $1",
                user_id
            )

        user_info = await bot.get_chat(user_id)
        username = f"@{user_info.username}" if user_info.username else f"user{user_id}"
        topic_name_ru = TRANSLATIONS["ru"]["topics"][topic]
        new_name = f"🔒 ЗАКРЫТО: {topic_name_ru} - {username}"

        await bot.edit_forum_topic(
            chat_id=SUPPORT_CHAT_ID,
            message_thread_id=thread_id,
            name=new_name
        )

        await bot.close_forum_topic(
            chat_id=SUPPORT_CHAT_ID,
            message_thread_id=thread_id
        )

        await callback.answer("Тикет закрыт")
        await callback.message.edit_reply_markup(reply_markup=None)

        try:
            await state.clear()
            lang = await get_language(user_id)
            converter = MessageToHtmlConverter(TRANSLATIONS[lang]["ticket_closed"], None)
            await bot.send_message(
                chat_id=user_id,
                text=converter.html,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to notify user: {e}")

    except Exception as e:
        logger.error(f"Error closing ticket: {e}")
        await callback.answer("Ошибка при закрытии тикета")

@router.message(F.chat.id == SUPPORT_CHAT_ID, F.is_topic_message)
async def forward_to_user(message: Message, state: FSMContext):
    thread_id = message.message_thread_id
    user_id = await get_user_by_thread(thread_id)

    if not user_id:
        logger.error(f"User not found for thread {thread_id}")
        return

    try:
        reply_markup = await extract_reply_markup(message)  # Извлечение клавиатуры

        if message.text:
            converter = MessageToHtmlConverter(message.text, message.entities)
            await bot.send_message(
                chat_id=user_id,
                text=converter.html,
                reply_markup=reply_markup,  # Передача клавиатуры
                parse_mode="HTML"
            )
        elif message.sticker:
            await bot.send_sticker(
                chat_id=user_id,
                sticker=message.sticker.file_id,
                reply_markup=reply_markup  # Передача клавиатуры
            )
        elif message.animation:
            await bot.send_animation(
                chat_id=user_id,
                animation=message.animation.file_id,
                reply_markup=reply_markup  # Передача клавиатуры
            )
        elif message.photo:
            converter = MessageToHtmlConverter(message.caption, message.caption_entities)
            await bot.send_photo(
                chat_id=user_id,
                photo=message.photo[-1].file_id,
                caption=converter.html,
                reply_markup=reply_markup,  # Передача клавиатуры
                parse_mode="HTML"
            )

        await update_ticket_time(user_id)

    except Exception as e:
        logger.error(f"Error forwarding to user {user_id}: {e}")