"""AniKato fixture tests — recorded payloads replayed with zero network.

The fixtures were captured live from anikototv.to during the Phase 0
probes (search page, watch page, VRF episode list, server list, a real
getSources enc token). These pin the MAPPING and the two fixed
transforms (the site's RC4 VRF and MegaPlay's AES-CBC enc), which are
the parts that break silently when a site changes.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _read(name: str) -> str:
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------
# Pure parsers
# ---------------------------------------------------------------------


def test_parse_items_maps_catalog_entries():
    from services.providers.anikato import _parse_items

    items = _parse_items(_read("anikato_search.html"))
    assert items, "search fixture must yield items"
    naruto = next(a for a in items if a.title == "Naruto")
    assert naruto.session == "anikato:naruto-eybxz"
    assert naruto.id == 958
    assert naruto.type == "TV"
    assert naruto.episodes == 220
    assert naruto.poster.startswith("https://cdn.anipixcdn.co/")
    assert naruto.year == 0  # not in the item markup — never invented


def test_parse_items_needs_no_bs4_and_survives_missing_fields():
    from services.providers.anikato import _parse_items

    junk = '<div class="item"><div class="inner">no links here</div></div>'
    assert _parse_items(junk) == []
    assert _parse_items("") == []


def test_parse_watch_maps_anime_id_and_metadata():
    from services.providers.anikato import _parse_watch

    watch = _parse_watch(_read("anikato_watch.html"))
    assert watch["anime_id"] == 958
    assert watch["poster"].startswith("https://cdn.anipixcdn.co/")


def test_parse_episode_list_maps_220_entries():
    from services.providers.anikato import _parse_episode_list

    entries = _parse_episode_list(_read("anikato_episode_list.html"))
    assert len(entries) == 220
    nums = [n for n, *_ in entries]
    assert nums[0] == 1 and 220 in nums
    # every entry carries the server-list token
    assert all(ids for _, ids, *_ in entries)
    # and the per-episode sub/dub flags and air timestamps the page serves
    # (not invented: at least one of each shape exists in a 220-episode run)
    assert any(subs for _n, _i, subs, _d, _ts in entries)
    assert any(dub for _n, _i, _s, dub, _ts in entries)
    assert any(ts for _n, _i, _s, _d, ts in entries)


def test_parse_servers_maps_sub_and_dub_groups():
    from services.providers.anikato import _parse_servers

    servers = _parse_servers(_read("anikato_servers.html"))
    kinds = {k for k, _ in servers}
    assert kinds == {"sub", "dub"}
    assert len(servers) >= 2  # at least one of each — nothing dropped


def test_megaplay_params_extracts_realid_type_and_s():
    from services.providers.anikato import _megaplay_params

    assert _megaplay_params("https://megaplay.buzz/stream/s-2/12352/sub?s=tcdn") == (
        "12352",
        "sub",
        "tcdn",
    )
    assert _megaplay_params("https://megaplay.buzz/videojs/stream/s-2/999/dub") == (
        "999",
        "dub",
        "",
    )
    assert _megaplay_params("https://megaplay.buzz/other") is None


# ---------------------------------------------------------------------
# The two fixed transforms
# ---------------------------------------------------------------------


def test_vrf_matches_the_site_scheme():
    from services.providers.anikato import _vrf

    # Recorded live in Phase 0: the site accepted exactly this token for
    # anime id 958.
    assert _vrf(958) == "LtGg"


def test_aes_decrypt_opens_the_live_enc_token():
    from services.aes import aes_cbc_decrypt
    from services.providers.anikato import _AES_IV, _AES_KEY, _decrypt_manifest

    enc = json.loads(_read("anikato_getsources.json"))["enc"]
    manifest = _decrypt_manifest(enc)
    assert manifest.startswith("https://")
    assert manifest.endswith("master.m3u8")
    # And the primitive agrees on the raw ciphertext round trip.
    import base64

    raw = base64.urlsafe_b64decode(enc + "=" * (-len(enc) % 4))
    plain = aes_cbc_decrypt(_AES_KEY, _AES_IV, raw)
    assert b"master.m3u8" in plain


# ---------------------------------------------------------------------
# Subtitles + skip data (Phase 1)
# ---------------------------------------------------------------------


def test_decrypt_returns_tracks_and_windows():
    """The full getSources payload: manifest + 9 tracks + intro/outro."""
    from services.providers.anikato import _decrypt_manifest

    enc = json.loads(_read("anikato_getsources.json"))["enc"]
    manifest = _decrypt_manifest(enc)
    gs = json.loads(_read("anikato_getsources.json"))
    # the provider normalizes tracks as {label, url, default}
    tracks = [
        {
            "label": str(t.get("label") or ""),
            "url": str(t.get("file") or ""),
            "default": bool(t.get("default")),
        }
        for t in (gs.get("tracks") or [])
        if t.get("file")
    ]
    assert manifest.endswith("master.m3u8")
    assert len(tracks) == 9
    english = [t for t in tracks if t["default"]]
    assert len(english) == 1 and english[0]["label"] == "English"
    # order and labels preserved exactly as served — nothing filtered
    assert tracks[0]["label"] == "Arabic"
    assert gs["intro"] == {"start": 30, "end": 119}
    assert gs["outro"] == {"start": 1315, "end": 1404}


def test_source_skip_merge_prefers_getsources_keeps_episode_arrays():
    """Both skip levels travel on the Source; the getSources object form
    is primary, the per-episode arrays stay as fallback."""
    from core.state import Source

    s = Source(
        url="https://x/master.m3u8",
        resolution=0,
        audio="jpn",
        fansub="AniKato",
        headers={"Referer": "https://megaplay.buzz/"},
        subtitles=[{"label": "English", "url": "https://x/eng-2.vtt", "default": True}],
        skip={
            "intro": {"start": 30, "end": 119},
            "outro": {"start": 1315, "end": 1404},
            "episode_intro": [0, 0],
            "episode_outro": [1280, 1369],
        },
    )
    assert s.skip["intro"]["start"] == 30
    assert s.skip["episode_outro"] == [1280, 1369]
    assert s.subtitles[0]["default"] is True


def test_vrf_bare_retry_fallback_exists():
    """The map proved the VRF is not server-enforced: the provider must
    keep sending it but fall back to the bare call on rejection."""
    import inspect

    from services.providers import anikato

    method_src = inspect.getsource(anikato.AniKatoProvider._episode_entries)
    assert "vrf=" in method_src  # still sent first, as the site's JS does
    assert "except Exception:" in method_src  # bare retry on rejection
    assert "style=list" in method_src


def test_player_window_math_accepts_both_shapes():
    from components.player.immersive_player import ImmersivePlayer as _IP  # noqa: F401

    """The skip chip's window helper: getSources serves objects, the
    per-episode skip_data serves arrays — both must work."""
    from components.player.immersive_player import ImmersivePlayer

    assert ImmersivePlayer._window({"start": 30, "end": 119}) == (30.0, 119.0)
    assert ImmersivePlayer._window([1280, 1369]) == (1280.0, 1369.0)
    assert ImmersivePlayer._window({}) is None
    assert ImmersivePlayer._window([1]) is None
    assert ImmersivePlayer._window("junk") is None


def test_player_active_window_prefers_sources_falls_back():
    from components.player.immersive_player import ImmersivePlayer

    player = ImmersivePlayer.__new__(ImmersivePlayer)  # no _build
    player.skip = {
        "intro": {"start": 30, "end": 119},
        "outro": {},
        "episode_intro": [],
        "episode_outro": [1280, 1369],
    }
    inside = player._active_window(60)
    assert inside == (30.0, 119.0)
    outside = player._active_window(200)
    assert outside is None
    # episode-array fallback when getSources served nothing
    player.skip = {
        "intro": {},
        "outro": {},
        "episode_intro": [],
        "episode_outro": [1280, 1369],
    }
    assert player._active_window(1300) == (1280.0, 1369.0)


def test_parse_watch_extracts_the_full_metadata_block():
    from services.providers.anikato import _parse_watch

    watch = _parse_watch(_read("anikato_watch.html"))
    assert watch["anime_id"] == 958
    assert watch["type"] == "TV"
    assert watch["status"] == "Finished Airing"
    assert watch["episodes"] == 220
    assert watch["score"] == 7.89
    assert watch["season"] == "FALL 2002"
    assert watch["aired"] == "Oct 3, 2002 to Feb 8, 2007"
    assert "Action" in watch["genres"]
    assert watch["synopsis"].startswith("Moments prior to Naruto")


def test_provider_anime_maps_the_watch_page():
    import asyncio

    from services.providers.anikato import AniKatoProvider

    class FakeClient:
        is_closed = False

        async def get(self, url, headers=None, timeout=None):
            class R:
                status_code = 200
                text = _read("anikato_watch.html")

                def json(self):
                    raise ValueError

            return R()

        async def aclose(self):
            pass

    provider = AniKatoProvider(client=FakeClient())
    anime = asyncio.run(provider.anime("anikato:naruto-eybxz"))
    assert anime.id == 958
    assert anime.title == "Naruto"
    assert anime.type == "TV"
    assert anime.episodes == 220
    assert anime.score == 7.89
    assert anime.year == 2002
    assert anime.synopsis.startswith("Moments prior")
    assert anime.session == "anikato:naruto-eybxz"
    # Genres parse on the watch page and reach the detail chips.
    assert "Action" in anime.genres and "Adventure" in anime.genres


def test_parse_schedule_tabs_and_day():
    from services.providers.anikato import _parse_schedule_day, _parse_schedule_tabs

    tabs = _parse_schedule_tabs(_read("anikato_schedule_tabs.html"))
    assert len(tabs) == 7
    assert tabs[0] == {"time": "1791158400", "date": "Oct 05", "weekday": "Mon"}
    day = _parse_schedule_day(_read("anikato_schedule_day.html"))
    assert day[0] == {
        "slug": "renegade-immortal-ogxqp",
        "episode": 161,
        "type": "sub",
        "time": "02:00",
        "title": "Renegade Immortal",
    }
    assert len(day) == 6
    # sub and dub rows stay separate as served — nothing merged
    types = {e["type"] for e in day}
    assert types <= {"sub", "dub"}


# ---------------------------------------------------------------------
# AnimePahe m=links (Phase 2) — the six-client-attested response shape
# ---------------------------------------------------------------------


def test_animepahe_sources_via_links_parses_renditions():
    import asyncio

    from services.providers.animepahe_provider import AnimePaheProvider

    LINKS_RESPONSE = {
        "status": 200,
        "data": {
            "360": {
                "audio": "jpn",
                "kwik": "https://kwik.si/e/abc360",
                "hd": "0",
                "filesize": 87.5,
            },
            "720": {
                "audio": "jpn",
                "kwik": "https://kwik.si/e/abc720",
                "hd": "1",
                "filesize": 176.2,
            },
            "1080": {
                "audio": "jpn",
                "kwik": "https://kwik.si/e/abc1080",
                "hd": "1",
                "filesize": 293.0,
            },
        },
    }

    class FakeScraper:
        ddos = None

        async def _fetch_api(self, params):
            assert params["m"] == "links"
            assert params["id"] == "958"
            assert params["p"] == "kwik"

            class R:
                def json(self):
                    return LINKS_RESPONSE

            return R()

    provider = AnimePaheProvider(scraper=FakeScraper())
    provider._anime_ids["ep-sess"] = 958
    # The play page is the live path (probe 2026-10-16); the retired
    # m=links JSON route is kept only as the last-resort fallback, so its
    # parser is exercised directly.
    sources = asyncio.run(provider._sources_via_links("pahe-anime", "ep-sess"))
    assert [s.resolution for s in sources] == [360, 720, 1080]
    assert all(s.audio == "jpn" for s in sources)
    assert sources[2].url == "https://kwik.si/e/abc1080"
    assert sources[1].size == "176.2MB"
    # hd marks the HD renditions in the fansub label; the 360 is unmarked.
    assert sources[0].fansub == "AnimePahe"
    assert sources[1].fansub == "AnimePahe HD"
    assert sources[2].fansub == "AnimePahe HD"


def test_animepahe_the_live_path_serves_before_the_retired_json():
    """Order probe 2026-10-16: the play page IS the site's mechanism (its
    markup never calls m=links), so it is tried FIRST; the retired JSON
    route is only the last resort. The fake scraper's sources() returns a
    rendition, so _fetch_api must never fire."""
    import asyncio

    from core.state import Source
    from services.providers.animepahe_provider import AnimePaheProvider

    class FakeScraper:
        ddos = None

        async def _fetch_api(self, params):
            raise AssertionError("m=links must not fire while the page serves")

        async def sources(self, a, e):
            return [
                Source(
                    url="https://kwik.si/e/live-path",
                    resolution=720,
                    audio="jpn",
                    fansub="Subs",
                )
            ]

    provider = AnimePaheProvider(scraper=FakeScraper())
    provider._anime_ids["ep-sess"] = 958
    sources = asyncio.run(provider.sources("pahe-anime", "ep-sess"))
    assert sources[0].url.endswith("live-path")


def test_animepahe_without_an_anime_id_the_page_still_serves():
    import asyncio

    from core.state import Source
    from services.providers.animepahe_provider import AnimePaheProvider

    class FakeScraper:
        ddos = None

        async def _fetch_api(self, params):
            raise AssertionError("m=links needs the id and must not fire here")

        async def sources(self, a, e):
            return [
                Source(
                    url="https://kwik.si/e/scraped",
                    resolution=1080,
                    audio="jpn",
                    fansub="Subs",
                )
            ]

    provider = AnimePaheProvider(scraper=FakeScraper())
    sources = asyncio.run(provider.sources("pahe-anime", "unknown-ep"))
    assert sources[0].resolution == 1080


# ---------------------------------------------------------------------
# AnimePahe details page (Phase 2) — selector evidence from the map
# ---------------------------------------------------------------------


def test_animepahe_details_parses_the_page():

    from services.providers.animepahe_provider import _parse_details

    # Representative markup per the map's three-convergent selectors.
    DETAILS_HTML = """
    <div class="title-wrapper"><h1><span>Shangri-La Frontier</span></h1></div>
    <h2 class="japanese">シャングリラ・フロンティア</h2>
    <div class="anime-poster"><a href="https://img.example/slf.jpg"></a></div>
    <div class="anime-synopsis">Fortune favours the players.<br/>Second line.</div>
    <div class="anime-info">
      <p><b>Type:</b> TV</p>
      <p><b>Episodes:</b> 25</p>
      <p><b>Status:</b> Currently Airing</p>
      <p><b>Aired:</b> Oct 1, 2023 to Mar 24, 2024</p>
      <p><b>Season:</b> Fall 2023</p>
      <p><b>Studio:</b> C2C</p>
    </div>
    <div class="anime-genre"><ul>
      <a title="Action movies"><li>Action</li></a>
      <a title="Adventure movies"><li>Adventure</li></a>
    </ul></div>
    <div class="external-links">
      <a href="https://anilist.co/anime/166531" target="_blank"></a>
      <a href="https://myanimelist.net/anime/56621" target="_blank"></a>
    </div>
    <script>release&id=4471&l=2</script>
    """
    anime = _parse_details(DETAILS_HTML, "shangri-la-frontier")
    assert anime is not None
    assert anime.title == "Shangri-La Frontier"
    assert anime.type == "TV"
    assert anime.episodes == 25
    assert anime.status == "Currently Airing"
    assert anime.season == "Fall 2023"
    assert anime.year == 2023
    assert anime.synopsis.startswith("Fortune favours")
    assert "Action" in anime.genres and "Adventure" in anime.genres
    assert anime.anilist_id == 166531
    assert anime.mal_id == 56621
    assert anime.id == 4471  # the numeric id m=links needs
    assert anime.session == "shangri-la-frontier"
    # Studios and the aired range are on the page and reach the screen now.
    assert anime.studios == ["C2C"]
    assert anime.aired == "Oct 1, 2023 to Mar 24, 2024"


def test_animepahe_details_co_production_splits_studios():
    from services.providers.animepahe_provider import _parse_details

    html = """
    <div class="title-wrapper"><h1><span>T</span></h1></div>
    <div class="anime-info"><p><b>Studio:</b> C2C, SoftBank / Hull</p></div>
    """
    anime = _parse_details(html, "t")
    assert anime is not None
    assert anime.studios == ["C2C", "SoftBank", "Hull"]


def test_animepahe_details_absent_studio_is_empty_not_invented():
    from services.providers.animepahe_provider import _parse_details

    html = '<div class="title-wrapper"><h1><span>T</span></h1></div>'
    anime = _parse_details(html, "t")
    assert anime is not None
    assert anime.studios == []
    assert anime.aired == ""


def test_animepahe_details_garbage_returns_none():
    from services.providers.animepahe_provider import _parse_details

    assert _parse_details("<html>totally not a details page</html>", "s") is None


def test_animepahe_anime_uses_ddos_get():
    import asyncio

    from services.providers.animepahe_provider import AnimePaheProvider

    seen: list[str] = []

    class FakeDdos:
        async def get(self, url):
            seen.append(url)

            class R:
                status_code = 200
                text = DETAILS_FIXTURE

            return R()

    DETAILS_FIXTURE = "<div class='title-wrapper'><h1><span>T</span></h1></div>"
    # The real scraper exposes ddos but NOT a BASE attribute (it is a
    # module constant) — a fake that invents one hides that mismatch.
    provider = AnimePaheProvider(scraper=type("S", (), {"ddos": FakeDdos()})())
    anime = asyncio.run(provider.anime("some-session"))
    assert anime is not None and anime.title == "T"
    assert seen == ["https://animepahe.com/anime/some-session"]


def test_kwik_referer_follows_the_issued_host():
    """The kwik family rotates (cx -> si -> pw) — a stale-host Referer is
    what CDNs reject. The resolver must derive it from the URL."""
    from services.kwik_resolver import KwikResolver

    resolver = KwikResolver(ddos_solver=None)
    assert resolver._headers("https://kwik.si/e/abc")["Referer"] == "https://kwik.si/"
    assert resolver._headers("https://kwik.cx/e/abc")["Referer"] == "https://kwik.cx/"
    # unparseable host keeps the historical default
    assert resolver._headers("not-a-kwik-url")["Referer"] == "https://kwik.cx/"


def test_play_page_scrape_carries_av1_and_download_sizes():
    import asyncio

    from services.animepahe import AnimePaheScraper

    PLAY_PAGE = """
    <div id="resolutionMenu">
      <button data-src="https://kwik.si/e/av1one" data-resolution="1080" data-audio="jpn" data-fansub="SubsPlease" data-av1="1"></button>
      <button data-src="https://kwik.si/e/plain" data-resolution="720" data-audio="jpn" data-fansub="SubsPlease"></button>
    </div>
    <div id="pickDownload">
      <a href="https://pahe.win/abc123">SubsPlease · 1080p (293MB) [BD]</a>
      <a href="https://pahe.win/def456">SubsPlease · 720p (176MB)</a>
    </div>
    """

    class FakeDdos:
        async def get(self, url):
            class R:
                status_code = 200
                text = PLAY_PAGE

            return R()

    scraper = AnimePaheScraper()
    scraper.ddos = FakeDdos()
    sources = asyncio.run(scraper._sources_data_src("a", "e"))
    assert sources[0].fansub.endswith("AV1")  # the codec qualifier rides the name
    assert sources[0].resolution == 1080
    assert sources[0].size == "293MB"  # zipped positionally from pickDownload
    assert sources[1].size == "176MB"


def test_position_row_carries_and_restores_rate():
    """The chosen speed rides the resume record."""
    import asyncio
    import tempfile

    from services.store import JsonStore

    async def run(path):
        store = JsonStore(filename=path)
        await store.save_position("ep1", 30.0, 1440.0, rate=1.5)
        entry = await store.get_position("ep1")
        assert entry["rate"] == 1.5
        assert entry["position"] == 30.0
        # an old row without a rate still reads (None = 1.0)
        await store.save_position("ep2", 10.0, 1440.0)
        assert (await store.get_position("ep2")).get("rate") is None

    fd, path = tempfile.mkstemp()
    import os

    os.close(fd)
    asyncio.run(run(path))


def test_adapter_no_op_without_extension():
    """Every call site degrades: the import may succeed while the calls
    no-op off-platform — nothing may raise."""


def test_follow_progress_round_trip():
    import asyncio
    import tempfile

    from services.store import JsonStore

    async def run(path):
        store = JsonStore(filename=path)
        await store.add_follow({"anime_session": "s", "title": "T", "poster": ""})
        assert await store.get_follow_progress("s") == 0  # legacy row reads 0
        await store.set_follow_progress("s", 42)
        assert await store.get_follow_progress("s") == 42
        await store.set_follow_progress("unknown", 7)  # not a follow: ignored
        row = (await store.get_follows())["s"]
        assert row["title"] == "T" and row["last_seen_episode"] == 42

    fd, path = tempfile.mkstemp()
    import os

    os.close(fd)
    asyncio.run(run(path))


def test_focus_scope_is_a_plain_function():
    """The component form is a crash class (frozen subtree) — the hook
    must be a plain function returning the listener."""
    import flet as ft

    from hooks.use_focus_scope import focus_scope

    seen = []

    class _FakePage:
        def run_task(self, fn):
            seen.append(fn)

    # KTV's bounds-bearing wrapper: an expanding Container around the
    # listener (a bare listener gives the player Stack no bounds — audio
    # with an empty surface).
    wrapper = focus_scope(ft.Container(), lambda: seen.append("back"))
    assert isinstance(wrapper, ft.Container)
    assert wrapper.expand is True
    listener = wrapper.content
    assert isinstance(listener, ft.KeyboardListener)
    assert listener.autofocus is True


def test_focus_manager_chains_instead_of_overwriting():
    """A second installer must not kill the first's handler."""
    import types

    from core.focus_manager import FocusManager

    page = types.SimpleNamespace()
    seen = []
    page.on_keyboard_event = lambda e: seen.append("old")
    mgr = FocusManager(page)
    mgr.set_back_handler(lambda: seen.append("back"))
    # simulate a Back event through the chain
    ev = types.SimpleNamespace(key="Back")
    page.on_keyboard_event(ev)
    assert "old" in seen and "back" in seen
    # restore is identity-guarded
    mgr.restore()
    assert page.on_keyboard_event is not None
    seen.clear()
    page.on_keyboard_event(ev)
    assert seen == ["old"]  # ours stepped aside, the old handler remains


