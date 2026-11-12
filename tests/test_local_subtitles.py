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

import components.player.immersive_player as ip
import core.shared_services as shared

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
    monkeypatch.setattr(core.notify, "show_snack", lambda page, msg, **kw: recorded.append(msg))
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
    picker = _Picker([types.SimpleNamespace(name="custom.srt", bytes=SRT)])
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
# The value-equality trap (flet 1.1.0 Prop.__set__)
# ---------------------------------------------------------------------------


class _TrapVideo(_Video):
    """A video stand-in that reproduces flet's `Prop.__set__` semantics:
    assigning a value equal to the current one is a no-op, so no delta is
    pushed to the player. This is why re-applying the same subtitle track
    (the Android retry path) silently did nothing."""

    def __init__(self):
        self._track = None
        self.updates = 0

    @property
    def subtitle_track(self):
        return self._track

    @subtitle_track.setter
    def subtitle_track(self, value):
        if self._track is not None and self._track == value:
            return  # no change — skip everything
        self._track = value


def test_reapplying_the_same_track_still_reaches_the_player():
    player = _player()
    player.video = _TrapVideo()
    player._apply_track("SAME", "English")
    assert player.video.subtitle_track.src == "SAME"
    # The first apply is dropped by mpv while the demuxer opens; the retry
    # re-applies the SAME track. Without the clear-first, the trap swallows
    # it and the phone never shows subtitles.
    player.video.updates = 0
    player._apply_track("SAME", "English")
    assert player.video.subtitle_track.src == "SAME"
    assert player.video.updates == 2  # clear + apply


def test_default_subtitle_retry_survives_the_trap():
    player = _player()
    player.video = _TrapVideo()
    player.subtitles = [{"label": "English", "url": "SAME", "default": True}]
    player._subtitle_selection = "auto"
    player._subtitle_applied = False
    player._is_closing = False
    asyncio.run(player._apply_default_subtitle(force=True))
    assert player.video.subtitle_track is not None
    assert player.video.subtitle_track.src == "SAME"
    # Second (retry) pass over the same track must still push a delta.
    player.video.updates = 0
    asyncio.run(player._apply_default_subtitle(force=True))
    assert player.video.subtitle_track.src == "SAME"
    assert player.video.updates == 2


def test_default_subtitle_schedule_survives_the_trap(monkeypatch):
    """The schedule runs the default across the load window and every pass
    clear-then-applies, so neither flet's Prop value equality nor media_kit's
    SubtitleTrack.__eq__ can swallow a re-apply (the Android regression)."""
    player = _player()
    player.video = _TrapVideo()
    player.subtitles = [
        {"label": "English", "url": "https://p/eng.vtt", "default": True}
    ]
    player._subtitle_selection = "auto"
    player._subtitle_applied = False
    player._is_closing = False
    player._subtitle_schedule_started = False
    monkeypatch.setattr(ip, "_SUBTITLE_RETRY_DELAYS", (0.0, 0.01))
    asyncio.run(player._run_default_subtitle_schedule())
    assert player.video.subtitle_track is not None
    assert player.video.subtitle_track.src == "https://p/eng.vtt"
    # Pass 1 applies (current is None -> plain apply); pass 2 clear-then-
    # applies the SAME track so the trap cannot swallow it.
    assert player.video.updates == 3


def test_a_user_selection_stops_the_schedule(monkeypatch):
    """Once the user picks a track (or Off), the schedule must not override
    them on its later passes."""
    player = _player()
    player.video = _TrapVideo()
    player.subtitles = [
        {"label": "English", "url": "https://p/eng.vtt", "default": True}
    ]
    player._subtitle_selection = 0  # the user picked track 0
    player._subtitle_applied = False
    player._is_closing = False
    player._subtitle_schedule_started = False
    monkeypatch.setattr(ip, "_SUBTITLE_RETRY_DELAYS", (0.0, 0.01))
    asyncio.run(player._run_default_subtitle_schedule())
    assert player.video.updates == 0


def test_subtitle_src_prefers_the_proxy_url():
    """The device-proven form: the proxied URL rides to flet_video untouched
    (the pre-port behaviour that showed Android subtitles); a local sidecar
    path is handed over verbatim for mpv to read off disk."""
    player = _player()

    class _Proxy:
        pass

    player.hls_proxy = _Proxy()
    src = asyncio.run(
        player._subtitle_src({"url": "https://p/eng.vtt", "default": True})
    )
    assert src == "https://p/eng.vtt"
    src = asyncio.run(player._subtitle_src({"url": "/data/subs/eng.vtt"}))
    assert src == "/data/subs/eng.vtt"


# ---------------------------------------------------------------------------
# The wiring can't silently disappear
# ---------------------------------------------------------------------------


def test_the_settings_sheet_and_the_bar_carry_the_entry_points():
    # The player is split KTV-style (player + controls + handlers); the
    # wiring may live in any of the three files, but it must EXIST.
    import components.player.controls as controls_mod
    import components.player.handlers as handlers_mod

    source = "\n".join(
        inspect.getsource(m)
        for m in (ip, controls_mod, handlers_mod)
        if hasattr(m, "__file__")
    )
    assert "Load from file…" in source, "the settings row vanished"
    assert "SUBTITLES_ROUNDED" in source, "the bar button vanished"
    assert "_pick_subtitle_file" in source, "the picker wiring vanished"
    assert "pick-subtitle" in source
