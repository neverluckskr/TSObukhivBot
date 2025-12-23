"""
Вспомогательные функции
"""
from datetime import datetime
from typing import Optional

from config import MODERATOR_IDS
from database.models import Post, User
from utils.texts import POST_TYPE_NAMES


def is_moderator(user_id: int) -> bool:
    """Проверка, является ли пользователь модератором"""
    return user_id in MODERATOR_IDS


def format_post_for_moderator(post: Post, user: User) -> str:
    """Форматирование поста для модератора"""
    post_type_name = POST_TYPE_NAMES.get(post.post_type, post.post_type)
    date_str = post.created_at.strftime("%d.%m.%Y, %H:%M") if post.created_at else "Неизвестно"
    
    return f"""🆕 Новый пост на модерацию

Тип: {post_type_name}
От: User ID: {user.user_id}
Username: @{user.username or 'не указан'}
Дата: {date_str}

Контент:
{post.content}"""


def format_user_info(user: User, posts_count: int = None) -> str:
    """Форматирование информации о пользователе"""
    reg_date = user.registration_date.strftime("%d.%m.%Y") if user.registration_date else "Неизвестно"
    ban_status = "🚫 Забанен" if user.is_banned else "✅ Активен"
    posts_info = f"{posts_count}" if posts_count is not None else "не загружено"
    
    return f"""👤 Информация о пользователе

ID: {user.user_id}
Username: @{user.username or 'не указан'}
Имя: {user.first_name or 'не указано'}
Статус: {ban_status}
Дата регистрации: {reg_date}
Всего постов: {posts_info}"""


def get_post_type_from_command(command: str) -> Optional[str]:
    """Получить тип поста из команды"""
    mapping = {
        "send": "free",
        "send35": "ad35",
        "send50": "offtopic50",
    }
    return mapping.get(command)

