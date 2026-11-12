"""Player presentation + confirmation surfaces.

Three things this file pins down, all found incomplete during the Phase 7
audit (2026-10-11):

1. The store now actually HAS the generic settings pair the player calls
   (`get_setting`/`save_setting` were missing — the subtitle size was
   silently never persisted, and the aspect fit had nowhere to live).
2. The aspect-fit switcher: names persist and map to BoxFit values, and
   an unknown name degrades to CONTAIN rather than crashing.
3. The fullscreen toast: registered at mount, unregistered at unmount
   (not at first-ready / close-only), and the resume/speed/skip
   confirmations actually reach the chip.
"""

import asyncio
import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="animepahe-player-test-")
os.environ["FLET_APP_STORAGE_DATA"] = _TMP

import flet as ft
import pytest

from components.player.immersive_player import (
    _BOX_FITS,
    ImmersivePlayer,
)
from core import (
    notify,
    tasks,
)
from services.store import JsonStore


class _Chip:
    """The toast chip's contract: a content.value, a visible flag, update()."""

    def __init__(self):
        self.content = type("C", (), {"value": ""})()
        self.visible = False
        self.updates = 0

    def update(self):
        self.updates += 1


class _Video:
    def __init__(self, seek_fails: bool = False):
        self.seeks: list[float] = []
        self.rates: list[float] = []
        self.playback_rate = 1.0
        self.updates = 0
        self._seek_fails = seek_fails

    async def seek(self, seconds):
        self.seeks.append(seconds)
        if self._seek_fails:
            raise RuntimeError("seek refused")

    def update(self):
        self.updates += 1


def _player(video=None, **attrs) -> ImmersivePlayer:
    """No _build — the tests drive individual methods on a bare instance."""
    player = ImmersivePlayer.__new__(ImmersivePlayer)
    player.store = attrs.pop("store", None)
    player.video = video or _Video()
    player.subtitles = []
    player.skip = {}
    player._speed_idx = 2
    player._last_position = 0.0
    player._last_duration = 0.0
    player._position_saved = False
    player._is_closing = False
    player._playback_started = False
    player._media_attached = False
    player._watchdog_task = None
    player._checkpoint_task = None
    player._toast_gen = 0
    player.resume_key = None
    player.source_headers = {}
    player.source_referer = None
    player.hls_proxy = None
    player.toast_chip = _Chip()
    player.toast_text = player.toast_chip.content
    for key, value in attrs.items():
        setattr(player, key, value)
    return player


@pytest.fixture
def no_spawn(monkeypatch):
    """Dispose of spawned coroutines instead of leaving them pending."""
    monkeypatch.setattr(tasks, "spawn", lambda coro, name="bg-task": coro.close())


@pytest.fixture(autouse=True)
def _clean_registry():
    notify._toast = None
    yield
    notify._toast = None


# ---------------------------------------------------------------------------
# The store's settings pair
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_settings_round_trip_and_cold_read(tmp_path):
    path = tmp_path / "settings.json"
    store = JsonStore(filename=str(path))
    await store.save_setting("video_fit", "cover")
    await store.save_setting("subtitle_size", 22)

    # A SECOND instance (cold, nothing loaded) must still see what the
    # first wrote — that is the path a freshly-constructed player takes.
    cold = JsonStore(filename=str(path))
    assert cold.get_setting("video_fit") == "cover"
    assert cold.get_setting("subtitle_size") == 22
    assert cold.get_setting("missing", "fallback") == "fallback"

    # Corrupt file: defaults, never a crash.
    path.write_text("{not json", encoding="utf-8")
    assert JsonStore(filename=str(path)).get_setting("video_fit", "contain") == "contain"


@pytest.mark.asyncio
async def test_settings_survive_other_sections(tmp_path):
    path = tmp_path / "mixed.json"
    store = JsonStore(filename=str(path))
    await store.save_setting("video_fit", "fill")
    await store.put_section("search_history", [{"title": "Naruto"}])
    await store.save_setting("subtitle_size", 30)

    cold = JsonStore(filename=str(path))
    assert cold.get_setting("video_fit") == "fill"
    assert cold.get_setting("subtitle_size") == 30
    assert await cold.section("search_history", []) == [{"title": "Naruto"}]


