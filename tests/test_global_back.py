"""Global Back precedence (the original 1.0.9 chain, translated to 1.0.4).

The old app popped `page.views`; views are gone in flet 1.0.4, so the
chain routes through the shell's navigation closures instead:

  open dialog -> close it
  player open -> do nothing (the player's FocusScope owns Back so it can
                  save the resume position before the shell tears it down)
  detail view -> back to tabs
  tabs root   -> let the OS background the app
"""

import sys

sys.path.insert(0, __file__.rsplit("tests", 1)[0] + "src")

import flet as ft

import main as app_main
from core.state import AppState
from state.app_state import state as singleton_state


class _Dialogs:
    """Models flet's Page._dialogs stack (controls list, open flag)."""

    def __init__(self):
        self.controls: list = []


class _FakePage:
    title = None

    def __init__(self):
        self.shown: list = []
        self.popped = 0
        self._dialogs = _Dialogs()

    def show_dialog(self, dialog):
        dialog.open = True
        self.shown.append(dialog)
        self._dialogs.controls.append(dialog)

    def pop_dialog(self):
        self.popped += 1
        for dialog in reversed(self._dialogs.controls):
            if getattr(dialog, "open", False):
                dialog.open = False
                return dialog
        return None


class _RecordingShell:
    """Stands in for the shell-owned ControllerMethods instance."""

    def __init__(self):
        self.calls: list[str] = []

    def close_dialog(self):
        self.calls.append("close_dialog")

    def back(self):
        self.calls.append("back")


def _controller(state, ui_state):
    controller = app_main.AppController(_FakePage())
    controller.shell = _RecordingShell()
    controller.ui_state = ui_state
    # Bind the module singleton the handler reads to the test instance.
    app_main.state = state
    return controller


def _back(state, ui_state) -> list[str]:
    controller = _controller(state, ui_state)
    controller._handle_global_back()
    calls = controller.shell.calls
    app_main.state = singleton_state  # restore for other tests
    return calls


def test_dialog_open_closes_dialog():
    state = AppState()
    state.player_open = False
    calls = _back(state, {"dialog_open": True, "view": "anime"})
    assert calls == ["close_dialog"]


def test_player_open_swallows_back():
    """The player's FocusScope owns Back so the position gets saved first."""
    state = AppState()
    state.player_open = True
    calls = _back(state, {"dialog_open": False, "view": "tabs"})
    assert calls == []


def test_detail_view_goes_back():
    state = AppState()
    state.player_open = False
    calls = _back(state, {"dialog_open": False, "view": "anime"})
    assert calls == ["back"]


def test_root_leaves_back_to_the_os():
    state = AppState()
    state.player_open = False
    calls = _back(state, {"dialog_open": False, "view": "tabs"})
    assert calls == []


def test_dialog_beats_player():
    """A dialog over the player still closes just the dialog."""
    state = AppState()
    state.player_open = True
    calls = _back(state, {"dialog_open": True, "view": "player"})
    assert calls == ["close_dialog"]


def test_ad_hoc_dialog_closes_without_navigating():
    """The update/KTV install prompts show directly (not through the shell
    portal), so Back must pop them without leaving the current view."""
    from core.dialogs import show_app_dialog

    controller = _controller(AppState(), {"dialog_open": False, "view": "anime"})
    show_app_dialog(controller.page, ft.AlertDialog(title=ft.Text("Update")))
    controller._handle_global_back()
    assert controller.page.popped == 1
    assert controller.shell.calls == []  # stayed on the detail view
    app_main.state = singleton_state


def test_close_app_dialog_does_not_pop_what_sits_above_it():
    """A SnackBar above the registered dialog must not be dismissed by the
    dialog's Back handler (pop_dialog closes the topmost open dialog)."""
    from core.dialogs import close_app_dialog, show_app_dialog

    page = _FakePage()
    dialog = ft.AlertDialog(title=ft.Text("Update"))
    show_app_dialog(page, dialog)
    snack = ft.SnackBar(ft.Text("update ready"))
    page.show_dialog(snack)  # sits above the dialog

    assert close_app_dialog(page) is True
    # the snack stays open; the dialog itself was closed directly
    assert snack.open is True
    assert dialog.open is False
