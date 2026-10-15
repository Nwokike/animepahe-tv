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


def test_no_stream_never_launches_anything(monkeypatch):
    """Live run: with no resolved m3u8 the old code built
    animepahe.com/play/kusonime:9538/… (another backend's session — a URL
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

    asyncio.run(controller._open_external_player("kusonime:9538", "9538|90"))

    assert launches == []
    assert snacks == ["No playable stream for this episode."]
