"""The kwik FILE route — AniKato's own download row, which is
AnimePahe's (proved live 2026-10-19, docs/testing-findings.md §6).

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
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

from services.kwik_files import KwikFileResolver

# The mapper's real answer for Black Clover episode 1 (live 2026-10-19).
MAPPER_PAYLOAD = {
    "Kiwi": {
        "sub": {
            "download": {
                "360p": "https://pahe.nekostream.site/yRVMl",
                "720p": "https://pahe.nekostream.site/BfqIe",
                "1080p": "https://pahe.nekostream.site/WjUUW",
            }
        }
    },
    "status": {"time": 1792094249, "serves_from": "database"},
}

# The kwik file page's real shape: a form that POSTs to /d/<token>.
KWIK_PAGE = """
<!DOCTYPE html>
<html><head><title>AnimePahe_Black_Clover_-_001_360p_SubsPlease.mp4 :: Kwik</title></head>
<body>
  <h1 class="title"> AnimePahe_Black_Clover_-_001_360p_SubsPlease.mp4 </h1>
  <form method="POST" action="https://kwik.cx/d/nHkd7KvJyRxT">
    <input type="hidden" name="_token" value="rRGJlYvb5CP08q9fpcOEXAm8f1YkJL51bocexzdY">
    <button type="submit" class="button is-success">Download&nbsp;(52.82 MB)</button>
  </form>
</body></html>
"""

# The pahe.nekostream shortlink page: its JS hands over to testpahe.
SHORTLINK_PAGE = """
<!DOCTYPE html>
<html><body>
<script>
function startDownload() {
  const id = getId();
  const url = "https://testpahe.nekostream.site/" + id;
  window.location.href = url;
}
</script>
</body></html>
"""


class _Resp:
    def __init__(self, status_code=200, json_data=None, text="", headers=None):
        self.status_code = status_code
        self._json = json_data
        self.text = text
        self.headers = headers or {}

    def json(self):
        return self._json


class _Client:
    """Answers by URL, like the site's own routing."""

    def __init__(self, routes: dict):
        self.routes = routes
        self.calls: list[tuple[str, str]] = []

    async def get(self, url, headers=None, follow_redirects=True, **kwargs):
        self.calls.append(("GET", url))
        # Longest-needle first: "testpahe..." contains "pahe...",
        # so a naive first-match would hand back the shortlink's page.
        for needle, resp in sorted(self.routes.items(), key=lambda kv: -len(kv[0])):
            if needle in url:
                return resp
        return _Resp(404, text="not found")

    async def post(self, url, data=None, headers=None, follow_redirects=True, **kwargs):
        self.calls.append(("POST", url))
        # Longest-needle first: "testpahe..." contains "pahe...",
        # so a naive first-match would hand back the shortlink's page.
        for needle, resp in sorted(self.routes.items(), key=lambda kv: -len(kv[0])):
            if needle in url:
                return resp
        return _Resp(404, text="not found")

    async def __aexit__(self, *args):
        return None


@pytest.mark.asyncio
async def test_the_mapper_answers_with_the_per_quality_files():
    """One GET, no auth, no Cloudflare: the per-episode, per-quality
    shortlinks straight from the mapper."""
    client = _Client({"/api/mal/": _Resp(200, json_data=MAPPER_PAYLOAD)})
    resolver = KwikFileResolver()
    resolver._client = client

    files = await resolver.episode_files(34572, 1, 1778012242)

    assert [f.quality for f in files] == ["360p", "720p", "1080p"]
    assert files[0].url == "https://pahe.nekostream.site/yRVMl"
    assert files[0].audio == "sub"
    # The mapper is keyed by MAL id + episode + timestamp.
    assert "34572/1/1778012242" in client.calls[0][1]


