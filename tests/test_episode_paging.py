"""Episode paging — Phase 3 Step 1.

The protocol has always promised ``episodes(session, page) -> (list,
has_more)``; the providers simply ignored ``page`` and returned the whole
list, so a 170-episode series dumped every card at once with a dead pager.
They now slice their already-cached full list to ``EPISODES_PER_PAGE``;
animepahe keeps its server pages.

The title-keyed lookups and the new-episode checker need the WHOLE list —
they walk pages through ``all_episodes`` instead of trusting page 1, which
is what the walk tests pin.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.state import Anime, Episode
from services.providers.anikato import AniKatoProvider
from services.providers.animeout import AnimeOutProvider
from services.providers.animepahe_provider import AnimePaheProvider
from services.providers.base import (
    EPISODES_PER_PAGE,
    all_episodes,
    page_slice,
)
from services.providers.kayoanime import KayoanimeProvider


def _eps(n: int) -> list[Episode]:
    return [
        Episode(
            id=i,
            anime_id=1,
            episode=i,
            title=f"Episode {i}",
            snapshot="",
            disc="",
            audio="jpn",
            duration="",
            session=f"ep{i}",
            filler=False,
        )
        for i in range(1, n + 1)
    ]


# ---------------------------------------------------------------------------
# The shared cap and its slice math
# ---------------------------------------------------------------------------


def test_the_house_cap_is_24():
    assert EPISODES_PER_PAGE == 24


def test_page_slice_math_and_edges():
    items = _eps(170)
    assert page_slice(items, 1)[0] == items[:24] and page_slice(items, 1)[1] is True
    # 170 = 7 full pages + 2 — the last page is the honest remainder.
    assert len(page_slice(items, 7)[0]) == 24 and page_slice(items, 7)[1] is True
    assert [e.episode for e in page_slice(items, 8)[0]] == [169, 170]
    assert page_slice(items, 8)[1] is False
    # Overflow is an empty page, not a wrap-around.
    assert page_slice(items, 9) == ([], False)
    # Page 0/negative behave as page 1 (callers never send them; the helper
    # must not alias to the tail).
    assert page_slice(items, 0)[0] == items[:24]
    assert page_slice([], 1) == ([], False)


# ---------------------------------------------------------------------------
# The four all-at-once providers page from their cached full list
# ---------------------------------------------------------------------------


def test_each_provider_pages_from_its_cached_full_list():
    cases = [
        (AniKatoProvider(client=None), "anikato:black-clover", "episodes_black-clover"),
        (AnimeOutProvider(client=None), "animeout:99", "episodes_99"),
        (KayoanimeProvider(client=None), "kayoanime:7", "episodes_7"),
    ]
    for provider, session, key in cases:
        # Seed exactly what a fresh fetch would cache: the FULL list.
        provider._cache_put(key, _eps(30), 300)
        first, more1 = asyncio.run(provider.episodes(session, 1))
        second, more2 = asyncio.run(provider.episodes(session, 2))
        third, more3 = asyncio.run(provider.episodes(session, 3))
        assert len(first) == 24 and more1 is True, session
        assert [e.episode for e in second] == list(range(25, 31)), session
        assert more2 is False, session
        assert third == [] and more3 is False, session


# ---------------------------------------------------------------------------
# A fresh fetch stores the full list and slices per page (anikato)
# ---------------------------------------------------------------------------


def test_anikato_fresh_fetch_slices_and_fetches_once():
    provider = AniKatoProvider(client=None)
    calls = {"watch": 0, "entries": 0}

    async def fake_watch(slug):
        calls["watch"] += 1
        return {"anime_id": 5, "poster": "p.jpg"}

    async def fake_entries(anime_id):
        calls["entries"] += 1
        # (num, ids, subs, dub, aired_ts) — the real 5-wide journal.
        return [(n, "tok", True, False, 0) for n in range(1, 51)]

    provider._watch_page = fake_watch
    provider._episode_entries = fake_entries

    first, more1 = asyncio.run(provider.episodes("anikato:slug", 1))
    second, more2 = asyncio.run(provider.episodes("anikato:slug", 2))
    third, more3 = asyncio.run(provider.episodes("anikato:slug", 3))

    assert [e.episode for e in first] == list(range(1, 25)) and more1 is True
    assert [e.episode for e in second] == list(range(25, 49)) and more2 is True
    assert [e.episode for e in third] == [49, 50] and more3 is False
    # The source was read once — every later page is a slice of the cache.
    assert calls == {"watch": 1, "entries": 1}


# ---------------------------------------------------------------------------
# animepahe keeps its own server pages
# ---------------------------------------------------------------------------


class _FakePaheScraper:
    def __init__(self):
        self.calls = []

    async def episodes(self, session, page):
        self.calls.append((session, page))
        return (_eps(2), page < 3)  # 3 server pages


def test_animepahe_provider_passes_server_pages_through():
    scraper = _FakePaheScraper()
    provider = AnimePaheProvider(scraper=scraper)
    episodes, has_more = asyncio.run(provider.episodes("uuid", 2))
    assert scraper.calls == [("uuid", 2)]  # the page reaches the server
    assert len(episodes) == 2 and has_more is True


# ---------------------------------------------------------------------------
# all_episodes — the whole-list walk the lookups and checker need
# ---------------------------------------------------------------------------


def test_all_episodes_walks_every_page():
    class _Paged:
        async def episodes(self, session, page):
            items = _eps(50)
            return page_slice(items, page)

    walked = asyncio.run(all_episodes(_Paged(), "s"))
    assert [e.episode for e in walked] == list(range(1, 51))


def test_all_episodes_caps_a_buggy_has_more():
    class _Stuck:
        async def episodes(self, session, page):
            return (_eps(1), True)  # has_more lies forever

    walked = asyncio.run(all_episodes(_Stuck(), "s", max_pages=3))
    assert len(walked) == 3  # bounded, not an infinite loop


# ---------------------------------------------------------------------------
# The page-1 consumers walk instead of trusting one page
# ---------------------------------------------------------------------------


def _anime(title: str, session: str) -> Anime:
    return Anime(
        id=1,
        title=title,
        type="TV",
        episodes=0,
        status="",
        season="",
        year=2024,
        score=0.0,
        poster="",
        session=session,
    )


def test_episodes_for_title_walks_all_pages_anikato():
    provider = AniKatoProvider(client=None)
    provider._cache_put("episodes_slug", _eps(50), 300)

    async def fake_search(query, page):
        return ([_anime("Black Clover", "anikato:slug")], False)

    provider.search = fake_search
    found = asyncio.run(provider.episodes_for_title("Black Clover"))
    # 50, not 24 — the failover lookup must see the whole series.
    assert len(found) == 50


def test_episodes_for_title_walks_server_pages_pahe():
    scraper = _FakePaheScraper()

    async def fake_search(query, page):
        return ([_anime("Black Clover", "uuid")], False)

    scraper.search = fake_search
    provider = AnimePaheProvider(scraper=scraper)
    found = asyncio.run(provider.episodes_for_title("Black Clover"))
    assert len(found) == 6  # 3 server pages x 2
    assert [c[1] for c in scraper.calls] == [1, 2, 3]
