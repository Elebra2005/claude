"""Клиент Higgsfield API для генерации видео.

Зависит только от aiohttp (он уже используется в bot.py), поэтому файл можно
просто положить рядом с проектом и импортировать.

Модель работы API асинхронная: запрос ставится в очередь, в ответ приходит
request_id и ссылки на статус/отмену, дальше либо опрос статуса, либо вебхук.

    import asyncio
    import higgsfield

    async def main():
        async with higgsfield.HiggsfieldClient() as hf:
            result = await hf.generate_video(
                "кот в скафандре плывёт над Москвой",
                duration=5,
                resolution="720p",
                aspect_ratio="16:9",
            )
            print(higgsfield.extract_video_urls(result))

    asyncio.run(main())

Ключи берутся из окружения: HF_KEY="<key_id>:<key_secret>" либо пара
HF_API_KEY/HF_API_SECRET. Получить их можно в консоли Higgsfield.

Запуск из командной строки:

    python3 higgsfield.py "кот в скафандре" --duration 5 --output cat.mp4
"""

import argparse
import asyncio
import json
import logging
import mimetypes
import os
import random
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Optional
from urllib.parse import urlencode, urlparse

import aiohttp

logger = logging.getLogger(__name__)

BASE_URL = os.getenv("HIGGSFIELD_BASE_URL", "https://platform.higgsfield.ai").rstrip("/")

# Модели по умолчанию. Список доступных моделей и их параметры — в консоли
# Higgsfield; здесь только разумный старт, всё переопределяется через --model.
DEFAULT_TEXT_TO_VIDEO = os.getenv(
    "HIGGSFIELD_TEXT_TO_VIDEO_MODEL", "bytedance/seedance-2.5/text-to-video"
)
DEFAULT_IMAGE_TO_VIDEO = os.getenv(
    "HIGGSFIELD_IMAGE_TO_VIDEO_MODEL", "bytedance/seedance-2.5/image-to-video"
)

REQUEST_TIMEOUT = float(os.getenv("HIGGSFIELD_TIMEOUT", "90"))
POLL_INTERVAL = float(os.getenv("HIGGSFIELD_POLL_INTERVAL", "5"))
POLL_TIMEOUT = float(os.getenv("HIGGSFIELD_POLL_TIMEOUT", "900"))
MAX_RETRIES = int(os.getenv("HIGGSFIELD_MAX_RETRIES", "3"))

USER_AGENT = "higgsfield-aiohttp/1.0"

# Статусы задачи
QUEUED = "queued"
IN_PROGRESS = "in_progress"
COMPLETED = "completed"
FAILED = "failed"
NSFW = "nsfw"
CANCELED = "canceled"

DONE_STATUSES = frozenset({COMPLETED, FAILED, NSFW, CANCELED})
RETRYABLE_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})

VIDEO_EXTENSIONS = (".mp4", ".mov", ".webm", ".m4v", ".mkv")
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif")


class HiggsfieldError(Exception):
    """Базовая ошибка клиента."""


class CredentialsMissedError(HiggsfieldError):
    """Не заданы ключи доступа."""


class HiggsfieldAPIError(HiggsfieldError):
    """Ошибка HTTP от API."""

    def __init__(self, status: int, message: str):
        super().__init__(f"Higgsfield API error {status}: {message}")
        self.status = status
        self.message = message


class HiggsfieldJobError(HiggsfieldError):
    """Задача завершилась не успехом (failed / nsfw / canceled)."""

    def __init__(self, status: str, payload: dict):
        detail = _error_message(payload) or status
        super().__init__(f"Задача завершилась со статусом {status}: {detail}")
        self.status = status
        self.payload = payload


class HiggsfieldTimeoutError(HiggsfieldError):
    """Задача не завершилась за отведённое время. Опрос можно продолжить по request_id."""

    def __init__(self, job: "Job", waited: float):
        super().__init__(
            f"Задача {job.request_id} не завершилась за {waited:.0f} с; "
            f"статус можно дозапросить: --status {job.request_id}"
        )
        self.job = job
        self.waited = waited