def test_history_clear_returns_rows_and_restore_puts_them_back():
    """Undo: the clear hands back the exact rows; the restore returns
    them (MRU order intact)."""
    import asyncio
    import tempfile

    from services.store import JsonStore

    async def run(path):
        store = JsonStore(filename=path)
        await store.add_search_selection("One Piece", "s1")
        await store.add_search_selection("Frieren", "s2")
        cleared = await store.clear_search_history()
        assert await store.get_search_history() == []
        assert [r["title"] for r in cleared] == ["Frieren", "One Piece"]
        await store.restore_search_history(cleared)
        restored = await store.get_search_history()
        assert [r["title"] for r in restored] == ["Frieren", "One Piece"]
        assert restored[0]["session"] == "s2"

    fd, path = tempfile.mkstemp()
    import os

    os.close(fd)
    asyncio.run(run(path))


def test_episode_flags_are_captured_not_dropped():
    """data-sub/data-dub were parsed away, so the card could never say an
    episode has a dub. The parser reads them per tag (order-independent).
    """
    from services.providers.anikato import _parse_episode_list

    html = (
        '<li><a href="#" data-id="1" data-num="1" data-slug="1" data-mal="20"'
        ' data-timestamp="1729197616" data-sub="1" data-dub="1" data-ids="AAA"'
        ' class="active"></a></li>'
        '<li><a href="#" data-ids="BBB" data-num="2" data-sub="0" data-dub="0"></a></li>'
        '<li><a href="#" data-num="3" data-ids="CCC" data-sub="1" data-dub="0"></a></li>'
    )
    entries = _parse_episode_list(html)
    assert entries == [
        (1, "AAA", True, True, 1729197616),
        (2, "BBB", False, False, 0),
        (3, "CCC", True, False, 0),
    ]


