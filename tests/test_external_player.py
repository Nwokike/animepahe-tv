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
