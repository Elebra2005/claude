#!/usr/bin/env python3
"""Бот MareevVPN_Report.

Кнопки:
  📊 Проверить статус — запускает `vpn-monitor.sh --report` (проверка всех узлов);
  🗓 Сроки оплаты    — таблица серверов и сколько дней осталось до оплаты.
Команды после продления:
  /paid NL 15.12.2026 — записать новую дату оплаты;
  /plus NL 30         — продлить на 30 дней от текущей даты.
Напоминания об оплате — сами, раз в день: за 7, 3, 1 день и в день окончания,
после окончания — каждый день.

Отвечает только владельцу (CHAT_ID из /etc/vpn-monitor.conf).
Тревоги о сбоях шлёт сам vpn-monitor.sh из cron — этот процесс для них не нужен.
"""
import datetime as dt
import json
import os
import re
import subprocess
import threading
import time
import urllib.parse
import urllib.request

CONF = os.environ.get("CONF", "/etc/vpn-monitor.conf")
MONITOR = os.environ.get("MONITOR", "/usr/local/bin/vpn-monitor.sh")
SERVERS = os.environ.get("SERVERS", "/etc/vpn-servers.txt")
STATE = os.environ.get("STATE", "/var/lib/vpn-monitor/remind-date")
BTN_STATUS = "📊 Проверить статус"
BTN_PAY = "🗓 Сроки оплаты"
KEYBOARD = {"keyboard": [[{"text": BTN_STATUS}, {"text": BTN_PAY}]],
            "resize_keyboard": True, "is_persistent": True}
MSK = dt.timezone(dt.timedelta(hours=3))
REMIND_HOUR = 10          # во сколько по Москве присылать напоминания
REMIND_DAYS = (7, 3, 1, 0)


def read_conf(path):
    conf = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            conf[key.strip()] = value.split("#", 1)[0].strip().strip('"').strip("'")
    return conf


conf = read_conf(CONF)
TOKEN, CHAT_ID = conf["BOT_TOKEN"], str(conf["CHAT_ID"])
API = f"https://api.telegram.org/bot{TOKEN}/"
busy = threading.Lock()
servers_lock = threading.Lock()


def call(method, **params):
    data = urllib.parse.urlencode(
        {k: json.dumps(v) if isinstance(v, dict) else v for k, v in params.items()}
    ).encode()
    with urllib.request.urlopen(API + method, data=data, timeout=70) as r:
        return json.loads(r.read())


def send(text, silent=False):
    call("sendMessage", chat_id=CHAT_ID, text=text, parse_mode="HTML",
         reply_markup=KEYBOARD, disable_notification="true" if silent else "false")


def today():
    return dt.datetime.now(MSK).date()


# ---------- Список серверов ----------
# Формат /etc/vpn-servers.txt (по строке на сервер, # — комментарий):
#   КОД | Название | IP | Хостер | ДД.ММ.ГГГГ | Цена в месяц (например 2.86 $)
def load_servers():
    items = []
    try:
        with open(SERVERS) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = [p.strip() for p in line.split("|")]
                parts += [""] * (6 - len(parts))
                code, name, ip, host, date, price = parts[:6]
                try:
                    due = dt.datetime.strptime(date, "%d.%m.%Y").date()
                except ValueError:
                    due = None
                items.append({"code": code, "name": name, "ip": ip, "host": host, "due": due,
                              "price": price})
    except FileNotFoundError:
        pass
    return items


def save_servers(items):
    lines = ["# КОД | Название | IP | Хостер | Оплачен до (ДД.ММ.ГГГГ) | Цена в месяц"]
    for s in items:
        date = s["due"].strftime("%d.%m.%Y") if s["due"] else ""
        lines.append(" | ".join([s["code"], s["name"], s["ip"], s["host"], date, s["price"]]))
    tmp = SERVERS + ".tmp"
    with open(tmp, "w") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(tmp, SERVERS)


def days_word(n):
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        return "день"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "дня"
    return "дней"


def parse_price(text):
    """'2.86 $' -> (2.86, '$'); без цены -> None."""
    m = re.match(r"\s*([\d.,]+)\s*(.*)", text or "")
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ".")), m.group(2).strip() or "?"
    except ValueError:
        return None


def fmt_money(amount, cur):
    num = f"{amount:.2f}".rstrip("0").rstrip(".")
    return f"{num} {cur}"


def totals(items):
    sums = {}
    for s in items:
        p = parse_price(s["price"])
        if p:
            sums[p[1]] = sums.get(p[1], 0) + p[0]
    return " + ".join(fmt_money(v, k) for k, v in sums.items())


def price_part(s):
    return f" · 💰 {s['price']}/мес" if s["price"] else ""


def line_for(s):
    if not s["due"]:
        return (f"⚪️ <b>{s['name']}</b> — дата не указана\n"
                f"      <code>{s['ip']}</code> · {s['host']}{price_part(s)}")
    left = (s["due"] - today()).days
    if left < 0:
        icon, when = "🔴", f"просрочен на {-left} {days_word(left)}"
    elif left == 0:
        icon, when = "🔴", "истекает сегодня"
    elif left <= 3:
        icon, when = "🟠", f"через {left} {days_word(left)}"
    elif left <= 7:
        icon, when = "🟡", f"через {left} {days_word(left)}"
    else:
        icon, when = "🟢", f"через {left} {days_word(left)}"
    return (f"{icon} <b>{s['name']}</b> — до {s['due'].strftime('%d.%m.%Y')} ({when})\n"
            f"      <code>{s['ip']}</code> · {s['host']}{price_part(s)} · код <code>{s['code']}</code>")


