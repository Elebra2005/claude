#!/usr/bin/env bash
# Бэкап всего, что переезжает со старого сервера. Запускать на СТАРОМ сервере.
# Результат: /root/migrate (дамп БД, образы контейнеров, тома, файлы).
set -euo pipefail

OUT=/root/migrate
# Контейнер базы: remnawave-db или с префиксом вида 103c04531ada_remnawave-db
DB=$(docker ps -a --format '{{.Names}}' | grep -E '(^|_)remnawave-db$' | head -1)
[ -n "$DB" ] || { echo "Не найден контейнер базы remnawave-db"; exit 1; }
# amnezia-awg2 не переносим: на новом сервере своя Amnezia с тем же именем контейнера.
# Берём только тех ботов, что реально есть на сервере.
BOTS=""
for b in remna-sales-bot remna-telegram-bot-prod rates-bot bus814-bot wallet-watch; do
  docker inspect "$b" >/dev/null 2>&1 && BOTS="$BOTS $b"
done
PANEL=""
for c in remnawave remnawave-subscription-page remnawave-nginx remnanode; do
  docker inspect "$c" >/dev/null 2>&1 && PANEL="$PANEL $c"
done
echo "База: $DB; боты:$BOTS"

mkdir -p "$OUT/containers"
cd "$OUT"

echo "== 1. Параметры контейнеров"
for c in $BOTS; do
  docker inspect "$c" > "containers/$c.json"
done

echo "== 2. Остановка ботов и панели (база остаётся работать для дампа)"
docker stop $BOTS $PANEL

echo "== 3. Дамп базы Remnawave (вместе с таблицами ботов)"
docker exec "$DB" pg_dump -U postgres -d postgres -Fc > remnawave-db.dump
ls -lh remnawave-db.dump

echo "== 4. Снимки контейнеров ботов (с правками внутри, например /app/bot.py)"
IMAGES=""
for c in $BOTS; do
  docker commit "$c" "migrate/$c:latest" >/dev/null
  IMAGES="$IMAGES migrate/$c:latest"
done
docker save $IMAGES | gzip > images.tar.gz
ls -lh images.tar.gz

echo "== 4b. Образы панели (чтобы не качать с Docker Hub на новом сервере)"
PIMAGES=$(for c in $DB $PANEL; do docker inspect "$c" --format '{{.Config.Image}}'; done | sort -u)
REDIS=$(docker ps -a --format '{{.Names}}' | grep -E '(^|_)remnawave-redis$' | head -1)
[ -n "$REDIS" ] && PIMAGES="$PIMAGES $(docker inspect "$REDIS" --format '{{.Config.Image}}')"
docker save $PIMAGES | gzip > panel-images.tar.gz
ls -lh panel-images.tar.gz

echo "== 5. Тома ботов"
VOLS=$(for c in $BOTS; do
  docker inspect "$c" --format '{{range .Mounts}}{{if eq .Type "volume"}}{{.Name}} {{end}}{{end}}'
done | tr ' ' '\n' | sort -u | grep -v '^$' || true)
echo "$VOLS" > volumes.txt
if [ -n "$VOLS" ]; then
  tar czf volumes.tar.gz -C /var/lib/docker/volumes $VOLS
fi

echo "== 6. Файлы: конфиги, исходники ботов, сертификаты, crontab"
crontab -l > crontab.txt 2>/dev/null || true
(ufw status numbered 2>/dev/null || true) > ufw-status.txt
BINDS=$(for c in $BOTS; do
  docker inspect "$c" --format '{{range .Mounts}}{{if eq .Type "bind"}}{{.Source}} {{end}}{{end}}'
done | tr ' ' '\n' | grep -vE '^$|^/(dev|proc|sys|lib/modules)' | sort -u || true)
PATHS=""
for p in /opt /root /etc/letsencrypt /var/www/html $BINDS; do
  [ -e "$p" ] && PATHS="$PATHS ${p#/}"
done
tar czf files.tar.gz -C / \
  --exclude=opt/containerd --exclude=opt/amnezia --exclude=root/migrate --exclude=root/snap --exclude=root/.ssh $PATHS

du -sh "$OUT"
echo
echo "Готово. Старые боты и панель ОСТАНОВЛЕНЫ, база работает."
echo "Дальше на НОВОМ сервере: scp -r root@$(hostname -I | awk '{print $1}'):/root/migrate /root/"
