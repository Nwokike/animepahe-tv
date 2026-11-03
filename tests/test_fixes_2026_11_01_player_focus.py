"""Tests for 2026-11-01 player/focus fixes (B-06, B-08, B-09).

These tests verify the specific fixes for:
- B-06: _stream_variants relative URI resolution
- B-08: FocusManager Backspace handling with text inputs + await chained handler
- B-09: card_focus_scale uses scale; attach_focus_zoom chains handlers
"""

import asyncio
import inspect
import os
import sys

import flet as ft

_TMP = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from components.focus_styles import (
    attach_focus_zoom,
    card_button_style,
    card_focus_scale,
)
from core.focus_manager import FieldFocusTracker, FocusManager
from services.hls_proxy import HLSProxy, _b64_decode


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


def _key(key, control=None):
    """Create a ft.KeyboardEvent with the given key and control."""
    return ft.KeyboardEvent("keydown", control or ft.Container(), key, False, False, False, False)


# ---------------------------------------------------------------------------
# B-06: relative variant URI resolution (now in the proxy's rewrite)
# ---------------------------------------------------------------------------


def _rewritten_uris(content, master_url):
    proxy = HLSProxy()
    proxy.host = "127.0.0.1"
    proxy.port = 12345
    out = proxy._rewrite_m3u8(content, master_url, None, {}, None, None)
    uris = []
    for line in out.splitlines():
        line = line.strip()
        if "url=" not in line:
            continue
        token = line.split("url=", 1)[1].split("&", 1)[0]
        uris.append(_b64_decode(token))
    return uris


def test_stream_variants_relative_uris_resolve_correctly():
    """Relative variant URIs must resolve against the master playlist URL
    using urllib.parse.urljoin, not against the first media line's directory.

    The old code collapsed every relative variant onto the first media URI
    because it used a single `base` computed from the first media line.
    """
    master = (
        "#EXTM3U\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=640x360\n"
        "360/index.m3u8\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=2400000,RESOLUTION=1280x720\n"
        "720/index.m3u8\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=4800000,RESOLUTION=1920x1080\n"
        "1080/index.m3u8\n"
    )
    uris = _rewritten_uris(master, "https://cdn.example/v/master.m3u8")
    assert uris == [
        "https://cdn.example/v/360/index.m3u8",
        "https://cdn.example/v/720/index.m3u8",
        "https://cdn.example/v/1080/index.m3u8",
    ], f"Expected correct resolution, got {uris}"


def test_stream_variants_absolute_uris_pass_through():
    """Absolute variant URIs must pass through unchanged."""
    master = (
        "#EXTM3U\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=1000\n"
        "https://other.example/a.m3u8\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=2000\n"
        "https://other.example/b.m3u8\n"
    )
    uris = _rewritten_uris(master, "https://cdn.example/master.m3u8")
    assert uris == [
        "https://other.example/a.m3u8",
        "https://other.example/b.m3u8",
    ]


def test_stream_variants_relative_with_parent_dir():
    """Relative URIs with parent directory references must resolve correctly."""
    master = "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1000\n../other/stream.m3u8\n"
    uris = _rewritten_uris(master, "https://cdn.example/v/master.m3u8")
    assert uris == [
        "https://cdn.example/other/stream.m3u8",
    ]


def test_media_playlist_segments_resolve_relative():
    """The proxy rewrite resolves a MEDIA playlist's segment URIs too (the
    player no longer parses playlists — the proxy owns all of it)."""
    media = "#EXTM3U\n#EXTINF:10,\nsegment1.ts\n"
    assert _rewritten_uris(media, "https://example.com/master.m3u8") == [
        "https://example.com/segment1.ts"
    ]


# ---------------------------------------------------------------------------
# B-08: FocusManager Backspace handling + async chained handler
# ---------------------------------------------------------------------------


