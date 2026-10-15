"""Download quality is chosen, never assumed.

A silent sources[0] downloaded whatever the provider listed first — a
360p when a 1080p exists. The list is now the SAME one the play dialog
shows, and the pick closes its own state so no dialog can strand.
"""

import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="animepahe-dlq-test-")
os.environ["FLET_APP_STORAGE_DATA"] = _TMP

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from main import _source_choices  # noqa: E402
from core.state import Source, state  # noqa: E402


def _src(resolution, audio="jpn", fansub="", size="", url="https://x/e.mkv"):
    return Source(
        url=url,
        resolution=resolution,
        audio=audio,
        fansub=fansub,
        headers={},
        subtitles=[],
        skip={},
        size=size,
    )


def test_choices_are_best_first_with_dubs_last():
    sources = [
        _src(480, audio="eng", fansub="DubGroup"),
        _src(1080, fansub="SubsPlease"),
        _src(720, fansub="Erai"),
    ]
    labels = [c["label"] for c in _source_choices(sources)]
    assert labels == [
        "1080p - SUB (JPN) (SubsPlease)",
        "720p - SUB (JPN) (Erai)",
        "480p - DUB (ENG) (DubGroup)",
    ]


def test_choice_carries_the_url_headers_and_size_for_the_download():
    sources = [_src(1080, size="293MB", url="https://cdn/a.mkv")]
    (choice,) = _source_choices(sources)
    assert choice["url"] == "https://cdn/a.mkv"
    assert choice["label"].endswith("[293MB]")
    assert choice["headers"] == {}


def test_the_first_choice_is_the_recommendation():
    """The dialog fills the first button in; it must be the best source,
    which is what a user who does not look gets."""
    sources = [_src(360), _src(1080)]
    assert _source_choices(sources)[0]["label"].startswith("1080p")


def test_choose_download_quality_closes_its_own_state():
    import asyncio

    import main as app_main

    controller = app_main.AppController.__new__(app_main.AppController)
    state.pending_download = {
        "anime_session": "s1",
        "episode_session": "e1",
        "title": "Frieren",
        "episode_num": 3,
    }
    state.download_choices = _source_choices([_src(1080), _src(720)])
    state.download_choice_open = True
    state.starting_downloads = set()
    state.busy_version = 0

    async def _run():
        # _begin_download does the real work; stub it so the test is about
        # the state machine, not the network.
        controller._begin_download = _recording_begin()
        await controller.choose_download_quality(1)

    started: list[dict] = []

    def _recording_begin():
        async def _begin(choice, anime_session, episode_session, ep, anime):
            started.append(
                {
                    "choice": choice,
                    "anime_session": anime_session,
                    "episode_session": episode_session,
                }
            )

        return _begin

    asyncio.run(_run())
    # The picked index (1) is the 720p, not the first.
    assert started and started[0]["choice"]["label"].startswith("720p")
    assert started[0]["episode_session"] == "e1"
    # The dialog is closed and nothing is left pending.
    assert state.download_choice_open is False
    assert state.download_choices is None
    assert state.pending_download is None
    # The tap's spinner is cleared too.
    assert "e1" not in state.starting_downloads


def test_choose_download_quality_ignores_a_stale_index():
    import asyncio

    import main as app_main

    controller = app_main.AppController.__new__(app_main.AppController)
    state.pending_download = {"episode_session": "e1", "anime_session": "s1"}
    state.download_choices = _source_choices([_src(1080)])
    state.download_choice_open = True
    called = []

    async def _begin(*args, **kwargs):
        called.append(args)

    controller._begin_download = _begin
    asyncio.run(controller.choose_download_quality(9))  # out of range
    assert called == []
    # Nothing stranded either: an invalid pick simply leaves the flag set.
    assert state.download_choice_open is True


