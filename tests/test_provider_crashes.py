"""Provider crash regressions — M1.2.

Each test kills one crash that shipped in the swarm audit:
- anikato sources(): 2-name unpack of the 5-tuple episode entries
  (ValueError on every call) + base64 query tokens sent unencoded
- kayoanime anime(): cached tuple returned where an Anime belongs,
  _quality never populated on the anime-first path, one folder's
  transport error aborting the whole episode walk
- animeout / kusonime episodes(): bare [] where the contract is a
  (episodes, has_more) tuple
- WP providers' latest_releases(): Anime rows where the home grid
  reads LatestRelease fields
"""

import asyncio

import pytest  # -----------------------------------------------------------------------

# anikato
# ---------------------------------------------------------------------------


def test_anikato_sources_resolves_without_the_unpack_crash():
    """The crash: `for n, ids in entries` over 5-tuples raised ValueError
    on EVERY sources() call — this provider's playback never ran."""
    from services.providers.anikato import AniKatoProvider

    provider = AniKatoProvider(client=object())

    async def fake_watch(slug):
        return {"anime_id": 958}

    async def fake_entries(anime_id):
        # (num, ids, subs, dub, aired_ts) — the real _parse_episode_list shape
        return [(219, "OTHER==", True, False, 0), (220, "TOKEN+/==", True, True, 0)]

    async def fake_servers(ids_token):
        assert ids_token == "TOKEN+/=="
        return [("sub", "LINK1")]

    async def fake_resolve(link_id):
        assert link_id == "LINK1"
        return ("realid1", "sub", "s1", {"intro": [0, 90]})

    async def fake_manifest(realid, kind, s):
        return ("https://megaplay.buzz/stream/index.m3u8", [], {"intro": {}, "outro": {}})

    async def fake_serves_video(manifest):
        return True  # this test is about the unpack crash, not door health

    provider._watch_page = fake_watch
    provider._episode_entries = fake_entries
    provider._server_links = fake_servers
    provider._resolve_link = fake_resolve
    provider._manifest_for = fake_manifest
    provider._door_serves_video = fake_serves_video

    sources = asyncio.run(provider.sources("anikato:naruto-eybxz", "naruto-eybxz|220"))
    assert len(sources) == 1
    assert sources[0].url.endswith("index.m3u8")


def test_anikato_server_list_encodes_the_base64_token():
    """ids_token is base64 (+/=): raw it corrupts the query (+ decodes as
    a space server-side)."""
    from services.providers.anikato import AniKatoProvider

    provider = AniKatoProvider(client=object())
    seen = {}

    async def fake_get_text(url, xhr=False):
        seen["url"] = url
        return '{"status": 200, "result": ""}'

    provider._get_text = fake_get_text
    asyncio.run(provider._server_links("aB+/=cD"))
    url = seen["url"]
    assert "servers=aB%2B%2F%3DcD" in url
    assert "+" not in url.partition("servers=")[2]


def test_anikato_report_sends_the_episode_number():
    """episode_id used to be sent empty; the site's own
    buildReportPostData sends the episode NUMBER."""
    from services.providers.anikato import AniKatoProvider

    posts = []

    class _Client:
        async def post(self, url, headers=None, content=None):
            posts.append((url, content.decode() if isinstance(content, bytes) else content))

            class _R:
                status_code = 200
                text = '{"status": true, "msg": "Reported."}'

            return _R()

    provider = AniKatoProvider(client=_Client())

    async def fake_watch(slug):
        return {"anime_id": 958}

    provider._watch_page = fake_watch
    ok, message = asyncio.run(
        provider.report_broken(
            "anikato:naruto-eybxz", "naruto-eybxz|220", ["video_broken"], note="x"
        )
    )
    assert ok is True
    url, body = posts[0]
    assert "episode_id=220" in body


# ---------------------------------------------------------------------------
# kayoanime
# ---------------------------------------------------------------------------


class _Resp:
    def __init__(self, status_code=200, json=None, text=""):
        self.status_code = status_code
        self._json = json
        self.text = text

    def json(self):
        return self._json


class _KayClient:
    """Routes by URL substring; returns the canned JSON for the provider."""

    def __init__(self, post, folder_files=None):
        self._post = post
        self._files = folder_files or []
        self.calls = []

    async def get(self, url, params=None, headers=None):
        self.calls.append(url)
        if "/wp-json/" in url and url.endswith("/posts"):
            # latest_releases hits the posts LIST endpoint.
            return _Resp(200, json=[self._post])
        if "/posts/" in url:
            return _Resp(200, json=self._post)
        if "googleapis.com" in url:
            return _Resp(200, json={"files": self._files})
        return _Resp(404)


def test_kayoanime_anime_cache_returns_anime_on_second_call():
    """The cache used to hold (anime, folders) and hand the tuple to
    callers typed for Anime."""
    from services.providers.kayoanime import KayoanimeProvider

    post = {
        "id": 5,
        "title": {"rendered": "Some Anime 1080p"},
        "content": {"rendered": '<a href="https://drive.google.com/drive/folders/F1">Box</a>'},
    }
    provider = KayoanimeProvider(client=_KayClient(post))
    first = asyncio.run(provider.anime("kayoanime:5"))
    assert first is not None and first.title == "Some Anime 1080p"
    second = asyncio.run(provider.anime("kayoanime:5"))
    assert second is first  # cached, not a tuple on the second call


