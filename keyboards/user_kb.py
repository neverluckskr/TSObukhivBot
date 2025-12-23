"""
Клавиатуры для пользователей
"""
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)


def get_main_menu() -> InlineKeyboardMarkup:
    """Главное меню"""
    keyboard = [
        [InlineKeyboardButton(text="📝 Отправить пост в канал", callback_data="send_free")],
        [InlineKeyboardButton(text="💰 Пост про подики/жидкости (35 грн)", callback_data="send_35")],
        [InlineKeyboardButton(text="🎯 Пост не по тематике (50 грн)", callback_data="send_50")],
        [InlineKeyboardButton(text="ℹ️ Подробности о боте", callback_data="help")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_payment_menu(amount: int) -> InlineKeyboardMarkup:
    """Меню выбора способа оплаты"""
    keyboard = [
        [InlineKeyboardButton(text="⭐ Оплатить Stars", callback_data=f"pay_stars_{amount}")],
        [InlineKeyboardButton(text="💳 Оплатить картой", callback_data=f"pay_stripe_{amount}")],
        [InlineKeyboardButton(text="« Назад", callback_data="back_to_menu")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_cancel_button() -> InlineKeyboardMarkup:
    """Кнопка отмены"""
    keyboard = [
        [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_action")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_main_reply_keyboard() -> ReplyKeyboardMarkup:
    """Главная Reply-клавиатура (снизу экрана)"""
    keyboard = [
        [KeyboardButton(text="📝 Отправить бесплатный пост")],
        [KeyboardButton(text="💰 Отправить пост про подики, жидкости")],
        [KeyboardButton(text="🎯 Отправить пост не по тематике")],
    ]
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
    )

