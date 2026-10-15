"""Local subtitle files — Phase 4 Step 2.

The player could only show the source's own tracks; a user with an .srt on
the device had no path in. Now: the bottom bar carries a subtitle-file
button (the bar is the one settings surface that is always reachable — the
quality/audio chips hide on single-option streams), the settings sheet's
Subtitles section gains the same row, and the picked file's text becomes
the track via fv.VideoSubtitleTrack(src=<raw text>) — no host, no headers.
Every failure is an honest snack. The picker itself is a boot singleton in
shared services (per-tap construction leaked a service entry each press —
the bug that module exists to kill).
"""

import asyncio
import inspect
import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import components.player.immersive_player as ip  # noqa: E402
import core.shared_services as shared  # noqa: E402

SRT = b"1\n00:00:01,000 --> 00:00:02,000\nHello\n"


class _Video:
    def __init__(self):
        self.subtitle_track = None
        self.updates = 0

    def update(self):
        self.updates += 1


def _player():
    player = ip.ImmersivePlayer.__new__(ip.ImmersivePlayer)
    player.video = _Video()
    player.subtitles = []
    player._local_subtitle = None
    player._page = lambda: types.SimpleNamespace(web=False)
    return player


class _Picker:
    def __init__(self, files=None, boom=None):
        self.files = files or []
        self.boom = boom

    async def pick_files(self, **kwargs):
        self.calls = kwargs
        if self.boom is not None:
            raise self.boom
        return self.files


def _with_picker(monkeypatch, picker):
    def _get(_page):
        return types.SimpleNamespace(file_picker=picker)

    monkeypatch.setattr(shared, "get_shared_services", _get)


def _snacks(monkeypatch):
    import core.notify

    recorded = []
    monkeypatch.setattr(
        core.notify, "show_snack", lambda page, msg, **kw: recorded.append(msg)
    )
    return recorded


# ---------------------------------------------------------------------------
# The singleton
# ---------------------------------------------------------------------------


def test_the_file_picker_is_appended_once():
    services = types.SimpleNamespace(page=types.SimpleNamespace(services=[]))
    first = shared.SharedServices.file_picker.fget(services)
    second = shared.SharedServices.file_picker.fget(services)
    assert first is second
    assert services.page.services.count(first) == 1


# ---------------------------------------------------------------------------
# Picking + applying
# ---------------------------------------------------------------------------


def test_picking_applies_the_file_text_as_the_track(monkeypatch):
    picker = _Picker(
        [types.SimpleNamespace(name="custom.srt", bytes=SRT)]
    )
    _with_picker(monkeypatch, picker)
    snacks = _snacks(monkeypatch)
    player = _player()
    asyncio.run(player._pick_subtitle_file())
    assert player.video.subtitle_track is not None
    assert player.video.subtitle_track.src == SRT.decode()
    assert player.video.subtitle_track.title == "custom.srt"
    assert player._local_subtitle["name"] == "custom.srt"
    assert snacks == ["Subtitles: custom.srt"]
    # The picker was asked for exactly srt/vtt with contents.
    assert picker.calls["with_data"] is True
    assert picker.calls["allowed_extensions"] == ["srt", "vtt"]


def test_cancel_changes_nothing(monkeypatch):
    _with_picker(monkeypatch, _Picker([]))
    snacks = _snacks(monkeypatch)
    player = _player()
    asyncio.run(player._pick_subtitle_file())
    assert player.video.subtitle_track is None
    assert player.video.updates == 0
    assert player._local_subtitle is None
    assert snacks == []


def test_unreadable_bytes_is_an_honest_snack(monkeypatch):
    _with_picker(monkeypatch, _Picker([types.SimpleNamespace(name="x.vtt", bytes=b"")]))
    snacks = _snacks(monkeypatch)
    player = _player()
    asyncio.run(player._pick_subtitle_file())
    assert snacks == ["Could not read that file"]
    assert player._local_subtitle is None


def test_a_picker_without_a_service_is_a_snack_not_a_crash(monkeypatch):
    _with_picker(monkeypatch, _Picker(boom=RuntimeError("no service in dev")))
    snacks = _snacks(monkeypatch)
    player = _player()
    asyncio.run(player._pick_subtitle_file())
    assert snacks == ["File picker unavailable"]
    assert player.video.subtitle_track is None


def test_apply_local_subtitle_without_a_file_is_a_noop():
    player = _player()
    player.apply_local_subtitle()
    assert player.video.subtitle_track is None
    assert player.video.updates == 0


# ---------------------------------------------------------------------------
# The wiring can't silently disappear
# ---------------------------------------------------------------------------


def test_the_settings_sheet_and_the_bar_carry_the_entry_points():
    source = inspect.getsource(ip.ImmersivePlayer)
    assert "Load from file…" in source, "the settings row vanished"
    assert "CLOSED_CAPTION_OUTLINED" in source, "the bar button vanished"
    assert "pick-subtitle" in source