@pytest.mark.asyncio
async def test_the_mapper_answers_nothing_for_a_series_it_does_not_have():
    """A series the mapper has no entry for is a RESULT, not a failure."""
    client = _Client({"/api/mal/": _Resp(400, json_data={"error": True, "message": "Failed to get the list"})})
    resolver = KwikFileResolver()
    resolver._client = client
    assert await resolver.episode_files(154587, 1, 1) == []


@pytest.mark.asyncio
async def test_the_shortlink_reaches_the_kwik_file_page():
    """pahe.nekostream -> testpahe (with the referer) -> kwik.cx/f/<token>."""
    client = _Client(
        {
            "pahe.nekostream.site/yRVMl": _Resp(200, text=SHORTLINK_PAGE),
            "testpahe.nekostream.site/yRVMl": _Resp(
                302, headers={"location": "https://kwik.cx/f/nHkd7KvJyRxT"}
            ),
        }
    )
    resolver = KwikFileResolver()
    resolver._client = client

    url = await resolver.kwik_file_url("https://pahe.nekostream.site/yRVMl")
    assert url == "https://kwik.cx/f/nHkd7KvJyRxT"


@pytest.mark.asyncio
async def test_the_file_page_yields_the_direct_media_url():
    """The page's own form: a CSRF'd POST to /d/<token>, whose 302 is
    the media file."""
    client = _Client(
        {
            "pahe.nekostream.site/yRVMl": _Resp(200, text=SHORTLINK_PAGE),
            "testpahe.nekostream.site/yRVMl": _Resp(
                302, headers={"location": "https://kwik.cx/f/nHkd7KvJyRxT"}
            ),
            "kwik.cx/f/": _Resp(200, text=KWIK_PAGE),
            "kwik.cx/d/": _Resp(
                302, headers={"location": "https://cdn.example/AnimePahe_Black_Clover_-_001_360p.mp4"}
            ),
        }
    )
    resolver = KwikFileResolver()
    resolver._client = client

    url = await resolver.media_url("https://pahe.nekostream.site/yRVMl")
    assert url == "https://cdn.example/AnimePahe_Black_Clover_-_001_360p.mp4"
    # The POST carried the page's CSRF token.
    post = next(c for c in client.calls if c[0] == "POST")
    assert post[1] == "https://kwik.cx/d/nHkd7KvJyRxT"


@pytest.mark.asyncio
async def test_without_a_clearance_the_kwik_page_is_not_reachable():
    """The kwik FILE page is the one guarded route: without a clearance
    it answers 403, and the resolver reports None (the caller falls back
    to the provider's own stream)."""
    client = _Client(
        {
            "pahe.nekostream.site/yRVMl": _Resp(200, text=SHORTLINK_PAGE),
            "testpahe.nekostream.site/yRVMl": _Resp(
                302, headers={"location": "https://kwik.cx/f/nHkd7KvJyRxT"}
            ),
            "kwik.cx/f/": _Resp(403, text="<html>Just a moment...</html>"),
        }
    )
    resolver = KwikFileResolver()
    resolver._client = client
    assert await resolver.media_url("https://pahe.nekostream.site/yRVMl") is None


@pytest.mark.asyncio
async def test_the_anikato_provider_offers_no_kwik_file_without_a_clearance():
    """A provider never opens a verification window on its own: without
    a stored clearance the kwik files are simply not there, and the
    megaplay stream path is untouched."""
    from services.providers.anikato import AniKatoProvider

    provider = AniKatoProvider()
    # No clearance in the store -> no kwik sources.
    assert await provider.kwik_file_sources("anikato:slug", "anikato:slug|1") == []


def test_the_mal_id_is_read_from_the_episode_list():
    """The mapper is keyed by MAL id, and AniKato's episode list carries
    data-mal on every episode link (Black Clover = 34572)."""
    from services.providers.anikato import _parse_mal_id, _quality_to_resolution

    html = '<a href="#" data-id="37933" data-num="1" data-mal="34572">ep</a>'
    assert _parse_mal_id(html) == 34572
    assert _parse_mal_id('<a data-num="1">no mal here</a>') == 0
    assert _quality_to_resolution("1080p") == 1080
    assert _quality_to_resolution("720") == 720
    assert _quality_to_resolution("weird") == 0


