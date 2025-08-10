# - *- coding: utf- 8 - *-
import asyncio

from aiogram import Router, Bot, F
from aiogram.filters import Command, StateFilter
from aiogram.types import CallbackQuery, Message

from tgbot.data.config import BOT_VERSION, get_desc
import math

from tgbot.database import Purchasesx
from tgbot.keyboards.inline_user import start_menu_finl, order_pay_method_finl
from tgbot.keyboards.inline_user_page import *
from tgbot.utils.const_functions import ded, del_message, convert_date, send_admins, ikb
from tgbot.utils.misc.bot_models import FSM, ARS
from tgbot.utils.misc_functions import upload_text, insert_tags, get_items_available
from tgbot.utils.text_functions import open_profile_user
from aiogram.utils.keyboard import InlineKeyboardBuilder

router = Router(name=__name__)


# Стартовое меню
@router.callback_query(F.data == "buy_currency")
async def buy_currency_start(call: CallbackQuery, bot: Bot, state: FSM, arSession: ARS):
    await state.clear()
    await call.message.edit_text("<b>Выберите сервер</b>", reply_markup=buy_servers_swipe_fp(0))


@router.callback_query(F.data.startswith("servers_page:"))
async def buy_currency_page(call: CallbackQuery, bot: Bot, state: FSM, arSession: ARS):
    page = int(call.data.split(":")[1])
    await call.message.edit_text("<b>Выберите сервер</b>", reply_markup=buy_servers_swipe_fp(page))


@router.callback_query(F.data.startswith("select_server:"))
async def buy_currency_server(call: CallbackQuery, bot: Bot, state: FSM, arSession: ARS):
    server = int(call.data.split(":")[1])
    await state.update_data(buy_server=server)
    await state.set_state("buy_amount")
    kb = InlineKeyboardBuilder()
    kb.row(ikb("🔙 Назад", data="buy_currency"))
    await call.message.edit_text("<b>Введите количество валюты</b>", reply_markup=kb.as_markup())


@router.message(StateFilter("buy_amount"))
async def buy_currency_amount(message: Message, bot: Bot, state: FSM, arSession: ARS):
    if not message.text.isdigit():
        return await message.answer("<b>Введите число</b>")
    amount = int(message.text)
    await state.update_data(buy_amount=amount)
    await state.set_state("buy_account")
    await message.answer("<b>Введите номер игрового счёта</b>")


@router.message(StateFilter("buy_account"))
async def buy_currency_account(message: Message, bot: Bot, state: FSM, arSession: ARS):
    data = await state.get_data()
    server = data['buy_server']
    amount = data['buy_amount']
    account = message.text
    pay_amount = amount
    stars_amount = math.ceil(pay_amount / 1.45)
    await state.update_data(buy_account=account, pay_amount=pay_amount)
    await state.set_state("order_pay")
    await message.answer(
        ded(f"""
            Ваш заказ:
            Сервер: {server}
            Счёт: {account}
            Кол-во валюты: {amount}
            К оплате: {pay_amount}₽ (~{stars_amount}⭐)
            Выберите способ оплаты:
        """),
        reply_markup=order_pay_method_finl(),
    )


@router.callback_query(F.data.startswith("order_pay:"), StateFilter("order_pay"))
async def order_pay_call(call: CallbackQuery, bot: Bot, state: FSM, arSession: ARS):
    method = call.data.split(":")[1]
    await call.answer(f"Оплата {method} пока в разработке", True)
    await call.message.edit_reply_markup()


@router.callback_query(F.data == "user_reviews")
async def user_reviews(call: CallbackQuery, bot: Bot, state: FSM, arSession: ARS):
    await state.clear()
    await call.message.edit_text("<b>Отзывы пока отсутствуют</b>", reply_markup=start_menu_finl())


@router.callback_query(F.data == "support_chat")
async def support_chat_start(call: CallbackQuery, bot: Bot, state: FSM, arSession: ARS):
    await state.set_state("support_message")
    kb = InlineKeyboardBuilder()
    kb.row(ikb("🔙 Назад", data="main_menu"))
    await call.message.edit_text("<b>Опишите вашу проблему</b>", reply_markup=kb.as_markup())


