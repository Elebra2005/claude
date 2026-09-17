"""Проверка scenario.py на том же локальном макете API. Сеть наружу не нужна.

    python3 test_scenario.py
"""

import asyncio
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("HF_KEY", "test-key-id:test-key-secret")

import higgsfield  # noqa: E402
import scenario  # noqa: E402
from test_higgsfield import MockAPI, check, start_server  # noqa: E402

TEXT = """Сцена 1. Панорама ночного города сверху, огни трасс.

2) Крупный план: капли дождя на стекле, за ними неоновая вывеска.

Финальный кадр — логотип на чёрном фоне.
"""


def write_scenario(tmp: Path, shots, defaults=None) -> Path:
    path = tmp / "scenario.json"
    path.write_text(json.dumps({
        "name": "test",
        "defaults": defaults or {"duration": 5, "resolution": "720p"},
        "shots": shots,
    }, ensure_ascii=False), encoding="utf-8")
    return path


def test_scenario_from_text():
    data = scenario.scenario_from_text(TEXT, name="promo")
    check(len(data["shots"]) == 3, f"сцен: {len(data['shots'])}")
    check(data["shots"][0]["prompt"].startswith("Панорама ночного города"),
          f"нумерация не убрана: {data['shots'][0]['prompt']}")
    check(data["shots"][1]["prompt"].startswith("Крупный план"),
          f"нумерация не убрана: {data['shots'][1]['prompt']}")
    print("ok  init: текст с пустыми строками разбирается на сцены, нумерация снимается")


def test_load_scenario_defaults():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        path = write_scenario(
            tmp,
            shots=["первая сцена", {"prompt": "вторая", "duration": 8, "params": {"seed": 1}}],
            defaults={"duration": 5, "resolution": "720p", "style": "кинематографично",
                      "params": {"cfg": 7}},
        )
        data = scenario.load_scenario(path)

        first, second = data["shots"]
        check(first["prompt"] == "первая сцена. кинематографично", f"стиль: {first['prompt']}")
        check(first["duration"] == 5 and second["duration"] == 8, "длительность из defaults/сцены")
        check(first["params"] == {"cfg": 7} and second["params"] == {"cfg": 7, "seed": 1},
              f"params: {first['params']} / {second['params']}")
        check(first["id"] != second["id"], "id сцен должны различаться")
    print("ok  defaults, стиль и params сливаются со сценой")


def test_audio():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        # Звук включён по умолчанию, описание звука дописывается к промпту.
        path = write_scenario(
            tmp,
            shots=["город сверху", {"prompt": "дождь на стекле", "sound": "капли по стеклу"}],
            defaults={"sound": "ровный гул города"},
        )
        first, second = scenario.load_scenario(path)["shots"]

        check(first["generate_audio"] is True, "звук должен быть включён по умолчанию")
        check(first["prompt"].endswith("Звук: ровный гул города"), f"промпт: {first['prompt']}")
        check(second["prompt"].endswith("Звук: капли по стеклу"), f"промпт: {second['prompt']}")

        # Звук можно выключить и целиком, и для отдельной сцены.
        path = write_scenario(
            tmp,
            shots=["без звука", {"prompt": "со звуком", "generate_audio": True}],
            defaults={"generate_audio": False},
        )
        quiet, loud = scenario.load_scenario(path)["shots"]
        check(quiet["generate_audio"] is False, "явное выключение звука не сработало")
        check(loud["generate_audio"] is True, "сцена должна переопределять defaults")

        # Заготовка из текста тоже со звуком и с местом под его описание.
        draft = scenario.scenario_from_text(TEXT)
        check(draft["defaults"]["generate_audio"] is True, "в заготовке звук выключен")
        check("sound" in draft["defaults"], "в заготовке нет поля sound")
    print("ok  звук: включён по умолчанию, описание звука идёт в промпт, выключается явно")


def test_audio_check():
    with tempfile.TemporaryDirectory() as tmp:
        clip = Path(tmp) / "clip.mp4"
        clip.write_bytes(b"clip")

        if shutil.which("ffprobe") is None:
            check(scenario.has_audio(clip) is None, "без ffprobe ожидается None")
            check(scenario.check_audio([clip]) == [], "без ffprobe жаловаться не на что")
            print("--  проверка дорожек: ffprobe не установлен, проверен только запасной путь")
        else:
            check(scenario.has_audio(clip) is False, "в мусорном файле не должно быть дорожки")
            check(scenario.check_audio([clip]) == [str(clip)], "сцена без звука не отмечена")
            print("ok  проверка дорожек: сцены без звука находятся через ffprobe")


