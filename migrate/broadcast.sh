#!/usr/bin/env bash
# Рассылка клиентам с активной подпиской через продающего бота.
# Без аргументов только показывает число получателей и текст.
# Отправка: bash broadcast.sh --send
# Свой текст: MSG_FILE=/root/msg.txt bash broadcast.sh [--send]
set -euo pipefail

ENV_FILE=/root/migrate/containers/env/remna-sales-bot.env
DB=remnawave-db
MSG='Мы переехали на новый сервер 🚀

Чтобы VPN работал, обновите подписку в приложении (кнопка обновления рядом с подпиской) и переподключитесь.

Ссылка подписки прежняя, ничего менять не нужно.'

# Свой текст: положить в файл и передать его вторым аргументом или через MSG_FILE
MSG_FILE=${MSG_FILE:-${2:-}}
if [ -n "$MSG_FILE" ]; then
  [ -f "$MSG_FILE" ] || { echo "Нет файла $MSG_FILE"; exit 1; }
  MSG=$(cat "$MSG_FILE")
fi

TOKEN=$(grep '^TELEGRAM_BOT_TOKEN=' "$ENV_FILE" | cut -d= -f2-)
[ -n "$TOKEN" ] || { echo "Нет TELEGRAM_BOT_TOKEN в $ENV_FILE"; exit 1; }

IDS=$(docker exec "$DB" psql -U postgres -d postgres -At -c \
  "select distinct telegram_id from users where telegram_id is not null and status = 'ACTIVE'")
COUNT=$(echo "$IDS" | grep -c . || true)

echo "Получателей: $COUNT"
echo "----- текст -----"
echo "$MSG"
echo "-----------------"

if [ "${1:-}" != "--send" ]; then
  echo "Это пробный запуск. Для отправки: bash $0 --send ${MSG_FILE}"
  exit 0
fi

ok=0; fail=0
for id in $IDS; do
  code=$(curl -s -o /dev/null -w '%{http_code}' -m 15 \
    "https://api.telegram.org/bot$TOKEN/sendMessage" \
    --data-urlencode "chat_id=$id" --data-urlencode "text=$MSG")
  if [ "$code" = 200 ]; then ok=$((ok+1)); else fail=$((fail+1)); echo "$id: $code"; fi
  sleep 0.1
done
echo "Отправлено: $ok, ошибок: $fail (403 — клиент заблокировал бота)"
