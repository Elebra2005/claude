"""Прогон сценария: несколько сцен → несколько клипов → один файл.

Модели Higgsfield генерируют короткие клипы (обычно 4–10 секунд), поэтому
сценарий разбивается на сцены, каждая генерируется отдельно, а потом склеивается
через ffmpeg.

    python3 scenario.py init --from-text описание.txt -o scenario.json
    python3 scenario.py run scenario.json --out-dir out --concat out/final.mp4

Ход работы пишется в out/manifest.json: готовые сцены при повторном запуске
пропускаются (--resume), упавшие — перегенерируются.
"""

import argparse
import asyncio
import json
import logging
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

import higgsfield

logger = logging.getLogger("scenario")

# Поля сцены, которые уходят в API как именованные параметры higgsfield.py
SHOT_FIELDS = (
    "model", "image", "duration", "resolution",
    "aspect_ratio", "output_format", "generate_audio",
)

DEFAULT_DEFAULTS = {
    "duration": 5,
    "resolution": "720p",
    "aspect_ratio": "16:9",
    "output_format": "mp4",
}


class ScenarioError(Exception):
    """Ошибка в файле сценария."""


def _slug(text: str, fallback: str) -> str:
    slug = re.sub(r"[^\w\-]+", "-", text.strip().lower(), flags=re.UNICODE).strip("-")
    return (slug[:40] or fallback)


def load_scenario(path) -> dict:
    """Читает и проверяет файл сценария."""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ScenarioError(f"Файл сценария не найден: {path}")
    except ValueError as exc:
        raise ScenarioError(f"Сценарий не разбирается как JSON: {exc}")

    if not isinstance(data, dict):
        raise ScenarioError("Сценарий должен быть объектом JSON")

    shots = data.get("shots")
    if not isinstance(shots, list) or not shots:
        raise ScenarioError("В сценарии нет непустого списка shots")

    defaults = {**DEFAULT_DEFAULTS, **(data.get("defaults") or {})}
    style = defaults.pop("style", None)

    prepared = []
    seen = set()
    for index, shot in enumerate(shots, start=1):
        if isinstance(shot, str):
            shot = {"prompt": shot}
        if not isinstance(shot, dict):
            raise ScenarioError(f"Сцена {index}: ожидается строка или объект")

        prompt = (shot.get("prompt") or "").strip()
        if not prompt and not shot.get("image"):
            raise ScenarioError(f"Сцена {index}: нужен prompt или image")

        shot_style = shot.get("style", style)
        if shot_style and prompt:
            prompt = f"{prompt}. {shot_style}".replace("..", ".")

        shot_id = str(shot.get("id") or f"{index:02d}-{_slug(prompt, str(index))}")
        if shot_id in seen:
            raise ScenarioError(f"Повторяющийся id сцены: {shot_id}")
        seen.add(shot_id)

        merged = {key: shot.get(key, defaults.get(key)) for key in SHOT_FIELDS}
        merged["id"] = shot_id
        merged["prompt"] = prompt or None
        merged["params"] = {**(defaults.get("params") or {}), **(shot.get("params") or {})}
        prepared.append(merged)

    return {"name": data.get("name") or Path(path).stem, "shots": prepared}


def scenario_from_text(text: str, name: str = "scenario") -> dict:
    """Превращает текстовое описание в заготовку сценария.

    Сцены разделяются пустой строкой; нумерация вида «1.» или «Сцена 2:» в
    начале абзаца убирается.
    """
    blocks = [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]
    shots = []
    for index, block in enumerate(blocks, start=1):
        prompt = " ".join(line.strip() for line in block.splitlines() if line.strip())
        prompt = re.sub(r"^(сцена|shot|scene)?\s*\d+[.):-]\s*", "", prompt, flags=re.IGNORECASE)
        shots.append({"id": f"{index:02d}", "prompt": prompt})

    if not shots:
        raise ScenarioError("В описании не нашлось ни одной сцены")

    return {
        "name": name,
        "defaults": {**DEFAULT_DEFAULTS, "style": ""},
        "shots": shots,
    }


