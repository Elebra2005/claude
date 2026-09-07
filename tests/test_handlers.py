"""Прогон команд бота со стабами вместо Telegram и сети.

Запуск:  python -m tests.test_handlers
"""

import asyncio
import os
import sys
import tempfile
from dataclasses import dataclass
from datetime import date, timedelta

os.environ.update(
    RATES_BOT_TOKEN="test:token",
    CURRENCIES="CNY,USD,EUR",
    PRIMARY_CURRENCY="CNY",
    MOEX_ENABLED="false",
    DOLGOV_ENABLED="false",
    DIGEST_TIME="10:00",
)

from aiogram import Dispatcher  # noqa: E402

from rates_bot import handlers  # noqa: E402
from rates_bot.config import Config  # noqa: E402
from rates_bot.service import RatesService  # noqa: E402
from rates_bot.storage import Storage  # noqa: E402

FAILED: list[str] = []


def check(name: str, condition: bool, extra: str = "") -> None:
    if condition:
        print(f"  ok   {name}")
    else:
        FAILED.append(name)
        print(f"  FAIL {name} {extra}")


@dataclass
class StubChat:
    id: int


class StubMessage:
    def __init__(self, chat_id: int = 555) -> None:
        self.chat = StubChat(chat_id)
        self.sent: list[str] = []

    async def answer(self, text, **kwargs):
        self.sent.append(text)
        return None

    @property
    def last(self) -> str:
        return self.sent[-1] if self.sent else ""


@dataclass
class StubCommand:
    args: str | None = None


class StubBot:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str]] = []
        self.photos: list[int] = []

    async def send_message(self, chat_id, text, **kwargs):
        self.messages.append((chat_id, text))

    async def send_photo(self, chat_id, photo, **kwargs):
        self.photos.append(chat_id)


def seed(store: Storage) -> None:
    """Юань падает последним днём, доллар и евро стоят ровно."""
    today = date.today()
    for offset in range(120, 0, -1):
        day = today - timedelta(days=offset)
        store.save_rates("CNY", [(day, 12.0 + (offset % 7) * 0.01)])
        store.save_rates("USD", [(day, 81.0 + (offset % 3) * 0.05)])
        store.save_rates("EUR", [(day, 95.0)])
    store.save_rates("CNY", [(today, 11.0)])
    store.save_rates("USD", [(today, 81.0)])
    store.save_rates("EUR", [(today, 95.0)])


