"""One rendition, one choice — Phase 3 Step 3.

The single-option auto-start gates (`len(choices) <= 1` in the play,
external and download paths) were always right; the failure was that one
logical rendition could produce two Source entries, so the picker asked a
question with two identical answers — kayoanime emitted its play route
(alt=media) and its download route (usercontent) as separate Sources, and
AniKato's master-only sources rendered "0p" in the label. Now: kayoanime
returns ONE Source (play url + download_url), `_source_choices` collapses
logical renditions, and an unknown resolution prints nothing.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.state import Source
from main import _source_choices
from services.providers.kayoanime import KayoanimeProvider


def test_duplicate_logical_renditions_collapse():
    sources = [
        Source("u1", 0, "jpn", "Kayoanime"),
        Source("u2", 0, "jpn", "Kayoanime"),  # the same stream, other route
    ]
    choices = _source_choices(sources)
    assert len(choices) == 1
    assert choices[0]["url"] == "u1"  # best-first entry wins


def test_distinct_renditions_all_stay():
    sources = [
        Source("u1", 1080, "jpn", "F"),
        Source("u2", 720, "jpn", "F"),
        Source("u3", 1080, "eng", "F"),
        Source("u4", 1080, "jpn", "F", size="300MB"),
        Source("u5", 1080, "jpn", "Other"),
    ]
    choices = _source_choices(sources)
    assert len(choices) == 5
    # SUB before DUB, each best-first — the ordering the dialogs rely on.
    assert [c["url"] for c in choices] == ["u1", "u4", "u5", "u2", "u3"]


def test_unknown_resolution_never_prints_zero_p():
    choices = _source_choices([Source("u", 0, "jpn", "AniKato")])
    assert choices[0]["label"] == "SUB (JPN) (AniKato)"
    assert "0p" not in choices[0]["label"]

    choices = _source_choices([Source("u", 1080, "jpn", "Fansub")])
    assert choices[0]["label"] == "1080p - SUB (JPN) (Fansub)"


def test_kayoanime_is_one_source_with_a_download_route():
    provider = KayoanimeProvider(client=None)
    provider._quality = {"77": 1080}
    sources = asyncio.run(provider.sources("kayoanime:77", "1mkuqtOVMUJ6Q6hwmRyojGaYcTm_tsYBs"))
    assert len(sources) == 1
    source = sources[0]
    # Play = the keyed route (206 with seek); download = the keyless route.
    assert source.url.startswith("https://www.googleapis.com/drive/v3/files/")
    assert "alt=media" in source.url
    assert source.download_url.startswith("https://drive.usercontent.google.com/download")
    assert "confirm=t" in source.download_url
    assert source.resolution == 1080
    assert source.headers["Referer"] == "https://drive.google.com/"

    # Kayoanime's download_url is a real file (usercontent route) — the
    # provider's own capability turns the direct path on.
    choices = _source_choices(sources, direct_download=True)
    assert len(choices) == 1  # -> the play/download gates auto-start
    assert choices[0]["url"] == source.url
    assert choices[0]["download_url"] == source.download_url
    assert choices[0]["direct"] is True  # downloads take the keyless route
    assert choices[0]["label"] == "1080p - SUB (JPN) (Kayoanime)"


def test_kayoanime_rejects_a_foreign_session_as_before():
    provider = KayoanimeProvider(client=None)
    # A foreign "post|ep" shape is not a Drive id — empty, the honest answer.
    assert asyncio.run(provider.sources("kayoanime:9", "48025|1")) == []
