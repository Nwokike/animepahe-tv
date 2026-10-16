"""The player mounts into page.overlay (imperatively), not the component tree.

Regression coverage for two crashes the user hit:
1. `RuntimeError: Frozen controls cannot be updated` — controls built inside
   a @ft.component render are frozen after mount, and ImmersivePlayer
   rewrites itself constantly (`overlay.visible = False` in _hide_overlay).
2. `Column.__init__() got an unexpected keyword argument 'padding'` on the
   Browse screen, plus the same latent bug on Downloads.

The fix for (1) is the KTV structure: mount the player as a top-level
overlay control (KTV uses a ft.View; page.views is gone in flet 1.0.4).
"""

import sys

sys.path.insert(0, __file__.rsplit("tests", 1)[0] + "src")

import flet as ft
from flet.controls.context import _context_page

import app_shell
from state.app_state import state as app_state


class _FakeController:
    def __init__(self):
        self._app_controller = self
        self.played: list[str] = []

    async def play_downloaded(self, episode_session: str):
        self.played.append(episode_session)


class _FakePage:
    """Only what the overlay mount uses."""

    def __init__(self):
        self.overlay: list = []
        self.updates = 0

    def update(self):
        self.updates += 1


def _reset_state():
    app_state.player_open = False
    app_state.player_spec = None
    app_state.player_error = None
    app_state.episodes_version = 0


def _walk(control):
    yield control
    for child in getattr(control, "controls", None) or []:
        yield from _walk(child)
    content = getattr(control, "content", None)
    if content is not None and not isinstance(content, list):
        yield from _walk(content)


def _find_buttons(control):
    # flet 0.85.3: OutlinedButton does not inherit Button (only FilledButton
    # does), so both are matched explicitly.
    _BUTTONS = tuple(
        c for c in (getattr(ft, "OutlinedButton", None), getattr(ft, "Button", None)) if c
    )
    return [
        c for c in _walk(control) if _BUTTONS and isinstance(c, _BUTTONS) and hasattr(c, "on_click")
    ]


def _reset_overlay():
    app_shell._active_player = None
    app_shell._active_mount = None
    app_shell._active_key = None


def _mount(state, controller, page, first: bool = False):
    if first:
        _reset_overlay()
    token = _context_page.set(page)
    try:
        app_shell._use_player_overlay(state, controller)
    finally:
        _context_page.reset(token)


def test_player_mounts_into_overlay_not_the_component_tree():
    state = app_state
    _reset_state()
    state.player_open = True
    state.player_spec = {
        "resource": "https://cdn/index.m3u8",
        "episode_session": "ep123",
        "title": "Frieren",
    }
    page = _FakePage()

    _mount(state, _FakeController(), page, first=True)

    assert len(page.overlay) == 1
    # FocusScope wraps the player so Back/Escape always reaches it.
    assert app_shell._active_player is not None
    assert page.updates == 1


def test_second_render_does_not_remount():
    state = app_state
    _reset_state()
    state.player_open = True
    state.player_spec = {"resource": "https://cdn/index.m3u8", "episode_session": "ep1"}
    page = _FakePage()
    controller = _FakeController()

    _mount(state, controller, page, first=True)
    first = app_shell._active_player
    _mount(state, controller, page)

    assert app_shell._active_player is first
    assert len(page.overlay) == 1


def test_episode_switch_remounts():
    state = app_state
    _reset_state()
    state.player_open = True
    state.player_spec = {"resource": "a.m3u8", "episode_session": "ep1"}
    page = _FakePage()
    controller = _FakeController()

    _mount(state, controller, page, first=True)
    first = app_shell._active_player

    state.player_spec = {"resource": "b.m3u8", "episode_session": "ep2"}
    _mount(state, controller, page)

    assert app_shell._active_player is not first
    assert len(page.overlay) == 1


def test_close_unmounts_the_overlay_node():
    import asyncio

    state = app_state
    _reset_state()
    state.player_open = True
    state.player_spec = {"resource": "a.m3u8", "episode_session": "ep1"}
    page = _FakePage()

    _mount(state, _FakeController(), page, first=True)
    assert len(page.overlay) == 1

    token = _context_page.set(page)
    try:
        asyncio.run(app_shell._async_close_player())
    finally:
        _context_page.reset(token)

    assert page.overlay == []
    assert state.player_open is False


def test_player_error_renders_card():
    state = app_state
    _reset_state()
    state.player_open = True
    state.player_error = "The downloaded file is missing."
    state.current_episode_session = "ep123"
    page = _FakePage()

    _mount(state, _FakeController(), page, first=True)

    mount = page.overlay[0]
    texts = [c.value for c in _walk(mount) if isinstance(c, ft.Text)]
    assert "The downloaded file is missing." in texts
    assert "Playback unavailable" in texts
    assert app_shell._active_player is None  # the error card is not a player


def test_retry_clears_error_and_replays():
    import asyncio

    state = app_state
    _reset_state()
    state.player_open = True
    state.player_error = "The downloaded file is missing."
    state.current_episode_session = "ep123"
    controller = _FakeController()
    page = _FakePage()

    _mount(state, controller, page, first=True)
    retry = next(
        b
        for b in _find_buttons(page.overlay[0])
        if isinstance(b.content, str) and b.content == "Retry"
    )

    async def _run():
        retry.on_click(None)
        await asyncio.sleep(0)

    asyncio.run(_run())
    assert state.player_error is None
    assert controller.played == ["ep123"]


def test_go_back_clears_error_and_unmounts():

    state = app_state
    _reset_state()
    state.player_open = True
    state.player_error = "The downloaded file is missing."
    page = _FakePage()

    _mount(state, _FakeController(), page, first=True)
    back = next(
        b
        for b in _find_buttons(page.overlay[0])
        if isinstance(b.content, str) and b.content == "Go Back"
    )
    back.on_click(None)
    assert state.player_error is None
    assert state.player_open is False

    # The next render drops the mount from the overlay.
    _mount(state, _FakeController(), page)
    assert page.overlay == []


def test_column_padding_is_moved_to_a_wrapper():
    """Browse + Downloads: Column has no padding field in flet 1.0.4."""
    assert "padding" not in set(ft.Column.__dataclass_fields__)
    # The screen-level insets must live on a Container, which does.
    assert "padding" in set(ft.Container.__dataclass_fields__)