def payments_table():
    items = load_servers()
    if not items:
        return f"Список серверов пуст. Заполни {SERVERS}."
    far = dt.date(9999, 1, 1)
    items.sort(key=lambda s: s["due"] or far)
    soon = sum(1 for s in items if s["due"] and (s["due"] - today()).days <= 7)
    head = "🗓 <b>Сроки оплаты серверов</b>"
    head += f"\n⚠️ Скоро оплатить: {soon}" if soon else "\n✅ В ближайшую неделю платить не нужно"
    body = "\n\n".join(line_for(s) for s in items)
    total = totals(items)
    if total:
        body += f"\n\n💰 <b>Итого в месяц:</b> {total}"
    tip = ("\n\nПосле продления:\n<code>/paid КОД ДД.ММ.ГГГГ</code> — новая дата\n"
           "<code>/plus КОД 30</code> — плюс 30 дней")
    return f"{head}\n\n{body}{tip}"


def update_due(args, add_days):
    if len(args) != 2:
        return "Формат: <code>/paid КОД ДД.ММ.ГГГГ</code> или <code>/plus КОД 30</code>"
    code, value = args[0].upper(), args[1]
    with servers_lock:
        items = load_servers()
        found = next((s for s in items if s["code"].upper() == code), None)
        if not found:
            codes = ", ".join(s["code"] for s in items) or "—"
            return f"Нет сервера с кодом {code}. Есть: {codes}"
        try:
            if add_days:
                base = max(found["due"] or today(), today())
                found["due"] = base + dt.timedelta(days=int(value))
            else:
                found["due"] = dt.datetime.strptime(value, "%d.%m.%Y").date()
        except ValueError:
            return "Не понял дату или число дней. Пример: <code>/paid NL 15.12.2026</code>"
        save_servers(items)
    return f"✅ {found['name']}: оплачен до {found['due'].strftime('%d.%m.%Y')}"


# ---------- Напоминания ----------
def reminders_loop():
    while True:
        try:
            now = dt.datetime.now(MSK)
            last = open(STATE).read().strip() if os.path.exists(STATE) else ""
            if now.hour >= REMIND_HOUR and last != now.date().isoformat():
                due = []
                for s in load_servers():
                    if not s["due"]:
                        continue
                    left = (s["due"] - now.date()).days
                    if left in REMIND_DAYS or left < 0:
                        due.append(s)
                if due:
                    due.sort(key=lambda s: s["due"])
                    total = totals(due)
                    send("💳 <b>Пора оплатить серверы</b>\n\n"
                         + "\n\n".join(line_for(s) for s in due)
                         + (f"\n\n💰 <b>К оплате:</b> {total}" if total else "")
                         + "\n\nПосле оплаты: <code>/paid КОД ДД.ММ.ГГГГ</code>")
                os.makedirs(os.path.dirname(STATE), exist_ok=True)
                with open(STATE, "w") as f:
                    f.write(now.date().isoformat())
        except Exception:
            pass
        time.sleep(600)


# ---------- Проверка статуса ----------
def run_report():
    if not busy.acquire(blocking=False):
        send("⏳ Проверка уже идёт, отчёт скоро придёт.")
        return
    try:
        send("⏳ Проверяю вход, ноды, подписки и панель…")
        r = subprocess.run([MONITOR, "--report"], capture_output=True, text=True, timeout=240)
        if r.returncode != 0 and r.stderr.strip():
            send("⚠️ Проверка завершилась с ошибкой:\n" + r.stderr.strip()[-500:])
    except subprocess.TimeoutExpired:
        send("⚠️ Проверка не уложилась в 4 минуты — часть узлов не отвечает.")
    finally:
        busy.release()


def main():
    threading.Thread(target=reminders_loop, daemon=True).start()
    offset = None
    while True:
        try:
            params = {"timeout": 50, "allowed_updates": '["message"]'}
            if offset is not None:
                params["offset"] = offset
            updates = call("getUpdates", **params).get("result", [])
        except Exception:
            time.sleep(5)
            continue
        for u in updates:
            offset = u["update_id"] + 1
            msg = u.get("message") or {}
            if str(msg.get("chat", {}).get("id")) != CHAT_ID:
                continue  # чужим не отвечаем
            text = (msg.get("text") or "").strip()
            cmd, *args = text.split() or [""]
            try:
                if text in (BTN_STATUS, "/status"):
                    threading.Thread(target=run_report, daemon=True).start()
                elif text in (BTN_PAY, "/servers"):
                    send(payments_table())
                elif cmd == "/paid":
                    send(update_due(args, add_days=False))
                elif cmd == "/plus":
                    send(update_due(args, add_days=True))
                elif text == "/start":
                    send("👋 Я слежу за MareevVPN.\n\n"
                         "🔴 О любом сбое напишу сам — с причиной и тем, что делать.\n"
                         "💳 Напомню об оплате серверов за 7, 3 и 1 день.\n\n"
                         f"📊 «{BTN_STATUS}» — проверить всё прямо сейчас.\n"
                         f"🗓 «{BTN_PAY}» — когда платить за серверы.")
                else:
                    send(f"Нажми кнопку внизу: «{BTN_STATUS}» или «{BTN_PAY}».")
            except Exception as e:
                send(f"⚠️ Ошибка: {e}")


if __name__ == "__main__":
    main()
