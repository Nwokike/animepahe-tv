"""Artwork probe tests — fake primp client and cache, no network.

The fake mirrors the real contract the probe relies on: ``client.get(...,
stream=True)`` returning a response whose ``aiter_bytes`` yields chunks, and
a client that is closed via ``__aexit__`` (primp 2.0.1's only teardown).
"""

import asyncio
import os
import struct
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.artwork import LANDSCAPE, PORTRAIT
from services import artwork_probe
from services.artwork_probe import (
    CACHE_PREFIX,
    PROBE_CONCURRENCY,
    SHAPE_TTL,
    shape_for,
    shapes_for,
)


def _png(width: int, height: int) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + b"\x00\x00\x00\rIHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x02\x00\x00\x00\x00\x00\x00\x00"
    )


def _jpeg(width: int, height: int) -> bytes:
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    sof = (
        b"\xff\xc0"
        + struct.pack(">H", 17)
        + b"\x08"
        + height.to_bytes(2, "big")
        + width.to_bytes(2, "big")
        + b"\x03\x01\x22\x00\x02\x11\x01\x03\x11\x01"
    )
    return b"\xff\xd8" + app0 + sof + b"\xff\xd9"


@pytest.fixture(autouse=True)
def _fresh_memo():
    artwork_probe._mem.clear()
    yield
    artwork_probe._mem.clear()


class FakeResponse:
    def __init__(self, chunks, status_code=206, owner=None, url=""):
        self.status_code = status_code
        self._chunks = chunks
        self._owner = owner
        self._url = url

    async def aiter_bytes(self, chunk_size=None):
        for chunk in self._chunks:
            if self._owner is not None:
                self._owner.consumed[self._url] = self._owner.consumed.get(self._url, 0) + 1
            await asyncio.sleep(0)
            yield chunk


