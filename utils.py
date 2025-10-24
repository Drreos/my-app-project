import random
import string
import logging
from html import escape
from typing import List, Optional, Dict, NamedTuple, Callable, Union  # Явно указываем Optional
from dataclasses import dataclass
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, InputMediaVideo, InputMediaAnimation

logger = logging.getLogger(__name__)

_UTF_16 = 'utf-16-le'

class _Tag(NamedTuple):
    opening: str
    closing: str

@dataclass
class _PositionChange:
    to_open: List[_Tag]
    to_close: List[_Tag]
    br: bool

_TagMakerFunction = Callable[[object, str], _Tag]

def _url_conv(entity, s: str) -> _Tag:
    return _Tag(f'<a href="{escape(s)}">', '</a>')

_ENTITIES_TO_TAG: Dict[str, Union[None, _Tag, _TagMakerFunction]] = {
    'bold': _Tag('<b>', '</b>'),
    'italic': _Tag('<i>', '</i>'),
    'code': _Tag('<code>', '</code>'),
    'pre': _Tag('<pre>', '</pre>'),
    'strikethrough': _Tag('<s>', '</s>'),
    'spoiler': _Tag('<tg-spoiler>', '</tg-spoiler>'),
    'underline': _Tag('<u>', '</u>'),
    'text_link': lambda e, s: _Tag(f'<a href="{escape(e.url)}">', '</a>'),
    'url': _url_conv,
    'blockquote': _Tag('<blockquote>', '</blockquote>'),
    'phone': None,
    'hashtag': None,
}

class MessageToHtmlConverter:
    def __init__(self, message: Optional[str], entities: Optional[List[object]], buttons: Optional[List] = None):
        self.html = ''
        self.buttons = buttons
        logger.debug(f"Initializing converter: text={message}, entities={entities}, buttons={buttons}")
        if message is None:
            logger.debug("Text is missing")
            self.html = ''
            return
        if not entities:
            self.html = message
            logger.debug(f"No entities, preserving HTML: {self.html}")
            return

        self._message = message
        self._message_b16 = message.encode(_UTF_16)
        self._positions: Dict[int, _PositionChange] = {}
        self._ensure_position_exists(0)
        self._ensure_position_exists(len(self._message_b16))
        self._prepare_entity_positions_utf16le(entities)
        self._prepare_br_positions()

        separations_points = list(sorted(self._positions.keys()))
        opened_tags: List[_Tag] = []
        for pos in range(len(separations_points)):
            index = separations_points[pos]
            next_index = None if pos == len(separations_points) - 1 else separations_points[pos + 1]
            unchanged_part = self._message_b16[index:next_index].decode(_UTF_16)
            for t in self._positions[index].to_close:
                if opened_tags:
                    opened_tags.pop()
                self.html += t.closing
            if self._positions[index].br:
                self.html += "\n"
            for t in self._positions[index].to_open:
                opened_tags.append(t)
                self.html += t.opening
            self.html += escape(unchanged_part.replace('\n', ''))
        logger.debug(f"Generated HTML: {self.html}")

    def _prepare_br_positions(self):
        for i in range(len(self._message)):
            if self._message[i] == '\n':
                i_utf16 = len(self._message[:i].encode(_UTF_16))
                self._ensure_position_exists(i_utf16)
                self._positions[i_utf16].br = True
        logger.debug(f"Newline positions: {self._positions}")

    def _prepare_entity_positions_utf16le(self, entities: Optional[List[object]]) -> None:
        if not entities:
            logger.debug("No entities provided")
            return
        for e in entities:
            entity_type = e.type
            logger.debug(f"Processing entity: type={entity_type}, offset={e.offset}, length={e.length}, url={getattr(e, 'url', None)}")
            start = e.offset * 2
            end = (e.offset + e.length) * 2
            self._ensure_position_exists(start)
            self._ensure_position_exists(end)
            tag = _ENTITIES_TO_TAG.get(entity_type)
            if tag is None:
                logger.debug(f"No tag for entity type: {entity_type}")
                continue
            if callable(tag):
                txt_bytes = self._message_b16[start:end]
                txt = txt_bytes.decode(_UTF_16)
                tag = tag(e, txt)
                logger.debug(f"Dynamic tag created: {tag}")
            self._positions[start].to_open.append(tag)
            self._positions[end].to_close.insert(0, tag)
        logger.debug(f"Entity positions: {self._positions}")

    def _ensure_position_exists(self, i: int):
        if i not in self._positions:
            self._positions[i] = _PositionChange([], [], False)

    def get_reply_markup(self) -> Optional[InlineKeyboardMarkup]:
        if not self.buttons:
            logger.debug("No buttons provided")
            return None
        processed = []
        for row in self.buttons:
            processed_row = []
            if isinstance(row, list):
                buttons = row
            elif hasattr(row, 'buttons'):
                buttons = row.buttons
            else:
                logger.warning(f"Invalid button row: {row}")
                buttons = []
            for button in buttons:
                logger.debug(f"Processing button: {button}")
                if hasattr(button, 'url') and button.url:
                    # Проверяем корректность URL
                    url = button.url
                    if not url.startswith(('http://', 'https://')):
                        logger.warning(f"Invalid URL in button: {url}, adding https://")
                        url = f"https://{url}"
                    processed_row.append(InlineKeyboardButton(text=button.text, url=url))
                elif hasattr(button, 'callback_data') and button.callback_data:
                    processed_row.append(InlineKeyboardButton(text=button.text, callback_data=button.callback_data))
                else:
                    logger.warning(f"Invalid button: {button}")
            if processed_row:
                processed.append(processed_row)
        if not processed:
            logger.warning("No valid buttons processed")
            return None
        markup = InlineKeyboardMarkup(inline_keyboard=processed)
        logger.debug(f"Generated reply_markup: {markup}")
        return markup

def generate_ticket_id() -> str:
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))


def build_topic_url(chat_id: int, thread_id: Optional[int]) -> Optional[str]:
    if chat_id is None or thread_id is None:
        return None
    if chat_id >= 0:
        return None
    base = abs(chat_id) - 1_000_000_000_000
    if base <= 0:
        return None
    return f"https://t.me/c/{base}/{thread_id}"
