"""Fixes for the owner's 2026-11-01 reports.

Covers: realtime download percent emission, play-local-if-downloaded,
prev/next episode context built from downloads, the fullscreen back
re-entrancy guard, and shared HLS variant expansion for downloads.
"""

import asyncio
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="animepahe-fixes-20261101-")
os.environ["FLET_APP_STORAGE_DATA"] = _TMP

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from services.downloads import DownloadManager


class _Store:
    def __init__(self, rows=None):
        self._rows = rows or {}

    async def get_downloads(self):
        return dict(self._rows)

    async def save_download(self, session, row):
        self._rows[session] = row


# --- realtime progress: emitted rows must carry "percent" -----------------


def test_emit_progress_includes_percent():
    mgr = DownloadManager(store=_Store(), downloads_dir=str(_TMP))
    captured = []
    mgr.on_progress = lambda s, row: captured.append((s, dict(row)))
    mgr._progress["ep1"] = {
        "done": 1,
        "total": 4,
        "bytes": 250,
        "state": "downloading",
        "title": "t",
        "anime_session": "a",
    }
    mgr._emit_progress("ep1")
    assert captured and captured[0][0] == "ep1"
    row = captured[0][1]
    assert row["percent"] == 25.0, f"live progress row must carry percent, got {row}"
    assert row["state"] == "downloading"


def test_emit_progress_percent_none_until_total_known():
    mgr = DownloadManager(store=_Store(), downloads_dir=str(_TMP))
    captured = []
    mgr.on_progress = lambda s, row: captured.append(dict(row))
    mgr._progress["ep2"] = {"done": 0, "total": 0, "bytes": 0, "state": "downloading"}
    mgr._emit_progress("ep2")
    assert captured and captured[0]["percent"] is None


# --- play local if downloaded ---------------------------------------------


def test_play_episode_delegates_to_play_downloaded_when_complete(tmp_path):
    import main as main_mod

    local = tmp_path / "ep1.mkv"
    local.write_bytes(b"x")
    ctrl = main_mod.AppController.__new__(main_mod.AppController)
    ctrl._play_lock = asyncio.Lock()
    ctrl.store = _Store({"ep1": {"state": "complete", "file": str(local)}})
    called = []

    async def fake_play_downloaded(session):
        called.append(session)

    ctrl.play_downloaded = fake_play_downloaded
    asyncio.run(ctrl.play_episode("anime1", "ep1"))
    assert called == ["ep1"], "complete download must play locally, not stream"


def test_play_episode_streams_when_download_partial(tmp_path):
    import main as main_mod

    local = tmp_path / "ep2.mkv"
    local.write_bytes(b"x")
    ctrl = main_mod.AppController.__new__(main_mod.AppController)
    ctrl._play_lock = asyncio.Lock()
    ctrl.store = _Store({"ep2": {"state": "partial", "file": str(local)}})

    async def fake_play_downloaded(session):  # pragma: no cover - must not run
        raise AssertionError("must not play partial download locally")

    async def fake_inner(anime_session, episode_session):  # stream path reached
        fake_inner.reached = True

    fake_inner.reached = False
    ctrl.play_downloaded = fake_play_downloaded
    ctrl._may_solve = lambda anime_session: False
    ctrl._play_episode = fake_inner

    class _Stack:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def enter_async_context(self, ctx):
            return ctx

    ctrl._user_action = lambda: _Stack()
    asyncio.run(ctrl.play_episode("anime1", "ep2"))
    assert fake_inner.reached, "partial download must fall through to streaming"


def test_episodes_from_downloads_orders_and_filters(tmp_path):
    import main as main_mod

    f = tmp_path / "a.mkv"
    f.write_bytes(b"x")
    rows = {
        "e2": {"anime_session": "an", "state": "complete", "file": str(f), "episode_num": 2},
        "e1": {"anime_session": "an", "state": "complete", "file": str(f), "episode_num": 1},
        "e3": {"anime_session": "an", "state": "partial", "file": str(f), "episode_num": 3},
        "e9": {"anime_session": "other", "state": "complete", "file": str(f), "episode_num": 9},
        "broken": "not-a-dict",
    }
    eps = main_mod.AppController._episodes_from_downloads(rows, "an")
    assert [e.session for e in eps] == ["e1", "e2"], "only complete rows of this anime, ordered"


# --- fullscreen back re-entrancy guard -------------------------------------


def test_player_back_reentrant_call_is_noop():
    import app_shell

    calls = []

    class FakePlayer:
        async def _on_back(self, e):
            calls.append(e)

    app_shell._back_in_flight = True
    app_shell._active_player = FakePlayer()
    try:
        asyncio.run(app_shell._player_back())
        assert calls == [], (
            "nested _player_back during an in-flight close must not re-enter _on_back"
        )
    finally:
        app_shell._back_in_flight = False
        app_shell._active_player = None


# --- shared variant expansion used by download paths -----------------------


def test_expand_variant_choices_for_master_playlist():
    import main as main_mod

    class FakeProxy:
        async def fetch_variants(self, url, headers=None):
            return [
                {"index": 0, "label": "1080p", "height": 1080},
                {"index": 1, "label": "720p", "height": 720},
            ]

    ctrl = main_mod.AppController.__new__(main_mod.AppController)
    ctrl.hls_proxy = FakeProxy()
    choices = [
        {"label": "SUB (JPN) (AniKato)", "url": "https://x/master.m3u8", "headers": {}},
        {"label": "MP4 720p", "url": "https://x/file.mp4", "headers": {}},
    ]
    out = asyncio.run(ctrl._expand_variant_choices(choices))
    labels = [c["label"] for c in out]
    assert "1080p - SUB (JPN) (AniKato)" in labels
    assert "720p - SUB (JPN) (AniKato)" in labels
    assert "MP4 720p" in labels, "non-master choices pass through"
    variants = [c for c in out if c.get("kind") == "variant"]
    assert [c["variant_index"] for c in variants] == [0, 1]
    # subtitles ride along on expanded variants so downloads keep them
    assert all("subtitles" in c for c in variants)
    assert out[-1]["label"] == "MP4 720p"  # passthrough untouched