# ---------------------------------------------------------------------------
# EVERY quality and BOTH audios — the owner's question, answered by a test.
#
# "I think Anikato separates English with Japanese and stuff like that. So
#  I hope you did not just hardcode one." (owner, 2026-10-20)
#
# Live probes (2026-10-20) settle what the mapper serves, and it is not a
# fixed vocabulary: Black Clover ep 1 returns 360p/720p/1080p under "sub";
# Naruto ep 1 returns 360p/800p under "sub". So both the quality LABELS and
# the number of them come from the payload, and neither is written down
# anywhere in this repo.
# ---------------------------------------------------------------------------

# The shape a series with both audio groups returns.
SUB_AND_DUB_PAYLOAD = {
    "Kiwi": {
        "sub": {
            "download": {
                "360p": "https://pahe.nekostream.site/sub360",
                "720p": "https://pahe.nekostream.site/sub720",
                "1080p": "https://pahe.nekostream.site/sub1080",
            }
        },
        "dub": {
            "download": {
                "360p": "https://pahe.nekostream.site/dub360",
                "720p": "https://pahe.nekostream.site/dub720",
            }
        },
    },
    "status": {"time": 1792511062, "serves_from": "cache"},
}


@pytest.mark.asyncio
async def test_every_quality_and_both_audios_come_back_from_the_mapper():
    """Nothing is truncated to one: all five renditions, both audios."""
    client = _Client({"/api/mal/": _Resp(200, json_data=SUB_AND_DUB_PAYLOAD)})
    resolver = KwikFileResolver()
    resolver._client = client

    files = await resolver.episode_files(34572, 1, 1778012242)

    assert [(f.audio, f.quality) for f in files] == [
        ("sub", "360p"),
        ("sub", "720p"),
        ("sub", "1080p"),
        ("dub", "360p"),
        ("dub", "720p"),
    ]
    # Five distinct shortlinks — the mapper hands one link per rendition,
    # not one link reused.
    assert len({f.url for f in files}) == 5


@pytest.mark.asyncio
async def test_quality_labels_the_site_writes_differently_still_resolve():
    """Naruto serves 360p and 800p (live, 2026-10-20): the label is read,
    never assumed, so an unusual label still carries its resolution."""
    client = _Client(
        {
            "/api/mal/": _Resp(
                200,
                json_data={
                    "Kiwi": {
                        "sub": {
                            "download": {
                                "360p": "https://pahe.nekostream.site/a",
                                "800p": "https://pahe.nekostream.site/b",
                            }
                        }
                    }
                },
            )
        }
    )
    resolver = KwikFileResolver()
    resolver._client = client

    files = await resolver.episode_files(20, 1, 1729197616)
    assert [f.quality for f in files] == ["360p", "800p"]


def _stub_provider_for_kwik(provider, files, resolver_cls):
    """Wire a provider whose watch/entries/mal reads and resolver are
    fakes, so only the kwik-file branch is under test."""
    import services.store as store_mod

    async def _watch_page(_slug):
        return {"anime_id": 2121}

    async def _episode_entries(_anime_id):
        return [(1, "ids", True, True, 1778012242)]

    async def _episode_mal_id(_anime_id):
        return 34572

    async def _clearance(*_a, **_k):
        return {"cookies": "cf_clearance=abc", "user_agent": "ua"}

    provider._watch_page = _watch_page
    provider._episode_entries = _episode_entries
    provider._episode_mal_id = _episode_mal_id
    store_mod.get_store = lambda: type(
        "S", (), {"get_clearance": staticmethod(_clearance)}
    )()
    resolver_cls()