class Manifest:
    """Состояние прогона на диске: что уже готово, что упало."""

    def __init__(self, path: Path):
        self.path = path
        self.data = {"shots": {}}
        if path.exists():
            try:
                self.data = json.loads(path.read_text(encoding="utf-8"))
            except ValueError:
                logger.warning("Манифест %s повреждён, начинаем заново", path)
        self.data.setdefault("shots", {})

    def get(self, shot_id: str) -> dict:
        return self.data["shots"].get(shot_id, {})

    def done(self, shot_id: str) -> bool:
        entry = self.get(shot_id)
        return entry.get("status") == "completed" and Path(entry.get("file", "")).exists()

    def update(self, shot_id: str, **fields):
        entry = self.data["shots"].setdefault(shot_id, {})
        entry.update(fields)
        self.save()

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8"
        )


async def generate_shot(hf: higgsfield.HiggsfieldClient, shot: dict, out_dir: Path,
                        manifest: Manifest, interval: float, timeout: float) -> Optional[Path]:
    """Генерирует одну сцену и кладёт файл в out_dir."""
    shot_id = shot["id"]
    extension = shot.get("output_format") or "mp4"
    target = out_dir / f"{shot_id}.{extension}"

    logger.info("Сцена %s: отправляем", shot_id)
    manifest.update(shot_id, status="in_progress", prompt=shot.get("prompt"), error=None)

    try:
        result = await hf.generate_video(
            shot.get("prompt"),
            model=shot.get("model"),
            image=shot.get("image"),
            duration=shot.get("duration"),
            resolution=shot.get("resolution"),
            aspect_ratio=shot.get("aspect_ratio"),
            output_format=shot.get("output_format"),
            generate_audio=shot.get("generate_audio"),
            params=shot.get("params"),
            interval=interval,
            timeout=timeout,
        )
    except higgsfield.HiggsfieldTimeoutError as exc:
        # Задача жива, просто долгая: сохраняем id, чтобы дозабрать позже.
        manifest.update(shot_id, status="timeout", request_id=exc.job.request_id,
                        error=str(exc))
        logger.error("Сцена %s: %s", shot_id, exc)
        return None
    except higgsfield.HiggsfieldError as exc:
        manifest.update(shot_id, status="failed", error=str(exc))
        logger.error("Сцена %s: %s", shot_id, exc)
        return None

    urls = higgsfield.extract_video_urls(result)
    if not urls:
        manifest.update(shot_id, status="failed", error="в ответе нет ссылки на файл")
        logger.error("Сцена %s: в ответе нет ссылки на файл", shot_id)
        return None

    await hf.download(urls[0], target)
    manifest.update(shot_id, status="completed", url=urls[0], file=str(target),
                    request_id=result.get("request_id"))
    logger.info("Сцена %s: готово → %s", shot_id, target)
    return target


