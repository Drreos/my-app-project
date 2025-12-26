import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

API_TOKEN = os.getenv("API_TOKEN")
SUPPORT_CHAT_ID = int(os.getenv("SUPPORT_CHAT_ID", "-1002395996451"))
TECH_SUPPORT_CHAT_ID = int(os.getenv("TECH_SUPPORT_CHAT_ID", "0"))
MEDIA_GROUP_TIMEOUT = 2

def _parse_id_list(raw: str | None) -> list[int]:
    if not raw:
        return []
    ids: list[int] = []
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError:
            logger.warning("Invalid ID '%s' in owner list", part)
    return ids


SUPPORT_OWNER_IDS = _parse_id_list(os.getenv("SUPPORT_OWNER_IDS"))
legacy_support_owner = os.getenv("SUPPORT_OWNER_ID", "").strip()
if legacy_support_owner:
    try:
        legacy_id = int(legacy_support_owner)
        if legacy_id not in SUPPORT_OWNER_IDS:
            SUPPORT_OWNER_IDS.append(legacy_id)
    except ValueError:
        logger.warning("Invalid SUPPORT_OWNER_ID value: %s", legacy_support_owner)

TECH_OWNER_IDS = _parse_id_list(
    os.getenv("TECH_OWNER_IDS") or os.getenv("TECH_OWNER_ID") or os.getenv("TECH_WNER_ID")
)

# PostgreSQL settings
POSTGRES_USER = os.getenv("POSTGRES_USER", "botuser")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "botpassword")
POSTGRES_DB = os.getenv("POSTGRES_DB", "support_bot")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "db")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5433"))

# AI Assistant settings
AI_ENABLED = os.getenv("AI_ENABLED", "true").lower() == "true"
AI_API_KEY = os.getenv("OPENAI_API_KEY", "")
AI_MODEL = os.getenv("AI_MODEL", "gpt-4o-mini")
AI_MAX_TOKENS = int(os.getenv("AI_MAX_TOKENS", "1000"))
AI_TEMPERATURE = float(os.getenv("AI_TEMPERATURE", "0.7"))
AI_AUTO_RESPOND = os.getenv("AI_AUTO_RESPOND", "true").lower() == "true"
AI_MAX_RESPONSES = int(os.getenv("AI_MAX_RESPONSES", "2"))  # Максимум ответов ИИ до передачи оператору

# Auto-close settings
AUTO_CLOSE_ENABLED = os.getenv("AUTO_CLOSE_ENABLED", "true").lower() == "true"
AUTO_CLOSE_HOURS = int(os.getenv("AUTO_CLOSE_HOURS", "1"))  # Закрывать тикет если клиент не отвечает N часов

TOPICS = {
    "balance": "💰 Balance",
    "withdrop": "🎁️ Withdrawal",
    "bugs": "🆘 Bugs",
    "other": "📣 Other",
    "cooperation": "📬 Cooperation"
}

