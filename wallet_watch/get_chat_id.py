"""Узнать свой chat_id: напишите боту /start, затем запустите этот скрипт.

    TELEGRAM_BOT_TOKEN=... python3 get_chat_id.py
"""

import json
import os
import sys
import urllib.request

from dotenv import load_dotenv

load_dotenv()
token = os.getenv("TELEGRAM_BOT_TOKEN")
if not token:
    sys.exit("Нет TELEGRAM_BOT_TOKEN (в .env или в окружении)")

with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getUpdates") as resp:
    updates = json.load(resp).get("result", [])

chats = {}
for u in updates:
    msg = u.get("message") or u.get("edited_message") or {}
    chat = msg.get("chat")
    if chat:
        chats[chat["id"]] = chat.get("username") or chat.get("first_name") or ""

if not chats:
    sys.exit("Сообщений нет — напишите боту /start и запустите ещё раз")
for chat_id, name in chats.items():
    print(f"chat_id = {chat_id}   ({name})")
