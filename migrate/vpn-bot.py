#!/usr/bin/env python3
"""Бот MareevVPN_Report: кнопка «📊 Проверить статус».

Слушает Telegram (long polling) и по нажатию кнопки запускает
`vpn-monitor.sh --report`, который проверяет все узлы и присылает отчёт.
Отвечает только владельцу (CHAT_ID из /etc/vpn-monitor.conf).
Тревоги о сбоях шлёт сам vpn-monitor.sh из cron — этот процесс для них не нужен.
"""
import json
import os
import subprocess
import threading
import time
import urllib.parse
import urllib.request

CONF = os.environ.get("CONF", "/etc/vpn-monitor.conf")
MONITOR = os.environ.get("MONITOR", "/usr/local/bin/vpn-monitor.sh")
BUTTON = "📊 Проверить статус"
KEYBOARD = {"keyboard": [[{"text": BUTTON}]], "resize_keyboard": True, "is_persistent": True}


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


def call(method, **params):
    data = urllib.parse.urlencode(
        {k: json.dumps(v) if isinstance(v, dict) else v for k, v in params.items()}
    ).encode()
    with urllib.request.urlopen(API + method, data=data, timeout=70) as r:
        return json.loads(r.read())


def send(text):
    call("sendMessage", chat_id=CHAT_ID, text=text, reply_markup=KEYBOARD)


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
            if text in (BUTTON, "/status"):
                threading.Thread(target=run_report, daemon=True).start()
            elif text == "/start":
                send("👋 Я слежу за MareevVPN.\n\n"
                     "🔴 О любом сбое напишу сам — с причиной и тем, что делать.\n"
                     f"📊 Нажми «{BUTTON}», чтобы проверить всё прямо сейчас.")
            else:
                send(f"Нажми «{BUTTON}» внизу.")


if __name__ == "__main__":
    main()
