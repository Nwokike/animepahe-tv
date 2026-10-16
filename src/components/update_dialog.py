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

from core.dialogs import show_app_dialog
from core.shared_services import get_shared_services

logger = logging.getLogger(__name__)


def show_update_dialog(page: ft.Page, update_data: dict):
    """'New Version Available!' — mandatory updates block dismissal."""
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