def test_single_rendition_start_clears_the_spinner_even_when_it_fails():
    """The single-rendition path had no try/finally: an I/O error inside
    _begin_download left the episode in state.starting_downloads forever,
    so the detail-screen button spun until restart. The real path, with a
    fake downloads manager that raises on the manifest write."""
    import asyncio

    import main as app_main
    from core.state import state

    class _Router:
        def __init__(self, sources):
            self._sources = sources

        def get(self, name):
            return None  # no provider -> no kwik unpack

        async def sources(self, anime_session, episode_session):
            return list(self._sources)

    class _Downloads:
        def __init__(self):
            self.active_jobs = []

        async def detect_kind(self, url, headers):
            return ("file", "")

        async def start_direct(self, *a, **kw):
            raise OSError("disk full")

    class _Store:
        async def get_downloads(self):
            return {}

        async def save_download(self, session, row):
            pass

    controller = app_main.AppController.__new__(app_main.AppController)
    controller._owner_of = lambda session: "s1"
    controller.router = _Router([_src(1080)])  # ONE rendition -> immediate start
    controller.downloads = _Downloads()
    controller.store = _Store()

    async def _anime(session):
        return {"title": "Frieren", "poster": "p"}

    async def _resolve(url, session, provider_name=None):
        return url

    controller._resolve_anime = _anime
    controller._resolve_source = _resolve
    state.starting_downloads = set()
    state.episodes = [type("E", (), {"session": "e1", "episode": 1, "anime_id": 9})()]
    state.downloads = {}

    try:
        asyncio.run(controller.download_episode("s1", "e1"))
        raise AssertionError("expected the OSError to propagate")
    except OSError:
        pass
    # The important part: the spinner is cleared either way.
    assert "e1" not in state.starting_downloads


def test_the_providers_own_download_route_is_not_reresolved():
    """A provider-authored download URL (animepahe's pahe.win link) is a
    file. Feeding it through the owner's kwik resolver can only fail — and
    the fallback would then discard the site's own offering."""
    import asyncio

    import main as app_main

    controller = app_main.AppController.__new__(app_main.AppController)
    resolves: list[str] = []

    async def _resolve(url, session, provider_name=None):
        resolves.append(url)
        return url

    controller._resolve_source = _resolve
    controller._owner_of = lambda session: "animepahe"
    controller.router = type("R", (), {"get": lambda self, name: None})()

    kind, filename = "file", ""
    captured = {}

    class _Downloads:
        active_jobs = []

        async def detect_kind(self, url, headers):
            return (kind, filename)

        async def start_direct(self, episode_session, url, headers, metadata):
            captured.update({"url": url, "metadata": metadata})

    class _Store:
        async def get_downloads(self):
            return {}

        async def save_download(self, session, row):
            pass

    controller.downloads = _Downloads()
    controller.store = _Store()

    from core.state import Source, state
    from main import _source_choices

    state.starting_downloads = set()
    state.downloads = {}
    src = Source(
        url="https://kwik.si/e/abc",
        resolution=1080,
        audio="jpn",
        fansub="Sub",
        download_url="https://pahe.win/xyz",
    )
    choices = _source_choices([src])
    assert choices[0]["direct"] is True
    assert choices[0]["download_url"] == "https://pahe.win/xyz"
    asyncio.run(controller._begin_download(choices[0], "s1", "e1", None, {}))
    # the pahe.win URL went straight through, and the kwik URL never did
    assert resolves == []
    assert captured["url"] == "https://pahe.win/xyz"


def test_a_stream_source_is_still_resolved_normally():
    import asyncio

    import main as app_main

    controller = app_main.AppController.__new__(app_main.AppController)
    resolves: list[str] = []

    async def _resolve(url, session, provider_name=None):
        resolves.append(url)
        return "https://cdn/stream.m3u8"

    controller._resolve_source = _resolve
    controller._owner_of = lambda session: "anikato"
    controller.router = type("R", (), {"get": lambda self, name: None})()
    captured = {}

    class _Downloads:
        active_jobs = []

        async def detect_kind(self, url, headers):
            return ("hls", "")

        async def start(self, episode_session, url, headers, metadata):
            captured.update({"url": url})

    class _Store:
        async def get_downloads(self):
            return {}

        async def save_download(self, session, row):
            pass

    controller.downloads = _Downloads()
    controller.store = _Store()

    from core.state import state

    state.starting_downloads = set()
    state.downloads = {}
    choice = {
        "label": "1080p",
        "url": "https://anikato/stream/abc",
        "headers": {},
        "download_url": "",
        "direct": False,
    }
    asyncio.run(controller._begin_download(choice, "s1", "e1", None, {}))
    assert resolves == ["https://anikato/stream/abc"]
    assert captured["url"] == "https://cdn/stream.m3u8"


