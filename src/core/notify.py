"""Snackbar helper — the working Flet 1.0.4 way to surface messages.

``page.show_dialog(...)`` is the supported path (verified against the installed
flet 1.0.4: ``SnackBar`` is a ``DialogControl``; there is no ``page.open``).

Note on the guard, because it is easy to get wrong: ``show_dialog`` raises
``RuntimeError("Dialog is already opened")`` when the dialog is already in the
page's stack, and flet controls are dataclasses — so the comparison is by value,
not identity. In practice a *fresh* snack never trips it (the one already on
the stack carries ``open=True`` from its own show, so the values differ), which
leaves exactly one reachable case: the same snack instance shown twice while
it is still open. The right move there is to skip — *not* to
``pop_dialog()`` first. ``pop_dialog`` closes the topmost open dialog whatever
it is, so popping when an ``AlertDialog`` sits above the lingering snack
dismisses the user's dialog and still fails to deliver the snack.
"""

import logging

import flet as ft

logger = logging.getLogger(__name__)


# The in-player fullscreen toast (KTV's pattern): native fullscreen
# swallows the snackbar, so a player that is open registers its chip here
# and every show_snack dispatches to BOTH.
_toast: object | None = None


def register_fullscreen_toast(handler) -> None:
    """The player calls this on mount with its chip's show(text)."""
    global _toast
    _toast = handler


def unregister_fullscreen_toast(handler=None) -> None:
    """Clear the registered toast handler. When handler is given, clears
    only if it matches the registered one to prevent stale teardown races."""
    global _toast
    if handler is None or _toast == handler:
        _toast = None


def show_snack(
    page: ft.Page,
    message: str,
    bgcolor: str | None = None,
    duration: int = 4000,
    action_label: str | None = None,
    on_action=None,
) -> None:
    """Best-effort snackbar: logs failures, never raises."""
    # Always dispatch to in-player toast if registered (dual dispatch)
    if _toast is not None:
        try:
            _toast(message)

        except Exception:
            logger.debug("suppressed")
    # A SnackBar appended while a REAL dialog (AlertDialog) is open
    # triggers `_dialogs.update()` — and flet's documented snapshot desync
    # (use_dialog.py:118-127) REPLACEs that dialog on Dart, which then
    # "refuses to close": a modal=True selector blocks every input and the
    # app looks hung (owner, 2026-11-05). Never stack a snack on an open
    # dialog — the message is dropped (the dialog is modal, so the user
    # is busy with it anyway; queued snacks after a close would arrive
    # stale).
    try:
        open_dialog = next(
            (
                d
                for d in reversed(page._dialogs.controls)
                if d.open and not isinstance(d, ft.SnackBar)
            ),
            None,
        )
    except Exception:
        open_dialog = None
    if open_dialog is not None:
        logger.debug("snack skipped: a modal dialog is open: %r", message)
        return
    try:
        action = None
        if action_label:
            action = ft.SnackBarAction(action_label, on_click=on_action)
        snack = ft.SnackBar(
            content=ft.Text(message, color=ft.Colors.WHITE),
            bgcolor=bgcolor or ft.Colors.BLACK,
            # DurationValue accepts int ms, but be explicit — version-proof.
            duration=ft.Duration(milliseconds=duration),
            action=action,
        )
        page.show_dialog(snack)
    except RuntimeError:
        # Same snack instance still on the stack: the message is already on
        # screen. Popping would close whatever real dialog is on top and
        # still not deliver this one.
        logger.debug("snack already on the dialog stack, skipping: %r", message)
    except Exception as ex:
        logger.warning("show_snack failed: %s", ex)