@dataclass
class Job:
    """Поставленная в очередь задача."""

    request_id: str
    status_url: str
    cancel_url: str
    raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_response(cls, data: dict, base_url: str = BASE_URL) -> "Job":
        request_id = data.get("request_id") or data.get("id")
        if not request_id:
            raise HiggsfieldError(f"В ответе API нет request_id: {json.dumps(data)[:500]}")

        default = f"{base_url}/requests/{request_id}"
        return cls(
            request_id=str(request_id),
            status_url=data.get("status_url") or f"{default}/status",
            cancel_url=data.get("cancel_url") or f"{default}/cancel",
            raw=data,
        )

    @classmethod
    def from_request_id(cls, request_id: str, base_url: str = BASE_URL) -> "Job":
        default = f"{base_url.rstrip('/')}/requests/{request_id}"
        return cls(
            request_id=request_id,
            status_url=f"{default}/status",
            cancel_url=f"{default}/cancel",
        )


def get_credential_key() -> str:
    """Собирает ключ вида ``key_id:key_secret`` из окружения."""
    key = os.getenv("HF_KEY") or os.getenv("HIGGSFIELD_KEY")
    if key:
        return key

    api_key = os.getenv("HF_API_KEY") or os.getenv("HIGGSFIELD_API_KEY")
    api_secret = os.getenv("HF_API_SECRET") or os.getenv("HIGGSFIELD_API_SECRET")
    if api_key and api_secret:
        return f"{api_key}:{api_secret}"

    raise CredentialsMissedError(
        "Нет ключей Higgsfield. Задайте HF_KEY='<key_id>:<key_secret>' "
        "или пару HF_API_KEY и HF_API_SECRET."
    )


