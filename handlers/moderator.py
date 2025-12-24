"""
Обработчики для модераторов
"""
import logging
from datetime import datetime
from functools import wraps

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup, ChatJoinRequest as TgChatJoinRequest
from sqlalchemy import func, select, case
from sqlalchemy.ext.asyncio import AsyncSession

from config import CHANNEL_ID, MODERATOR_IDS, OWNER_IDS
from database.db import get_db
from database.models import Post, User, Moderator, ChatJoinRequest
from keyboards.moderator_kb import get_moderation_keyboard, get_user_info_keyboard, get_moderator_main_keyboard
from states.states import ModerationStates
from utils.helpers import format_user_info, is_moderator, is_owner, format_post_for_moderator, format_join_request
from utils.texts import POST_APPROVED_MESSAGE, POST_REJECTED_TEMPLATE

logger = logging.getLogger(__name__)
router = Router()


def normalize_username(value: str | None) -> str | None:
    """Очистить username от пробелов и символа @"""
    if not value:
        return None
    username = value.strip()
    if not username:
        return None
    if username.startswith("@"):
        username = username[1:]
    return username or None


def format_username_display(value: str | None) -> str:
    """Отформатировать username для отображения"""
    normalized = normalize_username(value)
    return f"@{normalized}" if normalized else "@не указан"


def format_user_reference(username: str | None, full_name: str | None, user_id: int) -> str:
    """Красиво показать пользователя по username/full_name"""
    handle = format_username_display(username)
    if handle != "@не указан":
        return handle
    if full_name:
        return f"{full_name} (ID: {user_id})"
    return f"ID: {user_id}"


async def get_moderator_profiles():
    """Вернуть данные о всех модераторах и владельцах"""
    async for session in get_db():
        db_mods = (await session.scalars(select(Moderator))).all()
        db_map = {m.moderator_id: m for m in db_mods}
        id_pool = set(OWNER_IDS) | set(MODERATOR_IDS) | set(db_map.keys())
        if id_pool:
            users = (await session.scalars(select(User).where(User.user_id.in_(id_pool)))).all()
            user_map = {u.user_id: u for u in users}
        else:
            user_map = {}

    profiles = []
    for mod_id in sorted(id_pool):
        db_entry = db_map.get(mod_id)
        username = db_entry.username if db_entry else None
        if not username and mod_id in user_map:
            username = user_map[mod_id].username
        full_name = user_map[mod_id].first_name if mod_id in user_map else None
        profiles.append(
            {
                "id": mod_id,
                "username": username,
                "full_name": full_name,
                "is_owner": mod_id in OWNER_IDS,
                "has_db_entry": bool(db_entry),
            }
        )
    return profiles


async def build_moderator_management_view():
    """Получить текст и клавиатуру для панели управления модераторами"""
    profiles = await get_moderator_profiles()
    lines = [
        f"{'👑' if p['is_owner'] else '🛡️'} {format_user_reference(p['username'], p.get('full_name'), p['id'])}"
        for p in profiles
    ]
    text = "👥 *Список модераторов:*\n\n" + ("\n".join(lines) if lines else "Пока никто не добавлен.")

    kb_rows = []
    for profile in profiles:
        if profile["is_owner"]:
            continue
        kb_rows.append(
            [
                InlineKeyboardButton(
                    text=f"✏️ Изменить ID {profile['id']}",
                    callback_data=f"edit_mod_username_{profile['id']}",
                )
            ]
        )
    kb_rows.append([InlineKeyboardButton(text="➕ Добавить модератора", callback_data="add_moderator")])
    kb_rows.append([InlineKeyboardButton(text="↩️ Назад", callback_data="moderator_menu")])
    return text, InlineKeyboardMarkup(inline_keyboard=kb_rows)


async def notify_owners(bot, text: str, parse_mode: str | None = None):
    """Уведомить владельцев о действии"""
    for owner_id in OWNER_IDS:
        try:
            await bot.send_message(owner_id, text, parse_mode=parse_mode)
        except Exception:
            pass


def moderator_only(func):
    """Декоратор для проверки прав модератора"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        message_or_callback = args[0]
        user_id = message_or_callback.from_user.id if hasattr(message_or_callback, 'from_user') else message_or_callback.message.from_user.id
        
        if not is_moderator(user_id):
            # Проверим БД на наличие модератора (динамически добавляемых)
            async for session in get_db():
                mod = await session.get(Moderator, user_id)
                if not mod:
                    if isinstance(message_or_callback, CallbackQuery):
                        await message_or_callback.answer("❌ У тебя нет прав модератора.", show_alert=True)
                    else:
                        await message_or_callback.answer("❌ У тебя нет прав модератора.")
                    return
                # если есть запись в БД — разрешаем
                break
        
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


@router.message(Command("moderator"))
@moderator_only
async def cmd_moderator_panel(message: Message):
    """Панель модератора: главное меню"""
    async for session in get_db():
        pending_posts = await session.scalar(select(func.count(Post.post_id)).filter(Post.status == "pending"))
        pending_posts = pending_posts or 0
        pending_requests = await session.scalar(select(func.count(ChatJoinRequest.id)).filter(ChatJoinRequest.status == "pending", ChatJoinRequest.chat_id == int(CHANNEL_ID)))
        pending_requests = pending_requests or 0

    is_owner_user = message.from_user.id in OWNER_IDS
    kb = get_moderator_main_keyboard(pending_posts=pending_posts, pending_requests=pending_requests, is_owner=is_owner_user)
    
    text = f"""📋 *Панель модерации*

