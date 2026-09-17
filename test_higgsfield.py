"""Проверка higgsfield.py на локальном макете API. Сеть наружу не нужна.

    python3 test_higgsfield.py
"""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("HF_KEY", "test-key-id:test-key-secret")

from aiohttp import web  # noqa: E402

import higgsfield  # noqa: E402

VIDEO_BYTES = b"\x00\x00\x00\x18ftypmp42" + b"video-payload" * 100


class MockAPI:
    """Минимальный макет Higgsfield API: очередь, статусы, загрузка, отдача файла."""

    def __init__(self):
        self.requests = {}
        self.submissions = []
        self.uploaded = None
        self.auth_headers = []
        self.flaky_left = 1
        self.status_calls = 0

    def build_app(self) -> web.Application:
        app = web.Application()
        app.router.add_post("/files/generate-upload-url", self.generate_upload_url)
        app.router.add_put("/upload/{name}", self.receive_upload)
        app.router.add_get("/requests/{request_id}/status", self.status)
        app.router.add_post("/requests/{request_id}/cancel", self.cancel)
        app.router.add_get("/files/{name}", self.serve_file)
        app.router.add_post("/{model:.*}", self.submit)
        return app

    async def submit(self, request: web.Request) -> web.Response:
        self.auth_headers.append(request.headers.get("Authorization"))

        # Первый заход отдаёт 500 — проверяем повтор с бэкоффом.
        if self.flaky_left > 0:
            self.flaky_left -= 1
            return web.json_response({"detail": "temporary"}, status=500)

        body = await request.json()
        model = request.match_info["model"]
        self.submissions.append((model, body, dict(request.query)))

        request_id = f"req-{len(self.submissions)}"
        self.requests[request_id] = {
            "polls": 0,
            "canceled": False,
            # Промпт со словом "fail" роняем — это нужно прогону сценария.
            "fails": "fail" in str(body.get("prompt", "")),
        }
        return web.json_response({
            "request_id": request_id,
            "status_url": str(request.url.with_path(f"/requests/{request_id}/status").with_query(None)),
            "cancel_url": str(request.url.with_path(f"/requests/{request_id}/cancel").with_query(None)),
        })

    async def status(self, request: web.Request) -> web.Response:
        request_id = request.match_info["request_id"]
        state = self.requests.setdefault(request_id, {"polls": 0, "canceled": False})
        self.status_calls += 1

        if state["canceled"]:
            return web.json_response({"status": "canceled"})

        # Задача с таким id никогда не завершается — для проверки таймаута.
        if request_id == "stuck":
            return web.json_response({"status": "queued"})

        if state.get("fails"):
            return web.json_response({"status": "failed", "detail": "мок: сцена провалена"})

        state["polls"] += 1
        if state["polls"] == 1:
            return web.json_response({"status": "queued"})
        if state["polls"] == 2:
            return web.json_response({"status": "in_progress"})

        base = str(request.url.with_path("/files/result.mp4").with_query(None))
        return web.json_response({
            "status": "completed",
            "request_id": request_id,
            "videos": [{"url": base, "thumbnail": {"url": base.replace("result.mp4", "thumb.png")}}],
        })

    async def cancel(self, request: web.Request) -> web.Response:
        request_id = request.match_info["request_id"]
        self.requests.setdefault(request_id, {"polls": 0})["canceled"] = True
        return web.json_response({"status": "canceled"})

    async def generate_upload_url(self, request: web.Request) -> web.Response:
        body = await request.json()
        name = "uploaded.jpg"
        return web.json_response({
            "public_url": str(request.url.with_path(f"/files/{name}").with_query(None)),
            "upload_url": str(request.url.with_path(f"/upload/{name}").with_query(None)),
            "content_type": body.get("content_type"),
        })

    async def receive_upload(self, request: web.Request) -> web.Response:
        self.uploaded = (await request.read(), request.headers.get("Content-Type"))
        # На предподписанную ссылку свои ключи слать нельзя.
        assert "Authorization" not in request.headers, "в PUT ушёл заголовок авторизации"
        return web.Response(status=200)

    async def serve_file(self, request: web.Request) -> web.Response:
        return web.Response(body=VIDEO_BYTES, content_type="video/mp4")


