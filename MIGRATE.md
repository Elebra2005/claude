# Переезд на новый сервер (старый IP заблокировал РКН)

Переезжает всё: панель Remnawave, база, страница подписок, nginx с
сертификатами, нода и все боты (`remna-sales-bot`,
`remna-telegram-bot-prod`, `rates-bot`, `bus814-bot`, `wallet-watch`).
Домены те же: `panelnikitusik`, `subnikitusik`, `nodenikitusik`
(`.ncknms.com`). Меняется только IP.

Скрипты лежат в каталоге `migrate/`:

- `backup.sh` запускается на старом сервере. Он останавливает ботов и
  панель, снимает дамп базы и делает снимки контейнеров ботов (вместе с
  правками внутри, например `/app/bot.py`). Ещё он сохраняет их тома,
  `/opt`, `/root`, сертификаты и crontab в `/root/migrate`.
- `restore.sh` запускается на новом сервере. Он разворачивает всё обратно:
  сначала базу, потом дамп, потом панель, потом ботов.
- `recreate.py` пересоздаёт контейнеры ботов с теми же параметрами, что
  были на старом сервере (сеть, порты, тома, restart, capabilities).

## 0. Заранее

В DNS снизить TTL записей `panelnikitusik`, `subnikitusik` и
`nodenikitusik` до 60–300 секунд.

На новом сервере:

```bash
curl -fsSL https://get.docker.com | sh
```

## 1. Старый сервер

```bash
cd /root/bot-src && git fetch origin claude/beautiful-curie-v29j9d \
  && git checkout claude/beautiful-curie-v29j9d && git pull
bash /root/bot-src/migrate/backup.sh
```

Скрипт останавливает ботов и панель, чтобы после бэкапа не появились новые
оплаты и чтобы два одинаковых бота не работали одновременно. База остаётся
запущенной.

## 2. Новый сервер

```bash
scp -r root@СТАРЫЙ_IP:/root/migrate /root/
git clone -b claude/beautiful-curie-v29j9d https://github.com/elebra2005/claude.git /root/migrate-src
bash /root/migrate-src/migrate/restore.sh
```

Переменные окружения ботов с секретами скрипт сохраняет в
`/root/migrate/containers/env/` с правами 600.

## 3. DNS

Поменять A-записи на новый IP:

- `panelnikitusik.ncknms.com`
- `subnikitusik.ncknms.com`
- `nodenikitusik.ncknms.com`

Сертификаты скопированы со старого сервера и работают сразу. Для
продления certbot должен видеть домены на новом IP. Проверка после смены
DNS: `certbot renew --dry-run`.

## 4. Панель

- **Nodes**: если адрес ноды был указан IP-адресом, заменить его на новый
  IP. Нода должна стать online.
- **Hosts**: если адрес хоста указан доменом `nodenikitusik`, клиентам
  ничего делать не нужно. Если там старый IP, заменить его, после чего
  клиенты обновляют подписку в приложении.

## 5. AmneziaWG

Старую Amnezia не переносим: на новом сервере уже стоит своя, и её
контейнер тоже называется `amnezia-awg2`. Клиентам старой Amnezia нужно
выдать новые конфиги из приложения Amnezia на новом сервере.

Если `get.docker.com` заменил системный Docker и тот не поднялся сам:

```bash
systemctl enable --now docker.socket docker containerd
docker update --restart always amnezia-awg2
```

## 6. Проверка

```bash
docker ps --format '{{.Names}}\t{{.Status}}'
docker logs remna-sales-bot --tail 30
docker logs remna-telegram-bot-prod --tail 30
curl -sI https://panelnikitusik.ncknms.com | head -1
```

Сделать тестовую покупку в боте: пользователь должен создаться, а ссылка
подписки должна открыться.

Если всё работает, установить crontab: сначала посмотреть
`cat /root/migrate/crontab.txt`, потом выполнить
`crontab /root/migrate/crontab.txt`. Правила файрвола старого сервера
лежат в `/root/migrate/ufw-status.txt`.

## Откат

На старом сервере выполнить `docker start` для остановленных
контейнеров (список есть в начале `backup.sh`), а на новом остановить
ботов. Старый сервер не удалять, пока новый не отработает пару дней.
