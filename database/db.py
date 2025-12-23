"""
Подключение к базе данных и инициализация
"""
import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import sessionmaker

from config import settings
from database.models import Base, User, Post, Payment, Moderator


# Функция для получения правильного DATABASE_URL
def get_database_url() -> str:
    """Получить URL базы данных с учетом volume на Railway"""
    # Если есть /data директория (Railway volume), используем её
    if os.path.exists("/data") and settings.DATABASE_URL.startswith("sqlite+aiosqlite:///./"):
        db_path = "/data/bot.db"
        return f"sqlite+aiosqlite:///{db_path}"
    
    return settings.DATABASE_URL


# Создаем движок БД
database_url = get_database_url()
engine = create_async_engine(
    database_url,
    echo=False,
    future=True,
)

# Создаем фабрику сессий
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """Инициализация базы данных (создание таблиц)"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Получение сессии БД (для dependency injection)"""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# Вспомогательные функции для работы с БД
async def get_or_create_user(session: AsyncSession, user_id: int, username: str = None, first_name: str = None) -> User:
    """Получить или создать пользователя"""
    user = await session.get(User, user_id)
    if not user:
        user = User(
            user_id=user_id,
            username=username,
            first_name=first_name,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


async def create_post(
    session: AsyncSession,
    user_id: int,
    post_type: str,
    content: str,
    media_file_id: str = None,
) -> Post:
    """Создать пост"""
    post = Post(
        user_id=user_id,
        post_type=post_type,
        content=content,
        media_file_id=media_file_id,
        status="pending",
    )
    session.add(post)
    await session.commit()
    await session.refresh(post)
    return post


async def create_payment(
    session: AsyncSession,
    user_id: int,
    post_type: str,
    amount: float,
    currency: str,
    payment_method: str,
    transaction_id: str = None,
) -> Payment:
    """Создать платеж"""
    payment = Payment(
        user_id=user_id,
        post_type=post_type,
        amount=amount,
        currency=currency,
        payment_method=payment_method,
        transaction_id=transaction_id,
        status="pending",
    )
    session.add(payment)
    await session.commit()
    await session.refresh(payment)
    return payment

