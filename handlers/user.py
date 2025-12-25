"""
Обработчики команд пользователей
"""
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select

from config import CHANNEL_ID, MODERATOR_IDS, OWNER_IDS
from database.db import get_db, get_or_create_user, create_post
from database.models import User, Post, Moderator
from keyboards.moderator_kb import get_moderation_keyboard
from keyboards.user_kb import (
    get_main_menu,
    get_main_reply_keyboard,
    get_payment_menu,
)
from states.states import PostStates
from utils.helpers import format_post_for_moderator, is_moderator
from utils.texts import (
    ACTION_CANCELLED_MESSAGE,
    HELP_MESSAGE,
    POST_SENT_MESSAGE,
    REQUEST_POST_MESSAGE,
    START_MESSAGE,
    USER_BANNED_MESSAGE,
)

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message):
    """Обработчик команды /start"""
    # Регистрируем пользователя
    async for session in get_db():
        await get_or_create_user(
            session,
            message.from_user.id,
            message.from_user.username,
            message.from_user.first_name,
        )
    
    await message.answer(
        START_MESSAGE,
        reply_markup=get_main_reply_keyboard(),
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Обработчик команды /help"""
    await message.answer(HELP_MESSAGE, reply_markup=get_main_menu())


@router.message(Command("status"))
async def cmd_status(message: Message):
    """Обработчик команды /status - информация о текущих условиях"""
    from utils.texts import STATUS_MESSAGE
    await message.answer(STATUS_MESSAGE, reply_markup=get_main_menu())


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    """Обработчик команды /cancel"""
    await state.clear()
    await message.answer(ACTION_CANCELLED_MESSAGE, reply_markup=get_main_menu())


@router.message(Command("send"))
async def cmd_send(message: Message, state: FSMContext):
    """Обработчик команды /send (бесплатный пост)"""
    async for session in get_db():
        user = await session.get(User, message.from_user.id)
        if user and user.is_banned:
            await message.answer(USER_BANNED_MESSAGE)
            return
    
    await message.answer(REQUEST_POST_MESSAGE, reply_markup=None)
    await state.set_state(PostStates.waiting_free_post)


@router.message(lambda m: m.text == "📝 Отправить бесплатный пост")
async def process_send_free_button(message: Message, state: FSMContext):
    """Обработчик кнопки 'Отправить бесплатный пост'"""
    async for session in get_db():
        user = await session.get(User, message.from_user.id)
        if user and user.is_banned:
            await message.answer(USER_BANNED_MESSAGE)
            return
    
    await message.answer(REQUEST_POST_MESSAGE, reply_markup=None)
    await state.set_state(PostStates.waiting_free_post)


@router.message(Command("send35"))
async def cmd_send35(message: Message, state: FSMContext):
    """Обработчик команды /send35 (пост про подики/жидкости - временно бесплатно)"""
    async for session in get_db():
        user = await session.get(User, message.from_user.id)
        if user and user.is_banned:
            await message.answer(USER_BANNED_MESSAGE)
            return
    
    await message.answer(REQUEST_POST_MESSAGE, reply_markup=None)
    await state.set_state(PostStates.waiting_ad_post)


@router.message(lambda m: m.text == "💰 Отправить пост про подики, жидкости")
async def process_send_35_button(message: Message, state: FSMContext):
    """Обработчик кнопки 'Отправить пост про подики, жидкости' (временно бесплатно)"""
    async for session in get_db():
        user = await session.get(User, message.from_user.id)
        if user and user.is_banned:
            await message.answer(USER_BANNED_MESSAGE)
            return
    
    await message.answer(REQUEST_POST_MESSAGE, reply_markup=None)
    await state.set_state(PostStates.waiting_ad_post)


@router.message(Command("send50"))
async def cmd_send50(message: Message, state: FSMContext):
    """Обработчик команды /send50 (пост не по тематике)"""
    async for session in get_db():
        user = await session.get(User, message.from_user.id)
        if user and user.is_banned:
            await message.answer(USER_BANNED_MESSAGE)
            return
    
    await message.answer(
        "💰 Пост не по тематике\n\nСтоимость: 50 грн или 50 ⭐ Telegram Stars\n\nВыбери способ оплаты:",
        reply_markup=get_payment_menu(50),
    )
    await state.set_state(PostStates.waiting_payment_50)


@router.message(lambda m: m.text == "🎯 Отправить пост не по тематике")
async def process_send_50_button(message: Message, state: FSMContext):
    """Обработчик кнопки 'Отправить пост не по тематике'"""
    async for session in get_db():
        user = await session.get(User, message.from_user.id)
        if user and user.is_banned:
            await message.answer(USER_BANNED_MESSAGE)
            return
    
    await message.answer(
        "💰 Пост не по тематике\n\nСтоимость: 50 грн или 50 ⭐ Telegram Stars\n\nВыбери способ оплаты:",
        reply_markup=get_payment_menu(50),
    )
    await state.set_state(PostStates.waiting_payment_50)


@router.callback_query(F.data == "send_free")
async def process_send_free(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Отправить бесплатный пост'"""
    async for session in get_db():
        user = await session.get(User, callback.from_user.id)
        if user and user.is_banned:
            await callback.answer(USER_BANNED_MESSAGE, show_alert=True)
            return
    
    await callback.message.edit_text(REQUEST_POST_MESSAGE)
    await state.set_state(PostStates.waiting_free_post)
    await callback.answer()


@router.callback_query(F.data == "send_35")
async def process_send_35(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Пост про подики/жидкости' (временно бесплатно)"""
    async for session in get_db():
        user = await session.get(User, callback.from_user.id)
        if user and user.is_banned:
            await callback.answer(USER_BANNED_MESSAGE, show_alert=True)
            return
    
    await callback.message.edit_text(REQUEST_POST_MESSAGE)
    await state.set_state(PostStates.waiting_ad_post)
    await callback.answer()


@router.callback_query(F.data == "send_50")
async def process_send_50(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Пост не по тематике (50 грн)'"""
    async for session in get_db():
        user = await session.get(User, callback.from_user.id)
        if user and user.is_banned:
            await callback.answer(USER_BANNED_MESSAGE, show_alert=True)
            return
    
    await callback.message.edit_text(
        "💰 Пост не по тематике\n\nСтоимость: 50 грн или 50 ⭐ Telegram Stars\n\nВыбери способ оплаты:",
        reply_markup=get_payment_menu(50),
    )
    await state.set_state(PostStates.waiting_payment_50)
    await callback.answer()


@router.callback_query(F.data == "help")
async def process_help(callback: CallbackQuery):
    """Обработчик кнопки 'Подробности о боте'"""
    await callback.message.edit_text(HELP_MESSAGE, reply_markup=get_main_menu())
    await callback.answer()


@router.callback_query(F.data == "status")
async def process_status(callback: CallbackQuery):
    """Обработчик кнопки 'Текущие условия'"""
    from utils.texts import STATUS_MESSAGE
    await callback.message.edit_text(STATUS_MESSAGE, reply_markup=get_main_menu())
    await callback.answer()


@router.callback_query(F.data == "back_to_menu")
async def process_back_to_menu(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Назад'"""
    await state.clear()
    await callback.message.edit_text(START_MESSAGE, reply_markup=get_main_menu())
    await callback.answer()


@router.callback_query(F.data == "cancel_action")
async def process_cancel_action(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Отменить'"""
    await state.clear()
    await callback.message.edit_text(ACTION_CANCELLED_MESSAGE, reply_markup=get_main_menu())
    await callback.answer()


# Обработка постов
@router.message(PostStates.waiting_free_post)
async def receive_free_post(message: Message, state: FSMContext):
    """Обработка бесплатного поста"""
    bot = message.bot
    
    content = message.text or message.caption or ""
    if not content.strip():
        await message.answer("❌ Пост не может быть пустым. Отправь текст.")
        return
    
    media_file_id = None
    if message.photo:
        media_file_id = message.photo[-1].file_id
    elif message.video:
        media_file_id = message.video.file_id
    elif message.document:
        media_file_id = message.document.file_id
    
    # Сохраняем в БД
    async for session in get_db():
        user = await get_or_create_user(
            session,
            message.from_user.id,
            message.from_user.username,
            message.from_user.first_name,
        )
        
        if user.is_banned:
            await message.answer(USER_BANNED_MESSAGE)
            await state.clear()
            return
        
        post = await create_post(
            session,
            message.from_user.id,
            "free",
            content,
            media_file_id,
        )
        
        # Проверим, сколько постов в ожидании модерации, и добавим кнопку 'Одобрить всех' при необходимости
        pending_count = await session.scalar(select(func.count(Post.post_id)).filter(Post.status == "pending"))
        include_approve_all = (pending_count or 0) > 1

        # Собираем всех получателей: env-модераторы + модераторы из БД + владельцы
        db_mod_ids = (await session.scalars(select(Moderator.moderator_id))).all()
        recipient_ids = set(MODERATOR_IDS) | set(db_mod_ids) | set(OWNER_IDS)
        if not recipient_ids:
            logger.warning("Ни одна роль модератора не настроена: ни env, ни в БД. Уведомляю владельцев (OWNER_IDS).")
            recipient_ids = set(OWNER_IDS)
        sent_to_moderators = False
        for moderator_id in recipient_ids:
            try:
                if media_file_id:
                    if message.photo:
                        await bot.send_photo(
                            moderator_id,
                            media_file_id,
                            caption=format_post_for_moderator(post, user),
                            reply_markup=get_moderation_keyboard(post.post_id, message.from_user.id, include_approve_all=include_approve_all),
                        )
                        sent_to_moderators = True
                    elif message.video:
                        await bot.send_video(
                            moderator_id,
                            media_file_id,
                            caption=format_post_for_moderator(post, user),
                            reply_markup=get_moderation_keyboard(post.post_id, message.from_user.id, include_approve_all=include_approve_all),
                        )
                        sent_to_moderators = True
                    else:
                        await bot.send_document(
                            moderator_id,
                            media_file_id,
                            caption=format_post_for_moderator(post, user),
                            reply_markup=get_moderation_keyboard(post.post_id, message.from_user.id, include_approve_all=include_approve_all),
                        )
                        sent_to_moderators = True
                else:
                    await bot.send_message(
                        moderator_id,
                        format_post_for_moderator(post, user),
                        reply_markup=get_moderation_keyboard(post.post_id, message.from_user.id, include_approve_all=include_approve_all),
                    )
                    sent_to_moderators = True
            except Exception as e:
                logger.warning(f"Не удалось отправить пост модератору {moderator_id}: {e}")
        
        if not sent_to_moderators:
            logger.error("Не удалось отправить пост ни одному модератору/владельцу!")
            # Уведомим владельцев вручную, чтобы они могли принять меры
            for owner_id in OWNER_IDS:
                try:
                    await bot.send_message(
                        owner_id,
                        f"⚠️ Не удалось доставить пост модераторам, посмотри вручную:\n\n{format_post_for_moderator(post, user)}",
                        reply_markup=get_moderation_keyboard(post.post_id, message.from_user.id, include_approve_all=include_approve_all),
                    )
                except Exception as e:
                    logger.warning(f"Не удалось отправить уведомление владельцу {owner_id}: {e}")
    
    await message.answer(POST_SENT_MESSAGE)
    await state.clear()


@router.message(PostStates.waiting_ad_post)
async def receive_ad_post(message: Message, state: FSMContext):
    """Обработка рекламного поста после оплаты"""
    bot = message.bot
    
    content = message.text or message.caption or ""
    if not content.strip():
        await message.answer("❌ Пост не может быть пустым. Отправь текст.")
        return
    
    media_file_id = None
    if message.photo:
        media_file_id = message.photo[-1].file_id
    elif message.video:
        media_file_id = message.video.file_id
    elif message.document:
        media_file_id = message.document.file_id
    
    # Сохраняем в БД
    async for session in get_db():
        user = await get_or_create_user(
            session,
            message.from_user.id,
            message.from_user.username,
            message.from_user.first_name,
        )
        
        if user.is_banned:
            await message.answer(USER_BANNED_MESSAGE)
            await state.clear()
            return
        
        post = await create_post(
            session,
            message.from_user.id,
            "ad35",
            content,
            media_file_id,
        )
        
        # Проверим, сколько постов в ожидании модерации, и добавим кнопку 'Одобрить всех' при необходимости
        pending_count = await session.scalar(select(func.count(Post.post_id)).filter(Post.status == "pending"))
        include_approve_all = (pending_count or 0) > 1

        # Собираем всех получателей: env-модераторы + модераторы из БД + владельцы
        db_mod_ids = (await session.scalars(select(Moderator.moderator_id))).all()
        recipient_ids = set(MODERATOR_IDS) | set(db_mod_ids) | set(OWNER_IDS)
        if not recipient_ids:
            logger.warning("Ни одна роль модератора не настроена: ни env, ни в БД. Уведомляю владельцев (OWNER_IDS).")
            recipient_ids = set(OWNER_IDS)
        sent_to_moderators = False
        for moderator_id in recipient_ids:
            try:
                if media_file_id:
                    if message.photo:
                        await bot.send_photo(
                            moderator_id,
                            media_file_id,
                            caption=format_post_for_moderator(post, user),
                            reply_markup=get_moderation_keyboard(post.post_id, message.from_user.id, include_approve_all=include_approve_all),
                        )
                        sent_to_moderators = True
                    elif message.video:
                        await bot.send_video(
                            moderator_id,
                            media_file_id,
                            caption=format_post_for_moderator(post, user),
                            reply_markup=get_moderation_keyboard(post.post_id, message.from_user.id, include_approve_all=include_approve_all),
                        )
                        sent_to_moderators = True
                    else:
                        await bot.send_document(
                            moderator_id,
                            media_file_id,
                            caption=format_post_for_moderator(post, user),
                            reply_markup=get_moderation_keyboard(post.post_id, message.from_user.id, include_approve_all=include_approve_all),
                        )
                        sent_to_moderators = True
                else:
                    await bot.send_message(
                        moderator_id,
                        format_post_for_moderator(post, user),
                        reply_markup=get_moderation_keyboard(post.post_id, message.from_user.id, include_approve_all=include_approve_all),
                    )
                    sent_to_moderators = True
            except Exception as e:
                logger.warning(f"Не удалось отправить пост модератору {moderator_id}: {e}")
        
        if not sent_to_moderators:
            logger.error("Не удалось отправить пост ни одному модератору/владельцу!")
            # Уведомим владельцев вручную, чтобы они могли принять меры
            for owner_id in OWNER_IDS:
                try:
                    await bot.send_message(
                        owner_id,
                        f"⚠️ Не удалось доставить пост модераторам, посмотри вручную:\n\n{format_post_for_moderator(post, user)}",
                        reply_markup=get_moderation_keyboard(post.post_id, message.from_user.id, include_approve_all=include_approve_all),
                    )
                except Exception as e:
                    logger.warning(f"Не удалось отправить уведомление владельцу {owner_id}: {e}")
    
    await message.answer(POST_SENT_MESSAGE)
    await state.clear()


@router.message(PostStates.waiting_offtopic_post)
async def receive_offtopic_post(message: Message, state: FSMContext):
    """Обработка поста не по тематике после оплаты"""
    bot = message.bot
    
    content = message.text or message.caption or ""
    if not content.strip():
        await message.answer("❌ Пост не может быть пустым. Отправь текст.")
        return
    
    media_file_id = None
    if message.photo:
        media_file_id = message.photo[-1].file_id
    elif message.video:
        media_file_id = message.video.file_id
    elif message.document:
        media_file_id = message.document.file_id
    
    # Сохраняем в БД
    async for session in get_db():
        user = await get_or_create_user(
            session,
            message.from_user.id,
            message.from_user.username,
            message.from_user.first_name,
        )
        
        if user.is_banned:
            await message.answer(USER_BANNED_MESSAGE)
            await state.clear()
            return
        
        post = await create_post(
            session,
            message.from_user.id,
            "offtopic50",
            content,
            media_file_id,
        )
        
        # Проверим, сколько постов в ожидании модерации, и добавим кнопку 'Одобрить всех' при необходимости
        pending_count = await session.scalar(select(func.count(Post.post_id)).filter(Post.status == "pending"))
        include_approve_all = (pending_count or 0) > 1

        # Собираем всех получателей: env-модераторы + модераторы из БД + владельцы
        db_mod_ids = (await session.scalars(select(Moderator.moderator_id))).all()
        recipient_ids = set(MODERATOR_IDS) | set(db_mod_ids) | set(OWNER_IDS)
        if not recipient_ids:
            logger.warning("Ни одна роль модератора не настроена: ни env, ни в БД. Уведомляю владельцев (OWNER_IDS).")
            recipient_ids = set(OWNER_IDS)
        sent_to_moderators = False
        for moderator_id in recipient_ids:
            try:
                if media_file_id:
                    if message.photo:
                        await bot.send_photo(
                            moderator_id,
                            media_file_id,
                            caption=format_post_for_moderator(post, user),
                            reply_markup=get_moderation_keyboard(post.post_id, message.from_user.id, include_approve_all=include_approve_all),
                        )
                        sent_to_moderators = True
                    elif message.video:
                        await bot.send_video(
                            moderator_id,
                            media_file_id,
                            caption=format_post_for_moderator(post, user),
                            reply_markup=get_moderation_keyboard(post.post_id, message.from_user.id, include_approve_all=include_approve_all),
                        )
                        sent_to_moderators = True
                    else:
                        await bot.send_document(
                            moderator_id,
                            media_file_id,
                            caption=format_post_for_moderator(post, user),
                            reply_markup=get_moderation_keyboard(post.post_id, message.from_user.id, include_approve_all=include_approve_all),
                        )
                        sent_to_moderators = True
                else:
                    await bot.send_message(
                        moderator_id,
                        format_post_for_moderator(post, user),
                        reply_markup=get_moderation_keyboard(post.post_id, message.from_user.id, include_approve_all=include_approve_all),
                    )
                    sent_to_moderators = True
            except Exception as e:
                logger.warning(f"Не удалось отправить пост модератору {moderator_id}: {e}")
        
        if not sent_to_moderators:
            logger.error("Не удалось отправить пост ни одному модератору/владельцу!")
            # Уведомим владельцев вручную, чтобы они могли принять меры
            for owner_id in OWNER_IDS:
                try:
                    await bot.send_message(
                        owner_id,
                        f"⚠️ Не удалось доставить пост модераторам, посмотри вручную:\n\n{format_post_for_moderator(post, user)}",
                        reply_markup=get_moderation_keyboard(post.post_id, message.from_user.id, include_approve_all=include_approve_all),
                    )
                except Exception as e:
                    logger.warning(f"Не удалось отправить уведомление владельцу {owner_id}: {e}")
    
    await message.answer(POST_SENT_MESSAGE)
    await state.clear()

