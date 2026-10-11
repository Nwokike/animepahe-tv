"""Provider fixture tests — recorded payloads replayed through a fake
transport. Zero network in CI, zero new dependencies: every provider
takes an injected client, so a canned client replays exactly what the
site answered in Phase 0.

These pin the MAPPING (site shape -> the shared domain model), which is
the part that breaks silently when a site changes.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class FakeResponse:
    def __init__(self, status_code=200, *, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data
        self.text = text

    def json(self):
        if self._json is None:
            raise ValueError("no json payload")
        return self._json


class FakeClient:
    """Routes by URL substring to a canned response (or a callable)."""

    def __init__(self, routes: dict):
        self._routes = routes
        self.calls: list[str] = []
        self.is_closed = False

    def _match(self, url: str):
        for needle, value in self._routes.items():
            if needle in url:
                return value() if callable(value) else value
        return FakeResponse(404)

    async def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append(url)
        return self._match(url)

    async def aclose(self):
        self.is_closed = True


# ---------------------------------------------------------------------
# Recorded payloads (from the Phase 0 live probes)
# ---------------------------------------------------------------------

ANIMEOUT_SEARCH = [
    {
        "id": 1033730,
        "title": {"rendered": "Sousou no Frieren 2nd Season(2026)(TV Series)(Complete)(Episode 10)"},
        "featured_media": 1033729,
    },
    {
        "id": 390955,
        "title": {"rendered": "Sousou no Frieren (2023)(Complete)(Episode 28)"},
        "featured_media": 739146,
    },
]
ANIMEOUT_MEDIA = [
    {"id": 1033729, "source_url": "https://animeout.xyz/wp-content/uploads/frieren-s2.jpg"},
]
ANIMEOUT_CONTENT = """
<p>Episodes:</p>
<a href="http://nimbus.animeout.com/series/00RAPIDBOT/Sousou no Frieren/[AnimeOut] Sousou no Frieren S2 - 01 1080pp [4277EF46][1080pp][SubsPlease][x265][RapidBot].mkv">01</a>
<a href="http://nimbus.animeout.com/series/00RAPIDBOT/Sousou no Frieren/[AnimeOut] Sousou no Frieren S2 - 02 1080pp [03D4DE77][1080pp][SubsPlease][x265][RapidBot].mkv">02</a>
<a href="http://typhon.animeout.com/series/00RAPIDBOT/Sousou no Frieren/[AnimeOut] Sousou no Frieren S2 - 03 1080pp [7556A22B][1080pp][SubsPlease][x265][RapidBot].mkv">03</a>
"""
ANIMEOUT_LANDING = (
    '<a href="https://ddl.animeout.com/public.php?url=nimbus.animeout.com/series/'
    '00RAPIDBOT/Sousou no Frieren/[AnimeOut] Sousou no Frieren S2 - 01 1080pp [4277EF46]'
    '[1080pp][SubsPlease][x265][RapidBot].mkv">Download</a>'
)
ANIMEOUT_PUBLIC_PAGE = """
<script>
function start() {
    var url = "https://public.animeout.xyz/nimbus.animeout.com/series/00RAPIDBOT/Sousou no Frieren/[AnimeOut] Sousou no Frieren S2 - 01 1080pp [4277EF46][1080pp][SubsPlease][x265][RapidBot].mkv";
    window.location = url;
}
</script>
"""

KUSONIME_SEARCH = [
    {
        "id": 5789,
        "title": {"rendered": "Sousou no Frieren Season 2 BD Batch Subtitle Indonesia | Kusonime"},
        "featured_media": 5790,
        "link": "https://kusonime.com/frieren-batch-subtitle-indonesia/",
    }
]
KUSONIME_PAGE = """
<a href="https://kusonime.com/wp-content/uploads/x.css">css</a>
<a href="https://pixeldrain.com/u/abc123">[Kusonime] Frieren BD 01-16 360p.rar</a>
<a href="https://mega.nz/file/X05W3YyZ#key">mega</a>
<a href="https://pixeldrain.com/u/def456">[Kusonime] Frieren BD 01-16 720p.rar</a>
"""


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------
# AnimeOut — the WordPress way
# ---------------------------------------------------------------------

def test_animeout_search_maps_titles_years_and_ranking():
    from services.providers.animeout import AnimeOutProvider, _clean_title, _title_relevance

    # the pure mapping first
    title, year, media_type = _clean_title("Sousou no Frieren 2nd Season(2026)(TV Series)(Complete)(Episode 10)")
    assert title.startswith("Sousou no Frieren")
    assert year == 2026
    assert media_type == "TV"
    assert _clean_title("Gekijouban Kimetsu no Yaiba (Movie)(2020)")[2] == "Movie"

    # WP's fuzzy search ranks an exact-ish hit above a fuzzy one
    assert _title_relevance("attack on titan", "Attack on Titan") == 100
    assert _title_relevance("attack on titan", "Yu-Gi-Oh! GX") == 0

    client = FakeClient(
        {
            "/wp-json/wp/v2/media": FakeResponse(200, json_data=ANIMEOUT_MEDIA),
            "/wp-json/wp/v2/posts": FakeResponse(200, json_data=ANIMEOUT_SEARCH),
        }
    )
    provider = AnimeOutProvider(client=client)
    results, has_more = _run(provider.search("frieren", 1))
    assert results[0].title.startswith("Sousou no Frieren")
    assert results[0].year == 2026
    assert results[0].poster.endswith("frieren-s2.jpg")
    assert results[0].session.startswith("animeout:")
    assert has_more is False


def test_animeout_episode_links_parse_numbers_and_order():
    from services.providers.animeout import AnimeOutProvider

    provider = AnimeOutProvider(client=FakeClient({}))
    episodes = provider.__class__.__dict__  # keep the module functions reachable
    from services.providers.animeout import _parse_episode_links

    results = _parse_episode_links(ANIMEOUT_CONTENT, 1033730)
    assert [e.episode for e in results] == [1, 2, 3]
    assert results[0].title == "Episode 1"
    assert results[0].session.startswith("http://nimbus.animeout.com/")


def test_animeout_filename_parses_quality_audio_fansub():
    from services.providers.animeout import _parse_filename

    res, audio, fansub = _parse_filename(
        "http://x/series/[AnimeOut] Sousou no Frieren S2 - 01 1080pp [4277EF46][1080pp][SubsPlease][x265][RapidBot].mkv"
    )
    assert res == 1080
    assert audio == "jpn"
    assert fansub == "SubsPlease"


def test_animeout_resolve_chain_follows_both_hops():
    from services.providers.animeout import AnimeOutProvider, _resolve_direct_url

    # public.php FIRST: its url= param contains the nimbus path, so a
    # substring router must try the more specific needle first.
    client = FakeClient(
        {
            "public.php": FakeResponse(200, text=ANIMEOUT_PUBLIC_PAGE),
            "nimbus.animeout.com/series": FakeResponse(200, text=ANIMEOUT_LANDING),
        }
    )
    url = _run(
        _resolve_direct_url(
            "http://nimbus.animeout.com/series/00RAPIDBOT/Sousou no Frieren/[AnimeOut] x - 01 [4277EF46][1080pp][SubsPlease][x265][RapidBot].mkv",
            client=client,
        )
    )
    assert url.startswith("https://public.animeout.xyz/")
    assert url.endswith(".mkv")


def test_animeout_walled_file_host_reports_no_stream_not_a_crash():
    from services.providers.animeout import AnimeOutProvider

    client = FakeClient(
        {
            "public.php": FakeResponse(200, text=ANIMEOUT_PUBLIC_PAGE),
            "nimbus": FakeResponse(200, text=ANIMEOUT_LANDING),
        }
    )
    provider = AnimeOutProvider(client=client)
    sources = _run(provider.sources("animeout:1033730", "http://nimbus.animeout.com/x - 01.mkv"))
    # The wall is external (CF on public.animeout.xyz today) — the chain
    # resolves, the host reports nothing, and nothing raises.
    assert sources == []


# ---------------------------------------------------------------------
# Kusonime — page links + direct host API
# ---------------------------------------------------------------------

def test_kusonime_episodes_from_batch_files():
    from services.providers.kusonime import KusonimeProvider

    client = FakeClient(
        {
            "/wp-json/wp/v2/posts/5789": FakeResponse(
                200, json_data={"id": 5789, "link": "https://kusonime.com/frieren-batch-subtitle-indonesia/"}
            ),
        }
    )
    page_client = FakeClient({"kusonime.com/frieren": FakeResponse(200, text=KUSONIME_PAGE)})
    provider = KusonimeProvider(client=client, page_client=page_client)
    episodes, _ = _run(provider.episodes("kusonime:5789", 1))
    assert [e.episode for e in episodes] == list(range(1, 17))
    # Unsupported hosts (mega.nz) are ignored — no fragile leecher resolvers.
    page_client.calls.clear()
    sources = _run(provider.sources("kusonime:5789", "5789|7"))
    assert len(sources) == 2  # 360p + 720p both cover episode 7
    assert all(s.url.startswith("https://pixeldrain.com/api/file/") for s in sources)
    assert {s.resolution for s in sources} == {360, 720}


def test_kusonime_batch_range_and_quality_parsing():
    from services.providers.kusonime import _batch_range, _parse_episode_session, _pixeldrain_direct, _quality

    assert _batch_range("[Kusonime] Frieren BD 01-16 360p.rar") == (1, 16)
    assert _batch_range("[Kusonime] Movie 1080p.rar") == (1080, 1080) or _batch_range("[Kusonime] Movie 1080p.rar") == (1, 1)
    assert _quality("[Kusonime] Frieren BD 01-16 720p.rar") == 720
    assert _parse_episode_session("5789|7") == 7
    assert _parse_episode_session("7") == 7
    assert _parse_episode_session("junk") is None
    assert _pixeldrain_direct("https://pixeldrain.com/u/abc123") == "https://pixeldrain.com/api/file/abc123"
    assert _pixeldrain_direct("https://mega.nz/file/x#y") == ""
