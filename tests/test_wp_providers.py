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
        "title": {
            "rendered": "Sousou no Frieren 2nd Season(2026)(TV Series)(Complete)(Episode 10)"
        },
        "featured_media": 1033729,
    },
    {
        "id": 390955,
        "title": {"rendered": "Sousou no Frieren (2023)(Complete)(Episode 28)"},
        "featured_media": 739146,
    },
]
ANIMEOUT_MEDIA = [
    {
        "id": 1033729,
        "source_url": "https://animeout.xyz/wp-content/uploads/frieren-s2.jpg",
    },
]
ANIMEOUT_CONTENT = """
<p>Episodes:</p>
<a href="http://nimbus.animeout.com/series/00RAPIDBOT/Sousou no Frieren/[AnimeOut] Sousou no Frieren S2 - 01 1080pp [4277EF46][1080pp][SubsPlease][x265][RapidBot].mkv">01</a>
<a href="http://nimbus.animeout.com/series/00RAPIDBOT/Sousou no Frieren/[AnimeOut] Sousou no Frieren S2 - 02 1080pp [03D4DE77][1080pp][SubsPlease][x265][RapidBot].mkv">02</a>
<a href="http://typhon.animeout.com/series/00RAPIDBOT/Sousou no Frieren/[AnimeOut] Sousou no Frieren S2 - 03 1080pp [7556A22B][1080pp][SubsPlease][x265][RapidBot].mkv">03</a>
"""
ANIMEOUT_LANDING = (
    '<a href="https://ddl.animeout.com/public.php?url=nimbus.animeout.com/series/'
    "00RAPIDBOT/Sousou no Frieren/[AnimeOut] Sousou no Frieren S2 - 01 1080pp [4277EF46]"
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


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------
# AnimeOut — the WordPress way
# ---------------------------------------------------------------------


def test_animeout_search_maps_titles_years_and_ranking():
    from services.providers.animeout import (
        AnimeOutProvider,
        _clean_title,
        _title_relevance,
    )

    # the pure mapping first
    title, year, media_type = _clean_title(
        "Sousou no Frieren 2nd Season(2026)(TV Series)(Complete)(Episode 10)"
    )
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
    from services.providers.animeout import _episode_rows, _parse_episode_pairs

    pairs = _parse_episode_pairs(ANIMEOUT_CONTENT)
    assert [number for number, _ in pairs] == [1, 2, 3]
    results = _episode_rows(pairs, 1033730)
    assert [e.episode for e in results] == [1, 2, 3]
    assert results[0].title == "Episode 1"
    assert results[0].session.startswith("http://nimbus.animeout.com/")


def test_animeout_keeps_every_quality_of_one_episode():
    """A post serving both 1080p and 720p for the same episode must yield
    ONE row and TWO links — the old dedupe by episode number silently
    dropped the second quality, so the promised 1080p/720p choice could
    never appear."""
    from services.providers.animeout import (
        _episode_rows,
        _parse_episode_pairs,
        _variant_map,
    )

    html = """
    <a href="http://nimbus.animeout.com/s/[AnimeOut] Show S2 - 04 1080pp [AB12CD34][1080pp][SubsPlease][x265][RapidBot].mkv">04</a>
    <a href="http://nimbus.animeout.com/s/[AnimeOut] Show S2 - 04 720p [AB12CD35][720p][SubsPlease][x265][RapidBot].mkv">04</a>
    <a href="http://nimbus.animeout.com/s/[AnimeOut] Show S2 - 05 1080pp [AB12CD36][1080pp][SubsPlease][x265][RapidBot].mkv">05</a>
    """
    pairs = _parse_episode_pairs(html)
    rows = _episode_rows(pairs, 7)
    assert [e.episode for e in rows] == [4, 5]  # one row per episode
    # the row's session is the BEST quality
    assert "1080pp" in rows[0].session
    variants = _variant_map(pairs)
    assert len(variants[4]) == 2
    assert len(variants[5]) == 1
    # best-first inside the variant list
    assert "1080pp" in variants[4][0]


def test_animeout_filename_parses_quality_audio_fansub():
    from services.providers.animeout import _parse_filename

    res, audio, fansub = _parse_filename(
        "http://x/series/[AnimeOut] Sousou no Frieren S2 - 01 1080pp [4277EF46][1080pp][SubsPlease][x265][RapidBot].mkv"
    )
    assert res == 1080
    assert audio == "jpn"
    assert fansub == "SubsPlease"


def test_animeout_resolve_chain_follows_both_hops():
    from services.providers.animeout import _resolve_direct_url

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
    sources = _run(
        provider.sources("animeout:1033730", "http://nimbus.animeout.com/x - 01.mkv")
    )
    # The wall is external (CF on public.animeout.xyz today) — the chain
    # resolves, the host reports nothing, and nothing raises.
    assert sources == []


def test_animeout_sources_serves_every_quality_of_the_episode():
    """One tap on episode 4 offers both 1080p and 720p — the quality dialog
    finally has a real choice to make. The fake chain is routed per release
    hash so each variant resolves to its own landing page."""
    from services.providers.animeout import AnimeOutProvider

    def _landing(tag: str) -> str:
        return f'<a href="https://ddl.animeout.com/public.php?url=nimbus/{tag}">Download</a>'

    def _public(tag: str, quality: str) -> str:
        return (
            '<script>var url = "https://cdn.example/[AnimeOut] Show - 04 %s [%s][%s]'
            '[SubsProvide][x265][RapidBot].mkv";</script>' % (quality, tag, quality)
        )

    content = """
    <a href="http://nimbus.animeout.com/s/[AnimeOut] Show - 04 1080pp [AB12CD34][1080pp][SubsProvide][x265][RapidBot].mkv">04</a>
    <a href="http://nimbus.animeout.com/s/[AnimeOut] Show - 04 720p [AB12CD35][720p][SubsProvide][x265][RapidBot].mkv">04</a>
    """
    client = FakeClient(
        {
            "/posts/99": FakeResponse(
                200, json_data={"id": 99, "content": {"rendered": content}}
            ),
            # the specific routes must precede the generic ones
            "public.php?url=nimbus/AB12CD34": FakeResponse(
                200, text=_public("AB12CD34", "1080pp")
            ),
            "public.php?url=nimbus/AB12CD35": FakeResponse(
                200, text=_public("AB12CD35", "720p")
            ),
            "AB12CD34": FakeResponse(200, text=_landing("AB12CD34")),
            "AB12CD35": FakeResponse(200, text=_landing("AB12CD35")),
            "public.php": FakeResponse(200, text=ANIMEOUT_PUBLIC_PAGE),
            "nimbus": FakeResponse(200, text=ANIMEOUT_LANDING),
        }
    )
    provider = AnimeOutProvider(client=client)
    sources = _run(
        provider.sources(
            "animeout:99",
            "http://nimbus.animeout.com/s/[AnimeOut] Show - 04 1080pp [AB12CD34][1080pp][SubsProvide][x265][RapidBot].mkv",
        )
    )
    assert sorted(s.resolution for s in sources) == [720, 1080]
    assert all(s.fansub == "SubsProvide" for s in sources)
