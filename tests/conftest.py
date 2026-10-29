from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
import pytest
import respx

from stellards import AsyncStellarDS, StellarDS

BASE = "https://api.test.stellards.io"
PROJECT = "3fa85f64-5717-4562-b3fc-2c963f66afa6"


def envelope(data: Any = None, *, count: int | None = None, success: bool = True, messages: Any = None) -> Any:
    body: dict[str, Any] = {"data": data, "isSuccess": success, "messages": messages or []}
    if count is not None:
        body["count"] = count
    return body


def ok(data: Any = None, *, status: int = 200, count: int | None = None) -> httpx.Response:
    return httpx.Response(status, json=envelope(data, count=count))


@pytest.fixture
def mock() -> Iterator[respx.MockRouter]:
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        yield router


@pytest.fixture
def sds(mock: respx.MockRouter) -> Iterator[StellarDS]:
    with StellarDS("static-token", base_url=BASE, project=PROJECT) as client:
        yield client


@pytest.fixture
async def asds(mock: respx.MockRouter) -> AsyncIterator[AsyncStellarDS]:
    async with AsyncStellarDS("static-token", base_url=BASE, project=PROJECT) as client:
        yield client