def test_backspace_in_textfield_does_not_trigger_back():
    """Backspace while a TextField is focused must not navigate away."""
    page = _FakePage()
    seen = []
    fm = FocusManager(page)
    fm.set_back_handler(lambda: seen.append("back"))

    field = ft.TextField()
    fm._handle_keyboard(_key("Backspace", field))
    assert seen == [], "Backspace in TextField must not trigger back handler"


def test_backspace_in_searchbar_does_not_trigger_back():
    """Backspace while a SearchBar is focused must not navigate away."""
    page = _FakePage()
    seen = []
    fm = FocusManager(page)
    fm.set_back_handler(lambda: seen.append("back"))

    field = ft.SearchBar()
    fm._handle_keyboard(_key("Backspace", field))
    assert seen == [], "Backspace in SearchBar must not trigger back handler"


def test_backspace_in_cupertinotextfield_does_not_trigger_back():
    """Backspace while a CupertinoTextField is focused must not trigger back."""
    page = _FakePage()
    seen = []
    fm = FocusManager(page)
    fm.set_back_handler(lambda: seen.append("back"))

    field = ft.CupertinoTextField()
    fm._handle_keyboard(_key("Backspace", field))
    assert seen == [], "Backspace in CupertinoTextField must not trigger back handler"


def test_escape_in_textfield_does_not_trigger_back():
    """Escape while a TextField is focused must not navigate away (cancels edit).

    This is handled by FieldFocusTracker, not by _is_text_editing.
    """
    page = _FakePage()
    seen = []
    fm = FocusManager(page)
    fm.set_back_handler(lambda: seen.append("back"))

    field = ft.TextField()
    tracker = FieldFocusTracker()
    tracker.attach(field)
    fm.field_focus = tracker

    # First Escape cancels edit via tracker
    field.on_focus(None)  # activate tracker
    fm._handle_keyboard(_key("Escape", field))
    assert seen == [], "Escape in TextField must be consumed by tracker"

    # Second Escape triggers back (tracker no longer active)
    fm._handle_keyboard(_key("Escape", field))
    assert seen == ["back"], "Second Escape triggers back"


def test_backspace_in_container_triggers_back():
    """Backspace on a non-text control must trigger the back handler."""
    page = _FakePage()
    seen = []
    fm = FocusManager(page)
    fm.set_back_handler(lambda: seen.append("back"))

    fm._handle_keyboard(_key("Backspace", ft.Container()))
    assert seen == ["back"], "Backspace on non-text control must trigger back"


def test_other_back_keys_still_work_in_textfield():
    """Other BACK_KEYS (Go Back, Browser Back, etc.) must still navigate
    even when a text field is focused."""
    page = _FakePage()
    seen = []
    fm = FocusManager(page)
    fm.set_back_handler(lambda: seen.append("back"))

    field = ft.TextField()
    for key in ("Go Back", "Browser Back", "Back", "BrowserBack"):
        seen.clear()
        fm._handle_keyboard(_key(key, field))
        assert seen == ["back"], f"{key} must trigger back even in text field"


def test_async_previous_handler_is_awaited():
    """The previous page.on_keyboard_event handler, if async, must be
    awaited via page.run_task (not fire-and-forget)."""
    page = _FakePage()
    fired = []

    async def previous(e):
        fired.append(True)

    page.on_keyboard_event = previous
    fm = FocusManager(page)
    fm._handle_keyboard(_key("a"))

    # The async handler should have been scheduled via run_task
    assert page.run_tasks, "async previous handler must be scheduled"
    asyncio.run(page._drain())
    assert fired == [True], "async previous handler must complete"


def test_async_back_handler_is_awaited():
    """The back handler, if async, must be awaited via page.run_task."""
    page = _FakePage()
    fired = []
    fm = FocusManager(page)
    fm.set_back_handler(lambda: _async_back(fired))

    async def _async_back(fired_list):
        fired_list.append(True)

    fm._handle_keyboard(_key("Escape"))
    assert page.run_tasks, "async back handler must be scheduled"
    asyncio.run(page._drain())
    assert fired == [True], "async back handler must complete"