# ---------------------------------------------------------------------------
# Aspect fit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_box_fit_maps_every_option_and_rejects_junk(tmp_path):
    store = JsonStore(filename=str(tmp_path / "fits.json"))
    for name in ("contain", "cover", "fill"):
        await store.save_setting("video_fit", name)
        assert _player(store=store)._box_fit() is _BOX_FITS[name]

    await store.save_setting("video_fit", "nonsense")
    assert _player(store=store)._box_fit() is ft.BoxFit.CONTAIN
    assert _player(store=None)._box_fit() is ft.BoxFit.CONTAIN


@pytest.mark.asyncio
async def test_set_fit_persists_and_unknown_names_are_ignored(tmp_path):
    store = JsonStore(filename=str(tmp_path / "fits-save.json"))
    player = _player(store=store)

    async def _wait_for(value):
        # The save rides a spawned task: poll for it instead of guessing a
        # sleep (a fixed 10 ms made the suite flaky under load).
        for _ in range(100):
            if store.get_setting("video_fit") == value:
                return True
            await asyncio.sleep(0.02)
        return store.get_setting("video_fit") == value

    player.set_fit("cover")
    assert await _wait_for("cover")

    player.set_fit("melt-the-screen")
    await asyncio.sleep(0.05)
    assert store.get_setting("video_fit") == "cover"  # unchanged


@pytest.mark.asyncio
async def test_subtitle_size_reads_the_persisted_value(tmp_path):
    store = JsonStore(filename=str(tmp_path / "sizes.json"))
    await store.save_setting("subtitle_size", 22)
    assert _player(store=store)._subtitle_size() == 22
    await store.save_setting("subtitle_size", 99)
    assert _player(store=store)._subtitle_size() == 16  # not a legal size
    assert _player(store=None)._subtitle_size() == 16


# ---------------------------------------------------------------------------
# The fullscreen toast: lifecycle + the three confirmations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_toast_registers_at_mount_and_unregisters_at_unmount():
    player = _player()
    player._read_resume_position = lambda: None

    async def _noop():
        return None

    player.start_playback = _noop

    player.did_mount()
    # Identity-free check: bound methods are fresh objects per access, so
    # drive the registered handler instead of comparing them.
    assert notify._toast is not None
    notify._toast("hello")
    assert player.toast_chip.content.value == "hello"

    # will_unmount is SYNC (flet never awaits it); the save rides spawn().
    player.will_unmount()
    assert notify._toast is None
    await asyncio.sleep(0)  # let the spawned save task finish


@pytest.mark.asyncio
async def test_unmount_unregisters_even_when_the_close_path_already_saved():
    """The overlay-removal race: handle_close never ran, but the safety
    net must still release the registry (it short-circuits the save)."""
    player = _player()
    player._position_saved = True
    player.will_unmount()
    assert notify._toast is None


@pytest.mark.asyncio
async def test_will_unmount_is_sync_and_still_saves_the_position():
    """The crash the flet run log exposed: an ASYNC will_unmount produced
    "coroutine was never awaited" — flet calls it without awaiting, so the
    safety-net save never ran. It must be sync and schedule the save."""
    import asyncio as _asyncio
    from types import SimpleNamespace

    saved = {}

    class _Store:
        async def save_position(self, key, position, duration, rate):
            saved.update(key=key, position=position, duration=duration, rate=rate)

    class _SavingVideo(_Video):
        async def get_current_position(self):
            return SimpleNamespace(in_seconds=55.0)

        async def get_duration(self):
            return SimpleNamespace(in_seconds=1440.0)

    player = _player(video=_SavingVideo(), store=_Store(), resume_key="ep-1")

    result = player.will_unmount()
    assert not _asyncio.iscoroutine(result), "will_unmount must be sync"
    await _asyncio.sleep(0.05)  # the spawned save completes
    assert saved == {
        "key": "ep-1",
        "position": 55.0,
        "duration": 1440.0,
        "rate": 1.0,
    }
    assert player._position_saved is True


@pytest.mark.asyncio
async def test_close_also_unregisters(no_spawn):
    player = _player()
    player._save_current_position = lambda: _done()
    player._cancel_watchdog = lambda: None
    player._checkpoint_task = None
    await player.handle_close()
    assert notify._toast is None


async def _done():
    return None


