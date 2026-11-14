#!/usr/bin/env bash
# Мониторинг VPN-схемы с уведомлениями в Telegram. Запускать на сервере панели
# (с него доступен Telegram) раз в минуту через cron.
#
# Каждую минуту:
#   1. вход (Selectel) доступен по SSH;
#   2. с входа каждая нода отвечает как Reality+selfsteal (curl по SNI на :8445);
#   3. через вход открываются подписки (Caddy -> панель);
#   4. на сервере панели запущены контейнеры панели и ботов.
# Раз в час (если NODE_SSH=1): здоровье нод — контейнеры, диск, память, срок
# сертификатов selfsteal.
#
# При сбое скрипт сам перепроверяет узел с разных сторон (из-за границы, с входа,
# изнутри ноды) и присылает причину и что делать. Сообщения — только при смене
# состояния. Плановый отчёт — каждые REPORT_EVERY минут, без звука.
#
# Настройки — в /etc/vpn-monitor.conf (образец в конце файла).
set -u
export LC_ALL=C.UTF-8

# --report: проверить всё прямо сейчас и прислать отчёт (кнопка «Проверить статус»).
# В этом режиме состояние тревог не меняется, а причины сбоев идут в тот же отчёт.
ON_DEMAND=0; [ "${1:-}" = --report ] && ON_DEMAND=1

CONF=${CONF:-/etc/vpn-monitor.conf}
[ -f "$CONF" ] || { echo "Нет $CONF"; exit 1; }
# shellcheck disable=SC1090
. "$CONF"

