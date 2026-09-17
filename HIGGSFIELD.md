# Подключение Higgsfield (генерация видео)

`higgsfield.py` — самостоятельный асинхронный клиент Higgsfield API: ставит
задачу на генерацию видео, ждёт её, отдаёт ссылку и при необходимости скачивает
файл. Файл ни от чего в этом репозитории не зависит, к `bot.py` не подключён —
его можно положить в любой проект.

Единственная зависимость — `aiohttp` (он уже нужен `bot.py`).

## Ключи

Ключи выпускаются в консоли Higgsfield и берутся из окружения:

```bash
export HF_KEY="<key_id>:<key_secret>"
# или
export HF_API_KEY="<key_id>"
export HF_API_SECRET="<key_secret>"
```

Ключи держим только в окружении / `.env` (он уже в `.gitignore`), в код и в
логи они не попадают.

## Командная строка

```bash
# текст → видео, с сохранением файла
python3 higgsfield.py "кот в скафандре плывёт над Москвой" \
    --duration 5 --resolution 720p --aspect-ratio 16:9 --output cat.mp4

# картинка → видео (локальный файл заливается в Higgsfield автоматически)
python3 higgsfield.py "оживи фото" --image frame.jpg --output out.mp4

# другая модель и её собственные параметры
python3 higgsfield.py "промпт" -m bytedance/seedance-2.5/text-to-video \
    --param seed=42 --param generate_audio=true

# посмотреть, что уйдёт в API, ничего не отправляя (ключи не нужны)
python3 higgsfield.py "промпт" --duration 5 --dry-run

# работа с уже поставленной задачей
python3 higgsfield.py --status  <request_id>
python3 higgsfield.py --wait    <request_id> --output out.mp4
python3 higgsfield.py --cancel  <request_id>
```

Скрипт печатает ссылки на результат в stdout, логи идут в stderr, код возврата
`0` — успех.

## Из кода

```python
import asyncio
import higgsfield

async def main():
    async with higgsfield.HiggsfieldClient() as hf:
        result = await hf.generate_video(
            "кот в скафандре плывёт над Москвой",
            duration=5,
            resolution="720p",
            aspect_ratio="16:9",
            on_status=lambda s: print("статус:", s),
        )
        url = higgsfield.extract_video_urls(result)[0]
        await hf.download(url, "cat.mp4")

asyncio.run(main())
```

Если ждать в процессе не нужно — отдать задачу на вебхук:

```python
job = await hf.submit(
    "bytedance/seedance-2.5/text-to-video",
    {"prompt": "...", "duration": 5},
    webhook_url="https://example.com/hf-hook",
)
# job.request_id сохраняем у себя; результат придёт POST-ом на вебхук
```

Полезные методы `HiggsfieldClient`: `submit`, `status`, `poll`, `result`,
`cancel`, `upload_file`, `upload`, `download`, `generate_video`.

Ошибки: `CredentialsMissedError` (нет ключей), `HiggsfieldAPIError` (HTTP-ошибка,
есть `.status`), `HiggsfieldJobError` (задача завершилась как `failed`/`nsfw`/
`canceled`), `HiggsfieldTimeoutError` (не дождались; `.job.request_id` сохраняется,
опрос можно продолжить позже). Все наследуются от `HiggsfieldError`.

Временные ошибки (408, 429, 5xx, обрывы сети) повторяются автоматически с
экспоненциальной паузой и учётом заголовка `Retry-After`.

## Сценарий из нескольких сцен

Модель делает короткий клип (обычно 4–10 секунд), поэтому ролик собирается из
сцен: `scenario.py` генерирует каждую отдельно и склеивает через ffmpeg.

```bash
# 1. из текстового описания — заготовка сценария (сцены разделены пустой строкой)
python3 scenario.py init --from-text описание.txt -o scenario.json

# 2. посмотреть, что уйдёт в API, и хронометраж — без ключей и без трат
python3 scenario.py run scenario.json --dry-run

# 3. генерация и склейка
python3 scenario.py run scenario.json --out-dir out --concat out/final.mp4
```

Формат сценария — см. `scenario.example.json`: блок `defaults` задаёт модель и
параметры для всех сцен, `style` и `sound` дописываются к каждому промпту, любая
сцена может всё это переопределить и добавить своё в `params`.

### Непрерывность между сценами

Чтобы на стыке не было визуального скачка, сцена может начинаться с последнего
кадра предыдущей:

```json
{ "id": "r2-01", "prompt": "Игроки выходят в коридор", "continue_from": "r1-06" }
```

Такая сцена ждёт свою предыдущую, `scenario.py` достаёт из готового клипа
последний кадр (нужен ffmpeg) и генерирует продолжение через image-to-video
(`defaults.image_model`). Внешность персонажей дополнительно держит
`defaults.preamble` — общий кусок промпта, который подставляется в начало каждой
сцены. Поле `part` группирует сцены по роликам: `--concat-parts` склеит каждый
ролик отдельно в `<out-dir>/<part>.mp4`.

