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

from core.dialogs import close_app_dialog, show_app_dialog
from core.shared_services import get_shared_services
from core.theme import AppColors

logger = logging.getLogger(__name__)


def _show_up_to_date(page: ft.Page) -> None:
    """'You're up to date' — the version pill's destination.

    The house pattern, copied from Sherlock's components/update_dialog.py
    and DDGS's components/update_dialog.py (both build this dialog the
    same way): a "You're up to date" title with the verified icon, the
    current version, the bundled changelog as MARKDOWN, and a live
    re-check.

    Three things the house gets right that this copy did not (the
    2026-10-19 re-audit caught all three):
    - The notes are `ft.Markdown` with the GITHUB_WEB extension set and
      a tappable-link handler. `ft.Markdown` in flet 1.0.4 has NO
      `size` field — passing one raises TypeError and the dialog never
      opens, and the version pill is the most-tapped control in the
      header.
    - The notes FLOW: the outer Column scrolls and the notes are not
      boxed in a fixed-height window. The old fixed 340x220 box clipped
      ~60 % of the changelog and painted over the buttons.
    - A re-check that finds nothing shows a SNACKBAR, not the same
      dialog again (a button that re-opens itself looks like a no-op).
    """
    from core.changelog import notes_for
    from core.constants import APP_VERSION
    from core.notify import show_snack

    def _dismiss():
        # The app's own registry: it pops only if THIS dialog is the
        # topmost open one, so a snackbar above it is not eaten.
        close_app_dialog(page)

    def _launch(url: str):
        """Open a link in the changelog (the house's on_tap_link)."""

        async def _run():
            try:
                await get_shared_services(page).launch_url(url)
            except Exception as ex:
                logger.info("changelog link launch failed: %s", ex)

        page.run_task(_run)

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
            return
        show_snack(page, f"You're up to date on v{APP_VERSION}")

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
            controls=[
                ft.Text(f"\u2713 Latest version \u00b7 v{APP_VERSION}", size=13),
                ft.Text("What's New:", size=13, weight=ft.FontWeight.W_600),
                ft.Container(
                    content=ft.Markdown(
                        notes_for(APP_VERSION),
                        selectable=True,
                        extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                        on_tap_link=lambda e: _launch(e.data or ""),
                    ),
                    width=360,
                ),
            ],
            spacing=8,
            scroll=ft.ScrollMode.AUTO,
            tight=True,
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
        # re-check path appends the new dialog while the old one is still
        # closing).
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
        try:
            page.pop_dialog()

        except Exception:
            logger.debug("suppressed")

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
        try:
            show_update_dialog(page, update_data)

        except Exception:
            logger.debug("suppressed")

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