: "${BOT_TOKEN:?}" "${CHAT_ID:?}" "${ENTRY:?}" "${NODES:?}" "${SUB_URL:?}"
FAILS_TO_ALERT=${FAILS_TO_ALERT:-2}
REPORT_EVERY=${REPORT_EVERY:-0}
REPORT_TZ=${REPORT_TZ:-Europe/Moscow}
SLOW_MS=${SLOW_MS:-1500}
NODE_SSH=${NODE_SSH:-0}
HEALTH_EVERY=${HEALTH_EVERY:-60}
CERT_WARN_DAYS=${CERT_WARN_DAYS:-14}
DISK_WARN=${DISK_WARN:-90}
PANEL_CONTAINERS=${PANEL_CONTAINERS:-"remnawave remnawave-db remnawave-redis remnawave-subscription-page remnawave-nginx"}
BOT_CONTAINERS=${BOT_CONTAINERS:-"remna-sales-bot remna-telegram-bot-prod"}
STATE_DIR=${STATE_DIR:-/var/lib/vpn-monitor}
mkdir -p "$STATE_DIR"
SUB_HOST=$(echo "$SUB_URL" | sed -E 's#https?://([^/]+)/.*#\1#')
PANEL_IP=${PANEL_IP:-$(curl -4 -s -m 5 ifconfig.me 2>/dev/null)}
MINUTE=$(( 10#$(date +%M) ))

# ---------- Telegram ----------
tg() {  # $1 — текст (HTML), $2 — true = без звука
  curl -s -m 15 -o /dev/null "https://api.telegram.org/bot$BOT_TOKEN/sendMessage" \
    --data-urlencode "chat_id=$CHAT_ID" --data-urlencode "parse_mode=HTML" \
    --data-urlencode "disable_notification=${2:-false}" --data-urlencode "text=$1"
}
esc() { sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g' <<<"$1"; }

# ---------- Проверки ----------
tcp_state() {  # $1 ip, $2 порт -> open / refused / closed
  local e rc
  e=$(timeout 5 bash -c "exec 3<>/dev/tcp/$1/$2" 2>&1); rc=$?
  if [ $rc -eq 0 ]; then echo open
  elif grep -qi refused <<<"$e"; then echo refused
  else echo closed; fi
}
https_code() { curl -sk -o /dev/null -m 8 -w '%{http_code}' --resolve "$2:$3:$1" "https://$2:$3/" 2>/dev/null; }  # ip sni port
on_entry() { ssh -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new "root@$ENTRY" "$@" 2>/dev/null; }
on_node()  { ssh -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new "root@$1" 'bash -s' 2>/dev/null; }

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

# Состояние ноды изнутри (по SSH): контейнеры, порты, диск, память, сертификаты
NODE_INFO_SCRIPT='
st() { docker inspect -f "{{.State.Status}}" "$1" 2>/dev/null || echo none; }
lis() { ss -tln 2>/dev/null | grep -q ":$1 " && echo yes || echo no; }
days() { f=/opt/selfsteal/certs/$1.crt; [ -f "$f" ] || { echo none; return; }
  e=$(date -d "$(openssl x509 -enddate -noout -in "$f" | cut -d= -f2)" +%s 2>/dev/null) || { echo none; return; }
  echo $(( (e - $(date +%s)) / 86400 )); }
echo "rn=$(st remnanode) ss=$(st selfsteal) l8445=$(lis 8445) l9443=$(lis 9443) disk=$(df --output=pcent / | tail -1 | tr -dc 0-9) mem=$(awk "/MemAvailable/{print int(\$2/1024)}" /proc/meminfo) docs=$(days docs) notes=$(days notes)"
'
node_info() { on_node "$1" <<<"$NODE_INFO_SCRIPT"; }
kv() { sed -n "s/.*\b$2=\([^ ]*\).*/\1/p" <<<"$1"; }  # значение ключа $2 из строки $1

# ---------- Диагностика ----------
# Каждая diag_* печатает блок: Причина / Что сделать / Данные (HTML)
say() { printf '<b>Причина:</b> %s\n<b>Что сделать:</b> %s\n<i>Данные:</i> %s' "$1" "$2" "$3"; }

diag_node() {  # $1 код, $2 ip, $3 sni
  local name=$1 ip=$2 sni=$3 p22 p8445 p2222 code ent e22 e8445 info="" facts cause act
  p22=$(tcp_state "$ip" 22); p8445=$(tcp_state "$ip" 8445); p2222=$(tcp_state "$ip" 2222)
  code=$(https_code "$ip" "$sni" 8445)
  ent=$(on_entry "for p in 22 8445; do timeout 5 bash -c \"</dev/tcp/$ip/\$p\" 2>/dev/null && echo open || echo closed; done" | tr '\n' ' ')
  e22=$(awk '{print $1}' <<<"$ent"); e8445=$(awk '{print $2}' <<<"$ent")
  facts="из-за границы: 22 $p22, 8445 $p8445, 2222 $p2222, Reality ${code:-000} · с входа: 22 ${e22:-?}, 8445 ${e8445:-?}"
  if [ "$NODE_SSH" = 1 ]; then
    info=$(node_info "$ip")
    [ -n "$info" ] && facts+=" · на ноде: $info"
  fi

  if [ "$p22" != open ] && [ "$p8445" != open ] && [ "$p22" != refused ]; then
    cause="сервер ноды $ip недоступен даже из-за границы — выключен, завис, или проблемы у хостера (возможна миграция)."
    act="открыть кабинет хостера: статус сервера, при необходимости — перезагрузить. После загрузки remnanode и selfsteal поднимутся сами."
  elif [ "$code" = 200 ]; then
    if [ -z "$ent" ]; then
      cause="нода исправна (из-за границы отвечает), но проверить её с входа не удалось — вход недоступен по SSH."
      act="смотри отдельное сообщение про вход."
    elif [ "$e22" = closed ] && [ "$e8445" = closed ]; then
      cause="нода исправна, но вход $ENTRY до неё не достаёт — адрес $ip, скорее всего, попал в списки блокировок для российских серверов."
      act="сменить IP ноды: взять чистый адрес → проверить check-ips.sh с входа → поменять в панели (Nodes) и в /etc/nftables.conf на входе."
    else
      cause="с входа TCP до ноды проходит, но ответ Reality не доходит — похоже на фильтрацию трафика между входом и нодой или сбой сети."
      act="подождать 5–10 минут; если не пройдёт — сменить IP ноды."
    fi
  elif [ -n "$info" ]; then
    # Есть данные изнутри ноды — причина определяется точно
    local rn sst l8 l9 dd nd
    rn=$(kv "$info" rn); sst=$(kv "$info" ss); l8=$(kv "$info" l8445); l9=$(kv "$info" l9443)
    dd=$(kv "$info" docs); nd=$(kv "$info" notes)
    if [ "$rn" != running ]; then
      cause="контейнер remnanode на ноде не запущен (статус: $rn)."
      act="на ноде $ip: cd /opt/remnanode &amp;&amp; docker compose up -d &amp;&amp; docker logs remnanode --tail 20"
    elif [ "$l8" != yes ]; then
      cause="remnanode запущен, но Xray не слушает 8445 — панель не передала ноде конфиг."
      if [ "$p2222" != open ]; then act="порт 2222 ноды снаружи не отвечает — проверь файрвол ноды/хостера; нода в панели должна стать зелёной."
      else act="в панели открой ноду (Nodes) — она, вероятно, красная; на ноде: docker restart remnanode."; fi
    elif [ "$p8445" != open ]; then
      cause="Xray на ноде слушает 8445, но снаружи порт закрыт — его режет файрвол ноды или хостера."
      act="на ноде: ufw status / iptables -S INPUT; в кабинете хостера — файрвол/группы безопасности: открыть TCP 8445."
    elif [ "$sst" != running ]; then
      cause="контейнер selfsteal на ноде не запущен (статус: $sst) — Reality некуда отправлять маскировочный трафик."
      act="на ноде $ip: docker start selfsteal (если его нет — развернуть заново из /opt/selfsteal)."
    elif [ "$l9" != yes ]; then
      cause="selfsteal запущен, но не слушает 127.0.0.1:9443 — ошибка в его конфиге."
      act="на ноде $ip: docker logs selfsteal --tail 20, проверить /opt/selfsteal/Caddyfile."
    elif { [ "$dd" != none ] && [ "$dd" -lt 0 ]; } || { [ "$nd" != none ] && [ "$nd" -lt 0 ]; }; then
      cause="истёк сертификат selfsteal (docs: $dd дн., notes: $nd дн.)."
      act="скопировать свежие сертификаты docs/notes с входа (Caddy) в /opt/selfsteal/certs на ноде и docker restart selfsteal."
    else
      cause="внутри ноды всё запущено, но рукопожатие Reality не проходит — вероятно, не совпадают настройки профиля (SNI/ключи) с хостом."
      act="сравнить профиль конфигурации ноды и хост в панели с рабочей нодой; docker logs remnanode --tail 30."
    fi
  elif [ "$p8445" != open ]; then
    cause="сервер ноды жив, но порт 8445 закрыт — Xray не запущен (нет конфига от панели) или порт режет файрвол."
    act="на ноде: docker ps, ss -tlnp | grep 8445; проверить, что нода зелёная в панели. Для точной причины включи NODE_SSH=1."
  else
    cause="Xray слушает 8445, но рукопожатие Reality не проходит — скорее всего, не работает сайт маскировки (selfsteal)."
    act="на ноде: docker ps (selfsteal должен быть Up), ss -tlnp | grep 9443, docker logs selfsteal --tail 20. Для точной причины включи NODE_SSH=1."
  fi
  say "$cause" "$act" "$(esc "$facts")"
}

diag_entry() {
  local png p22 p443
  ping -c 2 -W 2 "$ENTRY" >/dev/null 2>&1 && png=ok || png=no
  p22=$(tcp_state "$ENTRY" 22); p443=$(tcp_state "$ENTRY" 443)
  if [ "$png" = no ] && [ "$p22" != open ] && [ "$p443" != open ]; then
    say "вход $ENTRY не отвечает вообще (ping, 22, 443) — сервер упал, выключен или проблема в сети Selectel. VPN и подписки у клиентов сейчас не работают." \
        "кабинет Selectel: статус сервера, перезагрузка; проверить плавающий IP и роутер. Запасной вариант — ProCloud." \
        "ping $png · 22 $p22 · 443 $p443"
  elif [ "$p22" = open ]; then
    say "порт 22 открыт, но вход по SSH-ключу не прошёл — ключ сервера панели больше не принимается." \
        "на сервере панели: ssh-copy-id root@$ENTRY" "ping $png · 22 $p22 · 443 $p443"
  else
    say "вход отвечает (443 $p443), но SSH (22) закрыт — проверки нод невозможны, сам VPN, скорее всего, работает." \
        "проверь файрвол/группу безопасности Selectel для порта 22." "ping $png · 22 $p22 · 443 $p443"
  fi
}

container_report() {  # $@ — имена контейнеров; печатает неработающие
  local c st bad=""
  for c in "$@"; do
    st=$(docker inspect -f '{{.State.Status}}{{if .State.Health}}/{{.State.Health.Status}}{{end}}' "$c" 2>/dev/null || echo "нет")
    case $st in running|running/healthy) ;; *) bad+="$c: $st; ";; esac
  done
  printf '%s' "$bad"
}

diag_sub() {
  local loc bad ent caddy fromentry
  loc=$(curl -sk -o /dev/null -m 10 -A 'Happ/1.0' -w '%{http_code}' --resolve "$SUB_HOST:443:127.0.0.1" "$SUB_URL")
  # shellcheck disable=SC2086
  bad=$(container_report $PANEL_CONTAINERS)
  if [ "$loc" != 200 ]; then
    if [ -n "$bad" ]; then
      say "подписки не работают на самом сервере панели — не запущены контейнеры: $(esc "$bad")" \
          "на сервере панели: cd /opt/remnawave &amp;&amp; docker compose up -d" "локально код $loc"
    else
      say "контейнеры панели запущены, но страница подписок отвечает кодом $loc (часто — неверный API-токен или панель недоступна для страницы подписок)." \
          "docker logs remnawave-subscription-page --tail 20" "локально код $loc"
    fi
    return
  fi
  ent=$(on_entry "systemctl is-active caddy; curl -sk -o /dev/null -m 8 -A Happ/1.0 -w '%{http_code}' --resolve $SUB_HOST:443:$PANEL_IP '$SUB_URL'")
  caddy=$(sed -n 1p <<<"$ent"); fromentry=$(sed -n 2p <<<"$ent")
  if [ -z "$ent" ]; then
    say "на сервере панели подписки работают, а вход недоступен по SSH — проблема на входе." "смотри сообщение про вход." "локально $loc"
  elif [ "$caddy" != active ]; then
    say "Caddy на входе остановлен (статус: $caddy) — через вход не открываются ни подписки, ни панель." \
        "на входе: systemctl restart caddy &amp;&amp; journalctl -u caddy -n 20" "локально $loc · caddy $caddy"
  elif [ "$fromentry" != 200 ]; then
    say "вход не достаёт до сервера панели $PANEL_IP (код ${fromentry:-000}) — адрес панели мог попасть в блок для российских серверов, или закрыт порт 443." \
        "с входа: bash /root/check-ips.sh $PANEL_IP:443; при блокировке — переносить панель на чистый адрес." \
        "локально $loc · caddy $caddy · вход→панель ${fromentry:-000}"
  else
    say "вход и панель по отдельности работают, сбой был на участке до входа или кратковременный." \
        "если повторится — проверить доступность $ENTRY:443 из России." "локально $loc · вход→панель $fromentry"
  fi
}

diag_panel() {
  local bad dsk mem
  # shellcheck disable=SC2086
  bad=$(container_report $PANEL_CONTAINERS)
  dsk=$(df --output=pcent / | tail -1 | tr -dc 0-9); mem=$(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo)
  if [ -n "$bad" ]; then
    say "на сервере панели не работают контейнеры: $(esc "$bad")" \
        "cd /opt/remnawave &amp;&amp; docker compose up -d; docker logs ИМЯ --tail 20" "диск ${dsk}%, свободно RAM ${mem} МБ"
  else
    say "диск сервера панели заполнен на ${dsk}%." "почистить место (docker system prune, старые бэкапы) или поднять тариф." "диск ${dsk}%, свободно RAM ${mem} МБ"
  fi
}
diag_bots() {
  local bad
  # shellcheck disable=SC2086
  bad=$(container_report $BOT_CONTAINERS)
  say "не работают боты: $(esc "$bad") — оплата и выдача подписок могут не работать." \
      "docker start ИМЯ; docker logs ИМЯ --tail 20" "$(esc "$bad")"
}

# ---------- Учёт состояний ----------
# $1 ключ, $2 ok/fail, $3 заголовок, $4 порог, далее — команда диагностики
DIAG_TEXT=""
track() {
  local key=$1 res=$2 title=$3 th=$4 f="$STATE_DIR/$1" fails=0 alerted=0 since=0 now mins
  shift 4
  if [ "$ON_DEMAND" = 1 ]; then
    [ "$res" = ok ] || DIAG_TEXT+=$'\n\n'"🔴 <b>$title</b>"$'\n'"$("$@")"
    return 0
  fi
  [ -f "$f" ] && read -r fails alerted since < "$f"
  now=$(date +%s)
  if [ "$res" = ok ]; then
    if [ "$alerted" = 1 ]; then
      mins=$(( (now - ${since:-$now}) / 60 ))
      tg "✅ <b>$title — снова работает</b>
Сбой длился ~${mins} мин."
    fi
    echo "0 0 0" > "$f"
  else
    [ "${fails:-0}" = 0 ] && since=$now
    fails=$(( ${fails:-0} + 1 ))
    if [ "$fails" -ge "$th" ] && [ "$alerted" != 1 ]; then
      tg "🔴 <b>$title</b>
$("$@")"
      alerted=1
    fi
    echo "$fails $alerted ${since:-$now}" > "$f"
  fi
}

# ---------- Строки отчёта ----------
ALL_OK=1; SLOW=0; NODES_OK=0; NODES_ALL=0
ENTRY_LINE=""; NODE_LINES=""; SUB_LINE=""; PANEL_LINE=""
mark() {
  local ms=""
  [ -n "${2:-}" ] && ms=$(awk -v t="$2" 'BEGIN{printf "%d", t*1000}')
  if [ "$1" != ok ]; then printf '🔴 сбой'; return; fi
  if [ -z "$ms" ]; then printf '🟢 в строю'; return; fi
  if [ "$ms" -ge "$SLOW_MS" ]; then printf '🟡 %s мс' "$ms"; else printf '🟢 %s мс' "$ms"; fi
}
note() {  # учесть результат в общей сводке (не в подоболочке)
  [ "$1" = ok ] || { ALL_OK=0; return 0; }
  [ -n "${2:-}" ] && awk -v t="$2" -v s="$SLOW_MS" 'BEGIN{exit !(t*1000>=s)}' && SLOW=1
  return 0
}

# ---------- 1–2. Вход и ноды ----------
remote_checks=""
for n in $NODES; do            # формат: Код=IP=SNI
  name=${n%%=*}; rest=${n#*=}; ip=${rest%%=*}; sni=${rest#*=}
  remote_checks+="c=\$(curl -sk -o /dev/null -m 8 -w '%{http_code} %{time_total}' --resolve $sni:8445:$ip https://$sni:8445/); echo \"$name \$c\"; "
done

out=$(on_entry "$remote_checks")
if [ $? -eq 0 ] && [ -n "$out" ]; then
  track entry ok "Вход $ENTRY" "$FAILS_TO_ALERT" diag_entry
  ENTRY_LINE="🛡 <b>Вход</b> · $(mark ok)"; note ok
  for n in $NODES; do
    name=${n%%=*}; rest=${n#*=}; ip=${rest%%=*}; sni=${rest#*=}
    NODES_ALL=$((NODES_ALL + 1))
    code=$(awk -v n="$name" '$1==n{print $2}' <<<"$out")
    t=$(awk -v n="$name" '$1==n{print $3}' <<<"$out")
    if [ "$code" = 200 ]; then r=ok; NODES_OK=$((NODES_OK + 1)); else r=fail; t=""; fi
    track "node-$name" "$r" "Нода $(country "$name") ($ip)" "$FAILS_TO_ALERT" diag_node "$name" "$ip" "$sni"
    NODE_LINES+="$(country "$name") · $(mark "$r" "$t")"$'\n'; note "$r" "$t"
  done
else
  track entry fail "Вход $ENTRY" "$FAILS_TO_ALERT" diag_entry
  ENTRY_LINE="🛡 <b>Вход</b> · $(mark fail)"; note fail
  for n in $NODES; do
    NODES_ALL=$((NODES_ALL + 1))
    NODE_LINES+="$(country "${n%%=*}") · ⚪️ не проверена"$'\n'
  done
fi

# ---------- 3. Подписки через вход ----------
res=$(curl -sk -o /dev/null -m 15 -A 'Happ/1.0' -w '%{http_code} %{time_total}' \
       --resolve "$SUB_HOST:443:$ENTRY" "$SUB_URL")
code=${res%% *}; t=${res#* }
if [ "$code" = 200 ]; then r=ok; else r=fail; t=""; fi
track sub "$r" "Подписки через вход" "$FAILS_TO_ALERT" diag_sub
SUB_LINE="📄 <b>Подписки</b> · $(mark "$r" "$t")"; note "$r" "$t"

# ---------- 4. Сервер панели и боты ----------
if command -v docker >/dev/null 2>&1; then
  # shellcheck disable=SC2086
  bad=$(container_report $PANEL_CONTAINERS)
  dsk=$(df --output=pcent / | tail -1 | tr -dc 0-9)
  if [ -z "$bad" ] && [ "${dsk:-0}" -lt "$DISK_WARN" ]; then r=ok; else r=fail; fi
  track panel "$r" "Сервер панели" "$FAILS_TO_ALERT" diag_panel
  PANEL_LINE="🖥 <b>Панель</b> · $(mark "$r")"; note "$r"
  # shellcheck disable=SC2086
  bad=$(container_report $BOT_CONTAINERS)
  if [ -z "$bad" ]; then r=ok; else r=fail; fi
  track bots "$r" "Боты" "$FAILS_TO_ALERT" diag_bots
  PANEL_LINE+=$'\n'"🤖 <b>Боты</b> · $(mark "$r")"; note "$r"
fi

# ---------- 5. Здоровье нод изнутри (раз в HEALTH_EVERY минут) ----------
if [ "$NODE_SSH" = 1 ] && { [ "$ON_DEMAND" = 1 ] || [ $(( MINUTE % HEALTH_EVERY )) -eq 0 ]; }; then
  for n in $NODES; do
    name=${n%%=*}; rest=${n#*=}; ip=${rest%%=*}
    info=$(node_info "$ip")
    [ -n "$info" ] || continue   # недоступность ноды ловит основная проверка
    warn=""
    dd=$(kv "$info" docs); nd=$(kv "$info" notes); dk=$(kv "$info" disk); mm=$(kv "$info" mem)
    [ -n "$dd" ] && [ "$dd" != none ] && [ "$dd" -le "$CERT_WARN_DAYS" ] && warn+="сертификат docs истекает через $dd дн.; "
    [ -n "$nd" ] && [ "$nd" != none ] && [ "$nd" -le "$CERT_WARN_DAYS" ] && warn+="сертификат notes истекает через $nd дн.; "
    [ -n "$dk" ] && [ "$dk" -ge "$DISK_WARN" ] && warn+="диск заполнен на ${dk}%; "
    [ -n "$mm" ] && [ "$mm" -lt 100 ] && warn+="свободно всего ${mm} МБ RAM; "
    if [ -z "$warn" ]; then r=ok; else r=fail; fi
    track "health-$name" "$r" "Нода $(country "$name"): предупреждение" 1 \
      say "$(esc "$warn")" "сертификаты — скопировать свежие docs/notes с входа в /opt/selfsteal/certs и docker restart selfsteal; диск/RAM — почистить или поднять тариф." "$(esc "$info")"
  done
fi

# ---------- 6. Плановый отчёт ----------
if [ "$ON_DEMAND" = 1 ] || { [ "$REPORT_EVERY" -gt 0 ] && [ $(( MINUTE % REPORT_EVERY )) -eq 0 ]; }; then
  if [ "$ALL_OK" != 1 ]; then head="🔴 <b>MareevVPN · есть сбои</b>"
  elif [ "$SLOW" = 1 ]; then head="🟡 <b>MareevVPN · работает, но медленно</b>"
  else head="🟢 <b>MareevVPN · всё работает</b>"; fi
  now=$(TZ=$REPORT_TZ date '+%d.%m.%Y · %H:%M')
  tail_note=""
  if [ "$ON_DEMAND" = 1 ]; then tail_note="$DIAG_TEXT"
  elif [ "$ALL_OK" != 1 ]; then tail_note=$'\n\n'"ℹ️ Причины сбоев — в отдельных сообщениях."; fi
  tg "$head
🕐 $now МСК

$ENTRY_LINE
━━━━━━━━━━━━━━━━
🌍 <b>Ноды</b> · $NODES_OK из $NODES_ALL в строю
${NODE_LINES%$'\n'}
━━━━━━━━━━━━━━━━
$SUB_LINE${PANEL_LINE:+$'\n'$PANEL_LINE}$tail_note" "$([ "$ON_DEMAND" = 1 ] && echo false || echo true)"
fi

# --- Образец /etc/vpn-monitor.conf ---
# BOT_TOKEN=123456:ABC...              # токен бота от @BotFather
# CHAT_ID=123456789                    # твой chat_id
# ENTRY=139.100.219.235                # российский вход
# PANEL_IP=31.77.6.157                 # адрес сервера панели
# NODES="FI=2.27.13.73=docs.ncknms.com NL=78.17.68.185=notes.ncknms.com DE=2.27.60.173=docs.ncknms.com PL=191.44.113.142=notes.ncknms.com"
# SUB_URL=https://subnikitusik.ncknms.com/КОРОТКИЙ_ID_ЛЮБОЙ_ПОДПИСКИ
# FAILS_TO_ALERT=2                     # сколько неудачных проверок подряд до тревоги
# REPORT_EVERY=0                       # плановый отчёт каждые N минут (0 — только по кнопке в боте)
# SLOW_MS=1500                         # с какого времени ответа нода считается медленной (🟡)
# NODE_SSH=1                           # заглядывать внутрь нод по SSH (нужен ключ панели на нодах)
# HEALTH_EVERY=60                      # как часто проверять сертификаты/диск/RAM на нодах (минуты)
# CERT_WARN_DAYS=14                    # предупреждать, если сертификат истекает раньше
# DISK_WARN=90                         # предупреждать при заполнении диска, %
# Коды нод в NODES: FI NL DE PL SE EE LV LT FR GB US TR KZ — подставляется флаг и название