@pytest.mark.asyncio
async def test_every_kwik_file_reaches_the_picker_as_its_own_choice(monkeypatch):
    """End to end, the way the play/download dialogs see them: the
    provider turns each mapper entry into a Source, and the
    controller's ``_source_choices`` turns each Source into a distinct
    labelled row.

    This is the guard on the owner's exact worry — a hardcode that kept
    one quality would collapse here to a single row.
    """
    from services import kwik_files
    from services.providers.anikato import AniKatoProvider

    provider = AniKatoProvider()
    renditions = [
        ("sub", "1080p", "https://pahe.nekostream.site/sub1080"),
        ("sub", "720p", "https://pahe.nekostream.site/sub720"),
        ("sub", "360p", "https://pahe.nekostream.site/sub360"),
        ("dub", "720p", "https://pahe.nekostream.site/dub720"),
        ("dub", "360p", "https://pahe.nekostream.site/dub360"),
    ]

    class _FakeResolver:
        def __init__(self, *a, **k):
            pass

        async def episode_files(self, *a):
            return [
                kwik_files.KwikFile(q, url, audio) for audio, q, url in renditions
            ]

        async def media_url(self, shortlink):
            return f"https://kwik.cx/media/{shortlink.rsplit('/', 1)[-1]}"

        async def close(self):
            return None

    monkeypatch.setattr(kwik_files, "KwikFileResolver", _FakeResolver)
    _stub_provider_for_kwik(provider, None, lambda: None)

    sources = await provider.kwik_file_sources(
        "anikato:black-clover-g7tjy", "black-clover-g7tjy|1"
    )

    # Five files in, five sources out — none dropped, none collapsed.
    assert len(sources) == 5
    assert sorted(s.resolution for s in sources) == [360, 360, 720, 720, 1080]
    assert sorted(s.audio for s in sources) == ["eng", "eng", "jpn", "jpn", "jpn"]
    assert all(s.fansub == "AnimePahe" for s in sources)
    # The site's own file link rides along verbatim (the download row).
    assert all(
        s.download_url.startswith("https://pahe.nekostream.site/") for s in sources
    )

    # ...and the picker renders five DISTINCT rows.
    from main import _source_choices

    labels = [c["label"] for c in _source_choices(sources)]
    assert len(labels) == 5
    assert len(set(labels)) == 5
    assert sum("1080p" in label for label in labels) == 1
    assert sum("720p" in label for label in labels) == 2
    assert sum("360p" in label for label in labels) == 2
    assert sum("DUB (ENG)" in label for label in labels) == 2
    assert sum("SUB (JPN)" in label for label in labels) == 3


@pytest.mark.asyncio
async def test_a_kwik_file_that_cannot_be_resolved_never_hides_the_rest(
    monkeypatch,
):
    """One unreachable quality is skipped on its own; the others still
    reach the picker. (An early `return` on the first failure is what
    would ship exactly one quality, which is what the owner suspected.)"""
    from services import kwik_files
    from services.providers.anikato import AniKatoProvider

    provider = AniKatoProvider()

    class _FakeResolver:
        def __init__(self, *a, **k):
            pass

        async def episode_files(self, *a):
            return [
                kwik_files.KwikFile(
                    "1080p", "https://pahe.nekostream.site/good", "sub"
                ),
                kwik_files.KwikFile(
                    "720p", "https://pahe.nekostream.site/bad", "sub"
                ),
            ]

        async def media_url(self, shortlink):
            return None if "bad" in shortlink else "https://kwik.cx/media/good"

        async def close(self):
            return None

    monkeypatch.setattr(kwik_files, "KwikFileResolver", _FakeResolver)
    _stub_provider_for_kwik(provider, None, lambda: None)

    sources = await provider.kwik_file_sources(
        "anikato:black-clover-g7tjy", "black-clover-g7tjy|1"
    )
    assert [s.resolution for s in sources] == [1080]