async def start_server(api: MockAPI):
    runner = web.AppRunner(api.build_app())
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = runner.addresses[0][1]
    return runner, f"http://127.0.0.1:{port}"


def check(condition, message):
    if not condition:
        raise AssertionError(message)


async def test_generate_video(base_url: str, api: MockAPI):
    async with higgsfield.HiggsfieldClient(base_url=base_url) as hf:
        statuses = []
        result = await hf.generate_video(
            "кот в скафандре",
            duration=5,
            resolution="720p",
            aspect_ratio="16:9",
            params={"seed": 42},
            interval=0.01,
            on_status=statuses.append,
        )

        check(result["status"] == "completed", "ожидался статус completed")
        check(statuses == ["queued", "in_progress", "completed"], f"статусы: {statuses}")

        model, body, query = api.submissions[-1]
        check(model == higgsfield.DEFAULT_TEXT_TO_VIDEO, f"модель: {model}")
        check(body == {
            "prompt": "кот в скафандре",
            "duration": 5,
            "resolution": "720p",
            "aspect_ratio": "16:9",
            "seed": 42,
        }, f"тело запроса: {body}")
        check(api.auth_headers[-1] == "Key test-key-id:test-key-secret", "заголовок авторизации")
        check(api.flaky_left == 0 and len(api.auth_headers) >= 2, "повтор после 500 не случился")

        urls = higgsfield.extract_video_urls(result)
        check(len(urls) == 1 and urls[0].endswith("result.mp4"), f"ссылки: {urls}")

        with tempfile.TemporaryDirectory() as tmp:
            path = await hf.download(urls[0], Path(tmp) / "out.mp4")
            check(path.read_bytes() == VIDEO_BYTES, "скачанный файл не совпал")

    print("ok  generate_video: отправка, повтор после 500, опрос, ссылка, скачивание")


async def test_image_to_video(base_url: str, api: MockAPI):
    with tempfile.TemporaryDirectory() as tmp:
        image = Path(tmp) / "frame.jpg"
        image.write_bytes(b"\xff\xd8\xff\xe0 jpeg")

        async with higgsfield.HiggsfieldClient(base_url=base_url) as hf:
            await hf.generate_video("оживи фото", image=str(image), interval=0.01)

    model, body, _ = api.submissions[-1]
    check(model == higgsfield.DEFAULT_IMAGE_TO_VIDEO, f"модель: {model}")
    check(body["image_url"].endswith("/files/uploaded.jpg"), f"image_url: {body['image_url']}")
    check(api.uploaded[0] == b"\xff\xd8\xff\xe0 jpeg", "залитые байты не совпали")
    check(api.uploaded[1] == "image/jpeg", f"content-type: {api.uploaded[1]}")
    print("ok  image-to-video: загрузка кадра и подстановка image_url")


async def test_webhook_and_cancel(base_url: str, api: MockAPI):
    async with higgsfield.HiggsfieldClient(base_url=base_url) as hf:
        job = await hf.submit(
            "test/model", {"prompt": "x"}, webhook_url="https://example.com/hook"
        )
        check(api.submissions[-1][2] == {"hf_webhook": "https://example.com/hook"},
              f"query: {api.submissions[-1][2]}")

        await hf.cancel(job)
        payload = await hf.status(job)
        check(payload["status"] == "canceled", f"статус: {payload}")

        try:
            await hf.result(job, interval=0.01)
        except higgsfield.HiggsfieldJobError as exc:
            check(exc.status == "canceled", f"статус ошибки: {exc.status}")
        else:
            raise AssertionError("отменённая задача должна бросать HiggsfieldJobError")

    print("ok  вебхук в query, отмена и ошибка по незавершённой задаче")


