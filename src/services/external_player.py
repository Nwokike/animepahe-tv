"""External player fallback: KTV Player via deep link.

Restored from the original build, with the two details the rewrite had
dropped: the link carries the **resolved m3u8** (base64) plus a human
title ("Anime - Episode 3 - (1080p)") instead of the play-page URL, and a
failed launch offers the KTV install dialog rather than failing silently.

The resolving progress dialog is also restored: kwik resolution can take
seconds, and a bare pause reads as a frozen app.
"""

import base64
import json
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
        page._app_dialog = None
        try:
            page.pop_dialog()

        except Exception:
            logger.debug("suppressed")

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


def _b64url(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def build_deep_link(
    m3u8_url: str,
    title: str,
    headers: dict | None = None,
    referer: str | None = None,
) -> str:
    """ktv://play?url=<base64 m3u8>&title=<url-encoded title>
    [&referer=<base64>][&headers=<base64 JSON>].

    The source's own headers travel WITH the stream. Every backend except
    Animepahe answers a bare request with 403 — anikato's MegaPlay CDN
    requires Referer: megaplay.buzz, animeout's file host is Cloudflare-
    walled and needs the clearance Cookie, kayoanime's Drive requires its
    own Referer — so a link carrying only the URL could only ever play
    Animepahe (KTV Player's built-in CDN_HEADER_OVERRIDES happen to add the
    kwik pair for owocdn.top). KTV Player has parsed `referer`/`headers`
    from this scheme since v2.0.2; the handoff now actually sends them.
    """
    if referer is None and headers:
        # KTV Player reads the Referer from the header map too, but carrying
        # it explicitly keeps the proxy URL and the media request in sync.
        referer = next(
            (v for k, v in headers.items() if k.lower() == "referer"), None
        )
    encoded_url = _b64url(m3u8_url)
    encoded_title = urllib.parse.quote(title)
    link = f"{KTV_DEEP_LINK_SCHEME}{encoded_url}&title={encoded_title}"
    if referer:
        link += f"&referer={_b64url(referer)}"
    if headers:
        payload = json.dumps(headers, separators=(",", ":"), sort_keys=True)
        link += f"&headers={_b64url(payload)}"
    return link


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
    headers: dict | None = None,
    referer: str | None = None,
) -> bool:
    """Hand the resolved stream to KTV Player. Returns True on success.

    `headers`/`referer` are the resolved source's own request headers (see
    `build_deep_link`) — without them the handoff only works for sources
    whose CDN needs nothing.

    A TimeoutError counts as success — KTV comes to the foreground and
    never reports back, so the launcher call simply never returns.
    """
    deep_link = build_deep_link(m3u8_url, title, headers=headers, referer=referer)
    logger.info("launching external player: %s", title)
    shared = get_shared_services(page)
    # Ask the OS FIRST: a custom scheme with no handler does not raise on
    # Android — the void-returning launch_url "succeeds" and the install
    # dialog never showed. The manifest declares the ktv:// <queries> (CI
    # patch), so a False here is RELIABLE even on Android 11+.
    try:
        can_handle = bool(await shared.launcher.can_launch_url(deep_link))
    except Exception as ex:
        # can_launch_url itself is best-effort: fall through and try.
        logger.info("can_launch_url failed: %s", ex)
        can_handle = None

    if can_handle is False:
        # A definitive "no handler": don't fire a launch nothing will
        # receive — offer the install (owner, 2026-11-02).
        logger.warning("no app handles %s — offering install dialog", deep_link)
        show_ktv_install_dialog(page)
        return False

    # launch_url is a VOID invoke on some flet lines and a bool on others —
    # only a definitive False counts as failure; None/True means "fired, no
    # report" (KTV comes to the foreground and never reports back). The
    # shared helper also wraps the call in a 1 s timeout whose expiry counts
    # as success (v1.0.9 rule).
    try:
        result = await shared.launch_url(deep_link)
        launched = result is not False
    except Exception as ex:
        logger.info("launch_url failed: %s", ex)
        launched = False

    if launched:
        return True

    logger.warning("external player launch failed — offering install dialog")
    show_ktv_install_dialog(page)
    return False