@router.message(StateFilter("support_message"))
async def support_chat_message(message: Message, bot: Bot, state: FSM, arSession: ARS):
    await state.clear()
    await send_admins(
        bot,
        ded(f"""
            🆘 Сообщение от <a href='tg://user?id={message.from_user.id}'>{message.from_user.full_name}</a> <code>{message.from_user.id}</code>
            {message.text}
        """),
    )
    await message.answer("<b>Сообщение отправлено. Ожидайте ответа.</b>", reply_markup=start_menu_finl())

# Открытие товаров
@router.message(F.text == "🎁 Купить")
async def user_shop(message: Message, bot: Bot, state: FSM, arSession: ARS):
    await state.clear()

    get_categories = get_categories_items()

    if len(get_categories) >= 1:
        await message.answer(
            "<b>🎁 Выберите нужный вам товар</b>",
            reply_markup=prod_item_category_swipe_fp(0),
        )
    else:
        await message.answer("<b>🎁 Увы, товары в данное время отсутствуют</b>")


# Открытие профиля
@router.message(F.text == "👤 Профиль")
async def user_profile(message: Message, bot: Bot, state: FSM, arSession: ARS):
    await state.clear()

    await open_profile_user(bot, message.from_user.id)



# Открытие сообщения с ссылкой на поддержку
# Получение версии бота
@router.message(Command(commands=['version']))
async def admin_version(message: Message, bot: Bot, state: FSM, arSession: ARS):
    await state.clear()

    await message.answer(f"<b>❇️ Текущая версия бота: <code>{BOT_VERSION}</code></b>")


# Получение информации о боте
@router.message(Command(commands=['dj_desc']))
async def admin_desc(message: Message, bot: Bot, state: FSM, arSession: ARS):
    await state.clear()

    await message.answer(get_desc(), disable_web_page_preview=True)


################################################################################
# Возвращение к профилю
@router.callback_query(F.data == "user_profile")
async def user_profile_return(call: CallbackQuery, bot: Bot, state: FSM, arSession: ARS):
    await state.clear()

    await del_message(call.message)
    await open_profile_user(bot, call.from_user.id)


# Просмотр истории покупок
@router.callback_query(F.data == "user_purchases")
async def user_purchases(call: CallbackQuery, bot: Bot, state: FSM, arSession: ARS):
    get_purchases = Purchasesx.gets(user_id=call.from_user.id)
    get_purchases = get_purchases[-5:]

    if len(get_purchases) >= 1:
        await call.answer("🎁 Последние 5 покупок")
        await del_message(call.message)

        for purchase in get_purchases:
            link_items = await upload_text(arSession, purchase.purchase_data)

            await call.message.answer(
                ded(f"""
                    <b>🧾 Чек: <code>#{purchase.purchase_receipt}</code></b>
                    ▪️ Товар: <code>{purchase.purchase_position_name} | {purchase.purchase_count}шт | {int(purchase.purchase_price)}₽</code>
                    ▪️ Дата покупки: <code>{convert_date(purchase.purchase_unix)}</code>
                    ▪️ Товары: <a href='{link_items}'>кликабельно</a>
                """)
            )

            await asyncio.sleep(0.2)

        await open_profile_user(bot, call.from_user.id)
    else:
        await call.answer("❗ У вас отсутствуют покупки", True)


# Страницы наличия товаров
@router.callback_query(F.data.startswith("user_available_swipe:"))
async def user_available_swipe(call: CallbackQuery, bot: Bot, state: FSM, arSession: ARS):
    remover = int(call.data.split(":")[1])

    items_available = get_items_available()

    if remover >= len(items_available):
        remover = len(items_available) - 1
    if remover < 0:
        remover = 0

    await call.message.edit_text(
        items_available[remover],
        reply_markup=prod_available_swipe_fp(remover, len(items_available)),
    )
