"""AniKato's kwik FILES are earned at the user's deliberate act.

The owner (2026-10-20): "something is not done right because my anikato
is not using kwik resolver."

They were right, and the gap was precise: the provider appends its kwik
FILE sources (AnimePahe's own download row, reached through the site's
mapper) ONLY when a kwik.cx clearance is already stored — a provider
never opens a verification window on its own — and NOTHING ever earned
that clearance. ``AppController.solve_kwik_clearance`` existed but had no
caller, so on every play and every download the kwik sources were
silently absent and AniKato streamed the megaplay HLS only.

The wiring under test: ``_sources_with_kwik`` is the ONE source-fetch
helper for play, external play and download, and it earns the clearance
at exactly those deliberate user acts — once per session, so a cancelled
solve never nags on every episode — then re-fetches so the kwik files
actually appear in the quality dialog. The ability check is the
provider's own (``kwik_file_sources``), never a hardcoded name.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

import main as app_main
from core.state import Source


def _src(url: str, resolution: int = 0, audio: str = "jpn") -> Source:
    return Source(url=url, resolution=resolution, audio=audio, fansub="AniKato")


def _kwik_src(url: str, resolution: int) -> Source:
    return Source(
        url=url,
        resolution=resolution,
        audio="jpn",
        fansub="AnimePahe",
        download_url="https://pahe.nekostream.site/x",
    )


class _FakeRouter:
    """Answers sources() with a scripted list and counts the calls."""

    def __init__(self, provider, pages):
        self._provider = provider
        self._pages = list(pages)
        self.calls = 0

    def get(self, _name):
        return self._provider

    async def sources(self, _anime, _episode):
        self.calls += 1
        return list(self._pages[min(self.calls, len(self._pages)) - 1])


class _ProviderWithKwik:
    """AniKato's shape: it OWNS the kwik-file ability."""

    name = "anikato"

    async def kwik_file_sources(self, _a, _e):
        return []


class _ProviderWithoutKwik:
    name = "kayoanime"


class _Store:
    def __init__(self, clearance):
        self._clearance = clearance
        self.reads = 0

    async def get_clearance(self, host):
        self.reads += 1
        assert host == "kwik.cx"
        return self._clearance


@pytest.mark.asyncio
async def test_no_kwik_ability_fetches_sources_once_and_never_solves(monkeypatch):
    """A provider without the kwik-file ability (kayoanime, animeout) is
    served in one fetch — no verification window, no second fetch."""
    provider = _ProviderWithoutKwik()
    router = _FakeRouter(provider, [[_src("https://stream/master.m3u8")]])
    store = _Store(None)

    import services.store as store_mod

    monkeypatch.setattr(store_mod, "get_store", lambda: store)
    controller = app_main.AppController.__new__(app_main.AppController)
    controller.router = router
    controller._owner_of = lambda _s: provider.name
    controller._kwik_solve_tried = False
    controller.page = None
    solves = []
    controller.solve_kwik_clearance = lambda: solves.append(1) or asyncio.sleep(0, result=False)

    sources = await controller._sources_with_kwik("kayoanime:x", "x|1")

    assert len(sources) == 1
    assert router.calls == 1, "no ability -> one fetch"
    assert store.reads == 0, "the clearance is never even read"
    assert solves == []


@pytest.mark.asyncio
async def test_clearance_already_stored_fetches_once_and_never_solves(monkeypatch):
    """With the clearance stored, the provider's own sources() already
    appended the kwik files — one fetch, no window."""
    provider = _ProviderWithKwik()
    kwik_pages = [
        [
            _kwik_src("https://kwik.media/1080.mp4", 1080),
            _src("https://stream/master.m3u8"),
        ]
    ]
    router = _FakeRouter(provider, kwik_pages)
    store = _Store({"cookies": "cf_clearance=abc", "user_agent": "ua"})

    import services.store as store_mod

    monkeypatch.setattr(store_mod, "get_store", lambda: store)
    controller = app_main.AppController.__new__(app_main.AppController)
    controller.router = router
    controller._owner_of = lambda _s: provider.name
    controller._kwik_solve_tried = False
    controller.page = None
    solves = []
    controller.solve_kwik_clearance = lambda: solves.append(1) or asyncio.sleep(0, result=True)

    sources = await controller._sources_with_kwik("anikato:x", "x|1")

    assert [s.resolution for s in sources] == [1080, 0]
    assert router.calls == 1
    assert store.reads == 1
    assert solves == []


@pytest.mark.asyncio
async def test_missing_clearance_is_earned_then_sources_are_refetched(monkeypatch):
    """THE FIX: no clearance + a successful solve -> the sources are
    fetched AGAIN, and this time they carry the kwik files."""
    provider = _ProviderWithKwik()
    router = _FakeRouter(
        provider,
        [
            [_src("https://stream/master.m3u8")],  # before the clearance
            [
                _kwik_src("https://kwik.media/1080.mp4", 1080),
                _src("https://stream/master.m3u8"),
            ],  # after
        ],
    )
    store = _Store(None)

    import services.store as store_mod

    monkeypatch.setattr(store_mod, "get_store", lambda: store)
    controller = app_main.AppController.__new__(app_main.AppController)
    controller.router = router
    controller._owner_of = lambda _s: provider.name
    controller._kwik_solve_tried = False
    controller.page = None
    solves = []
    controller.solve_kwik_clearance = lambda: solves.append(1) or asyncio.sleep(0, result=True)

    sources = await controller._sources_with_kwik("anikato:x", "x|1")

    assert solves == [1], "the window opened exactly once"
    assert router.calls == 2, "the refetch carries the kwik files"
    assert any(s.fansub == "AnimePahe" for s in sources), (
        "the kwik FILE sources must reach the quality dialog"
    )


@pytest.mark.asyncio
async def test_a_failed_or_cancelled_solve_nags_never_again(monkeypatch):
    """One failed solve per session: the second play must not open the
    window again — a user who cancels the challenge is not asked on
    every episode."""
    provider = _ProviderWithKwik()
    router = _FakeRouter(provider, [[_src("https://stream/master.m3u8")]])
    store = _Store(None)

    import services.store as store_mod

    monkeypatch.setattr(store_mod, "get_store", lambda: store)
    controller = app_main.AppController.__new__(app_main.AppController)
    controller.router = router
    controller._owner_of = lambda _s: provider.name
    controller._kwik_solve_tried = False
    controller.page = None
    solves = []
    controller.solve_kwik_clearance = lambda: solves.append(1) or asyncio.sleep(0, result=False)

    await controller._sources_with_kwik("anikato:x", "x|1")
    await controller._sources_with_kwik("anikato:x", "x|2")

    assert solves == [1], "the failed solve is never retried this session"
    assert router.calls == 2
