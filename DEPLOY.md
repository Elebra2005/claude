# Установка напоминаний в remna-sales-bot

## Что добавлено

Фоновая задача, которая раз в час проверяет истекающие подписки и шлёт
клиенту напоминание за 3 дня и за 1 день до окончания.

## Развёртывание

```bash
# 1. Бэкап текущей версии
docker cp remna-sales-bot:/app/bot.py /root/bot.py.bak.$(date +%F_%H-%M-%S)

# 2. Забрать новую версию
cd /root && git clone https://github.com/elebra2005/claude.git bot-src \
  || (cd /root/bot-src && git pull origin claude/fsdf-570zdo)
cd /root/bot-src && git checkout claude/fsdf-570zdo

# 3. Проверить синтаксис до заливки
python3 -m py_compile /root/bot-src/bot.py && echo "SYNTAX OK"

# 4. Залить и перезапустить
docker cp /root/bot-src/bot.py remna-sales-bot:/app/bot.py
docker restart remna-sales-bot
sleep 10
docker logs remna-sales-bot --since 2m --tail 50
```

## Проверка

Таблица отметок создаётся при старте автоматически:

```bash
docker exec 103c04531ada_remnawave-db psql -U postgres -d postgres \
  -c "\d bot_sent_reminders"
```

Кому уйдут напоминания в ближайшие дни:

```bash
docker exec 103c04531ada_remnawave-db psql -U postgres -d postgres -c "
select telegram_id, expire_at, expire_at - now() as osталось
from users u
where telegram_id is not null and status = 'ACTIVE'
  and expire_at between now() and now() + interval '5 days'
  and not exists (select 1 from users u2
                  where u2.telegram_id = u.telegram_id and u2.expire_at > u.expire_at)
order by expire_at;
"
```

Что уже отправлено:

```bash
docker exec 103c04531ada_remnawave-db psql -U postgres -d postgres \
  -c "select * from bot_sent_reminders order by sent_at desc limit 20;"
```

## Настройки (переменные окружения, необязательные)

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `REMINDER_CHECK_INTERVAL` | `3600` | период проверки, секунды |
| `REMINDER_STARTUP_DELAY` | `60` | пауза после старта до первой проверки |
| `REMINDER_SEND_DELAY` | `0.1` | пауза между отправками, секунды |

## Откат

```bash
docker cp /root/bot.py.bak.ГГГГ-ММ-ДД_ЧЧ-ММ-СС remna-sales-bot:/app/bot.py
docker restart remna-sales-bot
```

Таблицу `bot_sent_reminders` при откате можно оставить — она ничему не мешает.

## Важно

Файл `/app/bot.py` живёт внутри контейнера. При пересборке образа или
`--force-recreate` правки пропадут — заливать заново по инструкции выше.
