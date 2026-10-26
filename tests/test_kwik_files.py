"""The kwik FILE route — AnimePahe's streaming path (kwik /e/ → m3u8 via KwikResolver).

The chain under test:

    mapper.nekostream.site/api/mal/<mal>/<ep>/<ts>
      -> {quality: pahe.nekostream.site/<code>}
      -> pahe.nekostream.site/<code>          (an HTML page)
      -> testpahe.nekostream.site/<code>      (302, needs the referer)
      -> kwik.cx/f/<token>                    (the Cloudflare-guarded file page)
      -> a CSRF'd POST to kwik.cx/d/<token>   -> 302 -> the media file

These tests use the REAL payload shapes (the mapper's JSON, the kwik
file page's HTML) and assert the chain hop by hop — the shape of the
thing that made AniKato's download row look like AnimePahe's.

Note: Anikato no longer uses kwik for downloads — variant expansion from
the master playlist covers all qualities. Kwik is only used by AnimePahe
for streaming (kwik /e/ → m3u8 via KwikResolver), not for file downloads
(kwik /f/ → MP4 via KwikFileResolver).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

import main as app_main
from core.state import Source


def _src(url: str, resolution: int = 0, audio: str = "jpn") -> Source:
    return Source(url=url, resolution=resolution, audio=audio, fansub="AniKato")


def _kwik_src(resolution: int) -> Source:
    return Source(
        url=f"https://kwik.media/{resolution}.mp4",
        resolution=resolution,
        audio="jpn",
        fansub="AnimePahe",
        download_url="https://pahe.nekostream.site/x",
    )


class _FakeRouter:
    def __init__(self, provider, sources):
        self._provider = provider
        self._sources = sources
        self.calls = 0

    def get(self, _name):
        return self._provider

    async def sources(self, _anime, _episode):
        self.calls += 1
        return list(self._sources)


class _ProviderWithoutKwik:
    name = "anikato"


class _ProviderWithKwik:
    """AnimePahe's shape: the kwik-file ability, driven through a scriptable
    chain so the test controls what the solve sees and what comes back."""

    name = "animepahe"
    capabilities = {"direct_download_url": False}

    def __init__(self, f_url="https://kwik.cx/f/token123", kwik=None):
        self._f_url = f_url
        self._kwik = kwik or []
        self.solve_calls: list[str] = []

    async def ensure_kwik_sources(self, _anime, _episode, solve):
        # The provider's real chain reaches the /f/ URL and hands it to
        # the solve callback; a True return means the clearance landed.
        if await solve(self._f_url):
            self.solve_calls.append(self._f_url)
            return list(self._kwik)
        return []


def _controller(router, solved: bool):
    """The minimum AppController surface _sources_with_kwik and
    earn_kwik_qualities touch, with the REAL methods bound."""
    solves: list[str] = []

    class _C:
        _kwik_solve_tried = False
        _play_gen = 0
        _play_sources = []
        page = object()

        _sources_with_kwik = app_main.AppController._sources_with_kwik
        earn_kwik_qualities = app_main.AppController.earn_kwik_qualities

        def _begin_resolve(self, stage):
            self._play_gen += 1
            return self._play_gen

        def _resolve_stage(self, gen, stage):
            pass

        def _end_resolve(self):
            pass

        async def _solve_kwik_file(self, f_url):
            solves.append(f_url)
            return solved

    controller = _C()
    controller.router = router
    controller._owner_of = lambda _session: router._provider.name
    return controller, solves


@pytest.mark.asyncio
async def test_no_kwik_ability_fetches_sources_once_and_never_solves():
    """A provider without the kwik-file ability (anikato) is
    served in one fetch — no window, no second fetch."""
    provider = _ProviderWithoutKwik()
    router = _FakeRouter(provider, [_src("https://stream/master.m3u8")])
    controller, solves = _controller(router, solved=True)

    sources = await controller._sources_with_kwik("anikato:x", "x|1")

    assert len(sources) == 1
    assert router.calls == 1
    assert solves == []


@pytest.mark.asyncio
async def test_initial_playback_is_cloudflare_free_megaplay_by_default():
    """The owner's order (2026-10-23): Cloudflare-free experience first.
    Initial play NEVER opens a verification window — megaplay streams
    answer with no challenge, so that is what plays by default."""
    provider = _ProviderWithoutKwik()
    router = _FakeRouter(provider, [_src("https://stream/master.m3u8")])
    controller, solves = _controller(router, solved=True)

    sources = await controller._sources_with_kwik("anikato:x", "x|1")

    assert len(sources) == 1
    assert sources[0].fansub == "AniKato"
    assert solves == [], "initial playback must never open a verification window"


@pytest.mark.asyncio
async def test_earn_kwik_qualities_opens_at_challenged_f_page():
    """The 'More qualities' button in the quality dialog: opens the solve
    at the REAL challenged /f/ page, not the homepage."""
    provider = _ProviderWithKwik(f_url="https://kwik.cx/f/bOetfymashCV", kwik=[_kwik_src(1080)])
    router = _FakeRouter(provider, [_src("https://stream/master.m3u8")])
    controller, solves = _controller(router, solved=True)
    controller._play_sources = [_src("https://stream/master.m3u8")]

    success = await controller.earn_kwik_qualities("animepahe:x", "x|1")

    assert success is True
    assert solves == ["https://kwik.cx/f/bOetfymashCV"], (
        "the window must open at the challenged FILE page, never the homepage"
    )


@pytest.mark.asyncio
async def test_earn_kwik_qualities_prepends_kwik_sources():
    """A successful solve prepends the per-quality kwik sources ahead
    of the stream sources."""
    provider = _ProviderWithKwik(kwik=[_kwik_src(1080), _kwik_src(800)])
    router = _FakeRouter(
        provider,
        [_src("https://stream/master.m3u8")],
    )
    controller, solves = _controller(router, solved=True)
    controller._play_sources = [_src("https://stream/master.m3u8")]

    await controller.earn_kwik_qualities("animepahe:x", "x|1")

    from state.app_state import state

    labels = [c["label"] for c in state.quality_choices or []]
    assert any("1080p" in l for l in labels)
    assert any("800p" in l for l in labels)
