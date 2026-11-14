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

# Тихий плановый отчёт (без звука уведомления)
send_report() {
  curl -s -m 15 -o /dev/null "https://api.telegram.org/bot$BOT_TOKEN/sendMessage" \
    --data-urlencode "chat_id=$CHAT_ID" --data-urlencode "parse_mode=HTML" \
    --data-urlencode "disable_notification=true" --data-urlencode "text=$1"
}

# Флаг и название страны по коду ноды из NODES
country() {
  case $1 in
    FI) echo "🇫🇮 Финляндия";;   NL) echo "🇳🇱 Нидерланды";;
    DE) echo "🇩🇪 Германия";;    PL) echo "🇵🇱 Польша";;
    SE) echo "🇸🇪 Швеция";;      EE) echo "🇪🇪 Эстония";;
    LV) echo "🇱🇻 Латвия";;      LT) echo "🇱🇹 Литва";;
    FR) echo "🇫🇷 Франция";;     GB|UK) echo "🇬🇧 Великобритания";;
    US) echo "🇺🇸 США";;         TR) echo "🇹🇷 Турция";;
    KZ) echo "🇰🇿 Казахстан";;   *) echo "🌐 $1";;
  esac
}

# Значок и время для строки отчёта: $1 — ok/fail, $2 — время в секундах
SLOW_MS=${SLOW_MS:-1500}
mark() {
  local ms=""
  [ -n "${2:-}" ] && ms=$(awk -v t="$2" 'BEGIN{printf "%d", t*1000}')
  if [ "$1" != ok ]; then printf '🔴 нет ответа'; return; fi
  if [ -z "$ms" ]; then printf '🟢 в строю'; return; fi
  if [ "$ms" -ge "$SLOW_MS" ]; then printf '🟡 %s мс' "$ms"; else printf '🟢 %s мс' "$ms"; fi
}

# Учесть результат в общей сводке (вызывать не в подоболочке): $1 — ok/fail, $2 — время
note() {
  [ "$1" = ok ] || { ALL_OK=0; return; }
  [ -n "${2:-}" ] && awk -v t="$2" -v s="$SLOW_MS" 'BEGIN{exit !(t*1000>=s)}' && SLOW=1
  return 0
}

ALL_OK=1; SLOW=0; NODES_OK=0; NODES_ALL=0
ENTRY_LINE=""; NODE_LINES=""; SUB_LINE=""

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
  track entry ok "вход $ENTRY (SSH)"
  ENTRY_LINE="🛡 <b>Вход</b> · $(mark ok)"; note ok
  for n in $NODES; do
    name=${n%%=*}; NODES_ALL=$((NODES_ALL + 1))
    code=$(echo "$out" | awk -v n="$name" '$1==n{print $2}')
    t=$(echo "$out" | awk -v n="$name" '$1==n{print $3}')
    if [ "$code" = 200 ]; then r=ok; NODES_OK=$((NODES_OK + 1)); else r=fail; t=""; fi
    track "node-$name" "$r" "нода $(country "$name") (с входа код ${code:-нет ответа})"
    NODE_LINES+="$(country "$name") · $(mark "$r" "$t")"$'\n'; note "$r" "$t"
  done
else
  track entry fail "вход $ENTRY недоступен по SSH (ноды не проверены)"
  ENTRY_LINE="🛡 <b>Вход</b> · $(mark fail)"; note fail
  for n in $NODES; do
    NODES_ALL=$((NODES_ALL + 1))
    NODE_LINES+="$(country "${n%%=*}") · ⚪️ не проверена"$'\n'
  done
fi

# 3. Подписки через вход
host=$(echo "$SUB_URL" | sed -E 's#https?://([^/]+)/.*#\1#')
res=$(curl -sk -o /dev/null -m 15 -A 'Happ/1.0' -w '%{http_code} %{time_total}' \
       --resolve "$host:443:$ENTRY" "$SUB_URL")
code=${res%% *}; t=${res#* }
if [ "$code" = 200 ]; then r=ok; else r=fail; t=""; fi
track sub "$r" "подписки через вход (код $code)"
SUB_LINE="📄 <b>Подписки</b> · $(mark "$r" "$t")"; note "$r" "$t"

# 4. Плановый отчёт
if [ "$REPORT_EVERY" -gt 0 ] && [ $(( 10#$(date +%M) % REPORT_EVERY )) -eq 0 ]; then
  if [ "$ALL_OK" != 1 ]; then head="🔴 <b>MareevVPN · есть сбои</b>"
  elif [ "$SLOW" = 1 ]; then head="🟡 <b>MareevVPN · работает, но медленно</b>"
  else head="🟢 <b>MareevVPN · всё работает</b>"; fi
  now=$(TZ=$REPORT_TZ date '+%d.%m.%Y · %H:%M')
  send_report "$head
🕐 $now МСК

$ENTRY_LINE
━━━━━━━━━━━━━━━━
🌍 <b>Ноды</b> · $NODES_OK из $NODES_ALL в строю
${NODE_LINES%$'\n'}
━━━━━━━━━━━━━━━━
$SUB_LINE"
fi

# --- Образец /etc/vpn-monitor.conf ---
# BOT_TOKEN=123456:ABC...              # токен бота от @BotFather
# CHAT_ID=123456789                    # твой chat_id
# ENTRY=139.100.219.235                # российский вход
# NODES="FI=2.27.13.73=docs.ncknms.com NL=78.17.68.185=notes.ncknms.com DE=2.27.60.173=docs.ncknms.com PL=191.44.113.142=notes.ncknms.com"
# SUB_URL=https://subnikitusik.ncknms.com/КОРОТКИЙ_ID_ЛЮБОЙ_ПОДПИСКИ
# FAILS_TO_ALERT=2
# REPORT_EVERY=5                       # плановый отчёт каждые 5 минут (0 — выключить)
# SLOW_MS=1500                         # с какого времени ответа нода считается медленной (🟡)
# Коды нод в NODES: FI NL DE PL SE EE LV LT FR GB US TR KZ — подставляется флаг и название
