"""Artwork probe — how a screen learns the shape of art it hasn't loaded yet.

Cache-first and never-raising: a ``data:`` URI is sniffed locally (animepahe
resolves its art that way), known URLs answer from the TTL cache, and the
rest are streamed with primp — a Range request, the first chunk or two, then
the batch's client is closed. A failure is ``None``; the caller keeps its
default shape (the live animeout 403 is the proven case).

One backend at a time: the probe only ever sees the selected backend's own
URLs, its own referer, and nothing else's.
"""

import asyncio

import anyio
import primp

from core.artwork import (
    HEAD_LIMIT,
    LANDSCAPE,
    PORTRAIT,
    probe_referer,
    shape_from_data_uri,
    shape_of,
    sniff_dimensions,
)
from services.providers.base import close_client

CACHE_PREFIX = "artwork:"
SHAPE_TTL = 30 * 24 * 3600  # shape never changes for a URL
PROBE_CONCURRENCY = 6
PROBE_TIMEOUT = 3.0
PROBE_CHUNK = 4096
PROBE_HEADERS = {
    "Accept": "image/avif,image/webp,image/*,*/*;q=0.8",
    "Range": f"bytes=0-{HEAD_LIMIT - 1}",
}

# Session memo. Positives come from the disk cache; negatives live only here
# so a transient failure never sticks across launches — but a dead host is
# not re-dialed repeatedly within one session either.
_mem: dict[str, str | None] = {}
# Real w/h per URL, in-session. The shape labels are coarse (anything >= 1
# is "landscape"); the ratio lets a card decide whether a crop is a hairline
# (fill the cell) or a butchery (show the whole image over a frosted fill).
_aspect: dict[str, float] = {}


def cached_aspect(src: str) -> float | None:
    """width/height for a URL probed this session, else None."""
    if not src:
        return None
    return _aspect.get(CACHE_PREFIX + src)


def cached_shape(src: str) -> str | None:
    """The shape already known for this URL — a synchronous memo read.

    Cards call this while building: a probed URL answers instantly, a
    ``data:`` URI is sniffed locally (microseconds, no network), and None
    means unknown (the caller keeps the house cover-crop).
    """
    if not src:
        return None
    if src.startswith("data:"):
        return shape_from_data_uri(src)
    return _mem.get(CACHE_PREFIX + src)


async def shape_for(
    src: str,
    *,
    provider: str = "",
    referer: str | None = None,
    cache=None,
    client=None,
) -> str | None:
    """One URL's shape: ``"landscape"``, ``"portrait"`` or ``None`` (unknown)."""
    results = await shapes_for(
        [src], provider=provider, referer=referer, cache=cache, client=client
    )
    return results[0]


async def shapes_for(
    srcs: list[str],
    *,
    provider: str = "",
    referer: str | None = None,
    cache=None,
    client=None,
) -> list[str | None]:
    """Shapes aligned 1:1 with ``srcs``. Bounded, cached, never raises.

    ``cache`` is a services.cache.Cache instance (or any async get/set pair);
    ``client`` lets tests and batch callers share one primp client — when the
    caller passes one, it stays open; when we create one, we close it.
    """
    results: list[str | None] = [None] * len(srcs)
    referer = referer or probe_referer(provider) or None

    network: list[tuple[int, str]] = []
    for index, src in enumerate(srcs):
        if not src:
            continue
        if src.startswith("data:"):
            results[index] = shape_from_data_uri(src)
            continue
        key = CACHE_PREFIX + src
        if key in _mem:
            results[index] = _mem[key]
            continue
        network.append((index, src))

    if cache is not None and network:
        remaining: list[tuple[int, str]] = []
        for index, src in network:
            key = CACHE_PREFIX + src
            cached = await cache.get(key)
            if cached in (LANDSCAPE, PORTRAIT):
                _mem[key] = cached
                results[index] = cached
            else:
                remaining.append((index, src))
        network = remaining

    if not network:
        return results

    owned = client is None
    if owned:
        client = primp.AsyncClient(
            impersonate="chrome", timeout=PROBE_TIMEOUT, follow_redirects=True
        )
    try:
        semaphore = asyncio.Semaphore(PROBE_CONCURRENCY)

        async def probe(index: int, src: str) -> None:
            async with semaphore:
                shape = await _probe_one(client, src, referer)
            results[index] = shape
            _mem[CACHE_PREFIX + src] = shape
            if shape is not None and cache is not None:
                await cache.set(CACHE_PREFIX + src, shape, ttl=SHAPE_TTL)

        await asyncio.gather(*(probe(index, src) for index, src in network))
    finally:
        if owned:
            await close_client(client)
    return results


async def _probe_one(client, url: str, referer: str | None) -> str | None:
    """Stream the head of one image and parse its dimensions. None on anything odd."""
    headers = dict(PROBE_HEADERS)
    if referer:
        headers["Referer"] = referer
    buf = bytearray()
    try:
        with anyio.fail_after(PROBE_TIMEOUT):
            resp = await client.get(url, headers=headers, stream=True)
            if getattr(resp, "status_code", 200) >= 400:
                return None
            async for chunk in resp.aiter_bytes(PROBE_CHUNK):
                buf += chunk
                dims = sniff_dimensions(bytes(buf))
                if dims:
                    width, height = dims
                    if height:
                        _aspect[CACHE_PREFIX + url] = width / height
                    # Parsed: a square abstains (None) and reading more cannot help.
                    return shape_of(*dims)
                if len(buf) >= HEAD_LIMIT:
                    break
    except (primp.PrimpError, TimeoutError, OSError, ValueError):
        return None
    return None
