# Переезд панели Remnawave на новый сервер

Домены не меняются: `panelnikitusik.ncknms.com` (панель) и
`subnikitusik.ncknms.com` (подписки). Меняется только IP. Ссылки подписок у
клиентов остаются прежними.

Общая схема: бэкап на старом сервере → восстановление на новом → перенос
бота → смена A-записей → проверка → выключение старого сервера.

## 0. Заранее (за сутки)

- В DNS снизить TTL A-записей `panelnikitusik` и `subnikitusik` до 60–300 с,
  чтобы переключение разошлось быстро.
- Выяснить, работает ли на старом сервере ещё и нода (`docker ps | grep
  remnanode`). Если да, клиенты подключаются к VPN по его IP/домену, и ноду
  тоже нужно переносить или оставить старый сервер включённым как ноду.
- Записать, что запущено и где лежат файлы:

```bash
docker ps --format '{{.Names}}\t{{.Image}}'
ls -la /opt/remnawave
docker inspect remna-sales-bot --format '{{json .Config.Env}}' > /root/bot-env.json
docker inspect remna-sales-bot --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}'
```

## 1. Бэкап на старом сервере

Вариант А, скрипт `remnawave-backup` (как советовали): сделать бэкап и
убедиться, что в архив попали дамп БД **и** каталог `/opt/remnawave` с `.env`.

Вариант Б, вручную. Панель на время дампа остановить, чтобы после бэкапа
не появились новые оплаты или пользователи:

```bash
cd /opt/remnawave
docker stop remnawave remna-sales-bot
docker exec 103c04531ada_remnawave-db pg_dump -U postgres -d postgres -Fc \
  > /root/remnawave-db.dump
docker cp remna-sales-bot:/app/bot.py /root/bot.py
tar czf /root/remnawave-migrate.tgz -C / opt/remnawave root/remnawave-db.dump \
  root/bot.py root/bot-env.json
```

Бот хранит свои таблицы (`bot_sent_reminders` и др.) в той же базе
`postgres`, поэтому они попадут в дамп. А сам `bot.py` живёт только внутри
контейнера, и скрипт бэкапа панели его **не** сохранит.

Если правки бота уже есть в этом репозитории, `bot.py` можно взять отсюда.

## 2. Важно в `.env`

`.env` переносить **целиком, без перегенерации**. Особенно:

- `JWT_AUTH_SECRET`, `JWT_API_TOKENS_SECRET`: если они другие, перестанет
  работать `REMNAWAVE_API_TOKEN` бота и разлогинятся админы.
- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `DATABASE_URL`.
- `PANEL_DOMAIN`, `SUB_PUBLIC_DOMAIN` остаются прежними.

Ключи нод хранятся в БД, так что после восстановления ноды переподключатся
сами, перевыпускать `SECRET_KEY` на нодах не нужно.

## 3. Восстановление на новом сервере

```bash
# Docker
curl -fsSL https://get.docker.com | sh

scp root@СТАРЫЙ_IP:/root/remnawave-migrate.tgz /root/
tar xzf /root/remnawave-migrate.tgz -C /
cd /opt/remnawave

# Сначала ТОЛЬКО база: панель при старте накатывает миграции на пустую БД,
# и потом дамп ляжет с конфликтами.
docker compose up -d remnawave-db
sleep 10
docker exec -i remnawave-db pg_restore -U postgres -d postgres --clean --if-exists \
  < /root/remnawave-db.dump

# Теперь всё остальное
docker compose up -d
docker compose logs -f --tail 100 remnawave
```

Версия образа PostgreSQL на новом сервере должна быть **не ниже** старой.
Возьми тот же `docker-compose.yml`, тогда версия совпадёт.

Если используешь скрипт `remnawave-backup`, шаг 3 за тебя сделает его режим
восстановления. Дальше переходи к шагу 4.

Имя контейнера БД на новом сервере, скорее всего, будет `remnawave-db`, без
префикса `103c04531ada_`. Проверь через `docker ps`.

## 4. Бот remna-sales-bot

Запустить с теми же переменными, что в `/root/bot-env.json`, в сети панели
(обычно `remnawave-network`) и **явно** указать хост БД:

```bash
docker run -d --name remna-sales-bot --restart unless-stopped \
  --network remnawave-network \
  --env-file /root/bot.env \
  -e POSTGRES_HOST=remnawave-db \
  ОБРАЗ_БОТА
docker cp /root/bot.py remna-sales-bot:/app/bot.py
docker restart remna-sales-bot
docker logs remna-sales-bot --tail 50
```

`/root/bot.env` собрать из `bot-env.json`, по одной строке `КЛЮЧ=значение`.
Образ бота: либо `docker save`/`docker load` со старого сервера, либо
пересобрать. Бот работает через polling, поэтому от IP он не зависит.

**Старый бот должен быть остановлен**: два бота с одним токеном конфликтуют
(`TelegramConflictError`).

## 5. Файрвол

- На новом сервере открыть 80/443 (и SSH).
- **На каждой ноде** разрешить подключение к порту ноды (обычно 2222) с
  нового IP панели. Часто там стоит `ufw allow from СТАРЫЙ_IP to any port 2222`.

```bash
ufw allow from НОВЫЙ_IP to any port 2222 proto tcp
```

## 6. DNS

A-записи на IP нового сервера:

- `panelnikitusik.ncknms.com → НОВЫЙ_IP`
- `subnikitusik.ncknms.com → НОВЫЙ_IP`, если страница подписок жила на том
  же сервере. Без этого у клиентов перестанут обновляться подписки.

Сертификаты: Caddy выпустит их сам, как только DNS укажет на новый сервер.
Если используются nginx и certbot/acme.sh, скопировать каталог сертификатов
или перевыпустить их после смены DNS.

## 7. Проверка

```bash
dig +short panelnikitusik.ncknms.com
dig +short subnikitusik.ncknms.com
curl -sI https://panelnikitusik.ncknms.com | head -1
curl -s https://subnikitusik.ncknms.com/КОРОТКИЙ_UUID_ЛЮБОГО_КЛИЕНТА | head -c 200
```

- В панели все ноды в статусе online, пользователи и трафик на месте.
- Тестовая покупка в боте: пользователь создаётся, ссылка открывается.

## 8. Старый сервер

1–2 дня держать выключенными панель и бота, но не удалять (это откат). Потом
вернуть TTL в DNS и отключить сервер у хостера.

## Откат

Вернуть A-записи на старый IP, на старом сервере выполнить
`docker start remnawave remna-sales-bot`, а на новом остановить бота.
