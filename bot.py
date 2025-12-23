"""
Основной файл запуска бота
"""
import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from config import settings
from database.db import init_db
from handlers import moderator_router, payments_router, user_router

# Настройка логирования
# Для Railway логи идут в stdout, файл не нужен
import os
if os.getenv("RAILWAY_ENVIRONMENT"):
    # На Railway - только stdout
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
else:
    # Локально - файл + stdout
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler("bot.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )

logger = logging.getLogger(__name__)

# Создаем бота и диспетчер
bot = Bot(token=settings.BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


async def set_bot_commands():
    """Установка команд бота"""
    commands = [
        BotCommand(command="start", description="Запустить бота"),
        BotCommand(command="send", description="Отправить бесплатный пост"),
        BotCommand(command="send35", description="Пост про подики/жидкости (35 грн)"),
        BotCommand(command="send50", description="Пост не по тематике (50 грн)"),
        BotCommand(command="help", description="Помощь"),
        BotCommand(command="cancel", description="Отменить действие"),
    ]
    await bot.set_my_commands(commands)


async def main():
    """Главная функция"""
    logger.info("Запуск бота...")
    
    # Инициализация БД (путь к БД настраивается в database/db.py)
    try:
        await init_db()
        logger.info("База данных инициализирована")
    except Exception as e:
        logger.error(f"Ошибка инициализации БД: {e}")
        return
    
    # Регистрация роутеров
    dp.include_router(user_router)
    dp.include_router(moderator_router)
    dp.include_router(payments_router)
    
    # Установка команд
    await set_bot_commands()
    
    # Запуск polling
    logger.info("Бот запущен и готов к работе!")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        sys.exit(1)

