"""
Клавиатуры для модераторов
"""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def get_moderation_keyboard(post_id: int, user_id: int, include_approve_all: bool = False, offset: int = 0, total: int = 0, is_owner: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура для модерации поста с пагинацией"""
    keyboard = [
        [
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_{post_id}"),
            InlineKeyboardButton(text="❌ Отказать", callback_data=f"reject_{post_id}"),
        ],
        [
            InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_{post_id}"),
            InlineKeyboardButton(text="👤 Инфо о пользователе", callback_data=f"user_info_{user_id}"),
        ],
    ]

    # Навигация между постами
    if total and total > 1:
        nav_row = []
        if offset > 0:
            nav_row.append(InlineKeyboardButton(text="◀️ Предыдущий", callback_data=f"moderator_page_{offset - 1}"))
        else:
            nav_row.append(InlineKeyboardButton(text="◀️", callback_data=f"noop"))

        nav_row.append(InlineKeyboardButton(text=f"{offset + 1}/{total}", callback_data=f"noop"))

        if offset < total - 1:
            nav_row.append(InlineKeyboardButton(text="Следующий ▶️", callback_data=f"moderator_page_{offset + 1}"))
        else:
            nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"noop"))

        keyboard.append(nav_row)

    if include_approve_all:
        keyboard.append([
            InlineKeyboardButton(text="⚠️ Подтвердить массовое одобрение", callback_data="confirm_approve_all"),
        ])

    # Кнопка для владельца: добавить модератора
    if is_owner:
        keyboard.append([
            InlineKeyboardButton(text="➕ Добавить модератора", callback_data="add_moderator"),
        ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)  


def get_user_info_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Клавиатура с действиями для пользователя"""
    keyboard = [
        [
            InlineKeyboardButton(text="🚫 Забанить", callback_data=f"confirm_ban_{user_id}"),
            InlineKeyboardButton(text="✅ Разбанить", callback_data=f"confirm_unban_{user_id}"),
        ],
        [
            InlineKeyboardButton(text="📄 Просмотреть посты", callback_data=f"user_posts_{user_id}_0"),
            InlineKeyboardButton(text="⚠️ Предупредить", callback_data=f"warn_user_{user_id}"),
        ],
        [
            InlineKeyboardButton(text="↩️ Назад к модерации", callback_data=f"moderator_page_0"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