🔔 Постов на модерации: *{pending_posts}*
📝 Заявок на вступление: *{pending_requests}*"""
    
    try:
        await message.answer(text, reply_markup=kb, parse_mode="Markdown")
    except Exception as e:
        logger.warning(f"Не удалось отправить панель модератора: {e}")


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


@router.message(ModerationStates.waiting_new_moderator)
@moderator_only
async def receive_new_moderator(message: Message, state: FSMContext):
    """Получаем от владельца ID нового модератора (или пересланное сообщение) и сохраняем в БД"""
    if not is_owner(message.from_user.id):
        await message.answer("❌ Только владелец может выполнять это действие.")
        await state.clear()
        return

    user_id = None
    username = None
    if message.forward_from:
        user_id = message.forward_from.id
        username = normalize_username(message.forward_from.username)
    else:
        text = (message.text or "").strip()
        if not text:
            await message.answer("❌ Отправьте user_id (числом) или @username.")
            return
        user_id_candidate = None
        username_candidate = None
        for token in text.replace(",", " ").split():
            if token.isdigit() and not user_id_candidate:
                user_id_candidate = int(token)
            else:
                normalized = normalize_username(token)
                if normalized:
                    username_candidate = normalized
        if not user_id_candidate:
            await message.answer("❌ Укажите числовой user_id (например, 123456789).")
            return
        user_id = user_id_candidate
        username = username_candidate

    async for session in get_db():
        existing = await session.get(Moderator, user_id)
        if existing:
            await message.answer("❌ Пользователь уже является модератором.")
            await state.clear()
            return

        # Создаём запись модератора
        new_mod = Moderator(moderator_id=user_id, username=username)
        session.add(new_mod)

        # Если пользователя нет в таблице users — создаём запись (чтобы корректно считать посты и инфу)
        user = await session.get(User, user_id)
        if not user:
            new_user = User(user_id=user_id, username=username)
            session.add(new_user)

        await session.commit()

    # Обновим runtime-список MODERATOR_IDS (чтобы is_moderator работал без перезапуска)
    try:
        if user_id not in MODERATOR_IDS:
            MODERATOR_IDS.append(user_id)
    except Exception:
        pass

    try:
        await message.bot.send_message(user_id, "✅ Вы добавлены модератором.")
    except Exception:
        pass

    await message.answer(f"✅ Пользователь {user_id} добавлен как модератор.")
    try:
        text, kb = await build_moderator_management_view()
        await message.answer(text, reply_markup=kb, parse_mode="Markdown")
    except Exception:
        pass
    await state.clear()


@router.message(ModerationStates.waiting_moderator_username)
@moderator_only
async def receive_moderator_username(message: Message, state: FSMContext):
    """Получаем новый username для модератора"""
    if not is_owner(message.from_user.id):
        await message.answer("❌ Только владелец может выполнять это действие.")
        await state.clear()
        return

    data = await state.get_data()
    mod_id = data.get("edit_moderator_id")
    manage_chat_id = data.get("manage_chat_id")
    manage_message_id = data.get("manage_message_id")
    if not mod_id:
        await message.answer("❌ Не удалось определить модератора. Откройте список модераторов заново.")
        await state.clear()
        return

    new_username = None
    if message.forward_from:
        new_username = normalize_username(message.forward_from.username)
    else:
        text = (message.text or "").strip()
        if text.lower() in {"-", "удалить", "remove", "none"}:
            new_username = None
        else:
            for token in text.replace(",", " ").split():
                candidate = normalize_username(token)
                if candidate:
                    new_username = candidate
                    break

    if new_username is None and not message.forward_from:
        await message.answer("❌ Отправьте корректный @username или пересланное сообщение от пользователя.")
        return

    async for session in get_db():
        mod = await session.get(Moderator, mod_id)
        if not mod:
            mod = Moderator(moderator_id=mod_id, username=new_username)
            session.add(mod)
        else:
            mod.username = new_username

        user = await session.get(User, mod_id)
        if user:
            user.username = new_username
        await session.commit()

    await message.answer(f"✅ Username для модератора {mod_id} обновлён: {format_username_display(new_username)}")

    text, kb = await build_moderator_management_view()
    if manage_chat_id and manage_message_id:
        try:
            await message.bot.edit_message_text(text, manage_chat_id, manage_message_id, reply_markup=kb, parse_mode="Markdown")
        except Exception:
            try:
                await message.bot.send_message(manage_chat_id, text, reply_markup=kb, parse_mode="Markdown")
            except Exception:
                pass
    await state.clear()


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

            is_owner = message.from_user.id in OWNER_IDS
            if post.media_file_id:
                # Если есть медиа — пробуем отправить как фото, иначе как документ
                try:
                    await message.bot.send_photo(
                        chat_id,
                        post.media_file_id,
                        caption=format_post_for_moderator(post, user),
                        reply_markup=get_moderation_keyboard(post.post_id, user.user_id, include_approve_all=include_approve_all, is_owner=is_owner),
                    )
                except Exception:
                    await message.bot.send_document(
                        chat_id,
                        post.media_file_id,
                        caption=format_post_for_moderator(post, user),
                        reply_markup=get_moderation_keyboard(post.post_id, user.user_id, include_approve_all=include_approve_all, is_owner=is_owner),
                    )
            else:
                await message.bot.send_message(
                    chat_id,
                    format_post_for_moderator(post, user),
                    reply_markup=get_moderation_keyboard(post.post_id, user.user_id, include_approve_all=include_approve_all, is_owner=is_owner),
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


# --- Новые обработчики: пагинация, пользовательская инфа, подтверждения ---
@router.callback_query(F.data == "noop")
@moderator_only
async def noop_callback(callback: CallbackQuery):
    """Ничего не делать для декоративных кнопок"""
    await callback.answer()


@router.callback_query(F.data == "moderator_posts")
@moderator_only
async def moderator_posts(callback: CallbackQuery):
    """Показать первый пост на модерации (быстрый доступ)"""
    async for session in get_db():
        pending_posts = (await session.scalars(select(Post).filter(Post.status == "pending").order_by(Post.created_at.desc()))).all()
        total = len(pending_posts)
        if total == 0:
            await callback.answer("✅ Нет постов на модерации.", show_alert=True)
            return
        post = pending_posts[0]
        user = await session.get(User, post.user_id)
        include_approve_all = total > 1
        is_owner_user = callback.from_user.id in OWNER_IDS
        kb = get_moderation_keyboard(post.post_id, user.user_id, include_approve_all=include_approve_all, offset=0, total=total, is_owner=is_owner_user)
        chat_id = callback.message.chat.id

        try:
            if post.media_file_id:
                try:
                    await callback.message.edit_caption(format_post_for_moderator(post, user), reply_markup=kb)
                except Exception:
                    try:
                        await callback.bot.delete_message(chat_id, callback.message.message_id)
                    except Exception:
                        pass
                    try:
                        await callback.bot.send_photo(chat_id, post.media_file_id, caption=format_post_for_moderator(post, user), reply_markup=kb)
                    except Exception:
                        await callback.bot.send_document(chat_id, post.media_file_id, caption=format_post_for_moderator(post, user), reply_markup=kb)
            else:
                try:
                    await callback.message.edit_text(format_post_for_moderator(post, user), reply_markup=kb)
                except Exception:
                    try:
                        await callback.bot.delete_message(chat_id, callback.message.message_id)
                    except Exception:
                        pass
                    await callback.bot.send_message(chat_id, format_post_for_moderator(post, user), reply_markup=kb)
        except Exception as e:
            logger.warning(f"Не удалось показать пост: {e}")

        await callback.answer()


@router.callback_query(F.data == "moderator_add_mods")
@moderator_only
async def moderator_add_mods(callback: CallbackQuery, state: FSMContext):
    """Панель управления модераторами (показывает текущих и позволяет добавить)"""
    if not is_owner(callback.from_user.id):
        await callback.answer("❌ Только владелец может управлять модераторами.", show_alert=True)
        return
    await state.clear()
    text, kb = await build_moderator_management_view()
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    except Exception as e:
        logger.warning(f"Не удалось показать панель модераторов: {e}")
    await callback.answer()


@router.callback_query(F.data.startswith("edit_mod_username_"))
@moderator_only
async def edit_mod_username(callback: CallbackQuery, state: FSMContext):
    """Запросить новый username для модератора"""
    if not is_owner(callback.from_user.id):
        await callback.answer("❌ Только владелец может редактировать модераторов.", show_alert=True)
        return

    try:
        mod_id = int(callback.data.split("_")[3])
    except Exception:
        await callback.answer("❌ Некорректный модератор.", show_alert=True)
        return

    await state.update_data(
        edit_moderator_id=mod_id,
        manage_chat_id=callback.message.chat.id,
        manage_message_id=callback.message.message_id,
    )
    await state.set_state(ModerationStates.waiting_moderator_username)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ Назад", callback_data="moderator_add_mods")],
    ])
    text = (
        f"✏️ Введите новый username для модератора `{mod_id}`.\n\n"
        "Можете отправить @username текстом или переслать сообщение пользователя."
    )
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    except Exception as e:
        logger.warning(f"Не удалось запросить username модератора {mod_id}: {e}")
        await callback.answer("Не удалось запросить username. Попробуйте снова.", show_alert=True)
        return

    await callback.answer("Отправьте новый username модератора.")


@router.callback_query(F.data == "moderator_requests")
@moderator_only
async def moderator_requests(callback: CallbackQuery):
    """Показать список заявок на вступление в канал"""
    async for session in get_db():
        pending = (await session.scalars(select(ChatJoinRequest).filter(ChatJoinRequest.status == "pending").order_by(ChatJoinRequest.created_at.desc()).limit(10))).all()

    if not pending:
        await callback.answer("📭 Нет заявок на вступление.", show_alert=True)
        return

    lines = [
        f"ID: {r.id} — {format_user_reference(r.username, r.full_name, r.user_id)} — {r.created_at.strftime('%d.%m.%Y %H:%M')}"
        for r in pending
    ]
    text = "📝 Заявки на вступление (последние):\n\n" + "\n\n".join(lines)

    kb_rows = []
    for r in pending:
        kb_rows.append([InlineKeyboardButton(text=f"✅ Одобрить {r.id}", callback_data=f"joinreq_approve_{r.id}"), InlineKeyboardButton(text=f"❌ Отклонить {r.id}", callback_data=f"joinreq_reject_{r.id}")])
    kb_rows.append([InlineKeyboardButton(text="↩️ Назад", callback_data="moderator_page_0")])

    try:
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))
    except Exception as e:
        logger.warning(f"Не удалось показать заявки: {e}")


@router.chat_join_request()
async def handle_chat_join_request(req: TgChatJoinRequest):
    """Обрабатываем событие заявки на вступление в канал: сохраняем и уведомляем модераторов"""
    # Сохраняем заявку в БД
    user = req.from_user
    chat = req.chat
    async for session in get_db():
        new_req = ChatJoinRequest(user_id=user.id, chat_id=chat.id, username=user.username, full_name=(user.full_name if hasattr(user, 'full_name') else None))
        session.add(new_req)
        await session.commit()
        req_id = new_req.id

    # Нотифицируем модераторов
    mod_ids = set(MODERATOR_IDS) | set(OWNER_IDS)
    async for session in get_db():
        db_mods = (await session.scalars(select(Moderator))).all()
        for m in db_mods:
            mod_ids.add(m.moderator_id)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Одобрить", callback_data=f"joinreq_approve_{req_id}"), InlineKeyboardButton(text="❌ Отказать", callback_data=f"joinreq_reject_{req_id}")]
    ])

    user_reference = format_user_reference(user.username, getattr(user, "full_name", None), user.id)
    text = f"📨 Заявка в канал: {user_reference}\nID заявки: {req_id}"

    for mod_id in mod_ids:
        try:
            await req.bot.send_message(mod_id, text, reply_markup=kb)
        except Exception:
            pass


@router.callback_query(F.data.startswith("joinreq_approve_"))
@moderator_only
async def joinreq_approve(callback: CallbackQuery):
    try:
        req_id = int(callback.data.split("_")[2])
    except Exception:
        await callback.answer("❌ Некорректная заявка.", show_alert=True)
        return

    async for session in get_db():
        req = await session.get(ChatJoinRequest, req_id)
        if not req:
            await callback.answer("❌ Заявка не найдена.", show_alert=True)
            return
        if req.status != "pending":
            await callback.answer("❌ Заявка уже обработана.", show_alert=True)
            return

        # Попытаемся одобрить в канале
        try:
            await callback.bot.approve_chat_join_request(int(req.chat_id), int(req.user_id))
            req.status = "approved"
            req.moderator_id = callback.from_user.id
            req.handled_at = datetime.utcnow()
            await session.commit()

            try:
                await callback.bot.send_message(req.user_id, "✅ Ваша заявка в канал одобрена.")
            except Exception:
                pass

            await callback.answer("✅ Заявка одобрена.")
            try:
                await callback.message.edit_text((callback.message.text or "") + f"\n\n✅ Одобрено (Request {req_id})", reply_markup=None)
            except Exception:
                pass

            moderator_display = format_user_reference(callback.from_user.username, callback.from_user.full_name, callback.from_user.id)
            user_display = format_user_reference(req.username, req.full_name, req.user_id)
            await notify_owners(
                callback.bot,
                f"✅ *Заявка #{req_id}* — {user_display}\nОдобрил: {moderator_display}",
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error(f"Ошибка при одобрении заявки {req_id}: {e}")
            await callback.answer(f"❌ Ошибка при одобрении: {e}", show_alert=True)


@router.callback_query(F.data.startswith("joinreq_reject_"))
@moderator_only
async def joinreq_reject(callback: CallbackQuery):
    try:
        req_id = int(callback.data.split("_")[2])
    except Exception:
        await callback.answer("❌ Некорректная заявка.", show_alert=True)
        return

    async for session in get_db():
        req = await session.get(ChatJoinRequest, req_id)
        if not req:
            await callback.answer("❌ Заявка не найдена.", show_alert=True)
            return
        if req.status != "pending":
            await callback.answer("❌ Заявка уже обработана.", show_alert=True)
            return

        try:
            await callback.bot.decline_chat_join_request(int(req.chat_id), int(req.user_id))
            req.status = "rejected"
            req.moderator_id = callback.from_user.id
            req.handled_at = datetime.utcnow()
            await session.commit()

            try:
                await callback.bot.send_message(req.user_id, "❌ Ваша заявка в канал отклонена.")
            except Exception:
                pass

            await callback.answer("✅ Заявка отклонена.")
            try:
                await callback.message.edit_text((callback.message.text or "") + f"\n\n❌ Отклонено (Request {req_id})", reply_markup=None)
            except Exception:
                pass

            moderator_display = format_user_reference(callback.from_user.username, callback.from_user.full_name, callback.from_user.id)
            user_display = format_user_reference(req.username, req.full_name, req.user_id)
            await notify_owners(
                callback.bot,
                f"❌ *Заявка #{req_id}* — {user_display}\nОтклонил: {moderator_display}",
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error(f"Ошибка при отклонении заявки {req_id}: {e}")
            await callback.answer(f"❌ Ошибка при отклонении: {e}", show_alert=True)


@router.callback_query(F.data.startswith("moderator_page_"))
@moderator_only
async def moderator_page(callback: CallbackQuery):
    """Показать пост по номеру страницы (offset)"""
    try:
        offset = int(callback.data.split("_")[2])
    except Exception:
        await callback.answer("❌ Некорректная страница.", show_alert=True)
        return

    async for session in get_db():
        pending_posts = (await session.scalars(select(Post).filter(Post.status == "pending").order_by(Post.created_at.desc()))).all()
        total = len(pending_posts)
        if total == 0:
            await callback.answer("✅ Нет постов на модерации.", show_alert=True)
            return
        if offset < 0 or offset >= total:
            await callback.answer("❌ Страница вне диапазона.", show_alert=True)
            return

        post = pending_posts[offset]
        user = await session.get(User, post.user_id)
        include_approve_all = total > 1
        is_owner_user = callback.from_user.id in OWNER_IDS

        chat_id = callback.message.chat.id
        message_id = callback.message.message_id
        kb = get_moderation_keyboard(post.post_id, user.user_id, include_approve_all=include_approve_all, offset=offset, total=total, is_owner=is_owner_user)

        # Попытка отредактировать сообщение; при неудаче - удалить и отправить новое
        try:
            if post.media_file_id:
                # Попытаемся отредактировать подпись, если это возможно
                try:
                    await callback.message.edit_caption(format_post_for_moderator(post, user), reply_markup=kb)
                except Exception:
                    try:
                        await callback.bot.delete_message(chat_id, message_id)
                    except Exception:
                        pass
                    # Отправим как новое сообщение
                    try:
                        await callback.bot.send_photo(chat_id, post.media_file_id, caption=format_post_for_moderator(post, user), reply_markup=kb)
                    except Exception:
                        await callback.bot.send_document(chat_id, post.media_file_id, caption=format_post_for_moderator(post, user), reply_markup=kb)
            else:
                try:
                    await callback.message.edit_text(format_post_for_moderator(post, user), reply_markup=kb)
                except Exception:
                    try:
                        await callback.bot.delete_message(chat_id, message_id)
                    except Exception:
                        pass
                    await callback.bot.send_message(chat_id, format_post_for_moderator(post, user), reply_markup=kb)
        except Exception as e:
            logger.warning(f"Не удалось показать страницу модерации {offset}: {e}")

    await callback.answer()


@router.callback_query(F.data == "add_moderator")
@moderator_only
async def add_moderator(callback: CallbackQuery, state: FSMContext):
    """Начинает добавление нового модератора (только для владельца)"""
    if not is_owner(callback.from_user.id):
        await callback.answer("❌ Только владелец бота может добавлять модераторов.", show_alert=True)
        return

    await state.set_state(ModerationStates.waiting_new_moderator)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="moderator_add_mods")]
    ])
    try:
        await callback.message.edit_text("➕ Отправьте user_id пользователя или перешлите любое его сообщение, чтобы добавить модератора.", reply_markup=kb)
    except Exception:
        await callback.answer("Не удалось показать запрос. Попробуйте снова.", show_alert=True)
    await callback.answer("Отправьте ID или перешлите сообщение пользователя.")


@router.callback_query(F.data.startswith("user_info_"))
@moderator_only
async def show_user_info(callback: CallbackQuery):
    """Показать информацию о пользователе"""
    try:
        user_id = int(callback.data.split("_")[2])
    except Exception:
        await callback.answer("❌ Некорректный пользователь.", show_alert=True)
        return

    async for session in get_db():
        user = await session.get(User, user_id)
        if not user:
            await callback.answer("❌ Пользователь не найден.", show_alert=True)
            return
        posts_count = await session.scalar(select(func.count(Post.post_id)).filter(Post.user_id == user_id))

    text = format_user_info(user, posts_count)
    try:
        await callback.message.edit_text(text, reply_markup=get_user_info_keyboard(user_id, is_banned=user.is_banned))
    except Exception as e:
        logger.warning(f"Не удалось показать инфу о пользователе {user_id}: {e}")
        await callback.answer("Не удалось показать информацию. Попробуйте снова.", show_alert=True)


@router.callback_query(F.data.startswith("user_posts_"))
@moderator_only
async def show_user_posts(callback: CallbackQuery):
    """Показать список постов пользователя (страницы по 5)"""
    parts = callback.data.split("_")
    if len(parts) < 4:
        await callback.answer("❌ Некорректный запрос.", show_alert=True)
        return
    try:
        user_id = int(parts[2])
        page = int(parts[3])
    except Exception:
        await callback.answer("❌ Некорректные параметры.", show_alert=True)
        return

    page_size = 5
    offset = page * page_size

    async for session in get_db():
        total_posts = await session.scalar(select(func.count(Post.post_id)).filter(Post.user_id == user_id))
        posts = (await session.scalars(select(Post).filter(Post.user_id == user_id).order_by(Post.created_at.desc()).offset(offset).limit(page_size))).all()

    if not posts:
        await callback.answer("📄 Постов не найдено на этой странице.", show_alert=True)
        return

    lines = [f"📄 Пост ID: {p.post_id} — {p.status} — {p.created_at.strftime('%d.%m.%Y %H:%M')}\n{(p.content[:200] + '...') if len(p.content) > 200 else p.content}" for p in posts]
    text = f"📋 Посты пользователя {user_id} (страница {page + 1})\n\n" + "\n\n".join(lines)

    # Кнопки: просмотр конкретного поста и навигация
    keyboard = []
    for p in posts:
        keyboard.append([InlineKeyboardButton(text=f"Посмотреть {p.post_id}", callback_data=f"view_post_{p.post_id}")])

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="◀️", callback_data=f"user_posts_{user_id}_{page - 1}"))
    nav_row.append(InlineKeyboardButton(text=f"{page + 1}/{(total_posts + page_size - 1)//page_size}", callback_data="noop"))
    if offset + page_size < (total_posts or 0):
        nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"user_posts_{user_id}_{page + 1}"))
    keyboard.append(nav_row)
    keyboard.append([InlineKeyboardButton(text="↩️ Назад", callback_data=f"user_info_{user_id}")])

    try:
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    except Exception as e:
        logger.warning(f"Не удалось показать посты пользователя {user_id}: {e}")
        await callback.answer("Не удалось показать посты. Попробуйте снова.", show_alert=True)


@router.callback_query(F.data.startswith("view_post_"))
@moderator_only
async def view_post(callback: CallbackQuery):
    """Показать единичный пост (полный) по id"""
    try:
        post_id = int(callback.data.split("_")[2])
    except Exception:
        await callback.answer("❌ Некорректный пост.", show_alert=True)
        return

    async for session in get_db():
        post = await session.get(Post, post_id)
        if not post:
            await callback.answer("❌ Пост не найден.", show_alert=True)
            return
        user = await session.get(User, post.user_id)

    text = format_post_for_moderator(post, user)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"delete_post_{post.post_id}"), InlineKeyboardButton(text="↩️ Назад", callback_data=f"user_posts_{post.user_id}_0")]
    ])

    try:
        if post.media_file_id:
            try:
                await callback.message.edit_caption(text, reply_markup=kb)
            except Exception:
                try:
                    await callback.bot.delete_message(callback.message.chat.id, callback.message.message_id)
                except Exception:
                    pass
                try:
                    await callback.bot.send_photo(callback.message.chat.id, post.media_file_id, caption=text, reply_markup=kb)
                except Exception:
                    await callback.bot.send_document(callback.message.chat.id, post.media_file_id, caption=text, reply_markup=kb)
        else:
            await callback.message.edit_text(text, reply_markup=kb)
    except Exception as e:
        logger.warning(f"Не удалось показать пост {post_id}: {e}")
        await callback.answer("Не удалось показать пост. Попробуйте снова.", show_alert=True)


@router.callback_query(F.data.startswith("delete_post_"))
@moderator_only
async def delete_post(callback: CallbackQuery):
    """Удалить пост из базы (модератор)"""
    try:
        post_id = int(callback.data.split("_")[2])
    except Exception:
        await callback.answer("❌ Некорректный пост.", show_alert=True)
        return

    async for session in get_db():
        post = await session.get(Post, post_id)
        if not post:
            await callback.answer("❌ Пост не найден.", show_alert=True)
            return
        user_id = post.user_id
        await session.delete(post)
        await session.commit()

    await callback.answer("✅ Пост удалён.", show_alert=True)
    try:
        await callback.message.edit_text((callback.message.text or "") + "\n\n🗑️ Удалён модератором", reply_markup=get_user_info_keyboard(user_id))
    except Exception:
        pass


@router.callback_query(F.data.startswith("warn_user_"))
@moderator_only
async def warn_user(callback: CallbackQuery):
    """Отправить предупреждение пользователю (по умолчанию)"""
    try:
        user_id = int(callback.data.split("_")[2])
    except Exception:
        await callback.answer("❌ Некорректный пользователь.", show_alert=True)
        return

    try:
        await callback.bot.send_message(user_id, "⚠️ Вам отправлено предупреждение от модерации. Пожалуйста, ознакомьтесь с правилами.")
        await callback.answer("✅ Пользователь уведомлён.", show_alert=True)
        await callback.message.edit_text((callback.message.text or "") + f"\n\n⚠️ Пользователь {user_id} предупреждён.", reply_markup=get_user_info_keyboard(user_id))
    except Exception as e:
        logger.warning(f"Не удалось отправить предупреждение пользователю {user_id}: {e}")
        await callback.answer("Не удалось отправить предупреждение.", show_alert=True)


@router.callback_query(F.data.startswith("confirm_ban_"))
@moderator_only
async def confirm_ban(callback: CallbackQuery):
    """Попросить подтверждение бана"""
    user_id = int(callback.data.split("_")[2])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, забанить", callback_data=f"ban_yes_{user_id}"), InlineKeyboardButton(text="❌ Отмена", callback_data=f"user_info_{user_id}")]
    ])
    try:
        await callback.message.edit_text(f"🚫 Подтвердить бан пользователя {user_id}?", reply_markup=kb)
    except Exception:
        await callback.answer("Не удалось запросить подтверждение.", show_alert=True)


@router.callback_query(F.data.startswith("confirm_unban_"))
@moderator_only
async def confirm_unban(callback: CallbackQuery):
    """Попросить подтверждение разбана"""
    user_id = int(callback.data.split("_")[2])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, разбанить", callback_data=f"unban_yes_{user_id}"), InlineKeyboardButton(text="❌ Отмена", callback_data=f"user_info_{user_id}")]
    ])
    try:
        await callback.message.edit_text(f"✅ Подтвердить разбан пользователя {user_id}?", reply_markup=kb)
    except Exception:
        await callback.answer("Не удалось запросить подтверждение.", show_alert=True)


@router.callback_query(F.data.startswith("ban_yes_"))
@moderator_only
async def ban_yes(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[2])
    async for session in get_db():
        user = await session.get(User, user_id)
        if not user:
            await callback.answer("❌ Пользователь не найден.", show_alert=True)
            return
        user.is_banned = True
        await session.commit()

    await callback.answer("✅ Пользователь забанен.", show_alert=True)
    try:
        await callback.message.edit_text(f"🚫 Пользователь {user_id} забанен.", reply_markup=get_user_info_keyboard(user_id, is_banned=True))
    except Exception:
        pass


@router.callback_query(F.data.startswith("unban_yes_"))
@moderator_only
async def unban_yes(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[2])
    async for session in get_db():
        user = await session.get(User, user_id)
        if not user:
            await callback.answer("❌ Пользователь не найден.", show_alert=True)
            return
        user.is_banned = False
        await session.commit()

    await callback.answer("✅ Пользователь разбанен.", show_alert=True)
    try:
        await callback.message.edit_text(f"✅ Пользователь {user_id} разбанен.", reply_markup=get_user_info_keyboard(user_id, is_banned=False))
    except Exception:
        pass


@router.callback_query(F.data == "confirm_approve_all")
@moderator_only
async def confirm_approve_all(callback: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Одобрить всё", callback_data="approve_all_yes"), InlineKeyboardButton(text="❌ Отмена", callback_data="moderator_page_0")]
    ])
    try:
        await callback.message.edit_text("⚠️ Вы уверены, что хотите одобрить все посты?", reply_markup=kb)
    except Exception:
        await callback.answer("Не удалось запросить подтверждение.", show_alert=True)


@router.callback_query(F.data == "approve_all_yes")
@moderator_only
async def approve_all_yes(callback: CallbackQuery):
    # Реализуем массовое одобрение (взято из существующей логики)
    bot = callback.bot
    approved = 0
    failed = 0

    async for session in get_db():
        pending_posts = (await session.scalars(select(Post).filter(Post.status == "pending").order_by(Post.created_at.asc()))).all()
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


@router.callback_query(F.data == "moderator_menu")
@moderator_only
async def moderator_menu(callback: CallbackQuery):
    """Вернуться в главное меню модератора"""
    async for session in get_db():
        pending_posts = await session.scalar(select(func.count(Post.post_id)).filter(Post.status == "pending"))
        pending_posts = pending_posts or 0
        pending_requests = await session.scalar(select(func.count(ChatJoinRequest.id)).filter(ChatJoinRequest.status == "pending", ChatJoinRequest.chat_id == int(CHANNEL_ID)))
        pending_requests = pending_requests or 0

    is_owner_user = callback.from_user.id in OWNER_IDS
    kb = get_moderator_main_keyboard(pending_posts=pending_posts, pending_requests=pending_requests, is_owner=is_owner_user)
    
    text = f"""📋 *Панель модерации*

