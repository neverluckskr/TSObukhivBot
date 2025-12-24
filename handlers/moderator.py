"""
Обработчики для модераторов
"""
import logging
from datetime import datetime
from functools import wraps

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import CHANNEL_ID, MODERATOR_IDS
from database.db import get_db
from database.models import Post, User
from keyboards.moderator_kb import get_moderation_keyboard, get_user_info_keyboard
from states.states import ModerationStates
from utils.helpers import format_user_info, is_moderator
from utils.texts import POST_APPROVED_MESSAGE, POST_REJECTED_TEMPLATE

logger = logging.getLogger(__name__)
router = Router()


def moderator_only(func):
    """Декоратор для проверки прав модератора"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        message_or_callback = args[0]
        user_id = message_or_callback.from_user.id if hasattr(message_or_callback, 'from_user') else message_or_callback.message.from_user.id
        
        if not is_moderator(user_id):
            if isinstance(message_or_callback, CallbackQuery):
                await message_or_callback.answer("❌ У тебя нет прав модератора.", show_alert=True)
            else:
                await message_or_callback.answer("❌ У тебя нет прав модератора.")
            return
        
        return await func(*args, **kwargs)
    return wrapper


@router.message(Command("stats"))
@moderator_only
async def cmd_stats(message: Message):
    """Статистика постов"""
    async for session in get_db():
        # Подсчитываем статистику
        total_posts = await session.scalar(select(func.count(Post.post_id)))
        pending_posts = await session.scalar(select(func.count(Post.post_id)).filter(Post.status == "pending"))
        approved_posts = await session.scalar(select(func.count(Post.post_id)).filter(Post.status == "approved"))
        rejected_posts = await session.scalar(select(func.count(Post.post_id)).filter(Post.status == "rejected"))
        
        stats_text = f"""📊 Статистика постов

