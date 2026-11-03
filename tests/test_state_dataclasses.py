"""Domain dataclasses must keep the 1.0.4 app's EXACT field names —
every provider maps to one shared model and the ported screens keep
working. This is the parity guard for that contract.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.state import Anime, Episode, LatestRelease, Source


def test_anime_fields_unchanged_from_1_0_4():
    expected = [
        "id",
        "title",
        "type",
        "episodes",
        "status",
        "season",
        "year",
        "score",
        "poster",
        "session",
    ]
    assert list(Anime.__dataclass_fields__)[:10] == expected


def test_episode_fields_unchanged_from_1_0_4():
    expected = [
        "id",
        "anime_id",
        "episode",
        "title",
        "snapshot",
        "disc",
        "audio",
        "duration",
        "session",
        "filler",
    ]
    assert list(Episode.__dataclass_fields__)[:10] == expected


def test_source_fields_unchanged_from_1_0_4():
    expected = ["url", "resolution", "audio", "fansub"]
    assert list(Source.__dataclass_fields__)[:4] == expected


def test_latest_release_fields_unchanged_from_1_0_4():
    expected = [
        "anime_id",
        "anime_title",
        "anime_session",
        "episode",
        "snapshot",
        "session",
        "created_at",
    ]
    assert list(LatestRelease.__dataclass_fields__) == expected


def test_records_construct_with_1_0_4_payloads():
    anime = Anime(1, "Frieren", "TV", 28, "Finished", "fall", 2023, 9.3, "p", "s1")
    assert anime.title == "Frieren"
    assert anime.session == "s1"

    ep = Episode(0, 1, 1, "Ep 1", "snap", "", "jpn", "24m", "e1", False)
    assert ep.episode == 1
    assert ep.audio == "jpn"

    src = Source("https://x/e.mkv", 1080, "SubsPlease", "src")
    assert src.resolution == 1080
    assert src.fansub == "src"
