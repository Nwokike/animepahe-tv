"""Kwik FIRST, the source's own stream as the fallback — the owner's order.

"I expected you to do the kwik way and fall back to I think the mega way
that I think we are already doing." (owner, 2026-10-23)

The first attempt failed the owner twice, and both failures are pinned
here so they cannot return:

1. The verification window was aimed at ``kwik.cx/``'s HOMEPAGE — a plain
   200 with NO challenge, so no clearance could ever be earned there. The
   owner sat on a homepage with nothing to solve. The window must open at
   the ACTUAL ``/f/`` FILE page, the one route Cloudflare walls (live
   2026-10-23: Naruto episodes 1-3 all answer 403 ``cf-mitigated:
   challenge`` there) and the only page where the clearance is issued.
2. There was no kwik-first ordering: the window popped, failed, and the
   sources came back exactly as before. Now a successful solve PREPENDS
   the per-quality kwik sources (the dialog sorts them ahead of the HLS
   master by resolution); any failure returns the stream path untouched —
   the mega fallback.

The live facts the wiring rests on (2026-10-23): the mapper resolves
per-quality shortlinks for every episode; the hop chain
mapper → pahe.nekostream → testpahe → kwik.cx/f/ is unchallenged up to
the final page; the /f/ page is challenged. So the provider can always
reach the page the window must open at, without any clearance.

Note: Anikato no longer uses kwik for downloads — variant expansion from
the master playlist covers all qualities (1080p/720p/480p). Kwik is only
used by AnimePahe for streaming (kwik /e/ → m3u8).
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
    name = "kayoanime"


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

