"""HTTP-транспорт с повторами для публичных API.

Бесплатные RPC-узлы и API (Solana, Starknet, CoinGecko…) под нагрузкой
отвечают 429 "слишком много запросов", 5xx или просто обрывают соединение.
Все запросы бота — чтение, повторять их безопасно.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

log = logging.getLogger(__name__)

RETRY_STATUSES = {429, 500, 502, 503, 504}
PAUSES_S = [2, 5, 10, 20]


class RetryTransport(httpx.AsyncBaseTransport):
    def __init__(self, inner: httpx.AsyncBaseTransport | None = None) -> None:
        self._inner = inner or httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        body = request.content  # POST-тело уже в памяти, его можно отправить повторно
        for attempt, pause in enumerate([*PAUSES_S, None]):
            try:
                response = await self._inner.handle_async_request(request)
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                if pause is None:
                    raise
                log.debug("%s: %s, повтор через %dс", request.url.host, type(exc).__name__, pause)
            else:
                if response.status_code not in RETRY_STATUSES or pause is None:
                    return response
                retry_after = response.headers.get("retry-after", "")
                if retry_after.isdigit():
                    pause = min(int(retry_after), 60)
                await response.aclose()
                log.debug("%s: HTTP %s, повтор через %dс", request.url.host, response.status_code, pause)
            await asyncio.sleep(pause)
            request = httpx.Request(request.method, request.url, headers=request.headers, content=body,
                                    extensions=request.extensions)
        raise RuntimeError("unreachable")

    async def aclose(self) -> None:
        await self._inner.aclose()
