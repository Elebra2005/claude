"""Telegram-бот: «автобус 814 на остановке — пора выходить».

Раз в POLL_INTERVAL секунд бот запрашивает у Яндекс.Карт прогноз прибытия
маршрута на остановку STOP_ID («Касимовская улица»). Когда прогноз
опускается до NOTIFY_ETA_MIN (автобус подъезжает или уже стоит на
остановке), бот присылает уведомление. Если автобус проскочил остановку
между двумя опросами, уведомление всё равно придёт. Следующее — только
про следующий автобус.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from dotenv import load_dotenv

from yandex_transport import Arrival, YandexError, YandexTransport

load_dotenv()

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ROUTE = os.getenv("ROUTE", "814")
STOP_ID = os.getenv("STOP_ID", "")               # напр. stop__9643291
STOP_NAME = os.getenv("STOP_NAME", "Касимовская улица")
# Прогноз до STOP_ID не больше этого (мин) — считаем, что автобус на остановке
NOTIFY_ETA_MIN = float(os.getenv("NOTIFY_ETA_MIN") or os.getenv("DEPART_ETA_MIN") or "1")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "20"))
# Когда присылать уведомления (по Москве): дни 1=пн..7=вс и окно времени
ACTIVE_DAYS = os.getenv("ACTIVE_DAYS", "1-5")
ACTIVE_FROM = os.getenv("ACTIVE_FROM", "07:00")
ACTIVE_TO = os.getenv("ACTIVE_TO", "09:30")
# Кому можно пользоваться ботом (через запятую). Пусто — всем.
ALLOWED_CHAT_IDS = {int(x) for x in os.getenv("ALLOWED_CHAT_IDS", "").replace(" ", "").split(",") if x}
STATE_FILE = Path(os.getenv("STATE_FILE", "data/subscribers.json"))

# Фиксированное смещение, а не ZoneInfo — в контейнере может не быть tzdata.
MSK = timezone(timedelta(hours=3))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("bus814")


def parse_days(spec: str) -> set[int]:
    days: set[int] = set()
    for part in spec.replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-")
            days.update(range(int(a), int(b) + 1))
        else:
            days.add(int(part))
    return days


def parse_hm(s: str):
    h, m = s.split(":")
    return int(h), int(m)


def in_active_window(now: datetime) -> bool:
    if now.isoweekday() not in parse_days(ACTIVE_DAYS):
        return False
    t = (now.hour, now.minute)
    return parse_hm(ACTIVE_FROM) <= t < parse_hm(ACTIVE_TO)


class ArrivalDetector:
    """Автомат «взведён → сработал → ждёт, пока автобус проедет».

    Срабатывает, когда ближайший прогноз опустился до threshold.
    Перевзводится, когда близких прогнозов больше нет (автобус проехал
    остановку) или у ближайшего автобуса сменился vehicleId.

    Подстраховка: если на прошлом опросе автобус был в пределах grace,
    а теперь исчез (проехал остановку между опросами), а уведомления
    про него не было — тоже срабатывает.
    """

    def __init__(self, threshold_sec: float, grace_sec: float):
        self.threshold = threshold_sec
        self.grace = grace_sec
        self.fired_vehicle: str | None = None
        self.fired = False
        self.prev: Arrival | None = None

    def _passed(self, arrivals: list[Arrival]) -> bool:
        prev = self.prev
        if prev is None or prev.eta_sec > self.grace:
            return False
        if prev.vehicle_id is not None:
            return all(a.vehicle_id != prev.vehicle_id for a in arrivals)
        # без vehicleId: ближайший прогноз заметно вырос — значит это уже другой автобус
        return not arrivals or arrivals[0].eta_sec > prev.eta_sec + 60

    def update(self, arrivals: list[Arrival]) -> Arrival | None:
        hit = None
        near = [a for a in arrivals if a.eta_sec <= self.threshold]
        if near:
            first = near[0]
            if not (self.fired and first.vehicle_id == self.fired_vehicle):
                self.fired = True
                self.fired_vehicle = first.vehicle_id
                hit = first
        else:
            if not self.fired and self._passed(arrivals):
                hit = Arrival(0, self.prev.vehicle_id)
            self.fired = False
            self.fired_vehicle = None
        self.prev = arrivals[0] if arrivals else None
        return hit


class Subscribers:
    def __init__(self, path: Path):
        self.path = path
        try:
            self.ids: set[int] = set(json.loads(path.read_text()))
        except (FileNotFoundError, ValueError):
            self.ids = set()

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(sorted(self.ids)))

    def add(self, chat_id: int):
        self.ids.add(chat_id)
        self._save()

    def remove(self, chat_id: int):
        self.ids.discard(chat_id)
        self._save()


bot = Bot(BOT_TOKEN)
dp = Dispatcher()
yandex = YandexTransport()
subs = Subscribers(STATE_FILE)


def allowed(message: Message) -> bool:
    return not ALLOWED_CHAT_IDS or message.chat.id in ALLOWED_CHAT_IDS


def fmt_eta(sec: int) -> str:
    return "меньше минуты" if sec < 60 else f"{round(sec / 60)} мин"


@dp.message(CommandStart())
async def cmd_start(message: Message):
    if not allowed(message):
        await message.answer(f"Нет доступа. Ваш chat id: {message.chat.id}")
        return
    subs.add(message.chat.id)
    await message.answer(
        f"Готово! Пришлю сообщение, когда {ROUTE} будет на остановке «{STOP_NAME}».\n"
        f"Окно: дни {ACTIVE_DAYS}, {ACTIVE_FROM}–{ACTIVE_TO} (МСК).\n\n"
        "/status — что сейчас видно по автобусам\n"
        "/off — выключить уведомления, /on — включить снова\n"
        f"Ваш chat id: {message.chat.id}"
    )


@dp.message(Command("on"))
async def cmd_on(message: Message):
    if allowed(message):
        subs.add(message.chat.id)
        await message.answer("Уведомления включены.")


@dp.message(Command("off"))
async def cmd_off(message: Message):
    subs.remove(message.chat.id)
    await message.answer("Уведомления выключены. /on — включить снова.")


@dp.message(Command("status"))
async def cmd_status(message: Message):
    if not allowed(message):
        return
    try:
        arrivals = await yandex.arrivals(STOP_ID, ROUTE)
    except Exception as e:
        await message.answer(f"Не удалось получить данные: {e}")
        return
    now = datetime.now(MSK)
    lines = [f"Автобус {ROUTE}, остановка «{STOP_NAME}»:"]
    if arrivals:
        lines += [f"• через {fmt_eta(a.eta_sec)}" for a in arrivals[:5]]
    else:
        lines.append("прогнозов нет (автобусы ещё на конечной или не выходят на линию)")
    lines.append("")
    lines.append(f"Уведомляю при прогнозе ≤ {NOTIFY_ETA_MIN:g} мин")
    lines.append("Сейчас окно уведомлений: " + ("да" if in_active_window(now) else "нет"))
    lines.append("Вы подписаны: " + ("да" if message.chat.id in subs.ids else "нет"))
    await message.answer("\n".join(lines))


async def notify(arrival: Arrival):
    if arrival.eta_sec <= 30:
        where = f"на остановке «{STOP_NAME}»"
    else:
        where = f"подъезжает к «{STOP_NAME}» (~{fmt_eta(arrival.eta_sec)})"
    text = f"🚌 {ROUTE} {where} — пора выходить!"
    for chat_id in list(subs.ids):
        try:
            await bot.send_message(chat_id, text)
        except Exception as e:
            log.warning("не отправилось в %s: %s", chat_id, e)


async def poller():
    detector = ArrivalDetector(NOTIFY_ETA_MIN * 60, NOTIFY_ETA_MIN * 60 + 2 * POLL_INTERVAL)
    errors_in_row = 0
    while True:
        now = datetime.now(MSK)
        if not in_active_window(now) or not subs.ids:
            detector.update([])  # вне окна сбрасываем состояние
            await asyncio.sleep(POLL_INTERVAL)
            continue
        try:
            arrivals = await yandex.arrivals(STOP_ID, ROUTE)
            errors_in_row = 0
            log.info("прогнозы %s: %s", ROUTE, [a.eta_sec for a in arrivals])
            hit = detector.update(arrivals)
            if hit:
                log.info("на остановке: eta=%s vehicle=%s", hit.eta_sec, hit.vehicle_id)
                await notify(hit)
        except YandexError as e:
            errors_in_row += 1
            log.warning("Яндекс: %s", e)
        except Exception:
            errors_in_row += 1
            log.exception("ошибка опроса")
        # при серии ошибок притормаживаем, чтобы не словить бан
        await asyncio.sleep(POLL_INTERVAL * min(1 + errors_in_row, 6))


async def main():
    if not STOP_ID:
        raise SystemExit("Задайте STOP_ID в .env (см. README.md)")
    task = asyncio.create_task(poller())
    try:
        await dp.start_polling(bot)
    finally:
        task.cancel()
        await yandex.close()


if __name__ == "__main__":
    asyncio.run(main())
