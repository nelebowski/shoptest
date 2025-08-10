# -*- coding: utf-8 -*-
from typing import Union

from aiogram import Router, Bot, F
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, Message, PreCheckoutQuery, LabeledPrice
import math

from tgbot.database import Paymentsx, Refillx, Userx
from tgbot.keyboards.inline_user import refill_bill_finl, refill_method_finl
from tgbot.services.api_cryptobot import CryptobotAPI
from tgbot.services.api_yoomoney import YoomoneyAPI
from tgbot.utils.const_functions import is_number, to_number, gen_id, ded
from tgbot.utils.misc.bot_models import FSM, ARS
from tgbot.utils.misc_functions import send_admins

router = Router(name=__name__)

# ───────────────────────────────────────────────────────────────────────────────
# Настройки
MIN_REFILL_RUB = 10           # минимальная сумма пополнения, ₽
MAX_REFILL_RUB = 150_000      # максимальная сумма пополнения, ₽
RUB_PER_STAR = 1.3            # курс для Stars: 1⭐ = 1.3₽

# ───────────────────────────────────────────────────────────────────────────────
# Выбор способа пополнения
@router.callback_query(F.data == "user_refill")
async def refill_method(call: CallbackQuery, bot: Bot, state: FSM, arSession: ARS):
    get_payment = Paymentsx.get()

    # если все способы выключены
    if (
        getattr(get_payment, "status_cryptobot", "False") == "False"
        and getattr(get_payment, "status_yoomoney", "False") == "False"
        and getattr(get_payment, "status_stars", "False") == "False"
    ):
        return await call.answer("❗️ Пополнения временно недоступны", show_alert=True)

    await call.message.edit_text(
        "<b>💰 Выберите способ пополнения баланса</b>",
        reply_markup=refill_method_finl(),
    )

# Выбор способа → ожидание суммы
@router.callback_query(F.data.startswith("user_refill_method:"))
async def refill_method_select(call: CallbackQuery, bot: Bot, state: FSM, arSession: ARS):
    pay_method = call.data.split(":", 1)[1]
    await state.update_data(here_refill_method=pay_method)
    await state.set_state("here_refill_amount")
    await call.message.edit_text("<b>💰 Введите сумму пополнения (₽)</b>")

# ───────────────────────────────────────────────────────────────────────────────
# Ввод суммы
@router.message(F.text, StateFilter("here_refill_amount"))
async def refill_amount_get(message: Message, bot: Bot, state: FSM, arSession: ARS):
    if not is_number(message.text):
        return await message.answer(ded("""
            <b>❌ Данные были введены неверно</b>
            💰 Введите сумму для пополнения средств (₽)
        """))

    pay_amount = int(to_number(message.text))  # рубли, целое
    if pay_amount < MIN_REFILL_RUB or pay_amount > MAX_REFILL_RUB:
        return await message.answer(ded(f"""
            <b>❌ Неверная сумма пополнения</b>
            ❗️ Сумма не должна быть меньше <code>{MIN_REFILL_RUB}₽</code> и больше <code>{MAX_REFILL_RUB}₽</code>
            💰 Введите сумму для пополнения средств (₽)
        """))

    cache_message = await message.answer("<b>♻️ Подождите, платёж генерируется..</b>")
    data = await state.get_data()
    pay_method = data.get("here_refill_method")
    await state.clear()

    # Генерация платежа
    if pay_method == "Stars":
        # количество звёзд округляем вверх
        stars_amount = int(math.ceil(pay_amount / RUB_PER_STAR))
        pay_receipt = gen_id(10)

        await cache_message.delete()
        await bot.send_invoice(
            chat_id=message.from_user.id,
            title="Пополнение баланса",
            description=ded(f"Сумма пополнения: {pay_amount}₽ (~{stars_amount}⭐)\n1⭐ = {RUB_PER_STAR}₽"),
            # Кладём в payload и чек, и сумму в рублях — чтобы не пересчитывать обратно из ⭐
            payload=f"refill:{pay_receipt}:{pay_amount}",
            provider_token="",                # для Stars пустая строка
            currency="XTR",                   # Телеграм-звёзды
            prices=[LabeledPrice(label="Пополнение", amount=stars_amount)],  # amount = кол-во ⭐ (НЕ умножать на 100)
        )
        return

    elif pay_method == "Cryptobot":
        bill_message, bill_link, bill_receipt = await CryptobotAPI(
            bot=bot, arSession=arSession, update=cache_message
        ).bill(pay_amount)

    elif pay_method == "Yoomoney":
        bill_message, bill_link, bill_receipt = await YoomoneyAPI(
            bot=bot, arSession=arSession, update=cache_message
        ).bill(pay_amount)

    else:
        await cache_message.edit_text("<b>❌ Неизвестный способ оплаты</b>")
        return

    # Обработка статуса генерации счёта для YooMoney/CryptoBot
    if bill_message:
        await cache_message.edit_text(
            bill_message,
            reply_markup=refill_bill_finl(bill_link, bill_receipt, pay_method),
        )
    else:
        await cache_message.edit_text("<b>❌ Не удалось сгенерировать платёж. Попробуйте позже</b>")