Готовый пример на 24 сцены и три ролика — `scenarios/alexander-birthday.json`,
разбор — в `scenarios/README.md`.

### Звук

Звук включён по умолчанию (`generate_audio: true`), но модель делает его по
описанию — поэтому звук стоит проговаривать словами, в поле `sound`:

```json
{
  "defaults": { "generate_audio": true, "sound": "ровный низкий гул города" },
  "shots": [
    { "prompt": "Капли дождя на стекле, за ними неоновая вывеска",
      "sound": "капли дождя по стеклу, приглушённый шум улицы" }
  ]
}
```

`sound` уходит в промпт как «`Звук: ...`». Выключить звук целиком —
`"generate_audio": false` в `defaults`, для одной сцены — то же поле в сцене.

Перед склейкой сцены проверяются через `ffprobe`: если у какой-то нет звуковой
дорожки, в лог идёт предупреждение с её именем, а склейка автоматически
переходит на перекодирование (`-c copy` разные дорожки не переживает). Готовый
файл тоже проверяется — если звука в нём не оказалось, скрипт об этом скажет.

Учтите: `generate_audio` поддерживают не все модели. Если звука нет во всех
сценах сразу — скорее всего, дело в модели, посмотрите её параметры в консоли.
Отдельную музыкальную дорожку поверх готового ролика проще положить самим:
`ffmpeg -i final.mp4 -i music.mp3 -filter_complex amix=inputs=2:duration=first -c:v copy final_music.mp4`.

Как это ведёт себя на длинной дистанции:

* ход работы пишется в `out/manifest.json` (статус, `request_id`, ссылка, файл);
* повторный запуск доделывает только незавершённое, готовые сцены не перегенерируются
  (`--no-resume` — перегенерировать всё);
* упавшая сцена не останавливает остальные: причина попадает в манифест, код
  возврата `1`, повторный запуск пробует её снова;
* `--concurrency N` — сколько сцен генерить параллельно (по умолчанию 2);
* если ffmpeg не установлен, клипы всё равно скачиваются, а команда склейки
  печатается — останется выполнить её там, где ffmpeg есть.

## Настройки (переменные окружения, необязательные)

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `HIGGSFIELD_BASE_URL` | `https://platform.higgsfield.ai` | адрес API |
| `HIGGSFIELD_TEXT_TO_VIDEO_MODEL` | `bytedance/seedance-2.5/text-to-video` | модель по умолчанию |
| `HIGGSFIELD_IMAGE_TO_VIDEO_MODEL` | `bytedance/seedance-2.5/image-to-video` | модель при `--image` |
| `HIGGSFIELD_TIMEOUT` | `90` | таймаут одного HTTP-запроса, секунды |
| `HIGGSFIELD_POLL_INTERVAL` | `5` | пауза между опросами статуса, секунды |
| `HIGGSFIELD_POLL_TIMEOUT` | `900` | сколько всего ждать готовности, секунды |
| `HIGGSFIELD_MAX_RETRIES` | `3` | повторов при временных ошибках |

## Проверка

```bash
pip install aiohttp
python3 test_higgsfield.py
python3 test_scenario.py
```

Тест поднимает локальный макет API и прогоняет весь цикл: отправку, повтор
после 500, опрос статусов, разбор ответа, скачивание файла, загрузку кадра,
вебхук, отмену, таймаут и `--dry-run`. `test_scenario.py` на том же макете
проверяет прогон сценария: разбор описания, манифест, resume, упавшую сцену,
склейку. Сеть наружу и ключи им не нужны.

Живую связь с API удобно проверять так:

```bash
python3 higgsfield.py "test clip, 4 seconds" --duration 4 --resolution 480p --json
```

## Как устроен API

1. `POST {base}/{модель}` с JSON-параметрами модели → `{request_id, status_url, cancel_url}`.
   Если добавить `?hf_webhook=<url>`, результат придёт на вебхук.
2. `GET {status_url}` → `{"status": "queued|in_progress|completed|failed|nsfw|canceled", ...}`;
   после `completed` в том же ответе лежит результат со ссылками на файлы.
3. `POST {cancel_url}` — отмена, пока задача в очереди.
4. Загрузка своих файлов: `POST /files/generate-upload-url` → `{public_url, upload_url}`,
   затем `PUT` байтов на `upload_url` (без наших заголовков авторизации).

Авторизация — заголовок `Authorization: Key <key_id>:<key_secret>`.

Набор параметров у каждой модели свой (`duration`, `resolution`, `aspect_ratio`,
`output_format`, `generate_audio` и т.д.) — точный список смотрите на странице
модели в консоли Higgsfield и передавайте через `--param key=value`. Названия
полей в ответе тоже отличаются, поэтому `extract_video_urls()` собирает ссылки
из ответа независимо от структуры.
