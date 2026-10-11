"""Update dialog + version-pill state.

`UpdateService` has been checking on every boot since Phase 5, but
nothing ever showed it: `state.update_available` had zero readers. This
module restores the original dialog (mandatory/optional branches) and
exposes `show_update_dialog` for the Home version pill and the Settings
row to call.
"""

import asyncio
import logging

import flet as ft

from core.dialogs import show_app_dialog
from core.shared_services import get_shared_services

logger = logging.getLogger(__name__)


def show_update_dialog(page: ft.Page, update_data: dict):
    """'New Version Available!' — mandatory updates block dismissal."""
    mandatory = bool(update_data.get("mandatory"))
    shared = get_shared_services(page)

    def _dismiss_dialog():
        # Clear the Back-handler registration whether the pop lands or not.
        setattr(page, "_app_dialog", None)
        try:
            page.pop_dialog()
        except Exception:
            pass

    async def open_download(e):
        _dismiss_dialog()
        await shared.launch_url(update_data["apk_url"])
        page.update()

    def dismiss(e):
        _dismiss_dialog()
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
    )
    show_app_dialog(page, dlg)