# ───────────────────────────────────────────────────────────────────────────────
# Проверка платежей — YooMoney
@router.callback_query(F.data.startswith("Pay:Yoomoney"))
async def refill_check_yoomoney(call: CallbackQuery, bot: Bot, state: FSM, arSession: ARS):
    _, pay_method, pay_receipt = call.data.split(":", 2)

    pay_status, pay_amount = await YoomoneyAPI(
        bot=bot, arSession=arSession, update=call
    ).bill_check(pay_receipt)

    if pay_status == 0:
        get_refill = Refillx.get(refill_receipt=pay_receipt)
        if get_refill is None:
            await refill_success(
                bot=bot,
                call=call,
                pay_method=pay_method,
                pay_amount=int(pay_amount),
                pay_receipt=pay_receipt,
                pay_comment=pay_receipt,
            )
        else:
            await call.answer("❗ Ваше пополнение уже зачислено.", True, cache_time=60)
            await call.message.edit_reply_markup()
    elif pay_status == 1:
        await call.answer("❗️ Не удалось проверить платёж. Попробуйте позже", True, cache_time=30)
    elif pay_status == 2:
        await call.answer("❗️ Оплата не была найдена. Попробуйте позже", True, cache_time=5)
    elif pay_status == 3:
        await call.answer("❗️ Оплата была произведена не в рублях", True, cache_time=5)
    else:
        await call.answer(f"❗ Неизвестная ошибка {pay_status}. Обратитесь в поддержку.", True, cache_time=5)

# Проверка платежей — CryptoBot
@router.callback_query(F.data.startswith("Pay:Cryptobot"))
async def refill_check_cryptobot(call: CallbackQuery, bot: Bot, state: FSM, arSession: ARS):
    _, pay_method, pay_comment = call.data.split(":", 2)

    pay_status, pay_amount = await CryptobotAPI(
        bot=bot, arSession=arSession, update=call
    ).bill_check(pay_comment)

    if pay_status == 0:
        get_refill = Refillx.get(refill_comment=pay_comment)
        if get_refill is None:
            await refill_success(
                bot=bot,
                call=call,
                pay_method=pay_method,
                pay_amount=int(pay_amount),
                pay_comment=pay_comment,
            )
        else:
            await call.answer("❗ Ваше пополнение уже зачислено.", True, cache_time=60)
            await call.message.edit_reply_markup()
    elif pay_status == 1:
        await call.answer("❗️ Не удалось проверить платёж. Попробуйте позже", True, cache_time=30)
    elif pay_status == 2:
        await call.answer("❗️ Оплата не была найдена. Попробуйте позже", True, cache_time=5)
    elif pay_status == 3:
        await call.answer("❗️ Вы не успели оплатить счёт", True, cache_time=5)
        await call.message.edit_reply_markup()
    else:
        await call.answer(f"❗ Неизвестная ошибка {pay_status}. Обратитесь в поддержку.", True, cache_time=5)

# ───────────────────────────────────────────────────────────────────────────────
# Зачисление средств (универсально)
async def refill_success(
    bot: Bot,
    call: CallbackQuery,
    pay_method: str,
    pay_amount: int,
    pay_receipt: Union[str, int] = None,
    pay_comment: str = None,
):
    get_user = Userx.get(user_id=call.from_user.id)

    if pay_receipt is None:
        pay_receipt = gen_id(10)
    if pay_comment is None:
        pay_comment = ""

    if pay_method == "Yoomoney":
        text_method = "ЮMoney"
    elif pay_method == "Cryptobot":
        text_method = "CryptoBot"
    elif pay_method == "Stars":
        text_method = "Telegram Stars"
    else:
        text_method = f"Unknown - {pay_method}"

    pay_amount = int(pay_amount)

    Refillx.add(
        user_id=get_user.user_id,
        refill_comment=pay_comment,
        refill_amount=pay_amount,
        refill_receipt=pay_receipt,
        refill_method=pay_method,
    )

    Userx.update(
        call.from_user.id,
        user_balance=int(get_user.user_balance) + pay_amount,
        user_refill=int(get_user.user_refill) + pay_amount,
    )

    await call.message.edit_text(ded(f"""
        <b>💰 Вы пополнили баланс на сумму <code>{pay_amount}₽</code>. Удачи ❤️
        🧾 Чек: <code>#{pay_receipt}</code></b>
    """))

    await send_admins(
        bot,
        ded(f"""
            👤 Пользователь: <b>@{get_user.user_login}</b> | <a href='tg://user?id={get_user.user_id}'>{get_user.user_name}</a> | <code>{get_user.user_id}</code>
            💰 Сумма пополнения: <code>{pay_amount}₽</code> <code>({text_method})</code>
            🧾 Чек: <code>#{pay_receipt}</code>
        """),
    )

