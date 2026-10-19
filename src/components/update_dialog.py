"""Update dialog + version-pill state.

`UpdateService` has been checking on every boot since Phase 5, but
nothing ever showed it: `state.update_available` had zero readers. This
module restores the original dialog (mandatory/optional branches) and
exposes `show_update_dialog` for the Home version pill and the Settings
row to call.
"""

import asyncio
import contextlib
import logging

import flet as ft

from core.dialogs import close_app_dialog, show_app_dialog
from core.shared_services import get_shared_services
from core.theme import AppColors

logger = logging.getLogger(__name__)


def _show_up_to_date(page: ft.Page) -> None:
    """'You're up to date' — the version pill's destination.

    The house pattern (KTV components/version_dialog.py, Sherlock
    components/update_dialog.py, DDGS components/update_dialog.py — all
    three build this dialog the same way): a "You're up to date" title
    with the verified icon, the current version, the bundled changelog
    as MARKDOWN in a SCROLLABLE column, and a live re-check.

    Two things the house gets right that this copy did not (2026-10-19
    audit): the notes were a plain ``ft.Text`` in a FIXED 340x220 box, so
    the 1128-character changelog painted ~160px over the buttons; and
    the dismissal popped the topmost dialog unconditionally, which
    dismissed a SnackBar standing above this one and orphaned the
    dialog itself."""
    from core.changelog import notes_for
    from core.constants import APP_VERSION

    def _dismiss():
        # The app's own registry: it pops only if THIS dialog is the
        # topmost open one, so a snackbar above it is not eaten.
        close_app_dialog(page)

    async def _recheck(e=None):
        _dismiss()
        from core.state import state as app_state
        from services.update_service import UpdateService

        try:
            data = await UpdateService().check_for_update()
        except Exception:
            data = None
        # The header's pill morphs on these two fields; a re-check that
        # does not write them leaves the pill saying "up to date" even
        # when a newer build is waiting (the house writes both).
        app_state.update_available = bool(data)
        app_state.update_data = data or {}
        if data:
            show_update_dialog(page, data)
        else:
            show_update_dialog(page, None)

    dlg = ft.AlertDialog(
        modal=False,
        title=ft.Row(
            [
                ft.Icon(ft.Icons.VERIFIED_ROUNDED, color=AppColors.PRIMARY, size=24),
                ft.Text(
                    "You're up to date",
                    weight=ft.FontWeight.BOLD,
                ),
            ],
            spacing=8,
        ),
        content=ft.Column(
            [
                ft.Text(f"✓ Latest version · v{APP_VERSION}", size=13),
                ft.Container(height=4),
                ft.Text("What's New:", size=13, weight=ft.FontWeight.W_600),
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Markdown(
                                notes_for(APP_VERSION),
                                selectable=True,
                                size=12,
                            )
                        ],
                        scroll=ft.ScrollMode.AUTO,
                        # A bounded, SCROLLABLE box: the notes are a
                        # variable-length list, and a fixed height with
                        # no scroll cut the tail off the dialog.
                        height=220,
                    ),
                    width=340,
                ),
            ],
            tight=True,
            spacing=0,
        ),
        actions=[
            ft.OutlinedButton(
                content="Check for Updates",
                icon=ft.Icons.SYNC_ROUNDED,
                on_click=lambda e: page.run_task(_recheck, e),
            ),
            ft.TextButton(content="Close", on_click=lambda e: _dismiss()),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
        # NO on_dismiss handler here: flet 1.0.4 wraps on_dismiss and
        # removes the dialog from the stack BEFORE calling it, so a
        # handler that pops again closes whatever else is on top (the
        # re-check path appended the new dialog while this one was still
        # closing, and the round-trip popped the NEW one).
    )
    show_app_dialog(page, dlg)


def show_update_dialog(page: ft.Page, update_data: dict | None = None):
    """'New Version Available!' — mandatory updates block dismissal.

    With no data (or ``update_data=None``) it opens the UP-TO-DATE mode:
    the current version plus the bundled changelog. That is what the
    header's version pill opens (KTV/Sherlock house pattern — the pill is
    always live, and a tap works offline because the changelog is
    bundled)."""
    if not update_data:
        _show_up_to_date(page)
        return
    mandatory = bool(update_data.get("mandatory"))
    shared = get_shared_services(page)
    # One guard for every dismissal path (the Later button, the global
    # Back, a framework dismiss): the dialog used to be escapable through
    # Back because only the button scheduled the re-show.
    reshowing = False

    def _dismiss_dialog():
        # Clear the Back-handler registration whether the pop lands or not.
        page._app_dialog = None
        with contextlib.suppress(Exception):
            page.pop_dialog()

    def _schedule_reshow():
        nonlocal reshowing
        if not mandatory or reshowing:
            return
        reshowing = True
        page.run_task(_reshow)

    async def _reshow():
        nonlocal reshowing
        await asyncio.sleep(0.35)
        reshowing = False
        with contextlib.suppress(Exception):
            show_update_dialog(page, update_data)

    async def open_download(e):
        apk_url = update_data.get("apk_url") or ""
        if not apk_url:
            # A missing/unsafe URL used to KeyError here and leave the
            # dialog half-torn-down.
            logger.info("update dialog: no apk_url, nothing to launch")
            page.update()
            return
        # Dismiss only once the launch actually happens: a failed launch
        # must not silently bypass a mandatory update.
        launched = True
        try:
            await shared.launch_url(apk_url)
        except Exception as ex:
            launched = False
            logger.info("update launch failed: %s", ex)
        if launched:
            _dismiss_dialog()
        else:
            _schedule_reshow()
        page.update()

    def dismiss(e):
        _dismiss_dialog()
        if mandatory:
            _schedule_reshow()
        else:
            page.update()

    actions = [
        ft.TextButton(content="Later", on_click=dismiss),
        ft.FilledButton(
            content="Update Now",
            on_click=lambda e: page.run_task(open_download, e),
            style=ft.ButtonStyle(bgcolor="#F43F5E", color=ft.Colors.WHITE),
        ),
    ]
    if mandatory:
        actions = actions[1:]

    dlg = ft.AlertDialog(
        modal=mandatory,
        title=ft.Text("New Version Available!", weight=ft.FontWeight.BOLD),
        content=ft.Column(
            [
                ft.Text(
                    f"Version {update_data.get('version', '?')} is ready for installation.",
                    size=14,
                ),
                ft.Container(height=8),
                ft.Text("Highlights:", weight=ft.FontWeight.W_600, size=13),
                ft.Text(
                    update_data.get("release_notes", ""),
                    size=12,
                    color="#9CA3AF",
                ),
            ],
            tight=True,
        ),
        actions=actions,
        actions_alignment=ft.MainAxisAlignment.END,
        # Back / any framework dismissal re-shows a mandatory update.
        on_dismiss=lambda e: _schedule_reshow(),
    )
    show_app_dialog(page, dlg)