FAQ_QUESTIONS = {

    "balance":{
        "en": {
             "question1": "How to top up your balance?",
             "answer1": "To top up your balance, go to the <b>Profile</b> section, click the <b>“Deposit”</b> button and choose a convenient method:\n\n <blockquote><b>Telegram Stars\nToncoin\nTelegram Gifts</b></blockquote>",
             "question2": "Replenishment methods",
             "answer2": "Majestic offers four convenient ways to top up your balance — each comes with a bonus:\n\n 1️⃣ <b>Via Telegram Stars</b> — the simplest and fastest way to make a deposit directly within Telegram.\n To top up this way, go to the <b>“Top Up Balance”</b> section, select <b>“Telegram Stars”</b>, enter the desired amount, click <b>“Continue”</b>, and confirm the transaction.\n\n 2️⃣ <b>Via Toncoin</b> — when topping up with TON, you <b>receive a +10% bonus</b> on your deposit.\n To use this method, go to the <b>“Top Up Balance”</b> section, select <b>“Deposit Toncoin”</b>, enter the amount, click <b>“Connect Wallet”</b> (if not yet connected), and confirm the transaction.\n\n <b>3️⃣ Via CryptoBot</b> — topping up via CryptoBot gives you a <b>+5% bonus</b> on your deposit.\n To use this method, go to the <b>“Top Up Balance”</b> section, select <b>“Deposit CryptoBot”</b>, enter the amount, click <b>“Continue”</b>, and confirm the transaction via <b>@CryptoBot</b>.\n\n 4️⃣ <b>Via Telegram Gifts</b> — topping up with Telegram gifts gives you a <b>+20% bonus</b> on your deposit amount.\n The gift's in-game value includes the bonus. To use this method, go to the <b>“Top Up Balance”</b> section, select <b>“Deposit with Gifts”</b>, and <b>send a gift</b> to your current account.\n\n 🎁 <b>Bonuses are applied automatically</b> after every top-up and are reflected in your balance immediately.",
             "question3": "What should I do if the top-up didn’t arrive?",
             "answer3": "<b>Please wait a few minutes and refresh the page.</b> If the funds don’t appear within 15 minutes, contact support and we’ll check everything promptly.",
             "question4": "Which top-up method is the most profitable?",
             "answer4": "If you want to get the most out of it — choose <b>top-up via Gifts or Toncoin</b>.\n This will give you <b>+20% on the amount when topping up with Gifts</b> and <b>+10% on the amount when topping up with Toncoin</b>.",
        },
        "ru": {
            "question1": "Как пополнить баланс?",
            "answer1": "Чтобы пополнить баланс, перейдите в раздел <b>Профиль</b>, нажмите кнопку <b>«Пополнить»</b> и выберите удобный способ:\n\n <blockquote><b>Telegram Stars\nToncoin\nTelegram Подарки</b></blockquote>",
            "question2": "Способы пополнения",
            "answer2": "Majestic предлагает четыре удобных способа пополнения баланса — каждый из них дает бонус:\n\n 1️⃣ <b>Через Telegram Stars</b> — самый простой и быстрый способ пополнения прямо в Telegram.\n Чтобы пополнить таким способом, перейдите в раздел <b>«Пополнить баланс»</b>, выберите <b>«Telegram Stars»</b>, введите нужную сумму, нажмите <b>«Продолжить»</b> и подтвердите транзакцию.\n\n 2️⃣ <b>Через Toncoin</b> — при пополнении TON вы получаете <b>+10% бонуса</b> на депозит.\n Чтобы использовать этот метод, перейдите в раздел <b>«Пополнить баланс»</b>, выберите <b>«Пополнение Toncoin»</b>, введите сумму, нажмите <b>«Подключить кошелек»</b> (если еще не подключен) и подтвердите транзакцию.\n\n 3️⃣ <b>Через CryptoBot</b> — пополнение через CryptoBot дает вам <b>+5% бонуса</b> на депозит.\n Чтобы использовать этот метод, перейдите в раздел <b>«Пополнить баланс»</b>, выберите <b>«Пополнение CryptoBot»</b>, введите сумму, нажмите <b>«Продолжить»</b>, и подтвердите транзакцию через <b>@CryptoBot</b>.\n\n 4️⃣ <b>Через Telegram Подарки</b> — пополнение с помощью Telegram подарков дает вам <b>+20% бонуса</b> на сумму депозита.\n Cтоимость подарка в игре указана с учетом бонуса. Для пополнения баланса данным способом в разделе “Пополнение баланса” выберите пункт <b>“Пополнить подарками”</b> и <b>отправьте подарок</b> на текущий аккаунт.\n\n 🎁 <b>Бонусы начисляются автоматически</b> при каждом пополнении и отображаются на балансе сразу после зачисления средств.",
            "question3": "Что делать, если пополнение не пришло?",
            "answer3": "<b>Пожалуйста, подождите несколько минут и обновите страницу.</b> Если средства не начислились в течение 15 минут, свяжитесь с поддержкой, и мы оперативно все проверим.",
            "question4": "Какой способ пополнения самый выгодный",
            "answer4": "Если вы хотите получить максимальную выгоду — выбирайте <b>пополнение через Подарки или Toncoin</b>.\n Это даст вам <b>+20% на сумму при пополнении через Подарки</b> и <b>+10% на сумму при пополнении через Toncoin</b>."
        }
    },

    "withdrop": {
        "en": {
             "question1": "Why hasn’t my gift been withdrawn?",
             "answer1": "<b>Gift withdrawals in Majestic are processed automatically, usually within a few minutes.</b>\n However, due to high system load during certain periods, delays of up to 24 hours may occur.\n\n Some types of gifts may take up to 21 days to be delivered — depending on the gift type.\n\n We are actively working to make the prize delivery process even faster and more convenient. ",
             "question2": "How to withdraw gifts?",
             "answer2": "To withdraw gifts, follow these steps:\n\n 1️⃣ Go to the <b>“Gifts”</b> section in the app.\n 2️⃣ Select the gift you want to withdraw.\n3️⃣ Click the <b>“Withdraw”</b> button and confirm the transaction.\n\nPlease note that gifts are processed manually and may take up to 24 hours to be delivered.",
                      },
        "ru": {
            "question1": "Почему не вывели мой подарок?",
            "answer1": "Вывод подарков в Majestic осуществляется автоматически, как правило, в течение нескольких минут.\n Однако из-за высокой нагрузки на систему в отдельные периоды возможны задержки до 24 часов. \n\nНекоторые виды подарков могут доставляться до 21 дня — в зависимости от типа подарка.\n\nМы активно работаем над тем, чтобы сделать процесс получения призов ещё быстрее и удобнее.",
            "question2": "Как вывести подарки?",
            "answer2": "<blockquote><b>Чтобы вывести подарок, выполните следующие шаги:</b>\n 1. Перейдите в раздел <b>«Мои подарки»</b>.\n 2. Выберите подарок, который хотите вывести.\n 3. Нажмите кнопку <b>«Вывести»</b>.</blockquote>\n\n После этого статус подарка изменится — вы сможете <b>отслеживать его обработку прямо в этом разделе</b>.\n\n ⏳ Обработка подарков может занять некоторое время (в зависимости от типа подарка).",}
    },

    "bugs": {
        "en": {
            "question1": "Description inaccuracy or visual",
            "answer1": "",
            "question2": "Technical bug",
            "answer2": "",
            "question3": "Another bug",
            "answer3": ""
        },
        "ru": {
            "question1": "Неточное описание или картинка",
            "answer1": "",
            "question2": "Техническая ошибка",
            "answer2": "",
            "question3": "Другая ошибка",
            "answer3": ""
        }
    },

    "other": {
        "en": {
            "question1": "Referral Program",
            "answer1": "Earn more! Invite your friends via a unique link and get Telegram stars for each newcomer.\n\n<b>How to get rewards for inviting friends:</b>\n<blockquote>1. Open the “Friends” tab in the application.\n2. Tap the “Invite a Friend” button.\n3. Copy and share your personalized referral link.</blockquote>\n\n<b>Your bonuses for each invited friend:</b>\n<blockquote>1. You get <b>10% of their top-ups</b> in Telegram Stars — every time they make a deposit.</blockquote>\n\nYou can track all earnings and your referral balance directly in this section.\n\n<b>Tip:</b> Invite more friends to increase your steady income! If you have any questions, our support team is ready to help.",
            "question2": "Language",
            "answer2":  "To view the list of supported languages, follow these steps:\n\n<blockquote>1. Click on the bot avatar in the upper left corner of the screen.\n2. Scroll down to the bottom of the page.\n3. At the bottom of the screen you will find a toggle between the available languages.</blockquote>\n\nSelect your preferred language for a comfortable bot experience.",
            "question3": "<b>How to get free cases?</b>",
            "answer3": "Free cases are granted automatically if your <b>total top-up within a day exceeds 500 Telegram Stars.</b>",
        },

        "ru": {
            "question1": "Рефералы",
            "answer1": "<b>Зарабатывайте больше!</b> Приглашайте друзей по уникальной ссылке и получайте Telegram Stars за каждого нового участника.\n\n<b>Как получить награды за приглашения:</b>\n<blockquote>1. Откройте вкладку «Друзья» в приложении.\n2. Нажмите кнопку «Пригласить друга».\n3. Скопируйте и отправьте вашу персональную ссылку.</blockquote>\n\n<b>Ваши бонусы за каждого приглашённого:</b>\n<blockquote>1. Вы получаете <b>10% от всех пополнений</b> вашего друга в Telegram Stars.</blockquote>\n\nВы можете отслеживать все начисления и баланс по реферальной программе прямо в этом разделе.\n\n<b>Совет:</b> Приглашайте больше друзей, чтобы увеличить стабильный доход! Если возникнут вопросы — служба поддержки всегда рядом.",
            "question2": "Язык",
            "answer2": "Для просмотра списка поддерживаемых языков выполните следующие действия:\n\n<blockquote>1. Нажмите на аватар бота в левом верхнем углу экрана.\n2. Прокрутите страницу вниз до конца.\n3. В нижней части экрана вы найдете переключение между доступными языками.</blockquote>\n\nВыберите предпочитаемый язык для комфортного использования бота.",
            "question3": "Как получить бесплатные кейсы?",
            "answer3": "Бесплатные кейсы начисляются автоматически, если ваш <b>общий депозит в течение дня превышает 500 Telegram Stars.</b>",
        }
    }
}


