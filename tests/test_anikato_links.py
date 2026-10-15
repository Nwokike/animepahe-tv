"""AniKato link resolution — the cache-key collision regression.

Live-verified: episode link ids are base64 strings that share their first
40 characters across episodes. The old ``link_{link_id[:40]}`` cache key
therefore served episode N's cached realid to every later episode — the
owner's live run showed 160, 159 and 154 all opening one master.m3u8.
Keys must be the FULL ids.
"""

import asyncio
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from services.providers.anikato import AniKatoProvider

SHARED_PREFIX = "MTF1dkFtaW9BRTZPbzJJRElFZUZrOWdjeldjOERL"  # 40 chars, live shape


def _provider_with_recording_resolver():
    calls = []

    class _UnusedClient:
        pass

    provider = AniKatoProvider(client=_UnusedClient())

    async def fake_get_text(url, xhr=False):
        calls.append(url)
        link_id = url.split("get=", 1)[1]
        match = re.search(r"-(\d+)-tail$", link_id)
        realid = match.group(1) if match else "0"
        return json.dumps(
            {
                "status": 200,
                "result": {
                    "url": f"https://megaplay.buzz/stream/s-2/{realid}/sub?s=tcdn",
                    "skip_data": {},
                },
            }
        )

    provider._get_text = fake_get_text
    return provider, calls


def test_link_ids_sharing_a_40_char_prefix_resolve_independently():
    provider, calls = _provider_with_recording_resolver()
    link_a = SHARED_PREFIX + "-160-tail"
    link_b = SHARED_PREFIX + "-159-tail"

    resolved_a = asyncio.run(provider._resolve_link(link_a))
    resolved_b = asyncio.run(provider._resolve_link(link_b))

    assert resolved_a is not None and resolved_b is not None
    assert resolved_a[0] == "160", "each link keeps its own realid"
    assert resolved_b[0] == "159"
    assert len(calls) == 2, "both links must be dialed, not one cache hit"


def test_repeated_resolve_of_the_same_link_hits_the_cache():
    provider, calls = _provider_with_recording_resolver()
    link = SHARED_PREFIX + "-77-tail"
    first = asyncio.run(provider._resolve_link(link))
    second = asyncio.run(provider._resolve_link(link))
    assert first == second
    assert len(calls) == 1


def test_sources_collapse_mirror_flavors_to_one_per_audio_track():
    """Live picker showed six identical entries ("3 eng 0p and 3 jpn 0p"):
    tcdn/bare/videojs/bcdn are mirrors of ONE stream, not qualities.
    AniKato genuinely has Sub and Dub — the picker must show exactly those."""
    provider = _provider_with_recording_resolver()
    if isinstance(provider, tuple):
        provider, _calls = provider

    async def fake_watch(_slug):
        return {"anime_id": 1, "poster": ""}

    async def fake_entries(_anime_id):
        return [(3, "tok3", False, False, 0)]

    mirrors = [
        ("sub", "MTF1dkFtaW9BRTZPbzJJRElFZUZrOWdjeldj-sub-tcdn"),
        ("sub", "MTF1dkFtaW9BRTZPbzJJRElFZUZrOWdjeldj-sub-bare"),
        ("sub", "MTF1dkFtaW9BRTZPbzJJRElFZUZrOWdjeldj-sub-videojs"),
        ("dub", "MTF1dkFtaW9BRTZPbzJJRElFZUZrOWdjeldj-dub-tcdn"),
    ]
    resolved = []

    async def fake_server_links(_token):
        return mirrors

    async def fake_resolve(link_id):
        resolved.append(link_id)
        return (f"90{len(resolved)}", "sub" if "-sub-" in link_id else "dub", "tcdn", {})

    async def fake_manifest(realid, kind, s):
        return (f"https://cdn/{realid}/master.m3u8", [], {})

    provider._watch_page = fake_watch
    provider._episode_entries = fake_entries
    provider._server_links = fake_server_links
    provider._resolve_link = fake_resolve
    provider._manifest_for = fake_manifest

    async def fake_serves_video(_manifest):
        return True  # this test is about collapsing, not door health

    provider._door_serves_video = fake_serves_video

    sources = asyncio.run(provider.sources("anikato:x", "x|3"))
    assert len(sources) == 2, "one source per audio track, not one per mirror"
    assert {s.audio for s in sources} == {"jpn", "eng"}
    assert len(resolved) == 2, "only the first working mirror of each kind resolves"


# ---------------------------------------------------------------------------
# CDN doors: an ad-stub playlist must be skipped, the next door tried
# ---------------------------------------------------------------------------

