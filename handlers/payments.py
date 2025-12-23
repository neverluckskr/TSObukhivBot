"""
Обработчики платежей
"""
import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, LabeledPrice, Message, PreCheckoutQuery, SuccessfulPayment
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database.db import create_payment, get_db, get_or_create_user
from states.states import PostStates
from utils.texts import PAYMENT_ERROR_MESSAGE, PAYMENT_SUCCESS_MESSAGE

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data.startswith("pay_stars_"))
async def process_pay_stars(callback: CallbackQuery, state: FSMContext):
    """Обработка оплаты через Telegram Stars"""
    bot = callback.bot
    
    amount = int(callback.data.split("_")[2])
    
    # Определяем тип поста
    current_state = await state.get_state()
    if current_state == PostStates.waiting_payment_35:
        post_type = "ad35"
        post_type_name = "про подики/жидкости"
    elif current_state == PostStates.waiting_payment_50:
        post_type = "offtopic50"
        post_type_name = "не по тематике"
    else:
        await callback.answer("❌ Ошибка состояния.", show_alert=True)
        return
    
    # Сохраняем информацию о платеже в состоянии
    await state.update_data(
        post_type=post_type,
        amount=amount,
        payment_method="stars",
    )
    
    try:
        # Создаем invoice через sendInvoice (правильный способ для Telegram Stars)
        # Payload должен быть уникальным для каждого платежа
        import time
        payload = f"post_{post_type}_{callback.from_user.id}_{int(time.time())}"
        
        # Для Telegram Stars (XTR) цена указывается напрямую в Stars
        # НЕ нужно умножать на 100, как для обычных валют
        # Telegram API автоматически обработает это правильно
        
        await bot.send_invoice(
            chat_id=callback.from_user.id,
            title=f"Пост в канал ({amount} грн)",
            description=f"Оплата за {post_type_name} пост в канал «Тёмная сторона Обухова»",
            payload=payload,
            provider_token="",  # Пустая строка для цифровых товаров (Telegram Stars)
            currency="XTR",  # Telegram Stars
            prices=[LabeledPrice(label=f"Пост в канал ({amount} ⭐)", amount=amount)],  # Напрямую в Stars
            start_parameter=payload,  # Для возможности пересылки invoice
        )
        
        await callback.answer("💳 Счет на оплату отправлен!")
    except Exception as e:
        logger.error(f"Ошибка создания invoice: {e}")
        await callback.answer(PAYMENT_ERROR_MESSAGE, show_alert=True)


@router.callback_query(F.data.startswith("pay_stripe_"))
async def process_pay_stripe(callback: CallbackQuery, state: FSMContext):
    """Обработка оплаты через карту (Smart Glocal)"""
    bot = callback.bot
    
    amount = int(callback.data.split("_")[2])
    
    # Определяем тип поста
    current_state = await state.get_state()
    if current_state == PostStates.waiting_payment_35:
        post_type = "ad35"
        post_type_name = "про подики/жидкости"
    elif current_state == PostStates.waiting_payment_50:
        post_type = "offtopic50"
        post_type_name = "не по тематике"
    else:
        await callback.answer("❌ Ошибка состояния.", show_alert=True)
        return
    
    if not settings.PROVIDER_TOKEN:
        await callback.answer(
            "❌ Оплата через карту временно недоступна. Используйте Telegram Stars.",
            show_alert=True,
        )
        return
    
    # Сохраняем информацию о платеже в состоянии
    await state.update_data(
        post_type=post_type,
        amount=amount,
        payment_method="card",
    )
    
    try:
        # Создаем invoice через sendInvoice с оплатой картой
        import time
        payload = f"post_{post_type}_{callback.from_user.id}_{int(time.time())}"
        
        await bot.send_invoice(
            chat_id=callback.from_user.id,
            title=f"Пост в канал ({amount} грн)",
            description=f"Оплата за пост {post_type_name} в канал «Тёмная сторона Обухова»",
            payload=payload,
            provider_token=settings.PROVIDER_TOKEN,  # Токен Smart Glocal
            currency="UAH",  # Гривна
            prices=[LabeledPrice(label=f"Пост в канал ({amount} грн)", amount=amount * 100)],  # В копейках (1 грн = 100 копеек)
            start_parameter=payload,
        )
        
        await callback.answer("💳 Счет на оплату отправлен!")
    except Exception as e:
        logger.error(f"Ошибка создания invoice для оплаты картой: {e}")
        await callback.answer(PAYMENT_ERROR_MESSAGE, show_alert=True)


