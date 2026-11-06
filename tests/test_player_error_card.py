"""The player mounts as a /play VIEW on the views stack (KTV exact).

Regression coverage for two crashes the user hit:
1. `RuntimeError: Frozen controls cannot be updated` — controls built inside
   a @ft.component render are frozen after mount, and ImmersivePlayer
   rewrites itself constantly (`overlay.visible = False` in _hide_overlay).
2. The Android system back used to EXIT the app: the overlay mount never
   receives `view_pop`. The view stack is what makes back reach Python.

The fix for both is the KTV structure: the player is a ft.View(route="/play")
appended to page.views, with a /blank underlay beneath the shell.
"""

import sys

sys.path.insert(0, __file__.rsplit("tests", 1)[0] + "src")

import flet as ft
from flet.controls.context import _context_page

import app_shell
from state.app_state import state as app_state


class _FakeController:
    def __init__(self, page):
        self._app_controller = self
        self.page = page
        self.played: list[str] = []

    async def play_downloaded(self, episode_session: str):
        self.played.append(episode_session)


class _FakePage:
    """Only what the views mount uses."""

    def __init__(self):
        self.views: list = []
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


def _reset_mount():
    app_shell._active_player = None
    app_shell._active_key = None


def _mount(state, controller, page, first: bool = False):
    if first:
        _reset_mount()
    token = _context_page.set(page)
    try:
        app_shell.open_player_view(controller)
    finally:
        _context_page.reset(token)


def test_player_mounts_as_a_view_not_the_component_tree():
    state = app_state
    _reset_state()
    state.player_open = True
    state.player_spec = {
        "resource": "https://cdn/index.m3u8",
        "episode_session": "ep123",
        "title": "Frieren",
    }
    page = _FakePage()

    _mount(state, _FakeController(page), page, first=True)

    assert len(page.views) == 1
    assert page.views[-1].route == "/play"
    assert page.views[-1].padding == 0  # KTV exact — no SafeArea on the mount
    # FocusScope wraps the player so Back/Escape always reaches it.
    assert app_shell._active_player is not None
    assert page.updates == 1


def test_second_render_does_not_remount():
    state = app_state
    _reset_state()
    state.player_open = True
    state.player_spec = {"resource": "https://cdn/index.m3u8", "episode_session": "ep1"}
    page = _FakePage()
    controller = _FakeController(page)

    _mount(state, controller, page, first=True)
    first = app_shell._active_player
    _mount(state, controller, page)

    assert app_shell._active_player is first
    assert len(page.views) == 1


def test_episode_switch_remounts():
    state = app_state
    _reset_state()
    state.player_open = True
    state.player_spec = {"resource": "a.m3u8", "episode_session": "ep1"}
    page = _FakePage()
    controller = _FakeController(page)

    _mount(state, controller, page, first=True)
    first = app_shell._active_player

    state.player_spec = {"resource": "b.m3u8", "episode_session": "ep2"}
    _mount(state, controller, page)

    assert app_shell._active_player is not first
    assert len(page.views) == 1  # old view replaced, not stacked


def test_close_pops_the_view():
    import asyncio

    state = app_state
    _reset_state()
    state.player_open = True
    state.player_spec = {"resource": "a.m3u8", "episode_session": "ep1"}
    page = _FakePage()

    _mount(state, _FakeController(page), page, first=True)
    assert len(page.views) == 1
    player = app_shell._active_player

    token = _context_page.set(page)
    try:
        asyncio.run(app_shell._close_player_with_save(player))
    finally:
        _context_page.reset(token)

    assert page.views == []
    assert state.player_open is False
    assert app_shell._active_player is None


def test_player_error_renders_card():
    state = app_state
    _reset_state()
    state.player_open = True
    state.player_error = "The downloaded file is missing."
    state.current_episode_session = "ep123"
    page = _FakePage()

    _mount(state, _FakeController(page), page, first=True)

    view = page.views[-1]
    texts = [c.value for c in _walk(view) if isinstance(c, ft.Text)]
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
    page = _FakePage()
    controller = _FakeController(page)

    _mount(state, controller, page, first=True)
    retry = next(
        b
        for b in _find_buttons(page.views[-1])
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

    _mount(state, _FakeController(page), page, first=True)
    back = next(
        b
        for b in _find_buttons(page.views[-1])
        if isinstance(b.content, str) and b.content == "Go Back"
    )
    back.on_click(None)
    assert state.player_error is None
    assert state.player_open is False

    # The next render drops the view from the stack.
    _mount(state, _FakeController(page), page)
    assert page.views == []


def test_column_padding_is_moved_to_a_wrapper():
    """Browse + Downloads: Column has no padding field in flet 1.0.4."""
    assert "padding" not in set(ft.Column.__dataclass_fields__)
    # The screen-level insets must live on a Container, which does.
    assert "padding" in set(ft.Container.__dataclass_fields__)
