"""Snapshot save — Phase 4 Step 1.

The old `_take_snapshot` toasts "Saved a screenshot" while discarding the
bytes; the file below is the real thing. Tests pin: the sortable filename,
the atomic write, the rotation (newest kept), the player method actually
writing + naming the file in the toast, and the directory chooser's
fallbacks (web / service failure -> the data tier).
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.snapshots import (
    KEEP_SNAPSHOTS,
    save_snapshot,
    snapshot_filename,
)


def test_filename_is_sortable_and_stable():
    when = datetime(2026, 10, 15, 15, 30, 12, 123000)
    assert snapshot_filename(when) == "animepahe-20261015-153012-123.png"
    # Lexicographic order == chronological order (the rotation relies on it).
    later = datetime(2026, 10, 15, 15, 30, 12, 124000)
    assert snapshot_filename(when) < snapshot_filename(later)


def test_save_writes_atomically_and_returns_the_path(tmp_path):
    path = save_snapshot(b"\x89PNG-bytes", str(tmp_path))
    assert os.path.dirname(path) == str(tmp_path)
    assert path.endswith(".png")
    with open(path, "rb") as f:
        assert f.read() == b"\x89PNG-bytes"
    leftovers = [n for n in os.listdir(tmp_path) if n.endswith(".part")]
    assert leftovers == []


def test_rotation_keeps_the_newest(tmp_path):
    base = datetime(2026, 10, 15, 12, 0, 0)
    for i in range(KEEP_SNAPSHOTS + 5):
        save_snapshot(
            b"x",
            str(tmp_path),
            when=base + timedelta(milliseconds=i),
        )
    names = sorted(n for n in os.listdir(tmp_path) if n.endswith(".png"))
    assert len(names) == KEEP_SNAPSHOTS
    # The oldest five are gone; the newest is present.
    assert names[-1] == snapshot_filename(base + timedelta(milliseconds=KEEP_SNAPSHOTS + 4))
    assert snapshot_filename(base) not in names


def test_rotation_ignores_foreign_files(tmp_path):
    foreign = tmp_path / "other.png"
    foreign.write_bytes(b"keep me")
    base = datetime(2026, 10, 15, 12, 0, 0)
    for i in range(KEEP_SNAPSHOTS + 3):
        save_snapshot(b"x", str(tmp_path), when=base + timedelta(milliseconds=i))
    assert foreign.exists(), "pruning only ever touches our own files"


# ---------------------------------------------------------------------------
# The player method
# ---------------------------------------------------------------------------


class _FakeVideo:
    def __init__(self, shot):
        self._shot = shot

    async def take_screenshot(self):
        return self._shot


class _BarePlayer:
    """`_take_snapshot` only needs these three seams."""


def _player(shot, directory):
    import components.player.immersive_player as ip

    player = ip.ImmersivePlayer.__new__(ip.ImmersivePlayer)
    player.video = _FakeVideo(shot)

    async def _dir():
        return directory

    player._snapshot_directory = _dir
    player._page = lambda: object()  # non-None; show_snack is patched below
    return player


def test_take_snapshot_writes_and_names_the_file(monkeypatch, tmp_path):
    import core.notify

    snacks = []
    monkeypatch.setattr(core.notify, "show_snack", lambda page, msg, **kw: snacks.append(msg))
    player = _player(b"png-bytes", str(tmp_path))
    asyncio.run(player._take_snapshot())
    files = [n for n in os.listdir(tmp_path) if n.endswith(".png")]
    assert len(files) == 1
    assert snacks == [f"Saved {files[0]}"], "the toast names the real file"


def test_take_snapshot_without_bytes_says_unavailable(monkeypatch, tmp_path):
    import core.notify

    snacks = []
    monkeypatch.setattr(core.notify, "show_snack", lambda page, msg, **kw: snacks.append(msg))
    player = _player(None, str(tmp_path))
    asyncio.run(player._take_snapshot())
    assert snacks == ["Screenshot unavailable"]
    assert [n for n in os.listdir(tmp_path) if n.endswith(".png")] == []


def test_snapshot_directory_falls_back_off_web_and_on_error(monkeypatch):
    import components.player.immersive_player as ip

    player = ip.ImmersivePlayer.__new__(ip.ImmersivePlayer)

    class _Page:
        web = True

    player._page = lambda: _Page()
    assert asyncio.run(player._snapshot_directory()) is None

    class _PageNative:
        web = False

    player._page = lambda: _PageNative()

    class _Boom:
        def __init__(self):
            pass

        async def get_downloads_directory(self):
            raise TimeoutError("no service in dev")

    monkeypatch.setattr(ip.ft, "StoragePaths", _Boom)
    assert asyncio.run(player._snapshot_directory()) is None

    class _OK:
        async def get_downloads_directory(self):
            return "/storage/emulated/0/Download"

    monkeypatch.setattr(ip.ft, "StoragePaths", _OK)
    assert asyncio.run(player._snapshot_directory()) == "/storage/emulated/0/Download"
