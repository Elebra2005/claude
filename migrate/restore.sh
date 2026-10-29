#!/usr/bin/env bash
# Восстановление на НОВОМ сервере из /root/migrate (см. backup.sh).
set -euo pipefail

IN=/root/migrate
HERE=$(cd "$(dirname "$0")" && pwd)
OLD_DB=103c04531ada_remnawave-db

command -v docker >/dev/null || { echo "Нет Docker: curl -fsSL https://get.docker.com | sh"; exit 1; }
[ -f "$IN/remnawave-db.dump" ] || { echo "Нет $IN — сначала scp с старого сервера"; exit 1; }
cd "$IN"

# Уже распакованный архив можно удалить, чтобы освободить место: шаг пропустится
echo "== 1. Файлы"
if [ -f files.tar.gz ]; then tar xzf files.tar.gz -C /; else echo "(пропущено)"; fi

echo "== 2. Образы ботов"
if [ -f images.tar.gz ]; then gunzip -c images.tar.gz | docker load; else echo "(пропущено)"; fi

if [ -f panel-images.tar.gz ]; then
  echo "== 2b. Образы панели"
  gunzip -c panel-images.tar.gz | docker load
fi

echo "== 3. Тома ботов"
if [ -s volumes.txt ] && [ -f volumes.tar.gz ]; then
  for v in $(cat volumes.txt); do docker volume create "$v" >/dev/null; done
  tar xzf volumes.tar.gz -C /var/lib/docker/volumes
fi

echo "== 4. База Remnawave"
cd /opt/remnawave
DB_SERVICE=$(docker compose config --format json | python3 -c '
import json, sys
for name, s in json.load(sys.stdin)["services"].items():
    if s.get("container_name") == "remnawave-db":
        print(name)')
docker compose up -d "$DB_SERVICE"
until docker exec remnawave-db pg_isready -U postgres >/dev/null 2>&1; do sleep 2; done
docker exec -i remnawave-db pg_restore -U postgres -d postgres --clean --if-exists \
  < "$IN/remnawave-db.dump" || echo "(предупреждения pg_restore выше обычно не страшны)"

# Старое имя базы, на случай если оно зашито в коде ботов
docker network disconnect remnawave-network remnawave-db
docker network connect --alias "$DB_SERVICE" --alias "$OLD_DB" remnawave-network remnawave-db

echo "== 5. Панель, страница подписок, nginx, нода"
docker compose up -d

echo "== 6. Боты и AmneziaWG"
python3 "$HERE/recreate.py" "$IN"/containers/*.json

echo "== 7. certbot для продления сертификатов"
command -v certbot >/dev/null || apt-get install -y certbot >/dev/null || true

sleep 15
docker ps --format '{{.Names}}\t{{.Status}}'
cat <<MSG

Готово. Дальше вручную:
  1. DNS: A-записи panelnikitusik, subnikitusik, nodenikitusik → $(hostname -I | awk '{print $1}')
  2. Панель → Nodes: адрес ноды поменять на новый IP (если там был IP)
  3. crontab со старого сервера: cat $IN/crontab.txt ; установить: crontab $IN/crontab.txt
  4. Правила файрвола со старого сервера: $IN/ufw-status.txt
MSG