def test_episode_flags_absent_means_false_not_a_crash():
    from services.providers.anikato import _parse_episode_list

    entries = _parse_episode_list('<a data-num="5" data-ids="ZZZ"></a>')
    assert entries == [(5, "ZZZ", False, False, 0)]


def test_episode_air_timestamps_are_captured():
    """The timestamp was dropped along with the flags — the card now shows
    the air date."""
    from services.providers.anikato import _parse_episode_list

    html = (
        '<a data-id="1" data-num="1" data-ids="AAA" data-timestamp="1729197616"'
        ' data-sub="1" data-dub="0"></a>'
        '<a data-num="2" data-ids="BBB" data-sub="0" data-dub="0"></a>'
    )
    entries = _parse_episode_list(html)
    assert entries == [
        (1, "AAA", True, False, 1729197616),
        (2, "BBB", False, False, 0),
    ]


def test_pick_download_menu_is_the_sites_own_offering():
    """div#pickDownload names the fansub, quality, size and BD badge per
    rendition, with a pahe.win link — the site's download route, not a
    guess at one."""
    from services.animepahe import _parse_pick_download

    html = (
        '<div id="pickDownload">'
        '<a href="https://pahe.win/abc123">MiG_MuX · 720p (176MB) [BD]</a>'
        '<a href="https://pahe.win/def456">MiG_MuX · 1080p (293MB) [BD]</a>'
        '<a href="https://pahe.win/ghi789">SubsPlease · 480p (52MB)</a>'
        "</div>"
    )
    entries = _parse_pick_download(html)
    assert [e["quality"] for e in entries] == [720, 1080, 480]
    assert [e["size"] for e in entries] == ["176MB", "293MB", "52MB"]
    assert [e["bd"] for e in entries] == [True, True, False]
    assert entries[0]["url"] == "https://pahe.win/abc123"
    assert all(e["fansub"] for e in entries)
    assert entries[2]["fansub"] == "SubsPlease"