def _error_message(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in ("detail", "details", "message", "error", "reason"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
        if isinstance(value, (dict, list)) and value:
            return json.dumps(value, ensure_ascii=False)[:500]
    return ""


def _looks_like(url: str, extensions: tuple) -> bool:
    path = urlparse(url).path.lower()
    return path.endswith(extensions)


def _walk_urls(node: Any, acc: list):
    """Собирает все строки-ссылки из произвольного JSON."""
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, str) and value.startswith(("http://", "https://")):
                if key in ("url", "video_url", "image_url", "signed_url", "download_url", "src"):
                    acc.append(value)
            else:
                _walk_urls(value, acc)
    elif isinstance(node, list):
        for item in node:
            _walk_urls(item, acc)


def extract_urls(result: dict) -> list:
    """Все файловые ссылки из ответа, без дублей и в порядке появления."""
    acc: list = []
    _walk_urls(result, acc)

    seen = set()
    unique = []
    for url in acc:
        if url not in seen:
            seen.add(url)
            unique.append(url)
    return unique


def extract_video_urls(result: dict) -> list:
    """Ссылки на видео. Если по расширению ничего не опознали — отдаём всё,
    что не похоже на картинку (набор полей отличается от модели к модели)."""
    urls = extract_urls(result)
    videos = [u for u in urls if _looks_like(u, VIDEO_EXTENSIONS)]
    if videos:
        return videos
    return [u for u in urls if not _looks_like(u, IMAGE_EXTENSIONS)]


def _suggest_filename(url: str, default: str = "higgsfield-video.mp4") -> str:
    name = Path(urlparse(url).path).name
    return name or default


class HiggsfieldClient:
    """Асинхронный клиент Higgsfield API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = BASE_URL,
        timeout: float = REQUEST_TIMEOUT,
        max_retries: int = MAX_RETRIES,
        session: Optional[aiohttp.ClientSession] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self._api_key = api_key
        self._session = session
        self._own_session = session is None

    async def __aenter__(self) -> "HiggsfieldClient":
        return self

    async def __aexit__(self, *exc_info):
        await self.close()

    async def close(self):
        if self._own_session and self._session is not None and not self._session.closed:
            await self._session.close()
        if self._own_session:
            self._session = None

    @property
    def api_key(self) -> str:
        if self._api_key is None:
            self._api_key = get_credential_key()
        return self._api_key

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            self._own_session = True
        return self._session

    def _headers(self) -> dict:
        return {
            "Authorization": f"Key {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }

    def _absolute(self, url: str) -> str:
        if url.startswith(("http://", "https://")):
            return url
        return f"{self.base_url}/{url.lstrip('/')}"

    @staticmethod
    def _retry_delay(attempt: int, retry_after: Optional[str]) -> float:
        if retry_after:
            try:
                return min(float(retry_after), 60.0)
            except ValueError:
                pass
        # 1, 2, 4... секунды плюс джиттер, чтобы не биться синхронно
        return min(2 ** (attempt - 1), 30.0) + random.uniform(0, 0.5)

    async def _request(self, method: str, url: str, payload: Optional[dict] = None) -> dict:
        url = self._absolute(url)
        attempt = 0

        while True:
            attempt += 1
            try:
                async with self._get_session().request(
                    method,
                    url,
                    headers=self._headers(),
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as resp:
                    text = await resp.text()

                    if resp.status in RETRYABLE_STATUS_CODES and attempt <= self.max_retries:
                        delay = self._retry_delay(attempt, resp.headers.get("Retry-After"))
                        logger.warning(
                            "Higgsfield %s %s -> %s, повтор через %.1f с (попытка %s)",
                            method, url, resp.status, delay, attempt,
                        )
                        await asyncio.sleep(delay)
                        continue

                    if resp.status >= 400:
                        message = _error_message(_safe_json(text)) or text[:500]
                        raise HiggsfieldAPIError(resp.status, message)

                    if not text:
                        return {}
                    parsed = _safe_json(text)
                    return parsed if isinstance(parsed, dict) else {"result": parsed}

            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                if attempt > self.max_retries:
                    raise HiggsfieldError(f"Сеть недоступна: {exc}") from exc
                delay = self._retry_delay(attempt, None)
                logger.warning(
                    "Higgsfield %s %s: %s, повтор через %.1f с (попытка %s)",
                    method, url, exc, delay, attempt,
                )
                await asyncio.sleep(delay)

    async def submit(
        self,
        application: str,
        arguments: dict,
        webhook_url: Optional[str] = None,
    ) -> Job:
        """Ставит задачу в очередь. application — путь модели,
        например ``bytedance/seedance-2.5/text-to-video``."""
        path = application.strip("/")
        if webhook_url:
            path += "?" + urlencode({"hf_webhook": webhook_url})

        data = await self._request("POST", path, arguments)
        job = Job.from_response(data, self.base_url)
        logger.info("Higgsfield: задача %s поставлена в очередь", job.request_id)
        return job

    async def status(self, job: Job) -> dict:
        """Текущее состояние задачи (там же лежит и результат после completed)."""
        return await self._request("GET", job.status_url)

    async def cancel(self, job: Job) -> dict:
        """Отменяет задачу. Уже начатую генерацию отменить нельзя."""
        return await self._request("POST", job.cancel_url)

    async def poll(
        self,
        job: Job,
        interval: float = POLL_INTERVAL,
        timeout: float = POLL_TIMEOUT,
    ) -> AsyncIterator[dict]:
        """Опрашивает статус, пока задача не завершится."""
        started = time.monotonic()

        while True:
            payload = await self.status(job)
            yield payload

            if str(payload.get("status", "")).lower() in DONE_STATUSES:
                return

            waited = time.monotonic() - started
            if waited >= timeout:
                raise HiggsfieldTimeoutError(job, waited)

            await asyncio.sleep(interval)

    async def result(
        self,
        job: Job,
        interval: float = POLL_INTERVAL,
        timeout: float = POLL_TIMEOUT,
        on_status: Optional[Callable[[str], Any]] = None,
    ) -> dict:
        """Ждёт завершения задачи и возвращает финальный ответ."""
        payload: dict = {}
        last_status = None

        async for payload in self.poll(job, interval=interval, timeout=timeout):
            status = str(payload.get("status", "")).lower()
            if status != last_status:
                last_status = status
                logger.info("Higgsfield: задача %s — %s", job.request_id, status or "?")
                if on_status is not None:
                    maybe = on_status(status)
                    if asyncio.iscoroutine(maybe):
                        await maybe

        status = str(payload.get("status", "")).lower()
        if status != COMPLETED:
            raise HiggsfieldJobError(status or "unknown", payload)
        return payload

    async def generate_video(
        self,
        prompt: Optional[str] = None,
        *,
        model: Optional[str] = None,
        image: Optional[str] = None,
        duration: Optional[float] = None,
        resolution: Optional[str] = None,
        aspect_ratio: Optional[str] = None,
        output_format: Optional[str] = None,
        generate_audio: Optional[bool] = None,
        params: Optional[dict] = None,
        webhook_url: Optional[str] = None,
        interval: float = POLL_INTERVAL,
        timeout: float = POLL_TIMEOUT,
        on_status: Optional[Callable[[str], Any]] = None,
    ) -> dict:
        """Генерация видео «одним вызовом»: отправить, дождаться, вернуть результат.

        image — локальный файл или ссылка; локальный сначала заливается через
        /files/generate-upload-url. Если модель не указана, берётся text-to-video,
        а при наличии image — image-to-video.
        """
        image_url = None
        if image:
            image_url = image if image.startswith(("http://", "https://")) else await self.upload_file(image)

        application = model or (DEFAULT_IMAGE_TO_VIDEO if image_url else DEFAULT_TEXT_TO_VIDEO)

        arguments: dict = {}
        if prompt is not None:
            arguments["prompt"] = prompt
        if image_url is not None:
            arguments["image_url"] = image_url
        if duration is not None:
            arguments["duration"] = duration
        if resolution is not None:
            arguments["resolution"] = resolution
        if aspect_ratio is not None:
            arguments["aspect_ratio"] = aspect_ratio
        if output_format is not None:
            arguments["output_format"] = output_format
        if generate_audio is not None:
            arguments["generate_audio"] = generate_audio
        if params:
            arguments.update(params)

        if not arguments:
            raise HiggsfieldError("Пустой запрос: нужен хотя бы prompt или image.")

        job = await self.submit(application, arguments, webhook_url=webhook_url)
        return await self.result(job, interval=interval, timeout=timeout, on_status=on_status)

    async def upload_file(self, path) -> str:
        """Заливает локальный файл и возвращает публичную ссылку на него."""
        path = Path(path)
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        data = path.read_bytes()
        return await self.upload(data, content_type)

    async def upload(self, data: bytes, content_type: str) -> str:
        """Заливает байты и возвращает публичную ссылку."""
        if isinstance(data, str):
            data = data.encode("utf-8")

        response = await self._request(
            "POST", "/files/generate-upload-url", {"content_type": content_type}
        )
        public_url = response.get("public_url")
        upload_url = response.get("upload_url")
        if not public_url or not upload_url:
            raise HiggsfieldError(f"Неожиданный ответ на generate-upload-url: {response}")

        # Ссылка предподписанная — свои заголовки авторизации сюда не шлём.
        async with self._get_session().put(
            upload_url,
            data=data,
            headers={"Content-Type": content_type},
            timeout=aiohttp.ClientTimeout(total=max(self.timeout, 300)),
        ) as resp:
            if resp.status >= 400:
                raise HiggsfieldAPIError(resp.status, (await resp.text())[:500])

        logger.info("Higgsfield: файл загружен, %s", public_url)
        return public_url

    async def download(self, url: str, dest) -> Path:
        """Скачивает готовый файл на диск."""
        dest = Path(dest)
        if dest.is_dir():
            dest = dest / _suggest_filename(url)
        dest.parent.mkdir(parents=True, exist_ok=True)

        async with self._get_session().get(
            url, timeout=aiohttp.ClientTimeout(total=None, sock_read=120)
        ) as resp:
            if resp.status >= 400:
                raise HiggsfieldAPIError(resp.status, (await resp.text())[:500])
            with dest.open("wb") as fh:
                async for chunk in resp.content.iter_chunked(64 * 1024):
                    fh.write(chunk)

        logger.info("Higgsfield: сохранено в %s", dest)
        return dest


def _safe_json(text: str) -> Any:
    try:
        return json.loads(text)
    except ValueError:
        return {"raw": text}


def _parse_param(item: str) -> tuple:
    """``key=value`` для --param. Значение парсится как JSON, иначе строка."""
    if "=" not in item:
        raise argparse.ArgumentTypeError(f"Ожидается key=value, получено: {item!r}")
    key, value = item.split("=", 1)
    return key.strip(), _coerce(value)


def _coerce(value: str) -> Any:
    try:
        return json.loads(value)
    except ValueError:
        return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="higgsfield.py",
        description="Генерация видео через Higgsfield API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Примеры:\n"
            "  python3 higgsfield.py \"кот в скафандре\" --duration 5 --output cat.mp4\n"
            "  python3 higgsfield.py \"оживи фото\" --image photo.jpg --output out.mp4\n"
            "  python3 higgsfield.py --status 7f3c...\n"
        ),
    )
    parser.add_argument("prompt", nargs="?", help="текстовый промпт")
    parser.add_argument("-m", "--model", help=f"модель, по умолчанию {DEFAULT_TEXT_TO_VIDEO}")
    parser.add_argument("-i", "--image", help="стартовый кадр: локальный файл или ссылка")
    parser.add_argument("-d", "--duration", type=float, help="длительность, секунды")
    parser.add_argument("-r", "--resolution", help="например 720p")
    parser.add_argument("-a", "--aspect-ratio", help="например 16:9")
    parser.add_argument("--output-format", help="mp4 или mov")
    parser.add_argument("--audio", dest="generate_audio", action="store_true", default=None,
                        help="просить модель сгенерировать звук")
    parser.add_argument("--no-audio", dest="generate_audio", action="store_false",
                        help="явно выключить звук")
    parser.add_argument("-p", "--param", action="append", type=_parse_param, default=[],
                        metavar="KEY=VALUE", help="любой дополнительный параметр модели")
    parser.add_argument("--webhook", help="URL вебхука вместо ожидания в процессе")
    parser.add_argument("-o", "--output", help="куда сохранить готовый файл (файл или каталог)")
    parser.add_argument("--json", action="store_true", help="напечатать сырой ответ API")
    parser.add_argument("--status", metavar="REQUEST_ID", help="показать статус задачи и выйти")
    parser.add_argument("--wait", metavar="REQUEST_ID", help="дождаться результата по request_id")
    parser.add_argument("--cancel", metavar="REQUEST_ID", help="отменить задачу в очереди")
    parser.add_argument("--poll-interval", type=float, default=POLL_INTERVAL,
                        help=f"пауза между опросами, секунды (по умолчанию {POLL_INTERVAL:g})")
    parser.add_argument("--timeout", type=float, default=POLL_TIMEOUT,
                        help=f"сколько ждать завершения, секунды (по умолчанию {POLL_TIMEOUT:g})")
    parser.add_argument("--base-url", default=BASE_URL, help=f"адрес API (по умолчанию {BASE_URL})")
    parser.add_argument("--dry-run", action="store_true",
                        help="показать, что было бы отправлено, и выйти")
    parser.add_argument("-q", "--quiet", action="store_true", help="меньше логов")
    return parser


def _dry_run(args) -> int:
    image_url = args.image if (args.image or "").startswith(("http://", "https://")) else None
    application = args.model or (
        DEFAULT_IMAGE_TO_VIDEO if args.image else DEFAULT_TEXT_TO_VIDEO
    )

    arguments: dict = {}
    if args.prompt:
        arguments["prompt"] = args.prompt
    if args.image:
        arguments["image_url"] = image_url or f"<загрузка файла {args.image}>"
    for key, value in (
        ("duration", args.duration),
        ("resolution", args.resolution),
        ("aspect_ratio", args.aspect_ratio),
        ("output_format", args.output_format),
        ("generate_audio", args.generate_audio),
    ):
        if value is not None:
            arguments[key] = value
    arguments.update(dict(args.param))

    print(f"POST {args.base_url.rstrip('/')}/{application}")
    print(json.dumps(arguments, ensure_ascii=False, indent=2))
    return 0


async def _run(args) -> int:
    async with HiggsfieldClient(base_url=args.base_url) as hf:
        if args.cancel:
            await hf.cancel(Job.from_request_id(args.cancel, args.base_url))
            print(f"Задача {args.cancel} отменена.")
            return 0

        if args.status:
            payload = await hf.status(Job.from_request_id(args.status, args.base_url))
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0

        if args.wait:
            result = await hf.result(
                Job.from_request_id(args.wait, args.base_url),
                interval=args.poll_interval,
                timeout=args.timeout,
            )
        else:
            if not args.prompt and not args.image:
                build_parser().error("нужен промпт или --image")

            result = await hf.generate_video(
                args.prompt,
                model=args.model,
                image=args.image,
                duration=args.duration,
                resolution=args.resolution,
                aspect_ratio=args.aspect_ratio,
                output_format=args.output_format,
                generate_audio=args.generate_audio,
                params=dict(args.param),
                webhook_url=args.webhook,
                interval=args.poll_interval,
                timeout=args.timeout,
            )

        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))

        urls = extract_video_urls(result)
        if not urls:
            print("Задача завершена, но ссылок на файлы в ответе нет.", file=sys.stderr)
            if not args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            return 1

        for url in urls:
            print(url)

        if args.output:
            path = await hf.download(urls[0], args.output)
            print(f"Сохранено: {path}")

        return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stderr,
    )

    if args.dry_run:
        return _dry_run(args)

    try:
        return asyncio.run(_run(args))
    except KeyboardInterrupt:
        return 130
    except HiggsfieldError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
