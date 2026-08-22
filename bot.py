import os
import uuid
import json
import asyncio
import secrets
import string
from datetime import datetime, timedelta, timezone

import psycopg2

import aiohttp
from dotenv import load_dotenv
from yookassa import Configuration, Payment

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")

REMNAWAVE_API_TOKEN = os.getenv("REMNAWAVE_API_TOKEN")
API_BASE_URL = os.getenv("API_BASE_URL", "http://remnawave:3000/api").rstrip("/")
SUBSCRIPTION_URL = os.getenv("SUBSCRIPTION_URL", "https://subnikitusik.ncknms.com").rstrip("/")
FAMILY_SQUAD_UUID = os.getenv("FAMILY_SQUAD_UUID", "cadf2316-9ef9-4e9c-9e2f-20513068f9cd")

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "103c04531ada_remnawave-db")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.getenv("POSTGRES_DB", "postgres")
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")

Configuration.account_id = YOOKASSA_SHOP_ID
Configuration.secret_key = YOOKASSA_SECRET_KEY

TARIFFS = {
    "1m": {"title": "1 месяц", "days": 30, "price": "150.00"},
    "3m": {"title": "3 месяца", "days": 90, "price": "400.00"},
    "6m": {"title": "6 месяцев", "days": 180, "price": "750.00"},
    "12m": {"title": "1 год", "days": 365, "price": "1450.00"},
}

pending_payments = {}

bot = Bot(BOT_TOKEN)
dp = Dispatcher()


def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Купить подписку", callback_data="buy")],
        [InlineKeyboardButton(text="📘 Инструкция", callback_data="help")],
    ])


def tariffs_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1 месяц — 150 ₽", callback_data="tariff:1m")],
        [InlineKeyboardButton(text="3 месяца — 400 ₽", callback_data="tariff:3m")],
        [InlineKeyboardButton(text="6 месяцев — 750 ₽", callback_data="tariff:6m")],
        [InlineKeyboardButton(text="1 год — 1450 ₽", callback_data="tariff:12m")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")],
    ])


def pay_keyboard(payment_url: str, payment_id: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплатить", url=payment_url)],
        [InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"check:{payment_id}")],
    ])


def instruction_text(sub_url: str):
    return (
        "✅ Оплата получена.\n\n"
        f"Ваша ссылка подписки:\n{sub_url}\n\n"
        "В подписке доступны 3 сервера:\n"
        "🇫🇮 Финляндия\n"
        "🇩🇪 Германия\n"
        "🇳🇱 Нидерланды\n\n"
        "Выбор сервера выполняется в приложении после добавления подписки.\n\n"
        "Инструкция:\n"
        "1. Установите Happ, Hiddify или Koala Clash.\n"
        "2. Нажмите «Добавить подписку».\n"
        "3. Вставьте ссылку выше.\n"
        "4. Обновите профиль.\n"
        "5. Выберите нужный сервер и подключитесь.\n\n"
        "Для Koala Clash можно использовать Clash/Mihomo формат:\n"
        f"{sub_url}?format=clash"
    )