@router.message(lambda m: m.successful_payment is not None)
async def process_successful_payment(message: Message, state: FSMContext):
    """Обработка успешной оплаты"""
    payment: SuccessfulPayment = message.successful_payment
    
    # Получаем данные из состояния (если есть)
    data = await state.get_data()
    post_type = data.get("post_type")
    amount = data.get("amount")
    payment_method = data.get("payment_method", "stars")
    
    # Если нет в состоянии, пытаемся определить из payload
    # Формат payload: "post_{post_type}_{user_id}_{timestamp}"
    if not post_type:
        payload = payment.invoice_payload
        if payload and payload.startswith("post_"):
            parts = payload.split("_")
            if len(parts) >= 2:
                post_type = parts[1]  # ad35 или offtopic50
                if not amount:
                    # Определяем amount в зависимости от валюты
                    if payment.currency == "XTR":
                        # Для Telegram Stars total_amount уже в Stars
                        amount = int(payment.total_amount)
                    else:
                        # Для других валют (UAH и т.д.) total_amount в минимальных единицах (копейки)
                        amount = int(payment.total_amount / 100)
    
    if not post_type:
        logger.error(f"Не удалось определить тип поста из платежа. Payload: {payment.invoice_payload}")
        await message.answer(
            "❌ Ошибка обработки платежа. Обратитесь к администратору."
        )
        return
    
    # Определяем payment_method по валюте, если не указан
    if not payment_method or payment_method == "stars":
        if payment.currency == "XTR":
            payment_method = "stars"
        else:
            payment_method = "card"
    
    # Сохраняем платеж в БД
    async for session in get_db():
        await get_or_create_user(
            session,
            message.from_user.id,
            message.from_user.username,
            message.from_user.first_name,
        )
        
        # Определяем сумму для сохранения
        if payment.currency == "XTR":
            # Для Stars уже в Stars
            payment_amount = float(amount or payment.total_amount)
        else:
            # Для других валют делим на 100 (из копеек в основную валюту)
            payment_amount = float(amount or payment.total_amount / 100)
        
        await create_payment(
            session,
            message.from_user.id,
            post_type,
            payment_amount,
            payment.currency,
            payment_method,
            payment.telegram_payment_charge_id,
        )
        
        logger.info(
            f"Платеж успешно обработан: user_id={message.from_user.id}, "
            f"post_type={post_type}, amount={amount}, charge_id={payment.telegram_payment_charge_id}"
        )
    
    # Устанавливаем состояние для получения поста
    if post_type == "ad35":
        await state.set_state(PostStates.waiting_ad_post)
    elif post_type == "offtopic50":
        await state.set_state(PostStates.waiting_offtopic_post)
    else:
        logger.warning(f"Неизвестный тип поста: {post_type}")
    
    await message.answer(PAYMENT_SUCCESS_MESSAGE)


@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    """Обработка pre-checkout запроса"""
    # Проверяем payload и подтверждаем платеж
    payload = pre_checkout_query.invoice_payload
    
    # Проверяем, что это наш платеж
    if payload and payload.startswith("post_"):
        # Подтверждаем платеж
        await pre_checkout_query.answer(ok=True)
        logger.info(f"Pre-checkout подтвержден для payload: {payload}")
    else:
        # Отклоняем платеж с причиной
        await pre_checkout_query.answer(
            ok=False,
            error_message="Ошибка: неверный формат платежа. Попробуйте снова."
        )
        logger.warning(f"Pre-checkout отклонен для payload: {payload}")

