#!/usr/bin/env bash
# Автопродление сертификатов selfsteal на нодах.
# Caddy на входе (Selectel) сам продлевает сертификаты docs/notes. Этот скрипт
# забирает их с входа и раскладывает по нодам в /opt/selfsteal/certs, если они
# изменились, и перезапускает selfsteal. Запускать на сервере панели раз в день (cron).
# Берёт ENTRY, NODES, BOT_TOKEN, CHAT_ID из /etc/vpn-monitor.conf.
set -u
CONF=${CONF:-/etc/vpn-monitor.conf}
# shellcheck disable=SC1090
. "$CONF"
DOMAINS=${CERT_DOMAINS:-"docs notes"}
ZONE=${CERT_ZONE:-ncknms.com}
SSH="ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT

tg() {
  [ -n "${BOT_TOKEN:-}" ] || return 0
  curl -s -m 15 -o /dev/null "https://api.telegram.org/bot$BOT_TOKEN/sendMessage" \
    --data-urlencode "chat_id=$CHAT_ID" --data-urlencode "parse_mode=HTML" --data-urlencode "text=$1"
}

# 1. Забрать актуальные сертификаты с входа (ищем в хранилище Caddy, самый свежий)
for d in $DOMAINS; do
  host="$d.$ZONE"
  for ext in crt key; do
    $SSH "root@$ENTRY" "f=\$(find / -path /proc -prune -o -type f -name '$host.$ext' -path '*caddy*certificates*' -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-); [ -n \"\$f\" ] && cat \"\$f\"" > "$TMP/$d.$ext"
    if [ ! -s "$TMP/$d.$ext" ]; then
      tg "🔴 <b>Сертификаты:</b> не удалось забрать $host.$ext с входа $ENTRY — проверь Caddy на входе."
      exit 1
    fi
  done
  end=$(openssl x509 -enddate -noout -in "$TMP/$d.crt" | cut -d= -f2)
  echo "$host: на входе действует до $end"
done

# 2. Разложить по нодам, где отличаются
updated=""
for n in $NODES; do              # Код=IP=SNI
  name=${n%%=*}; rest=${n#*=}; ip=${rest%%=*}
  changed=0
  for d in $DOMAINS; do
    want=$(sha256sum "$TMP/$d.crt" | cut -d' ' -f1)
    have=$($SSH "root@$ip" "sha256sum /opt/selfsteal/certs/$d.crt 2>/dev/null | cut -d' ' -f1")
    [ "$want" = "$have" ] && continue
    for ext in crt key; do
      $SSH "root@$ip" "umask 077; cat > /opt/selfsteal/certs/$d.$ext.new && mv /opt/selfsteal/certs/$d.$ext.new /opt/selfsteal/certs/$d.$ext" < "$TMP/$d.$ext" || {
        tg "🔴 <b>Сертификаты:</b> не удалось записать $d.$ext на ноду $name ($ip)."; continue 3; }
    done
    changed=1
  done
  if [ "$changed" = 1 ]; then
    $SSH "root@$ip" "docker restart selfsteal >/dev/null" && updated+="$name "
  fi
done

if [ -n "$updated" ]; then
  tg "🔄 <b>Сертификаты обновлены</b> на нодах: $updated"
  echo "Обновлены: $updated"
else
  echo "На всех нодах сертификаты актуальны"
fi