🔔 Постов на модерации: *{pending_posts}*
📝 Заявок на вступление: *{pending_requests}*"""
    
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    except Exception:
        try:
            await callback.bot.delete_message(callback.message.chat.id, callback.message.message_id)
        except Exception:
            pass
        await callback.bot.send_message(callback.message.chat.id, text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data == "moderator_refresh")
@moderator_only
async def moderator_refresh(callback: CallbackQuery):
    """Обновить панель модератора"""
    async for session in get_db():
        pending_posts = await session.scalar(select(func.count(Post.post_id)).filter(Post.status == "pending"))
        pending_posts = pending_posts or 0
        pending_requests = await session.scalar(select(func.count(ChatJoinRequest.id)).filter(ChatJoinRequest.status == "pending", ChatJoinRequest.chat_id == int(CHANNEL_ID)))
        pending_requests = pending_requests or 0

    is_owner_user = callback.from_user.id in OWNER_IDS
    kb = get_moderator_main_keyboard(pending_posts=pending_posts, pending_requests=pending_requests, is_owner=is_owner_user)
    
    text = f"""📋 *Панель модерации*

🔔 Постов на модерации: *{pending_posts}*
📝 Заявок на вступление: *{pending_requests}*

🔄 _Обновлено_"""
    
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    except Exception as e:
        logger.warning(f"Не удалось обновить панель: {e}")
    await callback.answer("🔄 Обновлено")


@router.callback_query(F.data == "moderator_stats")
@moderator_only
async def moderator_stats_callback(callback: CallbackQuery):
    """Показать статистику постов, пользователей и активность модераторов"""
    is_owner_user = callback.from_user.id in OWNER_IDS
    async for session in get_db():
        # Статистика по постам
        total_posts = await session.scalar(select(func.count(Post.post_id)))
        pending_posts = await session.scalar(select(func.count(Post.post_id)).filter(Post.status == "pending"))
        approved_posts = await session.scalar(select(func.count(Post.post_id)).filter(Post.status == "approved"))
        rejected_posts = await session.scalar(select(func.count(Post.post_id)).filter(Post.status == "rejected"))

        # Статистика по пользователям
        total_users = await session.scalar(select(func.count(User.user_id)))
        banned_users = await session.scalar(select(func.count(User.user_id)).filter(User.is_banned == True))

        # Статистика по заявкам
        total_requests = await session.scalar(select(func.count(ChatJoinRequest.id)))
        pending_requests = await session.scalar(select(func.count(ChatJoinRequest.id)).filter(ChatJoinRequest.status == "pending"))
        approved_requests = await session.scalar(select(func.count(ChatJoinRequest.id)).filter(ChatJoinRequest.status == "approved"))
        rejected_requests = await session.scalar(select(func.count(ChatJoinRequest.id)).filter(ChatJoinRequest.status == "rejected"))

        recent_requests = (
            await session.scalars(
                select(ChatJoinRequest)
                .filter(ChatJoinRequest.status != "pending")
                .order_by(ChatJoinRequest.handled_at.desc())
                .limit(5)
            )
        ).all()

        moderator_activity = (
            await session.execute(
                select(
                    ChatJoinRequest.moderator_id,
                    func.count().label("total"),
                    func.sum(case((ChatJoinRequest.status == "approved", 1), else_=0)).label("approved"),
                    func.sum(case((ChatJoinRequest.status == "rejected", 1), else_=0)).label("rejected"),
                )
                .filter(ChatJoinRequest.status != "pending", ChatJoinRequest.moderator_id.isnot(None))
                .group_by(ChatJoinRequest.moderator_id)
                .order_by(func.count().desc())
                .limit(5)
            )
        ).all()

    profiles = await get_moderator_profiles()
    profiles_map = {p["id"]: p for p in profiles}

    mods_section = "👥 *Список модераторов:*\n"
    if profiles:
        for profile in profiles:
            role_icon = "👑" if profile["is_owner"] else "🛡️"
            mods_section += f"{role_icon} {format_user_reference(profile['username'], profile.get('full_name'), profile['id'])}\n"
    else:
        mods_section += "— пока пусто\n"

    requests_section = f"""📝 *Заявки:*