def test_preamble_and_chain_parsing():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        path = write_scenario(
            tmp,
            shots=[
                {"id": "a", "prompt": "первая сцена"},
                {"id": "b", "prompt": "вторая сцена", "continue_from": "a"},
            ],
            defaults={"preamble": "Одни и те же футболисты в красно-белой форме",
                      "style": "кинематографично"},
        )
        first, second = scenario.load_scenario(path)["shots"]

        check(first["prompt"].startswith("Одни и те же футболисты"), f"промпт: {first['prompt']}")
        check(first["prompt"].endswith("кинематографично"), f"промпт: {first['prompt']}")
        check(second["continue_from"] == "a", "сцепка не разобралась")
        check(second["image_model"] == higgsfield.DEFAULT_IMAGE_TO_VIDEO,
              f"модель для сцепки: {second['image_model']}")

        # Ссылка на несуществующую или на саму себя — ошибка до обращения к API.
        for shots, hint in (
            ([{"id": "a", "prompt": "x", "continue_from": "нет-такой"}], "неизвестный id"),
            ([{"id": "a", "prompt": "x", "continue_from": "a"}], "ссылка на себя"),
            ([{"id": "a", "prompt": "x", "continue_from": "b"}, {"id": "b", "prompt": "y"}],
             "ссылка на сцену ниже"),
        ):
            bad = write_scenario(tmp, shots=shots)
            try:
                scenario.load_scenario(bad)
            except scenario.ScenarioError:
                pass
            else:
                raise AssertionError(f"ожидалась ScenarioError: {hint}")
    print("ok  паспорт персонажей идёт в начало промпта, сцепка сцен проверяется")


async def test_chain_run(base_url: str, api: MockAPI):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        out = tmp / "out"
        path = write_scenario(tmp, shots=[
            {"id": "s1", "prompt": "раздевалка"},
            {"id": "s2", "prompt": "коридор", "continue_from": "s1"},
            {"id": "s3", "prompt": "тоннель", "continue_from": "s2"},
        ])
        data = scenario.load_scenario(path)

        before = len(api.submissions)
        outcome = await scenario.run_scenario(
            data, out, concurrency=3, interval=0.01, base_url=base_url
        )

        check(not outcome["missing"], f"пропущено: {outcome['missing']}")
        prompts = [body.get("prompt") for _, body, _ in api.submissions[before:]]
        check(prompts == ["раздевалка", "коридор", "тоннель"],
              f"сцепленные сцены должны идти по порядку: {prompts}")

        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        if shutil.which("ffmpeg") is None:
            # Без ffmpeg кадр не достать — сцены всё равно генерятся, но без сцепки.
            check("start_frame" not in manifest["shots"]["s2"], "без ffmpeg кадра быть не должно")
            print("--  сцепка: ffmpeg не установлен, проверен порядок и запасной путь")
        else:
            check(Path(manifest["shots"]["s2"]["start_frame"]).exists(), "стартовый кадр не создан")
            print("ok  сцепка: последний кадр сцены становится первым кадром следующей")


def test_load_scenario_errors():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        bad = tmp / "bad.json"

        bad.write_text('{"shots": []}', encoding="utf-8")
        for payload, hint in (
            ('{"shots": []}', "пустой список"),
            ('{"shots": [{"duration": 5}]}', "сцена без prompt и image"),
            ('{"shots": [{"id": "a", "prompt": "x"}, {"id": "a", "prompt": "y"}]}', "дубль id"),
        ):
            bad.write_text(payload, encoding="utf-8")
            try:
                scenario.load_scenario(bad)
            except scenario.ScenarioError:
                pass
            else:
                raise AssertionError(f"ожидалась ScenarioError: {hint}")
    print("ok  битый сценарий отлавливается до обращения к API")


