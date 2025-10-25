import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, F, Router
from html import escape
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    BotCommand,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
)
from aiogram.types import Sticker, Animation
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError
from typing import Optional  # Добавлен импорт для extract_reply_markup
from config import (
    API_TOKEN,
    SUPPORT_CHAT_ID,
    TECH_SUPPORT_CHAT_ID,
    SUPPORT_OWNER_IDS,
    TECH_OWNER_IDS,
    TRANSLATIONS,
    DEFAULT_LANGUAGE,
    MEDIA_GROUP_TIMEOUT,
    FAQ_QUESTIONS,
    TOPICS,
)
from database import (
    get_ticket,
    get_user_by_thread,
    update_ticket_client_activity,
    update_ticket_support_activity,
    get_db_pool,
    update_user_language,
    get_user_language,
    update_ticket_tech_thread,
    save_ticket_message,
    get_ticket_messages,
)
from utils import MessageToHtmlConverter, build_topic_url
import asyncio

logger = logging.getLogger(__name__)

router = Router()
bot = Bot(token=API_TOKEN)
dp = Dispatcher()
dp.include_router(router)
user_languages = {}
ticket_creation_locks = {}

def get_topic_display(topic: Optional[str]) -> str:
    if topic and topic in TRANSLATIONS["ru"]["topics"]:
        return TRANSLATIONS["ru"]["topics"][topic]
    return topic or "Не указан"

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

