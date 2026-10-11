"""External player fallback: KTV Player via deep link.

Restored from the original build, with the two details the rewrite had
dropped: the link carries the **resolved m3u8** (base64) plus a human
title ("Anime - Episode 3 - (1080p)") instead of the play-page URL, and a
failed launch offers the KTV install dialog rather than failing silently.

The resolving progress dialog is also restored: kwik resolution can take
seconds, and a bare pause reads as a frozen app.
"""

import asyncio
import base64
import logging
import urllib.parse

import flet as ft

from core.config import (
    KTV_DEEP_LINK_SCHEME,
    KTV_PLAY_STORE_URL,
    KTV_UPTODOWN_URL,
)
from core.dialogs import show_app_dialog
from core.shared_services import get_shared_services

logger = logging.getLogger(__name__)


def _button_style():
    return ft.ButtonStyle(
        bgcolor={
            ft.ControlState.FOCUSED: "#F43F5E",
            ft.ControlState.DEFAULT: "#111827",
        },
        color={
            ft.ControlState.FOCUSED: ft.Colors.WHITE,
            ft.ControlState.DEFAULT: "#F9FAFB",
        },
    )


def show_ktv_install_dialog(page: ft.Page):
    """Play Store / Uptodown / Not now — shown when the deep link fails."""
    shared = get_shared_services(page)

    def _dismiss_dialog():
        # Clear the Back-handler registration whether the pop lands or not.
        setattr(page, "_app_dialog", None)
        try:
            page.pop_dialog()
        except Exception:
            pass

    async def open_store(e):
        _dismiss_dialog()
        await shared.launch_url(KTV_PLAY_STORE_URL)
        page.update()

    async def open_uptodown(e):
        _dismiss_dialog()
        await shared.launch_url(KTV_UPTODOWN_URL)
        page.update()

    def dismiss(e):
        _dismiss_dialog()
        page.update()

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text("Install Player", weight=ft.FontWeight.BOLD),
        content=ft.Column(
            [
                ft.Text(
                    "KTV Player is required to play this stream in the external "
                    "player. Install it, or use the in-app player.",
                    size=14,
                ),
            ],
            tight=True,
        ),
        actions=[
            ft.TextButton(content="Not Now", on_click=dismiss),
            ft.OutlinedButton(
                content="Get it on Play Store",
                on_click=lambda e: page.run_task(open_store, e),
                style=_button_style(),
            ),
            ft.OutlinedButton(
                content="Download Uptodown",
                on_click=lambda e: page.run_task(open_uptodown, e),
                style=_button_style(),
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    show_app_dialog(page, dlg)


def build_deep_link(m3u8_url: str, title: str) -> str:
    """ktv://play?url=<base64 m3u8>&title=<url-encoded title>."""
    encoded_url = base64.urlsafe_b64encode(m3u8_url.encode()).decode().rstrip("=")
    encoded_title = urllib.parse.quote(title)
    return f"{KTV_DEEP_LINK_SCHEME}{encoded_url}&title={encoded_title}"


def episode_title(anime_title: str, episode_num=None, resolution=None) -> str:
    parts = [anime_title]
    if episode_num:
        parts.append(f"Episode {episode_num}")
    if resolution:
        parts.append(f"({resolution}p)")
    return " - ".join(parts)


async def launch_external(
    page: ft.Page,
    m3u8_url: str,
    title: str,
) -> bool:
    """Hand the resolved stream to KTV Player. Returns True on success.

    A TimeoutError counts as success — KTV comes to the foreground and
    never reports back, so the launcher call simply never returns.
    """
    deep_link = build_deep_link(m3u8_url, title)
    logger.info("launching external player: %s", title)
    shared = get_shared_services(page)
    if await shared.launch_url(deep_link):
        return True
    logger.warning("external player launch failed — offering install dialog")
    show_ktv_install_dialog(page)
    return False