class FakeClient:
    """Routes: url -> ("ok", bytes) | ("status", int) | ("error", exception)."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []
        self.headers = []
        self.concurrent = 0
        self.max_concurrent = 0
        self.consumed = {}
        self.aclosed = False

    async def get(self, url, params=None, headers=None, stream=False, **kwargs):
        self.calls.append(url)
        self.headers.append(headers or {})
        self.concurrent += 1
        self.max_concurrent = max(self.max_concurrent, self.concurrent)
        try:
            await asyncio.sleep(0)
            route = self.routes.get(url)
            if route is None:
                raise AssertionError(f"unexpected url dialed: {url}")
            kind, payload = route
            if kind == "status":
                return FakeResponse([], status_code=payload, owner=self, url=url)
            if kind == "error":
                raise payload
            if kind == "chunks":
                return FakeResponse(list(payload), owner=self, url=url)
            half = max(1, len(payload) // 2)
            chunks = [payload[:half], payload[half:]]
            return FakeResponse(chunks, owner=self, url=url)
        finally:
            self.concurrent -= 1

    async def aclose(self):
        self.aclosed = True


class FakeCache:
    def __init__(self, initial=None):
        self.data = dict(initial or {})
        self.gets = 0
        self.sets = 0
        self.ttls = []

    async def get(self, key):
        self.gets += 1
        return self.data.get(key)

    async def set(self, key, value, ttl=0):
        self.sets += 1
        self.ttls.append(ttl)
        self.data[key] = value


def test_shapes_parse_and_referer_is_sent():
    portrait_url = "https://cdn.example/anikato-poster.jpg"
    landscape_url = "https://cdn.example/wide.jpg"
    client = FakeClient(
        {portrait_url: ("ok", _png(266, 400)), landscape_url: ("ok", _jpeg(1280, 720))}
    )
    results = asyncio.run(
        shapes_for([portrait_url, landscape_url], provider="anikato", client=client)
    )
    assert results == [PORTRAIT, LANDSCAPE]
    assert len(client.calls) == 2
    for headers in client.headers:
        assert headers["Range"] == "bytes=0-65535"
        assert headers["Referer"] == "https://anikototv.to/"


def test_data_uris_never_dial():
    client = FakeClient({})  # would AssertionError on any call
    uri = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAlgAAAOAAAIAAADEDDBHAAAADUlEQVR42u3BAQ0AAADCoPdPbQ43oAAAAAAAAAAAAAAAAAAAAAAAfg0QAAABJfZkAAAAAElFTkSuQmCC"
    # A real 600x900-ish PNG header is not guaranteed by that string; build it.
    import base64

    uri = "data:image/png;base64," + base64.b64encode(_png(600, 900)).decode()
    assert asyncio.run(shapes_for([uri], client=client)) == [PORTRAIT]
    assert client.calls == []


def test_cache_hit_skips_the_network_and_the_second_call_skips_the_cache():
    url = "https://cdn.example/cached.jpg"
    cache = FakeCache({CACHE_PREFIX + url: LANDSCAPE})
    client = FakeClient({})
    assert asyncio.run(shapes_for([url], cache=cache, client=client)) == [LANDSCAPE]
    assert client.calls == []
    assert cache.gets == 1
    # Session memo now answers without touching the cache again.
    assert asyncio.run(shapes_for([url], cache=cache, client=client)) == [LANDSCAPE]
    assert cache.gets == 1


def test_detected_shapes_are_written_to_the_cache():
    url = "https://cdn.example/fresh.jpg"
    cache = FakeCache()
    client = FakeClient({url: ("ok", _png(266, 400))})
    assert asyncio.run(shapes_for([url], cache=cache, client=client)) == [PORTRAIT]
    assert cache.sets == 1
    assert cache.ttls == [SHAPE_TTL]
    assert cache.data[CACHE_PREFIX + url] == PORTRAIT


def test_failures_become_none_and_never_raise():
    timeout_url = "https://cdn.example/timeout.jpg"
    walled_url = "https://cdn.example/walled.jpg"
    junk_url = "https://cdn.example/junk.jpg"
    cap_url = "https://cdn.example/huge.jpg"
    client = FakeClient(
        {
            timeout_url: ("error", TimeoutError("probe deadline")),
            walled_url: ("status", 403),
            junk_url: ("ok", b"\x00" * 100),
            cap_url: ("ok", os.urandom(70000)),
        }
    )
    results = asyncio.run(shapes_for([timeout_url, walled_url, junk_url, cap_url], client=client))
    assert results == [None, None, None, None]
    # And the failures are memoized for the session — a second pass dials nothing.
    calls_before = len(client.calls)
    assert asyncio.run(shapes_for([timeout_url, walled_url], client=client)) == [None, None]
    assert len(client.calls) == calls_before


def test_concurrency_is_bounded():
    urls = [f"https://cdn.example/{i}.jpg" for i in range(12)]
    client = FakeClient({url: ("ok", _png(266, 400)) for url in urls})
    results = asyncio.run(shapes_for(urls, client=client))
    assert results == [PORTRAIT] * 12
    assert 2 <= client.max_concurrent <= PROBE_CONCURRENCY


def test_abstaining_square_stops_reading_immediately():
    url = "https://cdn.example/square.jpg"
    client = FakeClient({url: ("chunks", [_png(800, 800), b"\x00" * 50, b"\x00" * 50])})
    results = asyncio.run(shapes_for([url], client=client))
    assert results == [None]
    assert client.consumed[url] == 1  # parsed on the first chunk; nothing further pulled


def test_shape_for_wraps_shapes_for():
    url = "https://cdn.example/one.jpg"
    client = FakeClient({url: ("ok", _jpeg(1280, 720))})
    assert asyncio.run(shape_for(url, provider="kayoanime", client=client)) == LANDSCAPE


def test_owned_client_is_closed_injected_client_is_not(monkeypatch):
    url = "https://cdn.example/owned.jpg"
    created = []

    class Factory:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.inner = FakeClient({url: ("ok", _png(266, 400))})
            self.aexits = 0
            created.append(self)

        async def get(self, *args, **kwargs):
            return await self.inner.get(*args, **kwargs)

        async def __aexit__(self, *exc):
            self.aexits += 1

    monkeypatch.setattr(artwork_probe.primp, "AsyncClient", Factory)
    assert asyncio.run(shapes_for([url])) == [PORTRAIT]
    assert created[0].kwargs.get("impersonate") == "chrome"
    assert created[0].aexits == 1

    url2 = "https://cdn.example/injected.jpg"
    injected = FakeClient({url2: ("ok", _png(266, 400))})
    assert asyncio.run(shapes_for([url2], client=injected)) == [PORTRAIT]
    assert injected.aclosed is False
