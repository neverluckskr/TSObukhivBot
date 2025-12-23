"""
Клавиатуры для модераторов
"""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def get_moderation_keyboard(post_id: int, user_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для модерации поста"""
    keyboard = [
        [
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_{post_id}"),
            InlineKeyboardButton(text="❌ Отказать", callback_data=f"reject_{post_id}"),
        ],
        [InlineKeyboardButton(text="👤 Инфо о пользователе", callback_data=f"user_info_{user_id}")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_user_info_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Клавиатура с действиями для пользователя"""
    keyboard = [
        [
            InlineKeyboardButton(text="🚫 Забанить", callback_data=f"ban_user_{user_id}"),
            InlineKeyboardButton(text="✅ Разбанить", callback_data=f"unban_user_{user_id}"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

