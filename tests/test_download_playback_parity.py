"""The download writer and the local playlist must agree on every name.

Regression: a COMPLETE download played as a black frame while mpv logged
"Cannot open file .../seg-f1-00000.jpg" once per segment (owner's live
log, 2026-10-25). The writer named segments ``00000-seg-f1-00000.jpg``
(index prefix) while ``rewrite_playlist`` wrote ``seg-f1-00000.jpg``
(no prefix), so every URI in the local index.m3u8 pointed at a file that
did not exist.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from services.downloads import (
    parse_segment_uris,
    rewrite_playlist,
    segment_filename,
)

# The real shape AniKato serves: obfuscated extensions that rotate
# .jpg/.html/.js/.css/.txt/.png/.webp/.ico to defeat middlebox filtering.
ANIKATO_MEDIA = """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:4
#EXT-X-MEDIA-SEQUENCE:0
#EXT-X-PLAYLIST-TYPE:VOD
#EXTINF:4.004000,
https://fetch.nexabloom.top/anime/64aa9721797bd66f76fe695f4730e8b1/f8c1131062afb6d2a799577e79a30001/seg-f1-00000.jpg
#EXTINF:4.004000,
https://fetch.nexabloom.top/anime/64aa9721797bd66f76fe695f4730e8b1/f8c1131062afb6d2a799577e79a30001/seg-f1-00001.html
#EXTINF:4.004000,
https://fetch.nexabloom.top/anime/64aa9721797bd66f76fe695f4730e8b1/f8c1131062afb6d2a799577e79a30001/seg-f1-00002.js
#EXTINF:4.004000,
https://fetch.nexabloom.top/anime/64aa9721797bd66f76fe695f4730e8b1/f8c1131062afb6d2a799577e79a30001/seg-f1-00003.css
#EXT-X-ENDLIST
"""


def test_rewritten_uris_match_the_names_the_worker_writes():
    """Every URI in the local playlist resolves to a file the worker creates."""
    uris = parse_segment_uris(ANIKATO_MEDIA)
    out, count = rewrite_playlist(ANIKATO_MEDIA)

    assert count == len(uris) == 4
    for index, uri in enumerate(uris):
        expected = f"segs/{segment_filename(index, uri)}"
        assert expected in out, f"playlist is missing {expected}"
        # The bare basename (no index prefix) must NOT appear as a segment
        # line — that was the bug.
        bare = f"segs/{os.path.basename(uri.split('?')[0])}"
        assert bare not in out, f"playlist still carries the unprefixed {bare}"


def test_segment_filename_is_index_prefixed_and_query_free():
    assert segment_filename(0, "https://h/seg-f1-00000.jpg") == "00000-seg-f1-00000.jpg"
    assert segment_filename(52, "https://h/seg-f1-00052.txt") == "00052-seg-f1-00052.txt"
    # A query string never reaches the filename.
    assert segment_filename(3, "https://h/seg.ts?token=abc") == "00003-seg.ts"


def test_rewrite_is_stable_across_repeated_calls():
    """The rewriter is pure: same input, same output, same count."""
    first, count_a = rewrite_playlist(ANIKATO_MEDIA)
    second, count_b = rewrite_playlist(ANIKATO_MEDIA)
    assert first == second
    assert count_a == count_b


def test_plain_ts_playlists_still_rewrite():
    """The ordinary case (no obfuscation) keeps working, prefixed."""
    media = "#EXTM3U\n#EXTINF:10,\nhttps://cdn.example.com/segs/seg0.ts\n#EXT-X-ENDLIST\n"
    out, count = rewrite_playlist(media)
    assert count == 1
    assert "segs/00000-seg0.ts" in out
    assert "https://cdn.example.com" not in out