async def run_scenario(scenario: dict, out_dir: Path, *, concurrency: int = 2,
                       resume: bool = True, interval: float = higgsfield.POLL_INTERVAL,
                       timeout: float = higgsfield.POLL_TIMEOUT,
                       base_url: str = higgsfield.BASE_URL) -> dict:
    """Генерирует все сцены сценария. Упавшая сцена не останавливает остальные."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = Manifest(out_dir / "manifest.json")
    manifest.data["name"] = scenario["name"]

    semaphore = asyncio.Semaphore(max(1, concurrency))
    results: dict = {}

    async with higgsfield.HiggsfieldClient(base_url=base_url) as hf:
        async def worker(shot: dict):
            shot_id = shot["id"]
            if resume and manifest.done(shot_id):
                logger.info("Сцена %s: уже готова, пропускаем", shot_id)
                results[shot_id] = Path(manifest.get(shot_id)["file"])
                return
            async with semaphore:
                results[shot_id] = await generate_shot(
                    hf, shot, out_dir, manifest, interval, timeout
                )

        await asyncio.gather(*(worker(shot) for shot in scenario["shots"]))

    ready = [results.get(shot["id"]) for shot in scenario["shots"]]
    return {
        "manifest": manifest,
        "files": [path for path in ready if path is not None],
        "missing": [shot["id"] for shot in scenario["shots"] if results.get(shot["id"]) is None],
    }


def concat(files, target: Path) -> Optional[Path]:
    """Склеивает клипы в один файл через ffmpeg (перекодирования нет)."""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)

    list_file = target.parent / "concat.txt"
    list_file.write_text(
        "".join(f"file '{Path(f).resolve()}'\n" for f in files), encoding="utf-8"
    )

    command = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(list_file), "-c", "copy", str(target),
    ]

    if shutil.which("ffmpeg") is None:
        print("ffmpeg не найден. Список сцен сохранён, склейка одной командой:",
              file=sys.stderr)
        print(" ".join(command), file=sys.stderr)
        return None

    logger.info("Склеиваем %s сцен → %s", len(files), target)
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        # -c copy не переживает разные кодеки/размеры — пробуем с перекодированием.
        logger.warning("Склейка без перекодирования не вышла, пробуем перекодировать")
        fallback = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(target),
        ]
        result = subprocess.run(fallback, capture_output=True, text=True)
        if result.returncode != 0:
            print(result.stderr[-2000:], file=sys.stderr)
            raise ScenarioError("ffmpeg не смог склеить сцены")

    logger.info("Готово: %s", target)
    return target


def _dry_run(scenario: dict, base_url: str) -> int:
    total = 0
    for shot in scenario["shots"]:
        application = shot.get("model") or (
            higgsfield.DEFAULT_IMAGE_TO_VIDEO if shot.get("image")
            else higgsfield.DEFAULT_TEXT_TO_VIDEO
        )
        arguments = {"prompt": shot["prompt"]} if shot.get("prompt") else {}
        if shot.get("image"):
            arguments["image_url"] = f"<загрузка файла {shot['image']}>"
        for key in ("duration", "resolution", "aspect_ratio", "output_format", "generate_audio"):
            if shot.get(key) is not None:
                arguments[key] = shot[key]
        arguments.update(shot.get("params") or {})

        total += float(shot.get("duration") or 0)
        print(f"--- сцена {shot['id']}")
        print(f"POST {base_url.rstrip('/')}/{application}")
        print(json.dumps(arguments, ensure_ascii=False, indent=2))

    print(f"\nвсего сцен: {len(scenario['shots'])}, суммарно ~{total:g} с")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scenario.py",
        description="Генерация видео по сценарию через Higgsfield.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="сделать заготовку сценария из текста")
    init.add_argument("--from-text", required=True, metavar="FILE",
                      help="текстовое описание, сцены разделены пустой строкой")
    init.add_argument("-o", "--output", default="scenario.json", help="куда записать сценарий")

    run = sub.add_parser("run", help="сгенерировать сцены")
    run.add_argument("scenario", help="файл сценария (JSON)")
    run.add_argument("--out-dir", default="out", help="куда складывать клипы")
    run.add_argument("--concat", metavar="FILE", help="склеить всё в один файл")
    run.add_argument("--concurrency", type=int, default=2, help="сколько сцен генерить параллельно")
    run.add_argument("--no-resume", dest="resume", action="store_false",
                     help="перегенерировать даже готовые сцены")
    run.add_argument("--poll-interval", type=float, default=higgsfield.POLL_INTERVAL)
    run.add_argument("--timeout", type=float, default=higgsfield.POLL_TIMEOUT)
    run.add_argument("--base-url", default=higgsfield.BASE_URL)
    run.add_argument("--dry-run", action="store_true", help="показать запросы и выйти")
    run.add_argument("-q", "--quiet", action="store_true")

    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING if getattr(args, "quiet", False) else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stderr,
    )

    try:
        if args.command == "init":
            text = Path(args.from_text).read_text(encoding="utf-8")
            scenario = scenario_from_text(text, name=Path(args.from_text).stem)
            Path(args.output).write_text(
                json.dumps(scenario, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"Сцен: {len(scenario['shots'])}. Заготовка: {args.output}")
            print("Проверьте промпты и defaults, затем: "
                  f"python3 scenario.py run {args.output} --out-dir out")
            return 0

        scenario = load_scenario(args.scenario)

        if args.dry_run:
            return _dry_run(scenario, args.base_url)

        outcome = asyncio.run(run_scenario(
            scenario,
            Path(args.out_dir),
            concurrency=args.concurrency,
            resume=args.resume,
            interval=args.poll_interval,
            timeout=args.timeout,
            base_url=args.base_url,
        ))

        for path in outcome["files"]:
            print(path)

        if outcome["missing"]:
            print(f"Не сгенерировались сцены: {', '.join(outcome['missing'])}. "
                  f"Повторный запуск доделает только их.", file=sys.stderr)
            return 1

        if args.concat:
            concat(outcome["files"], Path(args.concat))
            print(f"Склеено: {args.concat}")

        return 0

    except (ScenarioError, higgsfield.HiggsfieldError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
