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

    sources = asyncio.run(provider.sources("anikato:x", "x|3"))
    assert len(sources) == 2, "one source per audio track, not one per mirror"
    assert {s.audio for s in sources} == {"jpn", "eng"}
    assert len(resolved) == 2, "only the first working mirror of each kind resolves"