def test_pick_download_unlabelled_entries_keep_their_url_and_size():
    from services.animepahe import _parse_pick_download

    html = '<div id="pickDownload"><a href="https://pahe.win/x1">Download</a></div>'
    (entry,) = _parse_pick_download(html)
    assert entry["url"] == "https://pahe.win/x1"
    assert entry["size"] == ""
    assert entry["quality"] == 0
    assert entry["bd"] is False


def test_details_page_carries_the_cover():
    """The map's verified selector for the page's own backdrop; absent it
    stays empty and the detail screen blurs the poster as before."""
    from services.providers.animepahe_provider import _parse_details

    html = (
        '<div class="title-wrapper"><h1><span>T</span></h1></div>'
        '<div class="header-wrapper" data-src="https://img.example/cover.jpg"></div>'
    )
    anime = _parse_details(html, "t")
    assert anime is not None
    assert anime.backdrop == "https://img.example/cover.jpg"

    bare = _parse_details('<div class="title-wrapper"><h1><span>T</span></h1></div>', "t")
    assert bare.backdrop == ""


class _PostClient:
    """anikato's client surface for the report: GET the watch page, POST
    the form."""

    def __init__(
        self, watch_text="", post_status=200, post_body='{"status":true,"msg":"Reported."}'
    ):
        self._watch_text = watch_text
        self._post_status = post_status
        self._post_body = post_body
        self.posts: list[tuple[str, object]] = []
        self.is_closed = False

    async def get(self, url, headers=None):
        class R:
            status_code = 200
            text = self._watch_text

        return R()

    async def post(self, url, headers=None, content=None):
        self.posts.append((url, content))

        class R:
            status_code = self._post_status
            text = self._post_body

        return R()

    async def aclose(self):
        self.is_closed = True


