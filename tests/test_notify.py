"""show_snack guard behavior.

The fake page mirrors flet 1.0.4's Page.show_dialog/pop_dialog as verified in
the installed source (flet/controls/base_page.py):
- show_dialog raises RuntimeError when the dialog is already in the stack
- pop_dialog closes and returns the topmost open dialog, whatever it is

``strict=True`` models the platform rejecting a snack that compares equal to
one already on the stack — flet controls are dataclasses, so that comparison
is by value, not identity. In real 1.0.4 a fresh snack escapes it because the
lingering one carries open=True; the strict mode checks the case anyway,
because that is the branch where a naive pop_dialog() fallback does damage.
"""

import flet as ft

from core.notify import show_snack


def _snack_key(dialog):
    if not isinstance(dialog, ft.SnackBar):
        return None
    return (dialog.content, dialog.bgcolor, dialog.duration, dialog.action)


class FakePage:
    """Minimal stand-in with 1.0.4 dialog-stack semantics."""

    def __init__(self, strict: bool = False):
        self.dialogs: list = []
        self.strict = strict

    def show_dialog(self, dialog):
        if self.strict:
            clash = any(
                (key := _snack_key(d)) is not None and key == _snack_key(dialog)
                for d in self.dialogs
            )
        else:
            clash = dialog in self.dialogs
        if clash:
            raise RuntimeError("Dialog is already opened")
        dialog.open = True
        self.dialogs.append(dialog)

    def pop_dialog(self):
        for dialog in reversed(self.dialogs):
            if getattr(dialog, "open", False):
                dialog.open = False
                return dialog
        return None


def test_show_snack_shows_snack():
    page = FakePage()
    show_snack(page, "Couldn't load.")
    assert len(page.dialogs) == 1
    snack = page.dialogs[0]
    assert isinstance(snack, ft.SnackBar)
    assert snack.open is True
    assert snack.content.value == "Couldn't load."
    assert snack.duration.milliseconds == 4000


def test_show_snack_custom_bgcolor_and_duration():
    page = FakePage()
    show_snack(page, "oops", bgcolor="#EF4444", duration=8000)
    snack = page.dialogs[0]
    assert snack.bgcolor == "#EF4444"
    assert snack.duration.milliseconds == 8000


def test_show_snack_action_label():
    page = FakePage()
    show_snack(page, "retry?", action_label="Retry")
    snack = page.dialogs[0]
    assert isinstance(snack.action, ft.SnackBarAction)
    assert snack.action.label == "Retry"


def test_snack_equality_is_by_value():
    """Documents why a guard is needed at all: flet controls are dataclasses,
    so two snacks built the same way compare == even as distinct objects."""
    a = ft.SnackBar(ft.Text("same"))
    b = ft.SnackBar(ft.Text("same"))
    assert a == b
    assert a is not b


def test_show_snack_swallows_dialog_already_open():
    """A rejected re-show must not raise, and must not pop anything."""
    page = FakePage(strict=True)
    show_snack(page, "Couldn't load.")
    first = page.dialogs[0]
    show_snack(page, "Couldn't load.")  # same values -> RuntimeError branch
    assert len(page.dialogs) == 1
    assert first.open is True


def test_show_snack_never_closes_a_real_dialog():
    """A snack on the stack must leave an open AlertDialog alone — including
    the RuntimeError branch, where the 1.0.1 port popped and closed it."""
    page = FakePage(strict=True)
    dialog = ft.AlertDialog(title=ft.Text("Update available"))
    page.show_dialog(dialog)
    show_snack(page, "Couldn't load.")
    assert dialog.open is True
    # Same snack values again: rejected, swallowed, dialog untouched.
    show_snack(page, "Couldn't load.")
    assert dialog.open is True
    assert len(page.dialogs) == 2


def test_show_snack_survives_a_broken_page():
    class BrokenPage:
        def show_dialog(self, dialog):
            raise ValueError("backend gone")

    show_snack(BrokenPage(), "Couldn't load.")  # must not raise