def test_kayoanime_quality_is_set_on_the_anime_first_path():
    """sources() reads self._quality; the anime-first path (detail screen
    before episodes) never populated it, so resolution stayed 0."""
    from services.providers.kayoanime import KayoanimeProvider

    post = {
        "id": 5,
        "title": {"rendered": "Some Anime 1080p"},
        "content": {"rendered": '<a href="https://drive.google.com/drive/folders/F1">Box</a>'},
    }
    provider = KayoanimeProvider(client=_KayClient(post))
    asyncio.run(provider.anime("kayoanime:5"))
    sources = asyncio.run(provider.sources("kayoanime:5", "FILEID"))
    assert sources and sources[0].resolution == 1080


def test_kayoanime_one_failing_folder_does_not_abort_the_walk():
    """_list_folder used to be unguarded: the first transport error
    propagated out of episodes() and the whole list was lost."""
    from services.providers.kayoanime import KayoanimeProvider

    post = {
        "id": 5,
        "title": {"rendered": "Some Anime"},
        "content": {
            "rendered": (
                '<a href="https://drive.google.com/drive/folders/DEADFOLDERDEADFOLDERDEAD12">Dead</a>'
                '<a href="https://drive.google.com/drive/folders/GOODFOLDERGOODFOLDERGOOD12">Good</a>'
            )
        },
    }
    files = [
        {"id": "f1", "name": "[Kayoanime] Show - 007.mkv", "mimeType": "video/x-matroska", "size": "10000000"}
    ]
    provider = KayoanimeProvider(client=_KayClient(post, files))
    original = provider._list_folder

    async def flaky(folder_id):
        if folder_id.startswith("DEAD"):
            raise ConnectionError("boom")
        return await original(folder_id)

    provider._list_folder = flaky
    episodes, has_more = asyncio.run(provider.episodes("kayoanime:5", 1))
    assert [e.episode for e in episodes] == [7]


def test_kayoanime_multiseason_post_keeps_both_seasons():
    """The flat episode number collided across seasons: S01E05 and
    S02E05 both became '5' and dedupe kept one."""
    from services.providers.kayoanime import KayoanimeProvider

    post = {
        "id": 6,
        "title": {"rendered": "Dandadan"},
        "content": {"rendered": '<a href="https://drive.google.com/drive/folders/GOODFOLDERGOODFOLDERGOOD12">Box</a>'},
    }
    files = [
        {"id": "f1", "name": "[Kayoanime] Dandadan - S01E05.mkv", "mimeType": "video/x-matroska", "size": "10000000"},
        {"id": "f2", "name": "[Kayoanime] Dandadan - S02E05.mkv", "mimeType": "video/x-matroska", "size": "10000000"},
    ]
    provider = KayoanimeProvider(client=_KayClient(post, files))
    episodes, _ = asyncio.run(provider.episodes("kayoanime:6", 1))
    assert sorted(e.episode for e in episodes) == [5, 5]
    assert len({e.session for e in episodes}) == 2


# ---------------------------------------------------------------------------
# tuple contracts + release-grid shape
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "provider_factory",
    [
        lambda: __import__(
            "services.providers.animeout", fromlist=["AnimeOutProvider"]
        ).AnimeOutProvider(client=object()),
        lambda: __import__(
            "services.providers.kusonime", fromlist=["KusonimeProvider"]
        ).KusonimeProvider(client=object()),
    ],
)
def test_episodes_returns_a_tuple_for_a_bad_session(provider_factory):
    """A bare [] crashed every `episodes, has_more = ...` caller."""
    provider = provider_factory()
    result = asyncio.run(provider.episodes("animeout:not-a-number", 1))
    assert result == ([], False)


def test_releases_from_anime_builds_the_grid_shape():
    from core.state import LatestRelease
    from services.providers.animeout import AnimeOutProvider
    from services.providers.base import releases_from_anime

    rows = asyncio.run(AnimeOutProvider(client=object())._posts_to_anime([]))
    assert releases_from_anime(rows) == []

    from core.state import Anime

    anime = Anime(
        id=7, title="Show", type="TV", episodes=12, status="", season="", year=2025,
        score=8.0, poster="https://p/x.jpg", session="animeout:7",
    )
    releases = releases_from_anime([anime])
    assert isinstance(releases[0], LatestRelease)
    # The exact fields the home grid reads.
    assert releases[0].anime_session == "animeout:7"
    assert releases[0].anime_title == "Show"
    assert releases[0].snapshot == "https://p/x.jpg"
    assert releases[0].episode == 0 and releases[0].session == ""


def test_wp_providers_latest_releases_are_latestrelease_rows():
    """The home grid reads release.anime_session — Anime rows crashed it
    the first time a WP provider won the startup race."""
    from core.state import LatestRelease
    from services.providers.kayoanime import KayoanimeProvider

    post = {
        "id": 5,
        "title": {"rendered": "Some Anime"},
        "content": {"rendered": ""},
    }
    client = _KayClient(post)
    provider = KayoanimeProvider(client=client)
    # latest_releases hits the WP posts list; route it through /posts/.
    provider._client.get = client.get
    releases, _ = asyncio.run(provider.latest_releases(1))
    assert releases and all(isinstance(r, LatestRelease) for r in releases)