async def test_timeout(base_url: str):
    async with higgsfield.HiggsfieldClient(base_url=base_url) as hf:
        job = higgsfield.Job.from_request_id("stuck", base_url)
        try:
            await hf.result(job, interval=0.01, timeout=0.02)
        except higgsfield.HiggsfieldTimeoutError as exc:
            check(exc.job.request_id == "stuck", "в таймауте должен остаться request_id")
        else:
            raise AssertionError("ожидался HiggsfieldTimeoutError")
    print("ok  таймаут ожидания не теряет request_id")


async def test_api_error(base_url: str):
    async with higgsfield.HiggsfieldClient(base_url=base_url, max_retries=0) as hf:
        try:
            await hf.submit("boom", {"prompt": "x"})
        except higgsfield.HiggsfieldAPIError as exc:
            check(exc.status == 500 and "temporary" in exc.message, f"ошибка: {exc}")
        else:
            raise AssertionError("ожидался HiggsfieldAPIError без повторов")
    print("ok  ошибка API без повторов пробрасывается как есть")


def test_extract_urls():
    result = {
        "status": "completed",
        "videos": [{"url": "https://cdn/a.mp4"}],
        "nested": {"items": [{"image_url": "https://cdn/b.png"}]},
        "ignore": {"docs": "https://docs.example.com"},
    }
    check(higgsfield.extract_video_urls(result) == ["https://cdn/a.mp4"],
          f"видео: {higgsfield.extract_video_urls(result)}")

    unknown = {"status": "completed", "output": {"url": "https://cdn/file?token=1"}}
    check(higgsfield.extract_video_urls(unknown) == ["https://cdn/file?token=1"],
          "ссылка без расширения должна возвращаться как видео")
    print("ok  разбор ответа: ссылки на видео отделяются от картинок")


def test_credentials():
    saved = {k: os.environ.pop(k, None) for k in
             ("HF_KEY", "HIGGSFIELD_KEY", "HF_API_KEY", "HF_API_SECRET",
              "HIGGSFIELD_API_KEY", "HIGGSFIELD_API_SECRET")}
    try:
        try:
            higgsfield.get_credential_key()
        except higgsfield.CredentialsMissedError:
            pass
        else:
            raise AssertionError("без ключей ожидалась CredentialsMissedError")

        os.environ["HF_API_KEY"] = "id"
        os.environ["HF_API_SECRET"] = "secret"
        check(higgsfield.get_credential_key() == "id:secret", "склейка ключа и секрета")
    finally:
        for key in ("HF_API_KEY", "HF_API_SECRET"):
            os.environ.pop(key, None)
        for key, value in saved.items():
            if value is not None:
                os.environ[key] = value
    print("ok  ключи: HF_KEY либо пара HF_API_KEY/HF_API_SECRET")


def test_cli_dry_run():
    argv = ["промпт", "--duration", "5", "--param", "seed=7", "--dry-run", "--quiet"]
    import contextlib
    import io

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = higgsfield.main(argv)

    check(code == 0, f"код возврата: {code}")
    lines = buffer.getvalue().splitlines()
    check(lines[0].endswith(f"/{higgsfield.DEFAULT_TEXT_TO_VIDEO}"), f"URL: {lines[0]}")
    body = json.loads("\n".join(lines[1:]))
    check(body == {"prompt": "промпт", "duration": 5.0, "seed": 7}, f"тело: {body}")
    print("ok  CLI --dry-run печатает точный запрос")


async def main():
    api = MockAPI()
    runner, base_url = await start_server(api)
    try:
        await test_generate_video(base_url, api)
        await test_image_to_video(base_url, api)
        await test_webhook_and_cancel(base_url, api)
        await test_timeout(base_url)
        api.flaky_left = 1
        await test_api_error(base_url)
    finally:
        await runner.cleanup()

    test_extract_urls()
    test_credentials()
    test_cli_dry_run()
    print("\nвсе проверки пройдены")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except AssertionError as exc:
        print(f"ПРОВАЛ: {exc}", file=sys.stderr)
        sys.exit(1)
