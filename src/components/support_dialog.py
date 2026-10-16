"""Support & feedback dialog — the original's third hero slide.

The 1.0.9 build opened a ``mailto:`` to a personal Gmail address. This app
deliberately carries no developer identity (see the repo's README), so the
support action routes to the project's public GitHub issues page instead:
same "reach the developer" affordance, no personal contact details shipped
in the binary.
"""

import contextlib
import logging

import flet as ft

from core.config import SUPPORT_URL
from core.dialogs import show_app_dialog
from core.shared_services import get_shared_services

logger = logging.getLogger(__name__)


def show_support_dialog(page: ft.Page):
    """'Contact Support & Feedback' — Close / Open."""
    shared = get_shared_services(page)

    def _dismiss():
        page._app_dialog = None
        with contextlib.suppress(Exception):
            page.pop_dialog()

    async def _open(e):
        _dismiss()
        if not await shared.launch_url(SUPPORT_URL):
            logger.warning("support link failed to open")
        page.update()

    def dismiss(e):
        _dismiss()
        page.update()

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text("Contact Support & Feedback", weight=ft.FontWeight.BOLD),
        content=ft.Text(
            "We would love to hear your suggestions, feature requests, or bug "
            "reports. We value your feedback.",
            size=13,
        ),
        actions=[
            ft.TextButton(content="Close", on_click=dismiss),
            ft.FilledButton(
                content="Open",
                icon=ft.Icons.OPEN_IN_NEW_ROUNDED,
                style=ft.ButtonStyle(
                    bgcolor="#F43F5E",
                    color=ft.Colors.WHITE,
                    shape=ft.RoundedRectangleBorder(radius=10),
                ),
                on_click=lambda e: page.run_task(_open, e),
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    show_app_dialog(page, dlg)