_STUB_PLAYLIST = "\n".join(
    ["#EXTM3U", "#EXT-X-TARGETDURATION:10", "#EXT-X-PLAYLIST-TYPE:VOD"]
    + [
        "#EXTINF:3.0,\n"
        f"https://p19-ad-site-sign-sg.tiktokcdn.com/ad-site-i18n-sg/x{i}.image?lk3s=6d71dd51"
        for i in range(4)
    ]
)
_REAL_PLAYLIST = "\n".join(
    ["#EXTM3U"]
    + [
        f"#EXTINF:10.0,\nhttps://9lc74.phantomharbor.space/anime/a/b/seg-{i}-f1-v1-a1.jpg"
        for i in range(4)
    ]
)


def test_is_ad_stub_playlist_detects_only_all_tiktok_playlists():
    from services.providers.anikato import is_ad_stub_playlist

    assert is_ad_stub_playlist(_STUB_PLAYLIST) is True
    assert is_ad_stub_playlist(_REAL_PLAYLIST) is False
    first_url = (
        "https://p19-ad-site-sign-sg.tiktokcdn.com/ad-site-i18n-sg/x0.image?lk3s=6d71dd51"
    )
    mixed = _STUB_PLAYLIST.replace(
        first_url, "https://9lc74.phantomharbor.space/x/seg-0.jpg", 1
    )
    assert is_ad_stub_playlist(mixed) is False
    too_short = "\n".join(
        ["#EXTM3U"]
        + ["#EXTINF:3.0,\nhttps://p19-ad-site-sign-sg.tiktokcdn.com/a.image" for _ in range(2)]
    )
    assert is_ad_stub_playlist(too_short) is False
    assert is_ad_stub_playlist("#EXTM3U\n") is False


def _door_fixture():
    provider, _calls = _provider_with_recording_resolver()
    doors_seen = []

    async def fake_watch(_slug):
        return {"anime_id": 1, "poster": ""}

    async def fake_entries(_anime_id):
        return [(3, "tok3", False, False, 0)]

    async def fake_server_links(_token):
        return [("sub", "L1"), ("sub", "L2"), ("dub", "L3"), ("dub", "L4")]

    by_link = {
        "L1": ("27379", "sub", "tcdn", {}),
        "L2": ("27379", "sub", "", {}),
        "L3": ("27379", "dub", "tcdn", {}),
        "L4": ("27379", "dub", "", {}),
    }

    async def fake_resolve(link_id):
        return by_link[link_id]

    async def fake_manifest(realid, kind, s):
        doors_seen.append((kind, s))
        return (f"master://{kind}/{s or 'bare'}", [], {})

    provider._watch_page = fake_watch
    provider._episode_entries = fake_entries
    provider._server_links = fake_server_links
    provider._resolve_link = fake_resolve
    provider._manifest_for = fake_manifest
    return provider, doors_seen


def test_sources_skips_the_stub_door_and_keeps_the_real_one():
    from services.providers.anikato import is_ad_stub_playlist  # noqa: F401

    provider, doors_seen = _door_fixture()

    async def fake_serves_video(manifest):
        return "/tcdn" not in manifest  # the tcdn door is the stub

    provider._door_serves_video = fake_serves_video

    sources = asyncio.run(provider.sources("anikato:x", "x|3"))
    assert [(s.audio, s.url) for s in sources] == [
        ("jpn", "master://sub/bare"),
        ("eng", "master://dub/bare"),
    ]
    assert doors_seen == [("sub", "tcdn"), ("sub", ""), ("dub", "tcdn"), ("dub", "")]


def test_all_stub_doors_yield_no_stream_not_a_stub():
    provider, _doors_seen = _door_fixture()

    async def everything_is_stub(_manifest):
        return False

    provider._door_serves_video = everything_is_stub
    assert asyncio.run(provider.sources("anikato:x", "x|3")) == []


def test_get_embed_id_parses_data_id_with_referer():
    class _Resp:
        def __init__(self, status_code, text):
            self.status_code = status_code
            self.text = text

    class _Client:
        def __init__(self):
            self.calls = []

        async def get(self, url, headers=None, **kwargs):
            self.calls.append((url, headers))
            return _Resp(
                200,
                '<div id="megaplay-player" data-id="104527" data-realid="27494"></div>',
            )

    client = _Client()
    provider = AniKatoProvider(client=client)
    res = asyncio.run(
        provider._get_embed_id(
            "https://megaplay.buzz/stream/s-2/27494/sub?s=tcdn", fallback="27494"
        )
    )
    assert res == "104527"
    assert len(client.calls) == 1
    url, headers = client.calls[0]
    assert headers.get("Referer") == "https://anikototv.to/"


def test_get_embed_id_falls_back_when_missing_or_failed():
    class _FailingClient:
        async def get(self, url, **kwargs):
            raise RuntimeError("net error")

    provider = AniKatoProvider(client=_FailingClient())
    res = asyncio.run(provider._get_embed_id("https://megaplay.buzz/x", fallback="fallback_id"))
    assert res == "fallback_id"