Всего постов: {total_posts or 0}
⏳ На модерации: {pending_posts or 0}
✅ Одобрено: {approved_posts or 0}
❌ Отклонено: {rejected_posts or 0}"""
        
        await message.answer(stats_text)


@router.callback_query(F.data.startswith("approve_"))
@moderator_only
async def approve_post(callback: CallbackQuery):
    """Одобрение поста"""
    bot = callback.bot
    
    post_id = int(callback.data.split("_")[1])
    
    async for session in get_db():
        post = await session.get(Post, post_id)
        if not post:
            await callback.answer("❌ Пост не найден.", show_alert=True)
            return
        
        if post.status != "pending":
            await callback.answer("❌ Пост уже обработан.", show_alert=True)
            return
        
        # Обновляем статус
        post.status = "approved"
        post.moderated_at = datetime.utcnow()
        post.moderator_id = callback.from_user.id
        await session.commit()
        
        # Публикуем в канал
        try:
            if post.media_file_id:
                # Пытаемся отправить как фото, если не получится - как документ
                try:
                    sent_message = await bot.send_photo(
                        CHANNEL_ID,
                        post.media_file_id,
                        caption=post.content,
                    )
                except Exception:
                    # Если фото не получилось, пробуем как документ
                    sent_message = await bot.send_document(
                        CHANNEL_ID,
                        post.media_file_id,
                        caption=post.content,
                    )
            else:
                sent_message = await bot.send_message(
                    CHANNEL_ID,
                    post.content,
                )
            
            post.channel_message_id = sent_message.message_id
            await session.commit()
            
            # Уведомляем пользователя
            try:
                await bot.send_message(
                    post.user_id,
                    POST_APPROVED_MESSAGE,
                )
            except Exception as e:
                logger.warning(f"Не удалось отправить уведомление пользователю {post.user_id}: {e}")
            
            await callback.answer("✅ Пост одобрен и опубликован!")
            current_text = callback.message.text or callback.message.caption or "Пост одобрен"
            await callback.message.edit_text(
                current_text + "\n\n✅ ОДОБРЕНО",
                reply_markup=None,
            )
        except Exception as e:
            error_msg = str(e)
            if "chat not found" in error_msg.lower():
                await callback.answer(
                    "❌ Бот не может публиковать в канал. Проверьте:\n"
                    "1. Бот добавлен в канал как администратор\n"
                    "2. У бота есть права на публикацию сообщений\n"
                    "3. CHANNEL_ID указан правильно",
                    show_alert=True,
                )
            else:
                await callback.answer(f"❌ Ошибка публикации: {error_msg}", show_alert=True)
            logger.error(f"Ошибка публикации поста {post_id}: {e}")


@router.callback_query(F.data.startswith("reject_"))
@moderator_only
async def reject_post(callback: CallbackQuery, state: FSMContext):
    """Отказ в публикации поста"""
    post_id = int(callback.data.split("_")[1])
    
    async for session in get_db():
        post = await session.get(Post, post_id)
        if not post:
            await callback.answer("❌ Пост не найден.", show_alert=True)
            return
        
        if post.status != "pending":
            await callback.answer("❌ Пост уже обработан.", show_alert=True)
            return
    
    # Сохраняем post_id в состоянии
    await state.update_data(post_id=post_id)
    await state.set_state(ModerationStates.waiting_rejection_reason)
    
    current_text = callback.message.text or callback.message.caption or "Пост отклонен"
    await callback.message.edit_text(
        current_text + "\n\n❌ ОТКЛОНЕНО\n\nВведите причину отказа:",
        reply_markup=None,
    )
    await callback.answer("Введите причину отказа")


@router.message(ModerationStates.waiting_rejection_reason)
@moderator_only
async def receive_rejection_reason(message: Message, state: FSMContext):
    """Получение причины отказа от модератора"""
    bot = message.bot
    
    data = await state.get_data()
    post_id = data.get("post_id")
    
    if not post_id:
        await message.answer("❌ Ошибка. Попробуйте снова.")
        await state.clear()
        return
    
    reason = message.text or "Причина не указана"
    
    async for session in get_db():
        post = await session.get(Post, post_id)
        if not post:
            await message.answer("❌ Пост не найден.")
            await state.clear()
            return
        
        # Обновляем статус
        post.status = "rejected"
        post.rejection_reason = reason
        post.moderated_at = datetime.utcnow()
        post.moderator_id = message.from_user.id
        await session.commit()
        
        # Уведомляем пользователя
        try:
            await bot.send_message(
                post.user_id,
                POST_REJECTED_TEMPLATE.format(reason=reason),
            )
        except Exception as e:
            print(f"Ошибка отправки уведомления пользователю {post.user_id}: {e}")
    
    await message.answer("✅ Пользователь уведомлен об отказе.")
    await state.clear()


# --- Редактирование поста модератором ---
@router.callback_query(F.data.startswith("edit_"))
@moderator_only
async def edit_post(callback: CallbackQuery, state: FSMContext):
    """Запрашиваем у модератора новый контент для поста"""
    post_id = int(callback.data.split("_")[1])

    # Сохраняем идентификаторы для последующей отправки
    await state.update_data(edit_post_id=post_id, edit_chat_id=callback.message.chat.id, edit_message_id=callback.message.message_id)
    await state.set_state(ModerationStates.waiting_edit_content)

    current_text = callback.message.text or callback.message.caption or ""
    await callback.message.edit_text(
        current_text + "\n\n✏️ Отправьте новый текст поста (можно прикрепить фото/видео/документ). После отправки вы сможете одобрить пост.",
        reply_markup=None,
    )
    await callback.answer("Отправьте новый текст и/или медиа для поста.")


@router.message(ModerationStates.waiting_edit_content)
@moderator_only
async def receive_edited_content(message: Message, state: FSMContext):
    """Получаем от модератора отредактированный контент и обновляем пост"""
    data = await state.get_data()
    post_id = data.get("edit_post_id")
    chat_id = data.get("edit_chat_id")
    message_id = data.get("edit_message_id")

    if not post_id:
        await message.answer("❌ Ошибка. Повторите операцию.")
        await state.clear()
        return

    content = message.text or message.caption or ""
    if not content.strip() and not message.photo and not message.video and not message.document:
        await message.answer("❌ Контент не может быть пустым. Отправьте текст или вложение.")
        return

    media_file_id = None
    if message.photo:
        media_file_id = message.photo[-1].file_id
    elif message.video:
        media_file_id = message.video.file_id
    elif message.document:
        media_file_id = message.document.file_id

    async for session in get_db():
        post = await session.get(Post, post_id)
        if not post:
            await message.answer("❌ Пост не найден.")
            await state.clear()
            return

        # Обновляем пост
        post.content = content
        if media_file_id:
            post.media_file_id = media_file_id
        await session.commit()

        # Удалим старое сообщение модератора и отправим обновленное
        try:
            await message.bot.delete_message(chat_id, message_id)
        except Exception:
            pass

        user = await session.get(User, post.user_id)
        try:
            # Проверим, есть ли ещё посты в ожидании и передадим кнопку "Одобрить всех" при необходимости
            pending_count = await session.scalar(select(func.count(Post.post_id)).filter(Post.status == "pending"))
            include_approve_all = (pending_count or 0) > 1

            if post.media_file_id:
                # Если есть медиа — пробуем отправить как фото, иначе как документ
                try:
                    await message.bot.send_photo(
                        chat_id,
                        post.media_file_id,
                        caption=format_post_for_moderator(post, user),
                        reply_markup=get_moderation_keyboard(post.post_id, user.user_id, include_approve_all=include_approve_all),
                    )
                except Exception:
                    await message.bot.send_document(
                        chat_id,
                        post.media_file_id,
                        caption=format_post_for_moderator(post, user),
                        reply_markup=get_moderation_keyboard(post.post_id, user.user_id, include_approve_all=include_approve_all),
                    )
            else:
                await message.bot.send_message(
                    chat_id,
                    format_post_for_moderator(post, user),
                    reply_markup=get_moderation_keyboard(post.post_id, user.user_id, include_approve_all=include_approve_all),
                )
        except Exception as e:
            logger.warning(f"Не удалось отправить модератору обновлённый пост: {e}")

    await message.answer("✅ Пост обновлён. Можешь одобрить его.")
    await state.clear()


@router.callback_query(F.data == "approve_all")
@moderator_only
async def approve_all_callback(callback: CallbackQuery):
    """Одобрить все посты, находящиеся в статусе pending (через кнопку)"""
    bot = callback.bot
    approved = 0
    failed = 0

    async for session in get_db():
        pending_posts = (await session.scalars(select(Post).filter(Post.status == "pending"))).all()
        for post in pending_posts:
            try:
                if post.media_file_id:
                    try:
                        sent_message = await bot.send_photo(
                            CHANNEL_ID,
                            post.media_file_id,
                            caption=post.content,
                        )
                    except Exception:
                        sent_message = await bot.send_document(
                            CHANNEL_ID,
                            post.media_file_id,
                            caption=post.content,
                        )
                else:
                    sent_message = await bot.send_message(
                        CHANNEL_ID,
                        post.content,
                    )

                post.channel_message_id = sent_message.message_id
                post.status = "approved"
                post.moderated_at = datetime.utcnow()
                post.moderator_id = callback.from_user.id
                await session.commit()

                try:
                    await bot.send_message(post.user_id, POST_APPROVED_MESSAGE)
                except Exception:
                    pass

                approved += 1
            except Exception as e:
                logger.error(f"Ошибка при массовом одобрении поста {post.post_id}: {e}")
                failed += 1

    await callback.answer(f"✅ Одобрено: {approved}\n❌ Ошибок: {failed}", show_alert=True)
    try:
        await callback.message.edit_text((callback.message.text or "") + f"\n\n✅ Массово одобрено: {approved}, ❌ Ошибок: {failed}", reply_markup=None)
    except Exception:
        pass


@router.callback_query(F.data.startswith("ban_user_"))
@moderator_only
async def ban_user(callback: CallbackQuery):
    """Забанить пользователя"""
    user_id = int(callback.data.split("_")[2])

    async for session in get_db():
        user = await session.get(User, user_id)
        if not user:
            await callback.answer("❌ Пользователь не найден.", show_alert=True)
            return

        user.is_banned = True
        await session.commit()

    await callback.answer("✅ Пользователь забанен.", show_alert=True)
    current_text = callback.message.text or callback.message.caption or "Пользователь"
    await callback.message.edit_text(
        current_text + "\n\n🚫 ЗАБАНЕН",
        reply_markup=get_user_info_keyboard(user_id),
    )


@router.callback_query(F.data.startswith("unban_user_"))
@moderator_only
async def unban_user(callback: CallbackQuery):
    """Разбанить пользователя"""
    user_id = int(callback.data.split("_")[2])
    
    async for session in get_db():
        user = await session.get(User, user_id)
        if not user:
            await callback.answer("❌ Пользователь не найден.", show_alert=True)
            return
        
        user.is_banned = False
        await session.commit()
        
        await callback.answer("✅ Пользователь разбанен.", show_alert=True)
        current_text = callback.message.text or callback.message.caption or "Пользователь"
        await callback.message.edit_text(
            current_text + "\n\n✅ РАЗБАНЕН",
            reply_markup=get_user_info_keyboard(user_id),
        )