# ───────────────────────────────────────────────────────────────────────────────
# Stars: подтверждение и успешная оплата
@router.pre_checkout_query()
async def stars_pre_checkout(pre_checkout_query: PreCheckoutQuery, bot: Bot, state: FSM, arSession: ARS):
    # Для Stars просто подтверждаем
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@router.message(F.successful_payment)
async def refill_stars_success(message: Message, bot: Bot, state: FSM, arSession: ARS):
    payload = message.successful_payment.invoice_payload
    if payload.startswith("refill:"):
        # payload = "refill:{receipt}:{pay_amount_rub}"
        parts = payload.split(":", 2)
        if len(parts) != 3:
            return
        _, pay_receipt, pay_amount_str = parts
        pay_amount = int(pay_amount_str)

        await refill_success_message(
            bot=bot,
            message=message,
            pay_amount=pay_amount,
            pay_receipt=pay_receipt,
        )

    elif payload.startswith("buy:"):
        # payload = "buy:{receipt}:{server}:{account}:{amount}:{pay_amount_rub}"
        parts = payload.split(":", 5)
        if len(parts) != 6:
            return
        _, pay_receipt, server, account, amount, pay_amount_str = parts
        pay_amount = int(pay_amount_str)

        await buy_success_message(
            bot=bot,
            message=message,
            pay_amount=pay_amount,
            pay_receipt=pay_receipt,
            server=server,
            account=account,
            amount=amount,
        )
    else:
        # Не наш payload — игнор
        return

# ───────────────────────────────────────────────────────────────────────────────
# Зачисление средств после оплаты звёздами (refill)
async def refill_success_message(
    bot: Bot,
    message: Message,
    pay_amount: int,
    pay_receipt: str,
):
    get_user = Userx.get(user_id=message.from_user.id)
    pay_amount = int(pay_amount)

    Refillx.add(
        user_id=get_user.user_id,
        refill_comment=pay_receipt,   # как идентификатор для Stars
        refill_amount=pay_amount,
        refill_receipt=pay_receipt,
        refill_method="Stars",
    )

    Userx.update(
        message.from_user.id,
        user_balance=int(get_user.user_balance) + pay_amount,
        user_refill=int(get_user.user_refill) + pay_amount,
    )

    await message.answer(ded(f"""
        <b>💰 Вы пополнили баланс на сумму <code>{pay_amount}₽</code>. Удачи ❤️
        🧾 Чек: <code>#{pay_receipt}</code></b>
    """))

    await send_admins(
        bot,
        ded(f"""
            👤 Пользователь: <b>@{get_user.user_login}</b> | <a href='tg://user?id={get_user.user_id}'>{get_user.user_name}</a> | <code>{get_user.user_id}</code>
            💰 Сумма пополнения: <code>{pay_amount}₽</code> <code>(Telegram Stars)</code>
            🧾 Чек: <code>#{pay_receipt}</code>
        """),
    )

# ───────────────────────────────────────────────────────────────────────────────
# (опционально) Успешная покупка через Stars — если используешь payload "buy:*"
async def buy_success_message(
    bot: Bot,
    message: Message,
    pay_amount: int,
    pay_receipt: str,
    server: str,
    account: str,
    amount: str,
):
    get_user = Userx.get(user_id=message.from_user.id)
    amount_int = int(amount)

    await message.answer(ded(f"""
        <b>Заказ принят!</b>
        Сервер: {server}
        Счёт: {account}
        Кол-во валюты: {amount_int} млн
        Сумма: {pay_amount}₽
        🧾 Чек: <code>#{pay_receipt}</code>
        Ожидайте выдачу в течение 5–10 минут.
    """))

    await send_admins(
        bot,
        ded(f"""
            👤 Пользователь: <b>@{get_user.user_login}</b> | <a href='tg://user?id={get_user.user_id}'>{get_user.user_name}</a> | <code>{get_user.user_id}</code>
            🕹 Сервер: {server}
            🎮 Счёт: {account}
            💰 Кол-во валюты: {amount_int} млн
            💵 Сумма: {pay_amount}₽ (Telegram Stars)
            🧾 Чек: <code>#{pay_receipt}</code>
        """),
    )