async def test_run(base_url: str, api: MockAPI):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        out = tmp / "out"
        path = write_scenario(tmp, shots=["город сверху", "капли на стекле", "логотип"])
        data = scenario.load_scenario(path)

        before = len(api.submissions)
        outcome = await scenario.run_scenario(
            data, out, concurrency=2, interval=0.01, base_url=base_url
        )

        check(len(outcome["files"]) == 3 and not outcome["missing"],
              f"файлы: {outcome['files']}, пропущено: {outcome['missing']}")
        check(all(p.exists() and p.stat().st_size > 0 for p in outcome["files"]),
              "клипы не скачались")
        check(len(api.submissions) - before == 3, "должно уйти ровно 3 запроса")

        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        check(all(s["status"] == "completed" for s in manifest["shots"].values()),
              f"манифест: {manifest}")
        check(all(s.get("request_id") for s in manifest["shots"].values()),
              "в манифесте нет request_id")

        # Повторный запуск не должен ничего перегенерировать.
        before = len(api.submissions)
        again = await scenario.run_scenario(
            data, out, concurrency=2, interval=0.01, base_url=base_url
        )
        check(len(api.submissions) == before, "resume: сцены сгенерились заново")
        check(len(again["files"]) == 3, "resume: файлы потерялись")

        print("ok  прогон сценария: 3 сцены, манифест, скачивание, resume без лишних запросов")


async def test_partial_failure(base_url: str, api: MockAPI):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        out = tmp / "out"
        path = write_scenario(tmp, shots=[
            {"id": "ok-1", "prompt": "нормальная сцена"},
            {"id": "bad", "prompt": "fail эта сцена падает"},
            {"id": "ok-2", "prompt": "ещё одна нормальная"},
        ])
        data = scenario.load_scenario(path)

        outcome = await scenario.run_scenario(
            data, out, concurrency=3, interval=0.01, base_url=base_url
        )

        check(outcome["missing"] == ["bad"], f"пропущено: {outcome['missing']}")
        check(len(outcome["files"]) == 2, f"остальные сцены должны сгенериться: {outcome['files']}")

        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        check(manifest["shots"]["bad"]["status"] == "failed", "упавшая сцена не помечена")
        check("мок" in manifest["shots"]["bad"]["error"], "в манифесте нет причины")
    print("ok  упавшая сцена не останавливает остальные и попадает в манифест")


def test_concat_without_ffmpeg():
    """Здесь проверяем только поведение без ffmpeg: на подсунутых байтах
    настоящий ffmpeg всё равно ничего не склеит, поэтому с ним тест пропускаем."""
    if shutil.which("ffmpeg") is not None:
        print("--  склейка: ffmpeg установлен, проверка пропущена")
        return

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        files = []
        for name in ("01.mp4", "02.mp4"):
            clip = tmp / name
            clip.write_bytes(b"clip")
            files.append(clip)

        target = tmp / "final.mp4"
        buffer = io.StringIO()
        with contextlib.redirect_stderr(buffer):
            result = scenario.concat(files, target)

        check(result is None, "без ffmpeg склейка не должна возвращать файл")
        check("ffmpeg -y -f concat" in buffer.getvalue(), "должна печататься команда ffmpeg")
        listed = (tmp / "concat.txt").read_text(encoding="utf-8")
        check(listed.count("file '") == 2, f"список сцен: {listed!r}")
        print("ok  без ffmpeg печатается готовая команда склейки, список сцен сохранён")


def test_dry_run():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        path = write_scenario(tmp, shots=["город сверху", {"prompt": "финал", "duration": 3}])

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = scenario.main(["run", str(path), "--dry-run", "--quiet"])

        output = buffer.getvalue()
        check(code == 0, f"код возврата: {code}")
        check(output.count("POST ") == 2, f"ожидались 2 запроса:\n{output}")
        check("всего сцен: 2" in output and "~8 с" in output, f"итог не посчитан:\n{output}")
    print("ok  run --dry-run показывает все запросы и общий хронометраж")


async def main():
    test_scenario_from_text()
    test_load_scenario_defaults()
    test_load_scenario_errors()
    test_preamble_and_chain_parsing()
    test_audio()
    test_audio_check()
    test_dry_run()

    api = MockAPI()
    api.flaky_left = 0  # повторы проверяются в test_higgsfield.py
    runner, base_url = await start_server(api)
    try:
        await test_run(base_url, api)
        await test_partial_failure(base_url, api)
        await test_chain_run(base_url, api)
    finally:
        await runner.cleanup()

    test_concat_without_ffmpeg()
    print("\nвсе проверки пройдены")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except AssertionError as exc:
        print(f"ПРОВАЛ: {exc}", file=sys.stderr)
        sys.exit(1)
