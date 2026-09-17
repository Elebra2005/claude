"""Запуск генерации роликов без bash — работает в Windows, macOS и Linux.

    python run_alexander.py             # первый ролик
    python run_alexander.py rolik-2     # конкретный ролик
    python run_alexander.py all         # все три

Ключ Higgsfield берётся из переменной окружения HF_KEY.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENARIO = HERE / "scenarios" / "alexander-birthday.json"
OUT_DIR = Path(os.getenv("OUT_DIR", HERE / "out" / "alexander"))

WINDOWS = os.name == "nt"


def say(text):
    print(f"\n=== {text}", flush=True)


def die(text, hint=""):
    print(f"\nОшибка: {text}", file=sys.stderr)
    if hint:
        print(hint, file=sys.stderr)
    sys.exit(1)


def check_key():
    if os.getenv("HF_KEY") or (os.getenv("HF_API_KEY") and os.getenv("HF_API_SECRET")):
        return

    if WINDOWS:
        hint = ("Задайте ключ и запустите снова:\n"
                "    set HF_KEY=key_id:key_secret\n"
                "    python run_alexander.py\n"
                "(в PowerShell: $env:HF_KEY=\"key_id:key_secret\")")
    else:
        hint = ("Задайте ключ и запустите снова:\n"
                "    export HF_KEY=\"key_id:key_secret\"\n"
                "    python3 run_alexander.py")

    die("не задан ключ Higgsfield.", hint + "\nКлюч берётся в консоли Higgsfield: https://cloud.higgsfield.ai")


def check_aiohttp():
    try:
        import aiohttp  # noqa: F401
        return
    except ImportError:
        pass

    say("Ставлю библиотеку aiohttp")
    result = subprocess.run([sys.executable, "-m", "pip", "install", "aiohttp"])
    if result.returncode != 0:
        die("не удалось поставить aiohttp.",
            f"Попробуйте вручную: {Path(sys.executable).name} -m pip install aiohttp")


def check_ffmpeg():
    if shutil.which("ffmpeg"):
        return True

    print("\nffmpeg не найден. Без него сцены сгенерируются, но не будет сцепки по\n"
          "последнему кадру и склейки роликов из сцен.")
    if WINDOWS:
        print("Поставить: winget install Gyan.FFmpeg  (затем закрыть и открыть окно консоли)")
    elif sys.platform == "darwin":
        print("Поставить: brew install ffmpeg")
    else:
        print("Поставить: sudo apt install ffmpeg")

    if not sys.stdin.isatty():
        print("Продолжаю без ffmpeg.")
        return False

    try:
        answer = input("Продолжить без ffmpeg? [y/N] ").strip().lower()
    except EOFError:
        answer = "y"
    if answer not in ("y", "yes", "д", "да"):
        sys.exit(1)
    return False


def run(args):
    command = [sys.executable, str(HERE / "scenario.py"), "run", str(SCENARIO)] + args
    return subprocess.run(command).returncode


def main() -> int:
    part = sys.argv[1] if len(sys.argv) > 1 else "rolik-1"

    if not SCENARIO.exists():
        die(f"не найден файл сценария: {SCENARIO}",
            "Запускайте скрипт из папки репозитория.")

    check_key()
    check_aiohttp()
    check_ffmpeg()

    part_args = [] if part == "all" else ["--part", part]
    say("Генерим все три ролика" if part == "all" else f"Генерим ролик: {part}")

    run(part_args + ["--dry-run", "--quiet"])

    say("Поехали. Прерванный прогон продолжается этой же командой — "
        "готовые сцены не перегенерируются.")

    code = run(part_args + ["--out-dir", str(OUT_DIR), "--concat-parts"])

    if code == 0:
        say(f"Готово. Файлы здесь: {OUT_DIR}")
        for path in sorted(OUT_DIR.glob("*.mp4")):
            print(f"  {path}  ({path.stat().st_size / 1_000_000:.1f} МБ)")
    else:
        say("Часть сцен не сгенерировалась — запустите эту же команду ещё раз, "
            "она доделает только их.")

    return code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
