"""Variant probing is for HLS ONLY — the direct-file play crash.

The flet run log (kayoanime episode): the resolve path called
_fetch_variants on a Google Drive MP4/MKV, hls_proxy.fetch_master tried to
read the entire video body as `resp.text`, primp timed out, and the
play-episode background task died with the player never opening.

_fetch_variants now returns [] for non-.m3u8 URLs before touching the
proxy (and before the direct-fetch fallback).
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import main as app_main  # noqa: E402


class _Proxy:
    def __init__(self):
        self.calls: list[str] = []

    async def fetch_variants(self, url, headers=None):
        self.calls.append(url)
        return [{"label": "1080p", "uri": url}]


def _controller(proxy):
    controller = app_main.AppController.__new__(app_main.AppController)
    controller.hls_proxy = proxy
    return controller


def test_direct_files_are_never_probed_for_variants():
    proxy = _Proxy()
    controller = _controller(proxy)

    direct_files = [
        # kayoanime's keyed Drive route (the exact URL from the log)
        "https://www.googleapis.com/drive/v3/files/1MQZpgV0yg33Dpr_tOkImhBgLLgydbTEe?alt=media&key=k",
        # keyless Drive download route
        "https://drive.usercontent.google.com/download?id=abc&export=download&confirm=t",
        # a direct file with a query signature
        "https://cdn.example/file.mkv?sig=1",
    ]
    for url in direct_files:
        assert asyncio.run(controller._fetch_variants(url)) == []
    assert proxy.calls == [], "a direct file must not reach the proxy"


def test_m3u8_urls_still_probe_through_the_proxy():
    proxy = _Proxy()
    controller = _controller(proxy)
    out = asyncio.run(
        controller._fetch_variants("https://cdn.example/master.m3u8?token=1")
    )
    assert proxy.calls == ["https://cdn.example/master.m3u8?token=1"]
    assert out and out[0]["label"] == "1080p"


def test_empty_or_none_url_is_a_noop():
    proxy = _Proxy()
    controller = _controller(proxy)
    assert asyncio.run(controller._fetch_variants("")) == []
    assert asyncio.run(controller._fetch_variants(None)) == []
    assert proxy.calls == []
