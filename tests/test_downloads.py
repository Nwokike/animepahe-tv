"""Playlist rewriting + download store rows."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from services.downloads import parse_key_uri, parse_segment_uris, rewrite_playlist

MEDIA = """#EXTM3U
#EXT-X-TARGETDURATION:10
#EXT-X-KEY:METHOD=AES-128,URI="https://cdn.example.com/keys/abc123.bin"
#EXTINF:10.0,
https://cdn.example.com/segs/seg0.ts
#EXTINF:10.0,
https://cdn.example.com/segs/seg1.ts
#EXTINF:10.0,
https://cdn.example.com/segs/seg2.ts
#EXT-X-ENDLIST
"""


def test_rewrite_segments_to_relative_paths():
    out, count = rewrite_playlist(MEDIA)
    assert count == 3
    assert "segs/seg0.ts" in out
    assert "segs/seg1.ts" in out
    assert "segs/seg2.ts" in out
    assert "https://cdn.example.com/segs/" not in out


def test_key_uri_rewritten_to_local():
    out, _ = rewrite_playlist(MEDIA)
    assert 'URI="segs/abc123.bin"' in out
    assert "https://cdn.example.com/keys/abc123.bin" not in out


def test_headers_and_tags_preserved():
    out, _ = rewrite_playlist(MEDIA)
    assert "#EXT-X-TARGETDURATION:10" in out
    assert "#EXT-X-KEY:METHOD=AES-128" in out
    assert out.endswith("\n")


def test_segment_uri_parsing_and_query_strings():
    uris = parse_segment_uris(MEDIA)
    assert len(uris) == 3
    with_token = "#EXTM3U\n#EXTINF:10,\nhttps://cdn.example.com/seg0.ts?token=abc\n"
    uris = parse_segment_uris(with_token)
    assert uris == ["https://cdn.example.com/seg0.ts?token=abc"]


def test_key_uri_extraction():
    assert parse_key_uri(MEDIA) == "https://cdn.example.com/keys/abc123.bin"
    assert parse_key_uri("#EXTM3U\n") is None
    assert parse_key_uri("") is None


def test_non_video_lines_pass_through():
    playlist = "#EXTM3U\n#EXTINF:10,\nsubs.vtt\n#EXT-X-ENDLIST\n"
    out, count = rewrite_playlist(playlist)
    assert count == 1  # vtt is a media segment
    assert "segs/subs.vtt" in out


def test_download_store_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path))
    import asyncio

    from services.store import JsonStore

    (tmp_path / "animepahe").mkdir(parents=True, exist_ok=True)

    async def _run():
        store = JsonStore(filename="dl-test.json")
        await store.save_download(
            "ep1",
            {"title": "Frieren", "state": "complete", "playlist": "/x/index.m3u8"},
        )
        await store.save_download("ep2", {"title": "Frieren", "state": "partial"})
        rows = await store.get_downloads()
        assert set(rows) == {"ep1", "ep2"}
        assert rows["ep1"]["state"] == "complete"

        await store.save_download_error("ep2", "boom")
        rows = await store.get_downloads()
        assert rows["ep2"]["error"] == "boom"
        assert rows["ep2"]["state"] == "partial"

        await store.remove_download("ep1")
        rows = await store.get_downloads()
        assert set(rows) == {"ep2"}

    asyncio.run(_run())