async def remna_request(method: str, path: str, payload: dict | None = None):
    url = f"{API_BASE_URL}/{path.lstrip('/')}"
    headers = {
        "Authorization": f"Bearer {REMNAWAVE_API_TOKEN}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    async with aiohttp.ClientSession() as session:
        async with session.request(method, url, headers=headers, json=payload, timeout=30) as resp:
            text = await resp.text()
            if resp.status >= 400:
                raise RuntimeError(f"Remnawave API error {resp.status}: {text[:1000]}")
            if not text:
                return {}
            try:
                return json.loads(text)
            except Exception:
                return {"raw": text}



def _rand_token(length=32):
    alphabet = string.ascii_letters + string.digits + "_-"
    return "".join(secrets.choice(alphabet) for _ in range(length))



def _db_create_user(tg_id: int, username: str, days: int):
    safe_name = username or f"user_{tg_id}"
    safe_name = "".join(c if c.isalnum() or c in "_-" else "_" for c in safe_name)
    suffix = _rand_token(6)
    remna_username = f"tg_{tg_id}_{safe_name}_{suffix}"[:32]

    user_uuid = str(uuid.uuid4())
    vless_uuid = str(uuid.uuid4())
    short_uuid = _rand_token(16)
    trojan_password = _rand_token(32)
    ss_password = _rand_token(32)
    expire_at = datetime.now(timezone.utc) + timedelta(days=days)

    conn = psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
    )
    conn.autocommit = False

    try:
        with conn.cursor() as cur:
            cur.execute("select coalesce(max(t_id), 0) + 1 from users")
            t_id = cur.fetchone()[0]

            cur.execute(
                """
                insert into users (
                    uuid,
                    short_uuid,
                    username,
                    status,
                    traffic_limit_bytes,
                    traffic_limit_strategy,
                    expire_at,
                    sub_revoked_at,
                    last_traffic_reset_at,
                    trojan_password,
                    vless_uuid,
                    ss_password,
                    created_at,
                    updated_at,
                    description,
                    email,
                    telegram_id,
                    hwid_device_limit,
                    tag,
                    last_triggered_threshold,
                    t_id,
                    external_squad_uuid
                )
                values (
                    %s, %s, %s, 'ACTIVE',
                    0, 'NO_RESET',
                    %s,
                    null, null,
                    %s, %s, %s,
                    now(), now(),
                    null, null, %s,
                    null, null,
                    0,
                    %s,
                    null
                )
                """,
                (
                    user_uuid,
                    short_uuid,
                    remna_username,
                    expire_at.replace(tzinfo=None),
                    trojan_password,
                    vless_uuid,
                    ss_password,
                    str(tg_id),
                    t_id,
                ),
            )

            cur.execute(
                """
                insert into user_traffic
                (t_id, used_traffic_bytes, lifetime_used_traffic_bytes, online_at, last_connected_node_uuid, first_connected_at)
                values (%s, 0, 0, null, null, null)
                on conflict do nothing
                """,
                (t_id,)
            )

            cur.execute(
                """
                insert into internal_squad_members (internal_squad_uuid, user_id)
                values (%s, %s)
                on conflict do nothing
                """,
                (FAMILY_SQUAD_UUID, t_id),
            )

        conn.commit()
        return f"{SUBSCRIPTION_URL}/{short_uuid}"

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


async def create_remna_user(tg_id: int, username: str, days: int):
    # 1. Создаём пользователя старым SQL-способом
    sub_url = await asyncio.to_thread(_db_create_user, tg_id, username, days)
    old_short = sub_url.rstrip("/").split("/")[-1]

    # 2. Берём UUID созданного пользователя
    conn = psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
    )

    try:
        with conn.cursor() as cur:
            cur.execute(
                "select uuid from users where short_uuid = %s limit 1",
                (old_short,),
            )
            row = cur.fetchone()

        if not row:
            raise RuntimeError(f"Created user not found by short_uuid={old_short}")

        user_uuid = str(row[0])

    finally:
        conn.close()

    # 3. Штатный перевыпуск подписки Remnawave
    headers = {
        "Authorization": f"Bearer {REMNAWAVE_API_TOKEN}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Forwarded-Proto": "https",
        "X-Forwarded-For": "127.0.0.1",
        "X-Real-IP": "127.0.0.1",
    }

    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.post(
            f"{API_BASE_URL}/users/bulk/revoke-subscription",
            json={"uuids": [user_uuid]},
            timeout=30,
        ) as resp:
            text = await resp.text()
            if resp.status not in (200, 201):
                raise RuntimeError(f"Subscription reissue failed: {resp.status} {text[:500]}")

    # 4. Забираем новый short_uuid после перевыпуска
    await asyncio.sleep(1)

    conn = psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
    )

    try:
        with conn.cursor() as cur:
            cur.execute(
                "select short_uuid from users where uuid = %s limit 1",
                (user_uuid,),
            )
            row = cur.fetchone()

        if not row or not row[0]:
            raise RuntimeError(f"Reissued user has no short_uuid, uuid={user_uuid}")

        return f"{SUBSCRIPTION_URL}/{row[0]}"

    finally:
        conn.close()