def test_report_broken_stream_posts_the_sites_own_form():
    import asyncio

    from services.providers.anikato import AniKatoProvider

    watch = '<div id="watch-main" data-id="958"></div><div class="anime-synopsis">x</div>'
    client = _PostClient(watch_text=watch)
    provider = AniKatoProvider(client=client)
    ok, message = asyncio.run(
        provider.report_broken(
            "anikato:naruto-eybxz",
            "naruto-eybxz|220",
            ["video_broken", "sub_sync"],
            note="stops at 4:10",
            server_name="HD-1",
        )
    )
    assert ok is True
    assert message == "Reported."
    (url, body) = client.posts[0]
    assert url.endswith("/ajax/episode/report")
    # primp's content arg is bytes — the old code passed a str, which the
    # Rust layer rejects.
    if isinstance(body, bytes):
        body = body.decode()
    # the repeated field survives: one issue[] per checked issue
    assert body.count("issue%5B%5D=") == 2
    assert "video_broken" in body and "sub_sync" in body
    assert "show_id=958" in body
    # episode_id is the site's own episode NUMBER (buildReportPostData),
    # not a row id — it used to be sent empty.
    assert "episode_id=220" in body
    assert "show_slug=naruto-eybxz" in body
    assert "stops+at+4%3A10" in body