def test_async_key_consumer_is_awaited():
    """The key consumer (player), if async, must be awaited via page.run_task."""
    page = _FakePage()
    fired = []
    fm = FocusManager(page)
    fm.set_key_consumer(lambda e: _async_consumer(fired))

    async def _async_consumer(fired_list):
        fired_list.append(True)

    fm._handle_keyboard(_key("ArrowRight"))
    assert page.run_tasks, "async key consumer must be scheduled"
    asyncio.run(page._drain())
    assert fired == [True], "async key consumer must complete"


def test_raising_back_handler_does_not_break_dispatch():
    """A back handler that raises must not break keyboard dispatch."""
    page = _FakePage()
    fm = FocusManager(page)
    fm.set_back_handler(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    fm._handle_keyboard(_key("Escape"))  # must not raise


def test_raising_key_consumer_does_not_break_dispatch():
    """A key consumer that raises must not break keyboard dispatch."""
    page = _FakePage()
    fm = FocusManager(page)
    fm.set_key_consumer(lambda e: (_ for _ in ()).throw(RuntimeError("boom")))
    fm._handle_keyboard(_key("ArrowRight"))  # must not raise


def test_field_focus_tracker_consumes_first_backspace():
    """FieldFocusTracker.handle_back must consume the first Back when active."""
    from core.focus_manager import FieldFocusTracker

    tracker = FieldFocusTracker()
    assert tracker.handle_back() is False  # not active

    tracker.active = True
    assert tracker.handle_back() is True  # consumes and deactivates
    assert tracker.active is False


def test_field_focus_tracker_calls_on_cancel():
    """FieldFocusTracker must call on_cancel when handling back."""
    from core.focus_manager import FieldFocusTracker

    cancelled = []
    tracker = FieldFocusTracker()
    tracker._cancel = lambda: cancelled.append(True)
    tracker.active = True
    tracker.handle_back()
    assert cancelled == [True]


# ---------------------------------------------------------------------------
# B-09: focus_styles card_focus_scale + attach_focus_zoom
# ---------------------------------------------------------------------------


def test_card_focus_scale_validates_scale():
    """card_focus_scale must validate the scale parameter."""
    # Valid scales
    anim = card_focus_scale(1.04)
    assert isinstance(anim, ft.Animation)
    assert anim.duration == 150
    assert anim.curve == ft.AnimationCurve.EASE_OUT

    anim = card_focus_scale(1.1)
    assert isinstance(anim, ft.Animation)

    # Invalid scales
    for bad in (0, -0.1, -1):
        try:
            card_focus_scale(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected ValueError for scale={bad}")


def test_card_focus_scale_returns_animation_with_correct_defaults():
    """card_focus_scale returns Animation with duration=150, curve=EASE_OUT."""
    anim = card_focus_scale()
    assert anim.duration == 150
    assert anim.curve == ft.AnimationCurve.EASE_OUT


def test_attach_focus_zoom_chains_existing_handlers():
    """attach_focus_zoom must chain (not clobber) pre-existing on_focus/on_blur."""
    button = ft.FilledButton("card")
    seen = []
    button.on_focus = lambda e: seen.append("focus")
    button.on_blur = lambda e: seen.append("blur")

    attach_focus_zoom(button, scale=1.05)

    class _Event:
        pass

    # Trigger focus - should call old handler AND apply zoom
    button.on_focus(_Event())
    assert seen == ["focus"], "old on_focus must be called"
    assert getattr(button, "scale", None) == 1.05, "zoom must apply"

    # Trigger blur - should call old handler AND reset zoom
    button.on_blur(_Event())
    assert seen == ["focus", "blur"], "old on_blur must be called"
    assert getattr(button, "scale", None) == 1.0, "zoom must reset"


def test_attach_focus_zoom_works_without_previous_handlers():
    """attach_focus_zoom must work when no previous handlers exist."""
    button = ft.FilledButton("card")
    assert button.on_focus is None
    assert button.on_blur is None

    attach_focus_zoom(button, scale=1.05)

    class _Event:
        pass

    button.on_focus(_Event())
    assert getattr(button, "scale", None) == 1.05
    button.on_blur(_Event())
    assert getattr(button, "scale", None) == 1.0


def test_attach_focus_zoom_scale_parameter_respected():
    """attach_focus_zoom must respect the scale parameter."""
    button = ft.FilledButton("card")

    attach_focus_zoom(button, scale=1.1)

    class _Event:
        pass

    button.on_focus(_Event())
    assert getattr(button, "scale", None) == 1.1
    button.on_blur(_Event())
    assert getattr(button, "scale", None) == 1.0


def test_card_button_style_has_focused_side():
    """card_button_style must have a FOCUSED side with primary color."""
    style = card_button_style()
    sides = style.side
    assert sides[ft.ControlState.FOCUSED].width == 2.5
    assert sides[ft.ControlState.FOCUSED].color is not None
    assert style.bgcolor == ft.Colors.TRANSPARENT
    assert style.elevation == 0


def test_card_button_style_overlay_alpha_validation():
    """card_button_style must validate overlay_alpha."""
    for bad in (-0.1, 1.5):
        try:
            card_button_style(overlay_alpha=bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected ValueError for overlay_alpha={bad}")

    try:
        card_button_style(radius=-1)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for negative radius")


# ---------------------------------------------------------------------------
# Integration: FocusManager + FieldFocusTracker together
# ---------------------------------------------------------------------------


def test_field_focus_tracker_integrated_with_focus_manager():
    """FieldFocusTracker attached to a field must be consulted by FocusManager.

    The tracker handles Escape (cancels edit) while _is_text_editing handles
    Backspace. Both must work together.
    """
    page = _FakePage()
    seen = []
    fm = FocusManager(page)
    fm.set_back_handler(lambda: seen.append("back"))

    field = ft.TextField()
    # Attach the tracker (simulating what dialogs do)
    tracker = FieldFocusTracker()
    tracker.attach(field)
    fm.field_focus = tracker

    # Focus the field (simulated by calling on_focus)
    field.on_focus(None)

    # Escape should be consumed by the tracker (first press cancels edit)
    fm._handle_keyboard(_key("Escape", field))
    assert seen == [], "Escape consumed by field focus tracker"

    # Second Escape (tracker no longer active) should trigger back
    fm._handle_keyboard(_key("Escape", field))
    assert seen == ["back"], "Second Escape triggers back"


# ---------------------------------------------------------------------------
# Verify flet 0.85.3 APIs used exist
# ---------------------------------------------------------------------------


def test_flet_0853_keyboardevent_fields():
    """Verify KeyboardEvent fields used in FocusManager exist in flet 0.85.3."""
    import dataclasses

    fields = {f.name for f in dataclasses.fields(ft.KeyboardEvent)}
    required = {"name", "data", "control", "key", "shift", "ctrl", "alt", "meta"}
    assert required.issubset(fields), f"Missing fields: {required - fields}"


def test_flet_0853_controlstate_exists():
    """Verify ControlState enum exists with expected values in flet 0.85.3."""
    assert hasattr(ft, "ControlState")
    states = set(ft.ControlState.__members__.keys())
    required = {"FOCUSED", "HOVERED", "PRESSED", "DISABLED", "DEFAULT"}
    assert required.issubset(states), f"Missing ControlState: {required - states}"


def test_flet_0853_animation_curve_exists():
    """Verify AnimationCurve.EASE_OUT exists in flet 0.85.3."""
    assert hasattr(ft.AnimationCurve, "EASE_OUT")
