"""KTV deep-link: base64 m3u8 + human title (the original format)."""

import base64
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from services.external_player import build_deep_link, episode_title


def test_episode_title_parts():
    assert episode_title("Frieren", 3, 1080) == "Frieren - Episode 3 - (1080p)"
    assert episode_title("Frieren", 3) == "Frieren - Episode 3"
    assert episode_title("Frieren") == "Frieren"


def test_deep_link_carries_base64_m3u8():
    url = "https://kwik.si/e/abc/master.m3u8"
    link = build_deep_link(url, "Frieren - Episode 3")
    assert link.startswith("ktv://play?url=")
    encoded, _, encoded_title = link[len("ktv://play?url=") :].partition("&title=")
    # base64url, padding stripped — decode with padding restored.
    padded = encoded + "=" * (-len(encoded) % 4)
    assert base64.urlsafe_b64decode(padded).decode() == url
    assert urllib.parse.unquote(encoded_title) == "Frieren - Episode 3"


def test_deep_link_carries_the_source_headers():
    """The handoff must carry the source's own headers/referer: the backends'
    CDNs answer a bare request with 403 (anikato needs Referer megaplay.buzz,
    animeout's file host is Cloudflare-walled and needs the clearance Cookie).
    KTV Player has parsed these params since v2.0.2."""
    import json

    url = "https://fetch.nexabloom.top/anime/x/index.m3u8"
    headers = {"Referer": "https://megaplay.buzz/", "User-Agent": "KTV/1.0"}
    link = build_deep_link(url, "Slime - Episode 1", headers=headers)
    query = urllib.parse.parse_qs(urllib.parse.urlparse(link).query)

    def _d(value: str) -> str:
        return base64.b64decode(value + "=" * (-len(value) % 4)).decode()

    assert _d(query["url"][0]) == url
    assert _d(query["referer"][0]) == "https://megaplay.buzz/"
    assert json.loads(_d(query["headers"][0])) == headers


def test_deep_link_omits_absent_headers():
    link = build_deep_link("https://x.test/s.m3u8", "Title")
    assert "referer=" not in link
    assert "headers=" not in link


def test_downloaded_episode_always_plays_in_app(monkeypatch):
    """Downloads stay in-app: KTV Player's deep link REJECTS local paths
    ("Deep link decoded invalid URL", verified on device) and the files live
    in this app's private storage, which Android does not let another app
    read. A handoff attempt there only launched a player that did nothing,
    so the feature is deliberately gone — external mode covers streams only."""
    import asyncio
    import os

    import main as app_main
    from core.state import state as app_state

    launches = []

    async def fake_launch(*args, **kwargs):
        launches.append(args)

    monkeypatch.setattr("services.external_player.launch_external", fake_launch)
    monkeypatch.setattr(os.path, "exists", lambda _p: True)

    class _Store:
        async def get_downloads(self):
            return {
                "ep-1": {
                    "state": "complete",
                    "file": "/private/downloads/show/ep-1/01.mkv",
                    "title": "Show",
                    "episode_num": 1,
                }
            }

        async def get_external_player(self):
            return True

    controller = app_main.AppController.__new__(app_main.AppController)
    controller.store = _Store()

    asyncio.run(controller.play_downloaded("ep-1"))

    assert launches == [], "a local download must never be handed off"
    assert app_state.player_spec["resource"] == "/private/downloads/show/ep-1/01.mkv"


def test_downloaded_episode_plays_in_app_when_external_is_off(monkeypatch):
    import asyncio
    import os

    import main as app_main
    from core.state import state as app_state

    monkeypatch.setattr(os.path, "exists", lambda _p: True)

    class _Store:
        async def get_downloads(self):
            return {
                "ep-1": {
                    "state": "complete",
                    "file": "/private/downloads/show/ep-1/01.mkv",
                    "title": "Show",
                    "episode_num": 1,
                }
            }

        async def get_external_player(self):
            return False

    controller = app_main.AppController.__new__(app_main.AppController)
    controller.store = _Store()

    asyncio.run(controller.play_downloaded("ep-1"))

    assert app_state.player_spec["resource"] == "/private/downloads/show/ep-1/01.mkv"
    assert app_state.player_open is True


def test_no_stream_never_launches_anything(monkeypatch):
    """Live run: with no resolved m3u8 the old code built
    animepahe.com/play/foreign:9538/… (another backend's session — a URL
    that can never resolve) and launched it, raising the KTV install
    dialog for nothing. Now it says the truth and launches nothing."""
    import asyncio

    import main as app_main

    launches = []

    async def fake_launch(*args, **kwargs):
        launches.append(args)

    monkeypatch.setattr("services.external_player.launch_external", fake_launch)

    controller = app_main.AppController.__new__(app_main.AppController)
    controller._resolved_m3u8 = None
    controller.page = None
    snacks = []
    controller._show_error_snackbar = snacks.append

    async def fake_resolve(_session):
        return {"title": "Black Clover"}

    controller._resolve_anime = fake_resolve

    asyncio.run(controller._open_external_player("animeout:9538", "9538|90"))

    assert launches == []
    assert snacks == ["No playable stream for this episode."]
