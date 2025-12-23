"""
Конфигурация бота
"""
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Telegram Bot Token
    BOT_TOKEN: str
    
    # База данных
    # Для Railway с volume используем /data/bot.db
    # Для локальной разработки используем ./bot.db
    DATABASE_URL: str = "sqlite+aiosqlite:///./bot.db"
    
    # Канал для публикации постов
    CHANNEL_ID: str
    
    # Модераторы (через запятую, user_id)
    MODERATORS: str = ""
    
    # Smart Glocal (для оплаты картой через Telegram)
    PROVIDER_TOKEN: Optional[str] = None  # Токен провайдера от Smart Glocal Bot
    
    # Stripe (опционально, для будущего использования)
    STRIPE_SECRET_KEY: Optional[str] = None
    STRIPE_PUBLIC_KEY: Optional[str] = None
    
    # Webhook для Stripe (опционально)
    STRIPE_WEBHOOK_SECRET: Optional[str] = None
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Создаем экземпляр настроек
settings = Settings()

# Парсим список модераторов
MODERATOR_IDS = [
    int(mod_id.strip()) 
    for mod_id in settings.MODERATORS.split(",") 
    if mod_id.strip().isdigit()
] if settings.MODERATORS else []

# Экспортируем для удобства
CHANNEL_ID = settings.CHANNEL_ID

