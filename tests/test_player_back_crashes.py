"""Player + Back crash regressions — M1.4.

Each test kills one defect from the swarm audit:
- focus_scope: page.run_task(lambda: coro) raises TypeError (run_task
  wants a coroutine FUNCTION) — player Back never worked
- focus_manager: Backspace while typing navigated away from the query;
  an async previous handler's coroutine was dropped; a raising back
  handler broke key dispatch
- focus_styles: attach_focus_zoom clobbered a pre-installed on_focus
- immersive_player: relative HLS variants all resolved to the first
  rendition; skip-intro seeked in milliseconds; the screenshot snack
  claimed success before the frame existed; the first-ready signal
  hid a just-raised error card; an older toast's hide task killed a
  newer toast
"""

import asyncio
import inspect
import os
import sys

_TMP = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import flet as ft  # noqa: E402
import pytest  # noqa: E402

from components.focus_styles import attach_focus_zoom  # noqa: E402
from components.player.immersive_player import (  # noqa: E402
    ImmersivePlayer,
    _stream_variants,
)
from core.focus_manager import FocusManager  # noqa: E402
from hooks.use_focus_scope import focus_scope  # noqa: E402


class _FakePage:
    """Captures run_task calls instead of scheduling them."""

    def __init__(self):
        self.run_tasks = []
        self.on_keyboard_event = None

    def run_task(self, handler, *args, **kwargs):
        self.run_tasks.append((handler, args, kwargs))

    async def _drain(self):
        """Run the captured coroutine handlers to completion."""
        while self.run_tasks:
            handler, args, kwargs = self.run_tasks.pop(0)
            result = handler(*args, **kwargs)
            if inspect.isawaitable(result):
                await result


# ---------------------------------------------------------------------------
# focus_scope
# ---------------------------------------------------------------------------


def test_focus_scope_schedules_the_sync_handlers_coroutine():
    """The crash: run_task(lambda: coro) — run_task demands a coroutine
    FUNCTION, so every player Back press raised TypeError."""
    from flet.controls.context import _context_page

    page = _FakePage()
    fired = []

    async def on_back():
        fired.append(True)

    scope = focus_scope(ft.Container(), on_back)

    class _Event:
        key = "Go Back"

    token = _context_page.set(page)
    try:
        scope.on_key_down(_Event())
    finally:
        _context_page.reset(token)
    assert page.run_tasks, "the coroutine must be scheduled"
    (scheduled, _args, _kwargs) = page.run_tasks[0]
    assert inspect.iscoroutinefunction(scheduled)
    asyncio.run(page._drain())
    assert fired == [True]


def test_focus_scope_tolerates_no_page_context():
    """ft.context.page RAISES outside a live page — the old None-guard
    was dead code and the raise escaped the handler."""

    async def on_back():
        raise AssertionError("must not fire without a page")

    scope = focus_scope(ft.Container(), on_back)

    class _Event:
        key = "Go Back"

    # Deliberately outside any page context.
    scope.on_key_down(_Event())  # must not raise


# ---------------------------------------------------------------------------
# FocusManager
# ---------------------------------------------------------------------------


def _key(key, control=None):
    """ft.KeyboardEvent(name, control, key, shift, ctrl, alt, meta) — the
    first two are required positionals."""
    return ft.KeyboardEvent(
        "keydown", control or ft.Container(), key, False, False, False, False
    )


def test_backspace_while_typing_does_not_navigate_away():
    """The search fields lost every second Backspace press to the global
    Back handler, closing the screen mid-query."""
    page = _FakePage()
    seen = []
    fm = FocusManager(page)
    fm.set_back_handler(lambda: seen.append("back"))

    field = ft.TextField()
    fm._handle_keyboard(_key("Backspace", field))
    assert seen == []

    fm._handle_keyboard(_key("Backspace", ft.Container()))
    assert seen == ["back"]


def test_async_previous_handler_is_scheduled():
    page = _FakePage()
    fired = []

    async def previous(e):
        fired.append(True)

    page.on_keyboard_event = previous
    fm = FocusManager(page)
    fm._handle_keyboard(_key("a"))
    assert page.run_tasks
    asyncio.run(page._drain())
    assert fired == [True]


