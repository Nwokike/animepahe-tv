"""Header corrections from the owner's live run — 2026-10-16 (later).

Two reports:
1. "I see the back button… the back button with title anime is ahead of the
   header. Find a way to integrate the back button in the header; the header
   should always be top. Just remove 'Anime'."
   → the shell's separate `_detail_appbar` is gone; the back control is an
   optional leading disc INSIDE `app_header`.
2. "To change color mode… there's an error."
   Log: `RuntimeError: Frozen controls cannot be updated.` at
   `theme_action.content.icon = icon` — the 3-way cycle mutated a control
   inside a frozen `@ft.component` subtree. The icon now lands through the
   observable `state.theme_mode` (a normal re-render), never a mutation.
"""

import inspect
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import flet as ft


class _State:
    def __init__(self):
        self.current_source_name = "anikato"
        self.theme_mode = ft.ThemeMode.DARK
        self.update_available = False
        self.update_data = None


class _AppController:
    def __init__(self):
        self.saved: list[str] = []

    async def save_theme_mode(self, mode):
        self.saved.append(str(mode))


class _Controller:
    def __init__(self):
        self._app_controller = _AppController()
        self.picker_opens = 0

    def open_backend_picker(self):
        self.picker_opens += 1


class _Page:
    def __init__(self):
        self.theme_mode = ft.ThemeMode.DARK


def _walk(control):
    yield control
    for child in getattr(control, "controls", []) or []:
        yield from _walk(child)
    content = getattr(control, "content", None)
    if content is not None:
        yield from _walk(content)


def _header(**kwargs):
    from components.app_header import app_header

    state = _State()
    controller = _Controller()
    page = _Page()
    return app_header(state, page, controller, **kwargs), state, page, controller


# ---------------------------------------------------------------------------
# 1. Back lives INSIDE the header; no second bar above it
# ---------------------------------------------------------------------------


def test_no_back_control_by_default():
    header, _, _, _ = _header()
    icons = [n for n in _walk(header) if isinstance(n, ft.Icon)]
    assert not any(n.icon == ft.Icons.ARROW_BACK_ROUNDED for n in icons)


def test_on_back_puts_a_round_back_button_in_the_header():
    back_calls = []
    header, _, _, _ = _header(on_back=lambda: back_calls.append("b"))
    back = next(
        n
        for n in _walk(header)
        if isinstance(n, ft.Icon) and n.icon == ft.Icons.ARROW_BACK_ROUNDED
    )
    # It is tappable and routes to the caller's handler.
    disc = next(
        n
        for n in _walk(header)
        if isinstance(n, ft.Container) and n.content is back
    )
    disc.on_click(None)
    assert back_calls == ["b"]


def test_the_detail_screen_has_no_appbar_strip_and_drops_the_anime_title():
    import app_shell
    import screens.anime_detail_screen as detail

    shell = inspect.getsource(app_shell)
    assert "_detail_appbar" not in shell, "the separate AppBar must be gone"
    # The shell no longer sets chrome for the detail view (the screen's own
    # header is the only top element).
    shell_body = shell[shell.index('if active_view == "anime"') :][:600]
    assert "chrome = None" in shell_body

    source = inspect.getsource(detail)
    assert 'subtitle="Episodes"' not in source, "the 'Episodes' subtitle was dropped"
    assert 'Text("Anime"' not in source, "the bare 'Anime' title must be gone"
    # The back control is handed to the shared header instead.
    assert "on_back=lambda: controller.back()" in source


# ---------------------------------------------------------------------------
# 2. The theme cycle never mutates a frozen control
# ---------------------------------------------------------------------------


def test_the_theme_action_does_not_mutate_its_own_icon():
    import components.app_header as app_header_module

    source = inspect.getsource(app_header_module)
    assert "theme_action.content.icon" not in source, (
        "mutating the action raised 'Frozen controls cannot be updated.' "
        "inside a frozen component subtree (owner's run)"
    )
    assert "state.theme_mode = nxt" in source, "the observable carries the change"


def test_cycling_the_theme_sets_the_observable_state(monkeypatch):
    header, state, page, _controller = _header()
    # `spawn` needs a running loop; on a click there is one in the real app.
    # Capture the coroutine instead of scheduling it.
    spawned: list = []

    def _capture(coro, **kwargs):
        spawned.append(coro)
        coro.close()

    monkeypatch.setattr("core.tasks.spawn", _capture)
    theme_action = next(
        n
        for n in _walk(header)
        if isinstance(n, ft.Container) and getattr(n, "tooltip", "") == "Switch theme"
    )
    theme_action.on_click(None)
    # DARK -> LIGHT, on the page (what Flutter paints) AND on the state
    # (what re-renders the header's icon through the component path).
    assert page.theme_mode == ft.ThemeMode.LIGHT
    assert state.theme_mode == ft.ThemeMode.LIGHT
    assert len(spawned) == 1, "the choice persists in the same tap"


def test_the_icon_names_the_mode_the_tap_lands_on():
    from components.app_header import theme_icon_for

    state = _State()
    for mode, expected in (
        (ft.ThemeMode.DARK, ft.Icons.LIGHT_MODE_ROUNDED),
        (ft.ThemeMode.LIGHT, ft.Icons.SETTINGS_SYSTEM_DAYDREAM_ROUNDED),
        (ft.ThemeMode.SYSTEM, ft.Icons.DARK_MODE_ROUNDED),
    ):
        state.theme_mode = mode
        assert theme_icon_for(_Page(), state) == expected
