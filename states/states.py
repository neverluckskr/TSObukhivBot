"""
FSM состояния для бота
"""
from aiogram.fsm.state import State, StatesGroup


class PostStates(StatesGroup):
    """Состояния для отправки постов"""
    # Бесплатный пост
    waiting_free_post = State()
    
    # Пост про подики/жидкости (35)
    waiting_payment_35 = State()
    waiting_ad_post = State()
    
    # Пост не по тематике (50)
    waiting_payment_50 = State()
    waiting_offtopic_post = State()


class ModerationStates(StatesGroup):
    """Состояния для модерации"""
    # Ожидание причины отказа от модератора
    waiting_rejection_reason = State()

