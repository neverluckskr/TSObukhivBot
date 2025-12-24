"""
Клавиатуры для модераторов
"""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def get_moderation_keyboard(post_id: int, user_id: int, include_approve_all: bool = False, offset: int = 0, total: int = 0, is_owner: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура для модерации поста с пагинацией"""
    keyboard = [
        [
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_{post_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{post_id}"),
        ],
        [
            InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_{post_id}"),
        ],
        [
            InlineKeyboardButton(text="👤 Инфо", callback_data=f"user_info_{user_id}"),
            InlineKeyboardButton(text="🚫 Бан", callback_data=f"confirm_ban_{user_id}"),
        ],
    ]

    # Навигация между постами
    if total and total > 1:
        nav_row = []
        if offset > 0:
            nav_row.append(InlineKeyboardButton(text="◀️", callback_data=f"moderator_page_{offset - 1}"))
        else:
            nav_row.append(InlineKeyboardButton(text="·", callback_data="noop"))

        nav_row.append(InlineKeyboardButton(text=f"📄 {offset + 1}/{total}", callback_data="noop"))

        if offset < total - 1:
            nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"moderator_page_{offset + 1}"))
        else:
            nav_row.append(InlineKeyboardButton(text="·", callback_data="noop"))

        keyboard.append(nav_row)

    if include_approve_all:
        keyboard.append([
            InlineKeyboardButton(text="⚡ Одобрить все посты", callback_data="confirm_approve_all"),
        ])

    # Кнопка назад в главное меню
    keyboard.append([
        InlineKeyboardButton(text="↩️ Главное меню", callback_data="moderator_menu"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)  


def get_user_info_keyboard(user_id: int, is_banned: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура с действиями для пользователя"""
    keyboard = []
    
    # Показываем кнопку бана/разбана в зависимости от статуса
    if is_banned:
        keyboard.append([
            InlineKeyboardButton(text="✅ Разбанить", callback_data=f"confirm_unban_{user_id}"),
        ])
    else:
        keyboard.append([
            InlineKeyboardButton(text="🚫 Забанить", callback_data=f"confirm_ban_{user_id}"),
        ])
    
    keyboard.extend([
        [
            InlineKeyboardButton(text="📄 Посты пользователя", callback_data=f"user_posts_{user_id}_0"),
        ],
        [
            InlineKeyboardButton(text="⚠️ Предупредить", callback_data=f"warn_user_{user_id}"),
        ],
        [
            InlineKeyboardButton(text="↩️ Назад к модерации", callback_data="moderator_page_0"),
            InlineKeyboardButton(text="🏠 Главное меню", callback_data="moderator_menu"),
        ],
    ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_moderator_main_keyboard(pending_posts: int = 0, pending_requests: int = 0, is_owner: bool = False) -> InlineKeyboardMarkup:
    """Главная панель модератора с быстрыми действиями"""
    keyboard = [
        [
            InlineKeyboardButton(
                text=f"📥 Посты на модерации ({pending_posts})" if pending_posts else "📥 Посты (нет)",
                callback_data="moderator_posts"
            ),
        ],
        [
            InlineKeyboardButton(
                text=f"📝 Заявки на вступление ({pending_requests})" if pending_requests else "📝 Заявки (нет)",
                callback_data="moderator_requests"
            ),
        ],
        [
            InlineKeyboardButton(text="📊 Статистика", callback_data="moderator_stats"),
        ],
    ]

    # Только для владельца — управление модераторами
    if is_owner:
        keyboard.append([
            InlineKeyboardButton(text="👑 Управление модераторами", callback_data="moderator_add_mods"),
        ])

    keyboard.append([
        InlineKeyboardButton(text="🔄 Обновить", callback_data="moderator_refresh"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard) 