async def scenario() -> None:
    config = Config.load()
    check("конфиг: три валюты", config.currencies == ["CNY", "USD", "EUR"])
    check("конфиг: основная CNY", config.primary_currency == "CNY")
    check("конфиг: время сводки", (config.digest_hour, config.digest_minute) == (10, 0))

    with tempfile.TemporaryDirectory() as tmp:
        store = Storage(os.path.join(tmp, "handlers.db"))
        seed(store)
        bot = StubBot()
        service = RatesService(config, store, session=None, bot=bot)

        print("\nРегистрация роутера")
        dispatcher = Dispatcher()
        dispatcher.include_router(handlers.router)
        registered = len(handlers.router.message.handlers)
        check("хендлеры зарегистрированы", registered >= 14, f"их {registered}")

        print("\n/start")
        msg = StubMessage()
        await handlers.cmd_start(msg, service)
        check("ответ на /start", "Подписка оформлена" in msg.last)
        check("подписчик записан", store.subscriber(555) is not None)
        check("валюты перечислены", "CNY, USD, EUR" in msg.last)

        print("\n/rates")
        msg = StubMessage()
        await handlers.cmd_rates(msg, service)
        check("курсы отданы", "Курсы ЦБ" in msg.last)
        check("юань в сводке", "11,0000" in msg.last, msg.last[:300])
        check("все три валюты", all(c in msg.last for c in ("CNY", "USD", "EUR")))

        print("\n/dip")
        msg = StubMessage()
        await handlers.cmd_dip(msg, service)
        check("просадка найдена", "Просадка" in msg.last, msg.last[:200])

        print("\n/history")
        msg = StubMessage()
        await handlers.cmd_history(msg, service, StubCommand("CNY 90"))
        check("история отдана", "за 90 дней" in msg.last)
        check("минимум показан", "минимум" in msg.last)

        msg = StubMessage()
        await handlers.cmd_history(msg, service, StubCommand("XXX"))
        check("неизвестная валюта отсеяна", "Не отслеживаю" in msg.last)

        msg = StubMessage()
        await handlers.cmd_history(msg, service, StubCommand(None))
        check("без аргументов берётся основная", "Юань" in msg.last)

        print("\n/seasonality")
        msg = StubMessage()
        await handlers.cmd_seasonality(msg, service, StubCommand("CNY"))
        check("сезонность посчиталась", "Сезонность" in msg.last or "мало истории" in msg.last)

        print("\n/target")
        msg = StubMessage()
        await handlers.cmd_target(msg, service, StubCommand("CNY 10.5"))
        check("цель принята", "Цель" in msg.last)
        check("цель в базе", store.targets(555)[0][2] == 10.5)

        msg = StubMessage()
        await handlers.cmd_target(msg, service, StubCommand("CNY абв"))
        check("нечисловая цель отсеяна", "положительным числом" in msg.last)

        msg = StubMessage()
        await handlers.cmd_target(msg, service, StubCommand("CNY -5"))
        check("отрицательная цель отсеяна", "положительным числом" in msg.last)

        msg = StubMessage()
        await handlers.cmd_target(msg, service, StubCommand("CNY"))
        check("неполная команда объяснена", "Формат" in msg.last)

        msg = StubMessage()
        await handlers.cmd_targets(msg, service)
        check("список целей", "CNY ≤ 10,50" in msg.last)

        print("\nСрабатывание цели")
        # Курс 11,0 выше цели 10,5 — молчим.
        await service._check_targets({"CNY": await service.stats("CNY")})
        check("цель выше рынка — тишина", bot.messages == [])
        store.set_target(555, "CNY", 11.5)
        await service._check_targets({"CNY": await service.stats("CNY")})
        check("цель достигнута — письмо ушло", len(bot.messages) == 1)
        check("цель снята после срабатывания", store.targets(555) == [])
        await service._check_targets({"CNY": await service.stats("CNY")})
        check("повторно не дублируется", len(bot.messages) == 1)

        print("\nРассылка просадок")
        bot.messages.clear()
        await service.run_dip_alerts()
        check("просадка разослана", len(bot.messages) == 1, f"{len(bot.messages)} сообщений")
        await service.run_dip_alerts()
        check("повтор за ту же дату подавлен", len(bot.messages) == 1)

        print("\n/untarget, /mute, /settings, /stop")
        msg = StubMessage()
        await handlers.cmd_untarget(msg, service, StubCommand("CNY"))
        check("снятие несуществующей цели", "не было" in msg.last)

        msg = StubMessage()
        await handlers.cmd_digest_time(msg, service, StubCommand("09:30"))
        check("время сводки принято", "09:30" in msg.last)
        check("время в базе", store.subscriber(555).digest_hour == 9)

        msg = StubMessage()
        await handlers.cmd_digest_time(msg, service, StubCommand("25:99"))
        check("кривое время отсеяно", "Формат" in msg.last)

        msg = StubMessage()
        await handlers.cmd_mute(msg, service)
        check("mute сработал", store.subscriber(555).alerts_enabled is False)

        bot.messages.clear()
        store.save_rates("CNY", [(date.today() + timedelta(days=1), 10.0)])
        await service.run_dip_alerts()
        check("замьюченному не пишем", bot.messages == [])

        msg = StubMessage()
        await handlers.cmd_unmute(msg, service)
        check("unmute сработал", store.subscriber(555).alerts_enabled is True)

        msg = StubMessage()
        await handlers.cmd_settings(msg, service)
        check("настройки показаны", "Настройки" in msg.last and "09:30" in msg.last)

        print("\n/chart")
        msg = StubMessage()
        photos: list = []

        async def answer_photo(photo, **kwargs):
            photos.append(kwargs.get("caption", ""))

        msg.answer_photo = answer_photo
        await handlers.cmd_chart(msg, service, StubCommand("90"))
        check("график отрисован", len(photos) == 1, f"{len(photos)} фото")
        check("подпись про Долгова", "Долгова" in photos[0], photos[0] if photos else "")

        print("\n/dolgov при выключенном источнике")
        msg = StubMessage()
        await handlers.cmd_dolgov(msg, service)
        check("сообщает, что выключен", "выключен" in msg.last)

        print("\nЕжедневная сводка")
        bot.messages.clear()
        store.set_digest_time(555, *_now_msk())
        await service.run_digests()
        check("сводка ушла", len(bot.messages) == 1, f"{len(bot.messages)} сообщений")
        check("график приложен к сводке", len(bot.photos) == 1, f"{len(bot.photos)} фото")
        await service.run_digests()
        check("вторая сводка за день не ушла", len(bot.messages) == 1)

        msg = StubMessage()
        await handlers.cmd_stop(msg, service)
        check("отписка", store.subscriber(555).active is False)
        bot.messages.clear()
        await service.run_digests()
        check("отписанному не шлём", bot.messages == [])

        print("\nПрочее")
        msg = StubMessage()
        await handlers.fallback(msg)
        check("на текст отвечаем справкой", "Что умеет бот" in msg.last)

        store.close()


def _now_msk() -> tuple[int, int]:
    from datetime import datetime

    from rates_bot.config import MSK

    now = datetime.now(MSK)
    return now.hour, now.minute


def main() -> int:
    asyncio.run(scenario())
    print()
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} — {', '.join(FAILED)}")
        return 1
    print("Все проверки пройдены.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