├ Всего: *{total_requests or 0}*
├ ⏳ В ожидании: *{pending_requests or 0}*
├ ✅ Одобрено: *{approved_requests or 0}*
└ ❌ Отклонено: *{rejected_requests or 0}*"""

    owner_section = ""
    if is_owner_user:
        activity_lines = []
        for row in moderator_activity:
            mod_id = row.moderator_id
            approved_count = row.approved or 0
            rejected_count = row.rejected or 0
            total = row.total or 0
            profile = profiles_map.get(mod_id)
            mod_display = format_user_reference(
                profile["username"] if profile else None,
                profile.get("full_name") if profile else None,
                mod_id,
            ) if mod_id else "—"
            role_icon = "👑" if profile and profile["is_owner"] else "🛡️"
            activity_lines.append(
                f"{role_icon} {mod_display} — ✅ {approved_count} / ❌ {rejected_count} (всего {total})"
            )
        if not activity_lines:
            activity_lines.append("— пока нет обработанных заявок.")

        recent_lines = []
        for req in recent_requests:
            status_icon = "✅" if req.status == "approved" else "❌"
            mod_profile = profiles_map.get(req.moderator_id)
            mod_display = (
                format_user_reference(
                    mod_profile["username"] if mod_profile else None,
                    mod_profile.get("full_name") if mod_profile else None,
                    req.moderator_id,
                )
                if req.moderator_id
                else "—"
            )
            timestamp = req.handled_at.strftime("%d.%m %H:%M") if req.handled_at else "—"
            user_display = format_user_reference(req.username, req.full_name, req.user_id)
            recent_lines.append(f"{status_icon} #{req.id} {user_display} — {mod_display} ({timestamp})")
        if not recent_lines:
            recent_lines.append("— пока нет истории.")

        owner_section = (
            "\n\n🛡️ *Активность модераторов:*\n" + "\n".join(activity_lines) +
            "\n\n🧾 *Последние заявки:*\n" + "\n".join(recent_lines)
        )

    stats_text = f"""📊 *Статистика*

📄 *Посты:*
├ Всего: *{total_posts or 0}*
├ ⏳ На модерации: *{pending_posts or 0}*
├ ✅ Одобрено: *{approved_posts or 0}*
└ ❌ Отклонено: *{rejected_posts or 0}*

👥 *Пользователи:*
├ Всего: *{total_users or 0}*
└ 🚫 Забанено: *{banned_users or 0}*

{requests_section}

{mods_section.strip()}{owner_section}"""

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="moderator_stats")],
        [InlineKeyboardButton(text="↩️ Назад", callback_data="moderator_menu")]
    ])
    
    try:
        await callback.message.edit_text(stats_text, reply_markup=kb, parse_mode="Markdown")
    except Exception as e:
        logger.warning(f"Не удалось показать статистику: {e}")
    await callback.answer()

