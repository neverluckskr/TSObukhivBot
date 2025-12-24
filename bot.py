"""
Основной файл запуска бота
"""
import asyncio
import logging
import sys

import aiohttp
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

# URL для авто-пинга (чтобы бот не засыпал)
PING_URL = "https://self-ping-guardian.vercel.app/health"
PING_INTERVAL = 450  # 5 минут (300 секунд)


async def set_bot_commands():
    """Установка команд бота"""
    commands = [
        BotCommand(command="start", description="Запустить бота"),
        BotCommand(command="send", description="Отправить бесплатный пост"),
        BotCommand(command="send35", description="Пост про подики/жидкости"),
        BotCommand(command="send50", description="Пост не по тематике (50 ⭐)"),
        BotCommand(command="status", description="Текущие условия"),
        BotCommand(command="moderator", description="Панель модератора"),
        BotCommand(command="help", description="Помощь"),
        BotCommand(command="cancel", description="Отменить действие"),
    ]
    await bot.set_my_commands(commands)


async def ping_keepalive():
    """Фоновая задача для периодического пинга (чтобы бот не засыпал)"""
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(PING_URL, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        logger.debug(f"Keepalive ping успешен: {response.status}")
                    else:
                        logger.warning(f"Keepalive ping вернул статус: {response.status}")
            except asyncio.TimeoutError:
                logger.warning("Keepalive ping: таймаут запроса")
            except Exception as e:
                logger.error(f"Ошибка keepalive ping: {e}")
            
            # Ждем перед следующим пингом
            await asyncio.sleep(PING_INTERVAL)


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
    
    # Запуск фоновой задачи для keepalive пинга
    ping_task = asyncio.create_task(ping_keepalive())
    logger.info(f"Авто-пингер запущен (интервал: {PING_INTERVAL} сек)")
    
    # Запуск polling
    logger.info("Бот запущен и готов к работе!")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        # Отменяем задачу пинга при остановке
        ping_task.cancel()
        try:
            await ping_task
        except asyncio.CancelledError:
            logger.info("Авто-пингер остановлен")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        sys.exit(1)