def test_report_broken_stream_validates_before_the_wire():
    """The site's own rule: at least one issue or a note. Surfaced before
    any request is made, in the site's words."""
    import asyncio

    from services.providers.anikato import AniKatoProvider

    client = _PostClient()
    provider = AniKatoProvider(client=client)
    ok, message = asyncio.run(provider.report_broken("anikato:x", "x|1", [], note=""))
    assert ok is False
    assert "issue" in message
    assert client.posts == []


def test_report_broken_stream_with_a_note_only_is_sent():
    import asyncio

    from services.providers.anikato import AniKatoProvider

    client = _PostClient(watch_text='<div id="watch-main" data-id="7"></div>')
    provider = AniKatoProvider(client=client)
    ok, _ = asyncio.run(provider.report_broken("anikato:x", "x|2", [], note="audio drifts"))
    assert ok is True
    assert len(client.posts) == 1


class _ZipClient:
    """The play page: resolutionMenu buttons in one order, pickDownload
    anchors in ANOTHER (the map's captured order is 720p then 1080p)."""

    def __init__(self, html):
        self._html = html
        self.is_closed = False

    async def get(self, url, headers=None, timeout=None):
        class R:
            status_code = 200
            text = self._html

        return R()

    async def aclose(self):
        self.is_closed = True


