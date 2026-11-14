#!/usr/bin/env bash
# Мониторинг VPN-схемы с уведомлениями в Telegram. Запускать на сервере панели
# (с него доступен Telegram) раз в минуту через cron.
#
# Что проверяет:
#   1. вход (Selectel) доступен по SSH;
#   2. с входа каждая нода отвечает как Reality+selfsteal (curl по SNI на :8445) —
#      так видно и падение ноды, и блокировку её адреса со стороны российского хостера;
#   3. через вход открываются подписки (Caddy -> панель).
#
# Сообщение уходит только при смене состояния: «упало» после FAILS_TO_ALERT
# неудачных проверок подряд и «восстановилось» после первой удачной.
#
# Настройки — в /etc/vpn-monitor.conf (см. образец в конце файла).
set -u
export LC_ALL=C.UTF-8   # чтобы длина строк считалась в символах, а не байтах

CONF=${CONF:-/etc/vpn-monitor.conf}
[ -f "$CONF" ] || { echo "Нет $CONF"; exit 1; }
# shellcheck disable=SC1090
. "$CONF"

: "${BOT_TOKEN:?}" "${CHAT_ID:?}" "${ENTRY:?}" "${NODES:?}" "${SUB_URL:?}"
FAILS_TO_ALERT=${FAILS_TO_ALERT:-2}
REPORT_EVERY=${REPORT_EVERY:-0}      # отчёт каждые N минут (0 — не слать)
REPORT_TZ=${REPORT_TZ:-Europe/Moscow}
STATE_DIR=${STATE_DIR:-/var/lib/vpn-monitor}
mkdir -p "$STATE_DIR"

send() {
  curl -s -m 15 -o /dev/null "https://api.telegram.org/bot$BOT_TOKEN/sendMessage" \
    --data-urlencode "chat_id=$CHAT_ID" --data-urlencode "text=$1"
}

# Тихий отчёт моноширинной таблицей (без звука уведомления)
send_report() {
  curl -s -m 15 -o /dev/null "https://api.telegram.org/bot$BOT_TOKEN/sendMessage" \
    --data-urlencode "chat_id=$CHAT_ID" --data-urlencode "parse_mode=HTML" \
    --data-urlencode "disable_notification=true" --data-urlencode "text=$1"
}

# Дополнить строку пробелами до ширины $2 (в символах, кириллица тоже)
pad() { local t=$1; while [ ${#t} -lt "$2" ]; do t+=" "; done; printf '%s' "$t"; }

ROWS=""; ALL_OK=1
row() {  # $1 — название, $2 — ok/fail, $3 — код, $4 — время ответа
  local mark="OK  "; [ "$2" = ok ] || { mark="FAIL"; ALL_OK=0; }
  ROWS+="$(pad "$1" 9) $(pad "$mark" 4) $(pad "${3:--}" 4) ${4:--}"$'\n'
}

# Учёт состояния одной проверки: $1 — ключ, $2 — ok/fail, $3 — подпись
track() {
  local key=$1 res=$2 label=$3 f="$STATE_DIR/$1" fails=0 alerted=0
  [ -f "$f" ] && read -r fails alerted < "$f"
  if [ "$res" = ok ]; then
    [ "$alerted" = 1 ] && send "✅ Восстановилось: $label"
    echo "0 0" > "$f"
  else
    fails=$((fails + 1))
    if [ "$fails" -ge "$FAILS_TO_ALERT" ] && [ "$alerted" != 1 ]; then
      send "🔴 Не работает: $label (проверок подряд: $fails)"
      alerted=1
    fi
    echo "$fails $alerted" > "$f"
  fi
}

# 1–2. Вход и ноды: одна SSH-сессия на вход, внутри — проверки нод
remote_checks=""
for n in $NODES; do            # формат: Имя=IP=SNI
  name=${n%%=*}; rest=${n#*=}; ip=${rest%%=*}; sni=${rest#*=}
  remote_checks+="c=\$(curl -sk -o /dev/null -m 8 -w '%{http_code} %{time_total}' --resolve $sni:8445:$ip https://$sni:8445/); echo \"$name \$c\"; "
done

out=$(ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new \
      "root@$ENTRY" "$remote_checks" 2>/dev/null)
if [ $? -eq 0 ] && [ -n "$out" ]; then
  track entry ok "вход $ENTRY (SSH)"; row "Вход" ok
  for n in $NODES; do
    name=${n%%=*}
    code=$(echo "$out" | awk -v n="$name" '$1==n{print $2}')
    t=$(echo "$out" | awk -v n="$name" '$1==n{printf "%.2fs", $3}')
    if [ "$code" = 200 ]; then r=ok; else r=fail; fi
    track "node-$name" "$r" "нода $name (с входа код ${code:-нет ответа})"
    row "Нода $name" "$r" "$code" "$t"
  done
else
  track entry fail "вход $ENTRY недоступен по SSH (ноды не проверены)"
  row "Вход" fail
  for n in $NODES; do row "Нода ${n%%=*}" fail "?" ; done
fi

# 3. Подписки через вход
host=$(echo "$SUB_URL" | sed -E 's#https?://([^/]+)/.*#\1#')
res=$(curl -sk -o /dev/null -m 15 -A 'Happ/1.0' -w '%{http_code} %{time_total}' \
       --resolve "$host:443:$ENTRY" "$SUB_URL")
code=${res%% *}; t=$(printf '%.2fs' "${res#* }" 2>/dev/null)
if [ "$code" = 200 ]; then r=ok; else r=fail; fi
track sub "$r" "подписки через вход (код $code)"
row "Подписки" "$r" "$code" "$t"

# 4. Плановый отчёт
if [ "$REPORT_EVERY" -gt 0 ] && [ $(( 10#$(date +%M) % REPORT_EVERY )) -eq 0 ]; then
  if [ "$ALL_OK" = 1 ]; then head="🟢 MareevVPN: всё работает"; else head="🔴 MareevVPN: есть сбои"; fi
  now=$(TZ=$REPORT_TZ date '+%d.%m %H:%M')
  table="$(pad "Узел" 9) $(pad "Ст." 4) $(pad "Код" 4) Ответ"$'\n'"$ROWS"
  send_report "<b>$head</b>
$now (МСК), вход $ENTRY
<pre>$table</pre>"
fi

# --- Образец /etc/vpn-monitor.conf ---
# BOT_TOKEN=123456:ABC...              # токен бота от @BotFather
# CHAT_ID=123456789                    # твой chat_id
# ENTRY=139.100.219.235                # российский вход
# NODES="FI=2.27.13.73=docs.ncknms.com NL=78.17.68.185=notes.ncknms.com DE=2.27.60.173=docs.ncknms.com PL=191.44.113.142=notes.ncknms.com"
# SUB_URL=https://subnikitusik.ncknms.com/КОРОТКИЙ_ID_ЛЮБОЙ_ПОДПИСКИ
# FAILS_TO_ALERT=2
# REPORT_EVERY=5                       # плановый отчёт каждые 5 минут (0 — выключить)