@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "Добро пожаловать.\n\n"
        "Здесь вы можете оформить доступ к VPN-сервису с тремя серверными локациями.\n\n"
        "В подписку включены:\n"
        "🇫🇮 Финляндия\n"
        "🇩🇪 Германия\n"
        "🇳🇱 Нидерланды\n\n"
        "После оплаты бот автоматически выдаст персональную ссылку подписки и краткую инструкцию по подключению.\n"
        "Выбор нужного сервера выполняется в приложении после добавления подписки.",
        reply_markup=main_menu(),
    )


@dp.callback_query(F.data == "back")
async def back(callback: CallbackQuery):
    await callback.message.edit_text("Выберите действие:", reply_markup=main_menu())
    await callback.answer()


@dp.callback_query(F.data == "buy")
async def buy(callback: CallbackQuery):
    await callback.message.edit_text("Выберите тариф:", reply_markup=tariffs_menu())
    await callback.answer()


@dp.callback_query(F.data == "help")
async def help_cb(callback: CallbackQuery):
    await callback.message.edit_text(
        "Инструкция после оплаты:\n\n"
        "1. Установите Happ, Hiddify или Koala Clash.\n"
        "2. Добавьте подписку по ссылке.\n"
        "3. Обновите профиль.\n"
        "4. Подключитесь.",
        reply_markup=main_menu(),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("tariff:"))
async def choose_tariff(callback: CallbackQuery):
    tariff_id = callback.data.split(":", 1)[1]
    tariff = TARIFFS[tariff_id]

    payment = Payment.create({
        "amount": {
            "value": tariff["price"],
            "currency": "RUB",
        },
        "confirmation": {
            "type": "redirect",
            "return_url": "https://t.me/",
        },
        "capture": True,
        "description": f"VPN подписка {tariff['title']} для Telegram ID {callback.from_user.id}",
        "metadata": {
            "telegram_id": str(callback.from_user.id),
            "tariff_id": tariff_id,
        },
    }, uuid.uuid4().hex)

    payment_id = payment.id
    payment_url = payment.confirmation.confirmation_url

    pending_payments[payment_id] = {
        "telegram_id": callback.from_user.id,
        "username": callback.from_user.username or callback.from_user.first_name or "client",
        "tariff_id": tariff_id,
    }

    await callback.message.edit_text(
        f"Тариф: {tariff['title']}\n"
        f"К оплате: {tariff['price']} ₽\n\n"
        "Нажмите «Оплатить», затем вернитесь сюда и нажмите «Я оплатил».",
        reply_markup=pay_keyboard(payment_url, payment_id),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("check:"))
async def check_payment(callback: CallbackQuery):
    payment_id = callback.data.split(":", 1)[1]
    info = pending_payments.get(payment_id)

    if not info:
        await callback.answer("Платёж не найден. Начните покупку заново.", show_alert=True)
        return

    payment = Payment.find_one(payment_id)

    if payment.status != "succeeded":
        await callback.answer("Оплата пока не найдена. Подождите немного и нажмите снова.", show_alert=True)
        return

    tariff = TARIFFS[info["tariff_id"]]

    try:
        sub_url = await create_remna_user(
            tg_id=info["telegram_id"],
            username=info["username"],
            days=tariff["days"],
        )
    except Exception as e:
        await callback.message.answer(
            "Оплата прошла, но не удалось автоматически создать подписку.\n"
            "Администратор скоро выдаст её вручную.\n\n"
            f"Ошибка: {str(e)[:1000]}"
        )
        raise

    await callback.message.edit_text(instruction_text(sub_url))
    await callback.answer("Готово")


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
