"""Ad-hoc dialog registry — so global Back can close any open dialog.

The original 1.0.9 app checked ``page.dialog_open`` in its Back handler;
flet 1.0.4 has no public dialog-stack accessor (``page._dialogs`` is
private). Dialogs shown through the shell's portal are tracked by the
shell itself; these two call sites (update prompt, KTV install prompt)
show theirs directly, so they register here and the FocusManager pops the
registration when Back is pressed.
"""

import logging

import flet as ft

logger = logging.getLogger(__name__)


def show_app_dialog(page: ft.Page, dialog) -> None:
    """Show a dialog and remember it for global Back."""
    setattr(page, "_app_dialog", dialog)
    page.show_dialog(dialog)


def close_app_dialog(page: ft.Page) -> bool:
    """Close the registered dialog if one is open. True if one was.

    Only pops when the registered dialog is still the topmost open one:
    pop_dialog() closes whatever sits on top, so an unconditional pop would
    dismiss a SnackBar above our dialog and orphan the dialog itself.
    """
    dialog = getattr(page, "_app_dialog", None)
    if dialog is None:
        return False
    setattr(page, "_app_dialog", None)
    try:
        top = next(
            (d for d in reversed(page._dialogs.controls) if d.open), None
        )
        if top is dialog:
            page.pop_dialog()
        else:
            dialog.open = False
            dialog.update()
    except Exception as ex:
        logger.debug("close_app_dialog: %s", ex)
    return True