def test_pick_download_matches_by_quality_not_by_position():
    """The menu's order and the buttons' order differ. A positional zip
    attaches 720p's size to the 1080p button — the map even captures the
    menu as 720p-then-1080p."""
    from services.animepahe import AnimePaheScraper

    page = """
    <div class="resolutionMenu">
      <button data-src="https://kwik.si/e/hd1080" data-resolution="1080" data-audio="jpn" data-fansub="MiG_MuX"></button>
      <button data-src="https://kwik.si/e/hd720" data-resolution="720" data-audio="jpn" data-fansub="MiG_MuX"></button>
    </div>
    <div id="pickDownload">
      <a href="https://pahe.win/a720">MiG_MuX · 720p (176MB) [BD]</a>
      <a href="https://pahe.win/a1080">MiG_MuX · 1080p (293MB) [BD]</a>
    </div>
    """
    import asyncio

    scraper = AnimePaheScraper()
    scraper.ddos = _ZipClient(page)
    sources = asyncio.run(scraper.sources("session", "ep1"))
    by_resolution = {s.resolution: s for s in sources}
    # each rendition carries its OWN size and its OWN pahe.win link
    assert by_resolution[1080].size == "293MB"
    assert by_resolution[1080].download_url == "https://pahe.win/a1080"
    assert by_resolution[720].size == "176MB"
    assert by_resolution[720].download_url == "https://pahe.win/a720"
    assert all(s.bd for s in sources)