@pytest.mark.asyncio
async def test_speed_cycle_confirm(no_spawn):
    player = _player()
    player.speed_text = type("T", (), {"value": "1.0x", "update": lambda self: None})()

    await player._cycle_speed()  # 1.0 -> 1.25
    assert player.video.rates == []  # rate set on the control, not the fake
    assert player._speed_idx == 3  # SPEEDS[3] == 1.25
    assert player.speed_text.value == "1.25x"
    assert player.toast_chip.content.value == "Speed 1.25x"
    assert player.toast_chip.visible is True


@pytest.mark.asyncio
async def test_skip_confirm_says_intro_or_outro(no_spawn):
    player = _player()
    player.skip = {
        "intro": {"start": 30, "end": 119},
        "outro": {"start": 1280, "end": 1369},
    }

    # seek() takes DurationValue: a bare int is MILLISECONDS in
    # flet-video, so the seconds travel as an explicit Duration.
    def _seek_seconds():
        return [float(getattr(s, "seconds", s)) for s in player.video.seeks]

    player._last_position = 60.0
    await player._on_skip_chip()
    assert _seek_seconds() == [120.0]
    assert player.toast_chip.content.value == "Skipped intro"

    player._last_position = 1300.0
    await player._on_skip_chip()
    assert _seek_seconds() == [120.0, 1370.0]
    assert player.toast_chip.content.value == "Skipped outro"


@pytest.mark.asyncio
async def test_skip_stays_silent_when_the_seek_fails(no_spawn):
    player = _player(video=_Video(seek_fails=True))
    player.skip = {"intro": {"start": 30, "end": 119}}
    player._last_position = 60.0
    await player._on_skip_chip()
    assert player.toast_chip.content.value == ""  # nothing to confirm


@pytest.mark.asyncio
async def test_toast_show_sets_the_chip_and_hides_itself(no_spawn):
    player = _player()
    player._toast_show("Resumed from 1:05")
    assert player.toast_chip.content.value == "Resumed from 1:05"
    assert player.toast_chip.visible is True
    assert player.toast_chip.updates == 1


def test_window_label_agrees_with_the_skip_chip():
    """The confirmation and the chip label read the same window, so they
    can never call the same window intro and outro."""
    player = _player()
    player.skip = {
        "intro": {"start": 30, "end": 119},
        "outro": {"start": 1280, "end": 1369},
        "episode_intro": [],
        "episode_outro": [],
    }
    assert player._is_intro_window((30.0, 119.0)) is True
    assert player._is_intro_window((1280.0, 1369.0)) is False
    assert player._is_intro_window(None) is False

    player.skip = {"intro": {}, "outro": {}, "episode_intro": [100, 200]}
    assert player._is_intro_window((100.0, 200.0)) is True


# ---------------------------------------------------------------------------
# The quality chip: revealed from the resolved spec, not a racing probe
# ---------------------------------------------------------------------------


def test_quality_chip_reveals_from_the_resolved_spec():
    """The resolution already fetched the master's variants: the chip
    reveals at mount with a concrete quality label, instead of waiting for
    the probe that raced the proxy and never appeared on phones."""
    player = _player()
    player._variants_cache = [
        {"index": 0, "resolution": "1280x720", "bandwidth": 2_000_000}
    ]
    player._current_variant = None
    player.quality_text = _Chip().content
    player.quality_btn = _Chip()

    player._reveal_stream_options_from_spec()

    assert player.quality_btn.visible is True
    assert player.quality_btn.updates == 1
    assert player.quality_text.value == "720p"


def test_quality_chip_stays_hidden_without_variants():
    """A direct file has no variants — the chip must stay hidden rather than
    name a quality the stream cannot honour."""
    player = _player()
    player._variants_cache = None
    player.quality_btn = _Chip()

    player._reveal_stream_options_from_spec()

    assert player.quality_btn.visible is False


def test_quality_button_carries_its_row_as_content():
    """flet_video control bars reject a `content=None` Container on the 1.1.0
    line ("type 'Null' is not a subtype of type 'Control'"), so both buttons
    must mount their row as content and hide by visibility instead."""
    from components.player import controls as controls_mod

    player = _player()
    player.title = "Test"
    player.speed_text = ft.Text("1.0x", size=11)
    player.on_previous = None
    player.on_next = None
    controls_mod.build_player_controls(player)

    assert player.quality_btn.content is player.quality_row
    assert player.quality_btn.visible is False
    assert player.audio_btn.content is player.audio_row
    assert player.audio_btn.visible is False