def test_presets_pick_the_right_rendition():
    from main import _preset_choice

    choices = [
        {"label": "1080p", "url": "hi"},
        {"label": "720p", "url": "mid"},
        {"label": "480p", "url": "lo"},
    ]
    assert _preset_choice(choices, "highest")["url"] == "hi"
    assert _preset_choice(choices, "lowest")["url"] == "lo"
    # as-served is the provider's own default — the list head
    assert _preset_choice(choices, "as-served")["url"] == "hi"
    assert _preset_choice([], "highest") == {}


def test_the_batch_queues_each_episode_independently():
    """One failing episode must not stop the rest — Media3's per-request
    model. A 170-episode series is a queue, not a burst."""
    import asyncio

    import main as app_main
    from core.state import Episode, state

    class _Router:
        def get(self, name):
            return None

        async def sources(self, anime_session, episode_session):
            if "e3" in episode_session:
                raise RuntimeError("dead host")
            return [_src(1080, url=f"https://x/{episode_session}")]

    class _Downloads:
        def __init__(self):
            self.active_jobs = []
            self.started = []

        async def detect_kind(self, url, headers):
            return ("file", "")

        async def start_direct(self, session, url, headers, metadata):
            self.started.append(session)

    class _Store:
        def __init__(self):
            self.rows = {}

        async def get_downloads(self):
            return dict(self.rows)

        async def save_download(self, session, row):
            self.rows[session] = row

    controller = app_main.AppController.__new__(app_main.AppController)
    controller.router = _Router()
    controller.downloads = _Downloads()
    controller.store = _Store()
    controller._owner_of = lambda s: "s1"
    controller._resolve_source = _passthrough
    controller._resolve_anime = _anime

    eps = [
        Episode(id=i, anime_id=1, episode=i, title=f"E{i}", snapshot="", disc="",
                audio="jpn", duration="", session=f"e{i}", filler=False)
        for i in range(1, 6)
    ]
    state.episodes = eps
    state.starting_downloads = set()
    state.downloads = {}

    queued = asyncio.run(controller.download_series("s1", [f"e{i}" for i in range(1, 6)]))
    assert queued == 4  # e3 failed; the rest still queued
    assert "e3" not in controller.downloads.started
    assert len(controller.downloads.started) == 4
    # nothing was left spinning
    assert state.starting_downloads == set()


def test_the_batch_skips_already_complete_and_active():
    import asyncio

    import main as app_main
    from core.state import Episode, state

    class _Router:
        def get(self, name):
            return None

        async def sources(self, anime_session, episode_session):
            return [_src(1080, url=f"https://x/{episode_session}")]

    class _Downloads:
        def __init__(self):
            self.active_jobs = ["e2"]
            self.started = []

        async def detect_kind(self, url, headers):
            return ("file", "")

        async def start_direct(self, session, url, headers, metadata):
            self.started.append(session)

    class _Store:
        def __init__(self):
            self.rows = {"e2": {"state": "complete"}}

        async def get_downloads(self):
            return dict(self.rows)

        async def save_download(self, session, row):
            self.rows[session] = row

    controller = app_main.AppController.__new__(app_main.AppController)
    controller.router = _Router()
    controller.downloads = _Downloads()
    controller.store = _Store()
    controller._owner_of = lambda s: "s1"
    controller._resolve_source = _passthrough
    controller._resolve_anime = _anime

    eps = [
        Episode(id=i, anime_id=1, episode=i, title=f"E{i}", snapshot="", disc="",
                audio="jpn", duration="", session=f"e{i}", filler=False)
        for i in range(1, 4)
    ]
    state.episodes = eps
    state.starting_downloads = set()
    state.downloads = {}

    queued = asyncio.run(controller.download_series("s1", ["e1", "e2", "e3"]))
    assert queued == 2  # e2 complete AND active; e3 queued
    assert controller.downloads.started == ["e1", "e3"]


async def _passthrough(url, session, provider_name=None):
    return url


async def _anime(session):
    return {"title": "Frieren", "poster": "p"}
