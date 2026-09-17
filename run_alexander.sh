#!/usr/bin/env bash
# Генерация поздравительных роликов одной командой.
#
#   ./run_alexander.sh              # только первый ролик — посмотреть, что получается
#   ./run_alexander.sh rolik-2      # конкретный ролик
#   ./run_alexander.sh all          # все три
#
# Нужно: python3, ffmpeg и ключ Higgsfield в HF_KEY.

set -euo pipefail

cd "$(dirname "$0")"

SCENARIO="scenarios/alexander-birthday.json"
OUT_DIR="${OUT_DIR:-out/alexander}"
PART="${1:-rolik-1}"

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
die() { printf '\n\033[31mОшибка: %s\033[0m\n' "$*" >&2; exit 1; }

# --- проверки до того, как тратить деньги и время ---

command -v python3 >/dev/null || die "не найден python3"

if [ -z "${HF_KEY:-}" ] && { [ -z "${HF_API_KEY:-}" ] || [ -z "${HF_API_SECRET:-}" ]; }; then
    die "не задан ключ. Выполните:
    export HF_KEY=\"<key_id>:<key_secret>\"
Ключ берётся в консоли Higgsfield."
fi

python3 - <<'PY' 2>/dev/null || { say "Ставлю aiohttp"; python3 -m pip install --quiet aiohttp; }
import aiohttp
PY

if ! command -v ffmpeg >/dev/null; then
    printf '\n\033[33mffmpeg не найден: сцены сгенерятся, но без сцепки по кадру и без склейки.\033[0m\n'
    printf 'Поставьте: apt install ffmpeg  (или brew install ffmpeg)\n'
    read -r -p "Продолжить без ffmpeg? [y/N] " answer
    [ "$answer" = "y" ] || [ "$answer" = "Y" ] || exit 1
fi

[ -f "$SCENARIO" ] || die "не найден файл сценария: $SCENARIO"

# --- что будем генерить ---

if [ "$PART" = "all" ]; then
    PART_ARGS=()
    say "Генерим все три ролика"
else
    PART_ARGS=(--part "$PART")
    say "Генерим ролик: $PART"
fi

python3 scenario.py run "$SCENARIO" "${PART_ARGS[@]}" --dry-run --quiet | tail -5

say "Поехали. Прерванный прогон продолжается этой же командой — готовые сцены не перегенерируются."

python3 scenario.py run "$SCENARIO" \
    "${PART_ARGS[@]}" \
    --out-dir "$OUT_DIR" \
    --concat-parts

say "Готово. Смотрите:"
ls -lh "$OUT_DIR"/*.mp4 2>/dev/null || true