def test_a_raising_back_handler_does_not_break_dispatch():
    page = _FakePage()
    fm = FocusManager(page)
    fm.set_back_handler(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    fm._handle_keyboard(_key("Escape"))  # must not raise


# ---------------------------------------------------------------------------
# focus_styles
# ---------------------------------------------------------------------------


def test_attach_focus_zoom_chains_the_existing_handlers():
    """clobbering on_focus silently killed make_scroll_on_focus."""
    button = ft.FilledButton("card")
    seen = []
    button.on_focus = lambda e: seen.append("focus")
    button.on_blur = lambda e: seen.append("blur")

    attach_focus_zoom(button)

    class _Event:
        pass

    button.on_focus(_Event())
    assert seen == ["focus"]
    assert getattr(button, "scale", None) == 1.04  # the zoom still applies
    button.on_blur(_Event())
    assert seen == ["focus", "blur"]


# ---------------------------------------------------------------------------
# _stream_variants
# ---------------------------------------------------------------------------


def test_relative_variants_resolve_against_the_master_url():
    """Every relative variant used to collapse onto the first media
    line — pinning any quality replayed the same rendition."""
    master = (
        "#EXTM3U\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=640x360\n"
        "360/index.m3u8\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=2400000,RESOLUTION=1280x720\n"
        "720/index.m3u8\n"
    )
    variants = _stream_variants(master, "https://cdn.example/v/master.m3u8")
    uris = [v["uri"] for v in variants]
    assert uris == [
        "https://cdn.example/v/360/index.m3u8",
        "https://cdn.example/v/720/index.m3u8",
    ]


def test_absolute_variants_pass_through():
    master = (
        "#EXTM3U\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=1000\n"
        "https://other.example/a.m3u8\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=2000\n"
        "https://other.example/b.m3u8\n"
    )
    variants = _stream_variants(master, "https://cdn.example/master.m3u8")
    assert [v["uri"] for v in variants] == [
        "https://other.example/a.m3u8",
        "https://other.example/b.m3u8",
    ]


# ---------------------------------------------------------------------------
# ImmersivePlayer (bare instance — the test_player_presentation pattern)
# ---------------------------------------------------------------------------


class _Chip:
    def __init__(self):
        self.content = type("C", (), {"value": ""})()
        self.visible = False

    def update(self):
        self.updates = getattr(self, "updates", 0) + 1


class _Video:
    def __init__(self, screenshot=None):
        self.playback_rate = 1.0
        self.updates = 0
        self.seeks = []
        self._screenshot = screenshot

    def update(self):
        self.updates += 1

    async def seek(self, position):
        self.seeks.append(position)

    async def take_screenshot(self):
        if isinstance(self._screenshot, Exception):
            raise self._screenshot
        return self._screenshot


def _player(video=None, **attrs):
    player = ImmersivePlayer.__new__(ImmersivePlayer)
    player.video = video or _Video()
    player.toast_chip = _Chip()
    player.subtitles = []
    player.skip = {}
    player.speed_texts = []
    player._speed_index = 2
    player._speed_rate = 1.0
    player._is_closing = False
    player._is_final_error = False
    player._overlay_hidden = False
    player._toast_gen = 0
    player.store = None
    player.resume_key = None
    player._initial_resume_position = None
    player._last_duration = 0.0
    player._last_position = 0.0
    player._reconnect_count = 0
    for k, v in attrs.items():
        setattr(player, k, v)
    return player


@pytest.mark.asyncio
async def test_older_toast_hide_does_not_kill_the_newer_toast():
    player = _player()
    player._toast_show("first")
    await asyncio.sleep(0.05)
    player._toast_show("second")
    # The first toast's hide task (2s from its spawn) must not hide the
    # second toast early: it is still visible well past its own 0.05s.
    await asyncio.sleep(0.3)
    assert player.toast_chip.visible is True
    await asyncio.sleep(1.8)
    # ...and now it hides (the second toast's own timer).
    assert player.toast_chip.visible is False


@pytest.mark.asyncio
async def test_first_ready_does_not_hide_a_just_raised_error_card():
    player = _player()
    player._is_final_error = True
    hidden = []
    player._hide_overlay = lambda: hidden.append(True)
    player._check_and_trigger_seek = lambda: hidden.append("seek")
    player._apply_default_subtitle = lambda: hidden.append("subs")
    player._on_first_ready()
    assert hidden == []


@pytest.mark.asyncio
async def test_first_ready_applies_the_saved_speed():
    player = _player()
    player._speed_rate = 1.25
    player._hide_overlay = lambda: None
    player._check_and_trigger_seek = lambda: None
    player._apply_default_subtitle = lambda: None
    player._on_first_ready()
    assert player.video.playback_rate == 1.25


@pytest.mark.asyncio
async def test_snapshot_confirmation_rides_the_result(tmp_path):
    """The confirmation rides the RESULT: the toast names the file that
    was actually written (Phase 4 Step 1 made the save real)."""
    player = _player(video=_Video(screenshot=b"png"))

    async def _dir():
        return str(tmp_path)

    player._snapshot_directory = _dir
    messages = []
    import core.notify as notify

    original = notify.show_snack
    notify.show_snack = lambda page, msg, **kw: messages.append(msg)
    try:
        await player._take_snapshot()
    finally:
        notify.show_snack = original
    files = [n for n in os.listdir(tmp_path) if n.endswith(".png")]
    assert len(files) == 1, "the bytes reach the disk"
    assert messages == [f"Saved {files[0]}"]


@pytest.mark.asyncio
async def test_snapshot_failure_is_surfaced():
    player = _player(video=_Video(screenshot=None))  # backend can't capture
    messages = []
    import core.notify as notify

    original = notify.show_snack
    notify.show_snack = lambda page, msg, **kw: messages.append(msg)
    try:
        await player._take_snapshot()
    finally:
        notify.show_snack = original
    assert messages == ["Screenshot unavailable"]
