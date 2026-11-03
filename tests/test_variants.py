"""Master-playlist variant parsing drives the quality chip.

The player no longer parses playlists itself — `services.hls_proxy` owns
parsing (`parse_hls_variants`) and URI resolution (the proxy rewrites
variant URIs with urljoin against the master's own address, which fixed
the old every-variant-collapses-onto-the-first bug).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from services.hls_proxy import parse_hls_variants

MASTER = """#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=1280000,RESOLUTION=640x360
360/index.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=2560000,RESOLUTION=854x480
480/index.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=7680000,RESOLUTION=1280x720
720/index.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=15000000,RESOLUTION=1920x1080
1080/index.m3u8
"""

MEDIA = """#EXTM3U
#EXT-X-TARGETDURATION:10
#EXTINF:10.0,
segment0.ts
#EXTINF:10.0,
segment1.ts
"""

ABS_MASTER = """#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=7680000,RESOLUTION=1280x720
https://cdn.example.com/720/index.m3u8
"""


def test_master_playlist_variants():
    variants = parse_hls_variants(MASTER)
    assert len(variants) == 4
    assert variants[0]["label"].startswith("640x360")
    assert variants[0]["resolution"] == "640x360"
    assert variants[0]["uri"].endswith("360/index.m3u8")
    assert variants[-1]["label"].startswith("1920x1080")
    assert variants[-1]["bandwidth"] == 15000000
    # Proxy pinning is by playlist order.
    assert [v["index"] for v in variants] == [0, 1, 2, 3]


def test_media_playlist_has_no_variants():
    assert parse_hls_variants(MEDIA) == []


def test_absolute_variant_uris():
    variants = parse_hls_variants(ABS_MASTER)
    assert len(variants) == 1
    assert variants[0]["uri"] == "https://cdn.example.com/720/index.m3u8"


def test_empty_and_malformed():
    assert parse_hls_variants("") == []
    assert parse_hls_variants("not a playlist") == []
    assert parse_hls_variants("#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1\n") == []