TRANSLATIONS = {
    "en": {
        "start_screen": "Greetings! Here you can reach out to our @MajesticGameBot support team.\n\nPlease select a contact topic.",
        "select_language": "Please select a language:",
        "select_topic": "Select the most appropriate question from the list below.",
        "describe_issue": "📝 Please describe your problem in as much detail as possible. This will help us to solve your issue faster and more accurately.",
        "cooperation_message": "<b>📬 Cooperation</b>\n\nThank you for your interest in our game!\n\nFor any collaboration inquiries, please reach out to our PR department at:\n@majestic_ads",
        "error": "An error occurred. Please try again.",
        "back": "‹ Back",
        "contact_operator": "Contact operator",
        "contact_support_prompt": "If your issue persists, contact support.",
        "welcome_message": "Welcome! Please select a topic to get started.",
        "ticket_submitted": "Thank you for your request, our support team will review it in the order received.",
        "ticket_closed": "Thank you for contacting us. Based on our information, your issue has been resolved.\n\nIf you still need help, you can start a new conversation through the menu by sending /start.",
        "ticket_closed_message": "Your previous request has been closed, so the support team did not receive your last message. If you have any remaining questions, please contact us again by selecting the appropriate section in the menu below.",
        "ticket_already_open": "❌ <b>You already have an open support request.</b>\n\nWe are already working on it and will contact you as soon as possible. Thank you for your patience!",
        "message_sent": "",
        "command_start": "Start the bot",
        "command_lang": "Change language",
        "topics": {
            "balance": "💰 Balance",
            "withdrop": "🎁️ Withdrawal",
            "bugs": "🆘 Bugs",
            "other": "📣 Other",
            "cooperation": "📬 Cooperation"
        }
    },
    "ru": {
        "start_screen": "Приветствуем! Здесь вы можете связаться с поддержкой @MajesticGameBot.\n\nПожалуйста, выберите тему обращения.",
        "select_language": "Пожалуйста, выберите язык:",
        "select_topic": "Выберите наиболее подходящий вопрос из списка ниже.",
        "describe_issue": "📝 Пожалуйста, опишите вашу проблему максимально подробно. Это поможет нам быстрее и точнее решить ваш вопрос.",
        "cooperation_message": "<b>📬 Сотрудничество</b>\n\nБлагодарим вас за интерес к нашей игре!\n\nПо всем вопросам сотрудничества, пожалуйста, обращайтесь в наш PR-отдел по адресу:\n@majestic_ads",
        "error": "Произошла ошибка. Попробуйте снова.",
        "back": "‹ Назад",
        "contact_operator": "Связаться с оператором",
        "contact_support_prompt": "Если проблема сохраняется, свяжитесь с поддержкой.",
        "welcome_message": "Добро пожаловать! Пожалуйста, выберите тему для начала.",
        "ticket_submitted": "Спасибо за ваше обращение, наша команда поддержки рассмотрит его в порядке очереди.",
        "ticket_closed": "Спасибо, что связались с нами. На основании нашей информации, ваш вопрос решен.\n\nЕсли вам все еще нужна помощь, вы можете начать новый разговор через меню, отправив /start.",
        "ticket_closed_message": "Ваше предыдущее обращение закрыто, поэтому команда поддержки не получила ваше последнее сообщение. Если у вас остались вопросы, пожалуйста, свяжитесь с нами снова, выбрав соответствующую тему в меню ниже.",
        "ticket_already_open": "❌ <b>У вас есть открытый запрос в поддержке.</b>\n\nМы уже работаем над ним и свяжемся с вами в ближайшее время. Спасибо за терпение!",
        "message_sent": "",
        "command_start": "Запустить бота",
        "command_lang": "Сменить язык",
        "topics": {
            "balance": "💰 Баланс",
            "withdrop": "️🎁 Вывод подарков",
            "bugs": "🆘 Ошибки",
            "other": "📣 Другое",
            "cooperation": "📬 Сотрудничество"
        }

    }
}

DEFAULT_LANGUAGE = "en"