def create_close_ticket_keyboard(user_id: int, lang: str, tech_thread_id: Optional[int] = None) -> InlineKeyboardMarkup:
    buttons = [
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
    ]

    if TECH_SUPPORT_CHAT_ID:
        if TECH_SUPPORT_CHAT_ID and tech_thread_id:
            topic_url = build_topic_url(TECH_SUPPORT_CHAT_ID, tech_thread_id)
            if topic_url:
                buttons.append([
                    InlineKeyboardButton(
                        text="🛠 Открыть тех-чат",
                        url=topic_url
                    )
                ])
        else:
            buttons.append([
                InlineKeyboardButton(
                    text="🛠 Создать чат техподдержки",
                    callback_data=f"create_tech_ticket_{user_id}"
                )
            ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_tech_ticket_keyboard(user_id: int, support_thread_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(
                text="🦄 Информация о пользователе",
                url=f"https://t.me/MajesticGameBot?start=open_user_information_{user_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔒 Закрыть тех тикет",
                callback_data=f"close_tech_ticket_{user_id}"
            )
        ]
    ]

    support_link = build_topic_url(SUPPORT_CHAT_ID, support_thread_id)
    if support_link:
        buttons.append([
            InlineKeyboardButton(
                text="💬 Чат с клиентом",
                url=support_link
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)

async def create_forum_thread(user_id: int, topic: str, subtopic: str, lang: str) -> int:
    try:
        user_info = await bot.get_chat(user_id)
        username = f"@{user_info.username}" if user_info.username else f"user{user_id}"
        first_name = user_info.first_name or "N/A"
        last_name = user_info.last_name or "N/A"

        topic_name_ru = get_topic_display(topic)
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

        details_message = await bot.send_message(
            chat_id=SUPPORT_CHAT_ID,
            text=user_details,
            message_thread_id=forum_topic.message_thread_id,
            reply_markup=create_close_ticket_keyboard(user_id, "ru"),
            parse_mode="HTML"
        )

        await save_ticket_message(
            user_id,
            details_message.message_id,
            SUPPORT_CHAT_ID,
            forum_topic.message_thread_id
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
    await callback.answer(
        "Вы уверены, что хотите создать тикет с техническим отделом?",
        show_alert=True
    )

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

    thread_id, status, _, tech_thread_id = await get_ticket(user_id)
    if status == "open":
        await state.update_data(thread_id=thread_id, tech_thread_id=tech_thread_id)

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
    await callback.answer(
        "Вы уверены, что хотите создать тикет с техническим отделом?",
        show_alert=True
    )

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
        thread_id, status, _, tech_thread_id = await get_ticket(user_id)
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

        await state.update_data(topic=topic, subtopic=subtopic, tech_thread_id=tech_thread_id)
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
            existing_thread_id, status, _, tech_thread_id = await get_ticket(user_id)
            reply_markup = await extract_reply_markup(message)  # Извлечение клавиатуры
            if status == "open" and existing_thread_id:
                await state.set_state(TicketStates.active_ticket)
                await state.update_data(thread_id=existing_thread_id, tech_thread_id=tech_thread_id)
                if message.text:
                    converter = MessageToHtmlConverter(message.text, message.entities)
                    sent_message = await bot.send_message(
                        SUPPORT_CHAT_ID,
                        converter.html,
                        message_thread_id=existing_thread_id,
                        reply_markup=reply_markup,  # Передача клавиатуры
                        parse_mode="HTML"
                    )
                    await save_ticket_message(user_id, sent_message.message_id, SUPPORT_CHAT_ID, existing_thread_id)
                elif message.sticker:
                    sent_message = await bot.send_sticker(
                        SUPPORT_CHAT_ID,
                        message.sticker.file_id,
                        message_thread_id=existing_thread_id,
                        reply_markup=reply_markup  # Передача клавиатуры
                    )
                    await save_ticket_message(user_id, sent_message.message_id, SUPPORT_CHAT_ID, existing_thread_id)
                elif message.animation:
                    sent_message = await bot.send_animation(
                        SUPPORT_CHAT_ID,
                        message.animation.file_id,
                        message_thread_id=existing_thread_id,
                        reply_markup=reply_markup  # Передача клавиатуры
                    )
                    await save_ticket_message(user_id, sent_message.message_id, SUPPORT_CHAT_ID, existing_thread_id)
                elif message.photo:
                    converter = MessageToHtmlConverter(message.caption, message.caption_entities)
                    sent_message = await bot.send_photo(
                        SUPPORT_CHAT_ID,
                        message.photo[-1].file_id,
                        caption=converter.html,
                        message_thread_id=existing_thread_id,
                        reply_markup=reply_markup,  # Передача клавиатуры
                        parse_mode="HTML"
                    )
                    await save_ticket_message(user_id, sent_message.message_id, SUPPORT_CHAT_ID, existing_thread_id)
                await update_ticket_client_activity(user_id)
                return

            thread_id = await create_forum_thread(user_id, topic, subtopic, "ru")

            async with (await get_db_pool()).acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO tickets (user_id, thread_id, status, topic, last_message_time) 
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (user_id) DO UPDATE 
                    SET thread_id = $2,
                        status = $3,
                        topic = $4,
                        last_message_time = $5,
                        support_reminder_sent = FALSE,
                        tech_reminder_sent = FALSE,
                        tech_thread_id = NULL
                    """,
                    user_id, thread_id, "open", topic, datetime.now()
                )

            if message.text:
                converter = MessageToHtmlConverter(message.text, message.entities)
                sent_message = await bot.send_message(
                    SUPPORT_CHAT_ID,
                    converter.html,
                    message_thread_id=thread_id,
                    reply_markup=reply_markup,  # Передача клавиатуры
                    parse_mode="HTML"
                )
                await save_ticket_message(user_id, sent_message.message_id, SUPPORT_CHAT_ID, thread_id)
            elif message.sticker:
                sent_message = await bot.send_sticker(
                    SUPPORT_CHAT_ID,
                    message.sticker.file_id,
                    message_thread_id=thread_id,
                    reply_markup=reply_markup  # Передача клавиатуры
                )
                await save_ticket_message(user_id, sent_message.message_id, SUPPORT_CHAT_ID, thread_id)
            elif message.animation:
                sent_message = await bot.send_animation(
                    SUPPORT_CHAT_ID,
                    message.animation.file_id,
                    message_thread_id=thread_id,
                    reply_markup=reply_markup  # Передача клавиатуры
                )
                await save_ticket_message(user_id, sent_message.message_id, SUPPORT_CHAT_ID, thread_id)
            elif message.photo:
                converter = MessageToHtmlConverter(message.caption, message.caption_entities)
                sent_message = await bot.send_photo(
                    SUPPORT_CHAT_ID,
                    message.photo[-1].file_id,
                    caption=converter.html,
                    message_thread_id=thread_id,
                    reply_markup=reply_markup,  # Передача клавиатуры
                    parse_mode="HTML"
                )
                await save_ticket_message(user_id, sent_message.message_id, SUPPORT_CHAT_ID, thread_id)

            converter = MessageToHtmlConverter(TRANSLATIONS[lang]["ticket_submitted"], None)
            await message.answer(
                converter.html,
                parse_mode="HTML"
            )

            await update_ticket_client_activity(user_id)

            await state.set_state(TicketStates.active_ticket)
            await state.update_data(thread_id=thread_id, tech_thread_id=None)

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
    tech_thread_id = data.get("tech_thread_id")

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
        current_thread_id, status, _, db_tech_thread_id = await get_ticket(user_id)

        if current_thread_id and current_thread_id != thread_id:
            thread_id = current_thread_id
            await state.update_data(thread_id=thread_id)

        if db_tech_thread_id != tech_thread_id:
            tech_thread_id = db_tech_thread_id
            await state.update_data(tech_thread_id=tech_thread_id)

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
            sent_message = await bot.send_message(
                SUPPORT_CHAT_ID,
                converter.html,
                message_thread_id=thread_id,
                reply_markup=reply_markup,  # Передача клавиатуры
                parse_mode="HTML"
            )
            await save_ticket_message(user_id, sent_message.message_id, SUPPORT_CHAT_ID, thread_id)
        elif message.sticker:
            sent_message = await bot.send_sticker(
                SUPPORT_CHAT_ID,
                message.sticker.file_id,
                message_thread_id=thread_id,
                reply_markup=reply_markup  # Передача клавиатуры
            )
            await save_ticket_message(user_id, sent_message.message_id, SUPPORT_CHAT_ID, thread_id)
        elif message.animation:
            sent_message = await bot.send_animation(
                SUPPORT_CHAT_ID,
                message.animation.file_id,
                message_thread_id=thread_id,
                reply_markup=reply_markup  # Передача клавиатуры
            )
            await save_ticket_message(user_id, sent_message.message_id, SUPPORT_CHAT_ID, thread_id)
        elif message.photo:
            converter = MessageToHtmlConverter(message.caption, message.caption_entities)
            sent_message = await bot.send_photo(
                SUPPORT_CHAT_ID,
                message.photo[-1].file_id,
                caption=converter.html,
                message_thread_id=thread_id,
                reply_markup=reply_markup,  # Передача клавиатуры
                parse_mode="HTML"
            )
            await save_ticket_message(user_id, sent_message.message_id, SUPPORT_CHAT_ID, thread_id)

        await update_ticket_client_activity(user_id)

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

    thread_id, status, _, tech_thread_id = await get_ticket(user_id)

    if status == "open":
        await state.set_state(TicketStates.active_ticket)
        await state.update_data(thread_id=thread_id, tech_thread_id=tech_thread_id)
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

@router.callback_query(F.data.startswith("create_tech_ticket_"))
async def prompt_tech_ticket(callback: CallbackQuery):
    if not TECH_SUPPORT_CHAT_ID:
        await callback.answer("Технический чат не настроен", show_alert=True)
        return

    user_id = int(callback.data.split("_")[-1])
    thread_id = callback.message.message_thread_id
    source_message_id = callback.message.message_id

    _, _, _, tech_thread_id = await get_ticket(user_id)
    if tech_thread_id:
        thread_active = True
        try:
            await bot.send_chat_action(
                chat_id=TECH_SUPPORT_CHAT_ID,
                action="typing",
                message_thread_id=tech_thread_id
            )
        except (TelegramBadRequest, TelegramForbiddenError) as exc:
            logger.warning(f"Stored tech thread {tech_thread_id} invalid for user {user_id}: {exc}")
            async with (await get_db_pool()).acquire() as conn:
                await conn.execute(
                    "UPDATE tickets SET tech_thread_id = NULL WHERE user_id = $1",
                    user_id
                )
            thread_active = False

        if thread_active:
            markup = create_close_ticket_keyboard(user_id, "ru", tech_thread_id=tech_thread_id)
            try:
                await bot.edit_message_reply_markup(
                    chat_id=SUPPORT_CHAT_ID,
                    message_id=source_message_id,
                    reply_markup=markup
                )
            except TelegramBadRequest as exc:
                logger.warning(f"Failed to update support keyboard for existing tech chat: {exc}")

            await callback.answer("Технический чат уже создан", show_alert=True)
            return
        else:
            tech_thread_id = None

    confirm_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Да",
                callback_data=f"confirm_tech_ticket_yes_{user_id}_{thread_id}_{source_message_id}"
            ),
            InlineKeyboardButton(
                text="❌ Нет",
                callback_data=f"confirm_tech_ticket_no_{source_message_id}"
            )
        ]
    ])

    await callback.answer()
    await bot.send_message(
        chat_id=SUPPORT_CHAT_ID,
        text="Вы уверены, что хотите создать тикет с техническим отделом?",
        reply_markup=confirm_keyboard,
        message_thread_id=thread_id
    )


@router.callback_query(F.data.startswith("confirm_tech_ticket_no_"))
async def cancel_tech_ticket(callback: CallbackQuery):
    try:
        await callback.message.delete()
    except TelegramBadRequest as exc:
        logger.warning(f"Failed to delete confirmation message: {exc}")
    await callback.answer("Создание тикета отменено")


@router.callback_query(F.data.startswith("confirm_tech_ticket_yes_"))
async def confirm_tech_ticket(callback: CallbackQuery):
    if not TECH_SUPPORT_CHAT_ID:
        await callback.answer("Технический чат не настроен", show_alert=True)
        return

    parts = callback.data.split("_")
    try:
        user_id = int(parts[4])
        expected_thread_id = int(parts[5])
        source_message_id = int(parts[6])
    except (IndexError, ValueError):
        await callback.answer("Не удалось обработать запрос", show_alert=True)
        return

    support_thread_id, status, topic, existing_tech_thread_id = await get_ticket(user_id)
    if status != "open" or support_thread_id != expected_thread_id:
        await callback.answer("Актуальный тикет не найден", show_alert=True)
        await callback.message.delete()
        return

    if existing_tech_thread_id:
        markup = create_close_ticket_keyboard(user_id, "ru", tech_thread_id=existing_tech_thread_id)
        try:
            await bot.edit_message_reply_markup(
                chat_id=SUPPORT_CHAT_ID,
                message_id=source_message_id,
                reply_markup=markup
            )
        except TelegramBadRequest as exc:
            logger.warning(f"Failed to update support keyboard: {exc}")
        await callback.answer("Технический чат уже существует", show_alert=True)
        await callback.message.delete()
        return

    try:
        user_info = await bot.get_chat(user_id)
    except TelegramAPIError as exc:
        logger.error(f"Failed to load user info for tech ticket: {exc}")
        await callback.answer("Не удалось получить данные пользователя", show_alert=True)
        await callback.message.delete()
        return

    username = f"@{user_info.username}" if user_info.username else f"user{user_id}"
    first_name = user_info.first_name or "N/A"
    last_name = user_info.last_name or "N/A"

    topic_name_ru = TRANSLATIONS["ru"]["topics"].get(topic, topic or "Не указано")
    title = f"🛠 ТЕХ: {topic_name_ru} - id{user_id}"

    try:
        forum_topic = await bot.create_forum_topic(
            chat_id=TECH_SUPPORT_CHAT_ID,
            name=title
        )
    except TelegramAPIError as exc:
        logger.error(f"Failed to create tech forum topic: {exc}")
        await callback.answer("Не удалось создать чат технической поддержки", show_alert=True)
        await callback.message.delete()
        return

    support_link = build_topic_url(SUPPORT_CHAT_ID, support_thread_id)
    user_details = (
        f"<b>👤 Пользователь:</b> <code>{escape(first_name)} {escape(last_name)}</code>\n"
        f"<b>🆔 ID:</b> <code>{user_id}</code>\n"
        f"<b>📧 Username:</b> <code>{escape(username)}</code>\n"
        f"<b>📌 Тема:</b> <code>{escape(topic_name_ru)}</code>\n"
    )
    if support_link:
        user_details += f'<b>💬 Поддержка:</b> <a href="{support_link}">Открыть чат</a>\n'
    user_details += f"<b>⏰ Создан:</b> <code>{datetime.now().strftime('%Y-%m-%d %H:%M')}</code>\n"
    user_details += "────────────────────"

    try:
        await bot.send_message(
            chat_id=TECH_SUPPORT_CHAT_ID,
            text=user_details,
            message_thread_id=forum_topic.message_thread_id,
            reply_markup=create_tech_ticket_keyboard(user_id, support_thread_id),
            parse_mode="HTML"
        )
    except TelegramAPIError as exc:
        logger.error(f"Failed to send tech ticket details: {exc}")
        await callback.answer("Не удалось заполнить чат технической поддержки", show_alert=True)
        await callback.message.delete()
        return

    await update_ticket_tech_thread(user_id, forum_topic.message_thread_id)

    message_ids = await get_ticket_messages(user_id, support_thread_id)
    for mid in message_ids:
        try:
            await bot.copy_message(
                chat_id=TECH_SUPPORT_CHAT_ID,
                from_chat_id=SUPPORT_CHAT_ID,
                message_id=mid,
                message_thread_id=forum_topic.message_thread_id
            )
        except TelegramAPIError as exc:
            logger.warning(f"Failed to copy message {mid} to tech chat: {exc}")

    markup = create_close_ticket_keyboard(user_id, "ru", tech_thread_id=forum_topic.message_thread_id)
    try:
        await bot.edit_message_reply_markup(
            chat_id=SUPPORT_CHAT_ID,
            message_id=source_message_id,
            reply_markup=markup
        )
    except TelegramBadRequest as exc:
        logger.warning(f"Failed to update support keyboard after tech chat creation: {exc}")

    try:
        await callback.message.delete()
    except TelegramBadRequest as exc:
        logger.warning(f"Failed to delete confirmation message: {exc}")

    await callback.answer("Создан чат технической поддержки")


@router.callback_query(F.data.startswith("close_tech_ticket_"))
async def close_tech_ticket(callback: CallbackQuery):
    if not TECH_SUPPORT_CHAT_ID:
        await callback.answer("Технический чат не настроен", show_alert=True)
        return

    allowed_tech_ids = set(TECH_OWNER_IDS or [])
    if SUPPORT_OWNER_IDS:
        allowed_tech_ids.update(SUPPORT_OWNER_IDS)
    if allowed_tech_ids and callback.from_user.id not in allowed_tech_ids:
        await callback.answer("Закрывать тикет может только владелец", show_alert=True)
        return

    user_id = int(callback.data.split("_")[-1])
    tech_thread_id = callback.message.message_thread_id

    support_thread_id, _, topic, stored_tech_thread_id = await get_ticket(user_id)
    if stored_tech_thread_id and stored_tech_thread_id != tech_thread_id:
        logger.warning(f"Tech thread mismatch for user {user_id}")

    topic_name_ru = get_topic_display(topic)
    try:
        await bot.edit_forum_topic(
            chat_id=TECH_SUPPORT_CHAT_ID,
            message_thread_id=tech_thread_id,
            name=f"🔒 ТЕХ: {topic_name_ru} - id{user_id}"
        )
    except TelegramAPIError as exc:
        logger.warning(f"Failed to rename tech topic for user {user_id}: {exc}")

    try:
        await bot.close_forum_topic(
            chat_id=TECH_SUPPORT_CHAT_ID,
            message_thread_id=tech_thread_id
        )
    except TelegramAPIError as exc:
        logger.error(f"Failed to close tech ticket for user {user_id}: {exc}")
        await callback.answer("Не удалось закрыть тикет", show_alert=True)
        return

    async with (await get_db_pool()).acquire() as conn:
        await conn.execute(
            "UPDATE tickets SET tech_thread_id = NULL WHERE user_id = $1",
            user_id
        )

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Технический тикет закрыт")

    if support_thread_id:
        topic_name_ru = get_topic_display(topic)
        try:
            notification = await bot.send_message(
                chat_id=SUPPORT_CHAT_ID,
                text=f"Технический тикет по теме <b>{topic_name_ru}</b> закрыт.",
                message_thread_id=support_thread_id,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(
                        text="🛠 Создать чат техподдержки",
                        callback_data=f"create_tech_ticket_{user_id}"
                    )
                ]])
            )
            await save_ticket_message(user_id, notification.message_id, SUPPORT_CHAT_ID, support_thread_id)
        except TelegramAPIError as exc:
            logger.warning(f"Failed to notify support chat about tech closure: {exc}")


@router.callback_query(F.data.startswith("close_ticket_"))
async def close_ticket_button(callback: CallbackQuery, state: FSMContext):
    user_id = int(callback.data.split("_")[-1])
    thread_id = callback.message.message_thread_id

    allowed_support_ids = set(SUPPORT_OWNER_IDS or [])
    if allowed_support_ids and callback.from_user.id not in allowed_support_ids:
        await callback.answer("Закрывать тикет может только владелец", show_alert=True)
        return

    try:
        _, status, topic, tech_thread_id = await get_ticket(user_id)
        if status != "open":
            await callback.answer("Тикет уже закрыт")
            return

        async with (await get_db_pool()).acquire() as conn:
            await conn.execute(
                "UPDATE tickets SET status = 'closed', tech_thread_id = NULL WHERE user_id = $1",
                user_id
            )

        user_info = await bot.get_chat(user_id)
        username = f"@{user_info.username}" if user_info.username else f"user{user_id}"
        topic_name_ru = get_topic_display(topic)
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

        if tech_thread_id:
            tech_topic_name = f"🔒 ТЕХ: {topic_name_ru} - id{user_id}"
            try:
                await bot.edit_forum_topic(
                    chat_id=TECH_SUPPORT_CHAT_ID,
                    message_thread_id=tech_thread_id,
                    name=tech_topic_name
                )
            except TelegramAPIError as exc:
                logger.warning(f"Failed to rename tech topic for user {user_id}: {exc}")

            close_notice = "❗️ Тикет закрыт командой поддержки."
            support_link = build_topic_url(SUPPORT_CHAT_ID, thread_id)
            if support_link:
                close_notice += f'\n<a href="{support_link}">Перейти к диалогу</a>'

            try:
                await bot.send_message(
                    chat_id=TECH_SUPPORT_CHAT_ID,
                    text=close_notice,
                    message_thread_id=tech_thread_id,
                    parse_mode="HTML"
                )
            except TelegramAPIError as exc:
                logger.warning(f"Failed to notify tech chat about closure for user {user_id}: {exc}")

            try:
                await bot.close_forum_topic(
                    chat_id=TECH_SUPPORT_CHAT_ID,
                    message_thread_id=tech_thread_id
                )
            except TelegramAPIError as exc:
                logger.error(f"Failed to close tech thread for user {user_id}: {exc}")

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
        await save_ticket_message(user_id, message.message_id, SUPPORT_CHAT_ID, thread_id)
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

        await update_ticket_support_activity(user_id)

    except Exception as e:
        logger.error(f"Error forwarding to user {user_id}: {e}")
