#!/usr/bin/env bash
# Проверка, режут ли до адресов TCP с этого сервера (ping не показатель).
# Запускать на российском сервере, лучше у «фильтрующего» хостера (Selectel/Timeweb):
# если там адрес «ok», его, скорее всего, ещё нет в списках блокировок.
#
#   bash check-ips.sh 2.27.12.136 93.115.105.68:8445 ...
#   bash check-ips.sh -f ips.txt          # по одному адресу (IP или IP:порт) на строку
#
# Порт по умолчанию — 22. «refused» тоже значит, что адрес доступен: соединение дошло,
# просто на порту никто не слушает.
set -u

TIMEOUT=${TIMEOUT:-5}
DEFAULT_PORT=${PORT:-22}

targets=()
if [ "${1:-}" = "-f" ]; then
  [ -f "${2:-}" ] || { echo "Нет файла ${2:-}"; exit 1; }
  while read -r line; do
    line=${line%%#*}; line=$(echo "$line" | tr -d '[:space:]')
    [ -n "$line" ] && targets+=("$line")
  done < "$2"
else
  targets=("$@")
fi
[ ${#targets[@]} -gt 0 ] || { echo "Использование: $0 IP[:порт] ... | -f файл"; exit 1; }

printf '%-22s %-8s %s\n' "АДРЕС" "PING" "TCP"
ok=0; bad=0
for t in "${targets[@]}"; do
  ip=${t%%:*}
  port=$DEFAULT_PORT
  [ "$t" != "$ip" ] && port=${t#*:}

  if ping -c 2 -W 2 "$ip" >/dev/null 2>&1; then p=ok; else p=no; fi

  err=$(timeout "$TIMEOUT" bash -c "exec 3<>/dev/tcp/$ip/$port" 2>&1)
  rc=$?
  if [ $rc -eq 0 ]; then
    c="ok"
  elif echo "$err" | grep -qi refused; then
    c="ok (refused)"
  else
    c="BLOCKED"
  fi
  [ "$c" = BLOCKED ] && bad=$((bad+1)) || ok=$((ok+1))
  printf '%-22s %-8s %s\n' "$ip:$port" "$p" "$c"
done
echo "Доступно: $ok, заблокировано: $bad"
