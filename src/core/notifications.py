"""Notifications adapter — flet-notifications behind a safe seam.

The package RAISES off-platform (its documented behavior) and is not
installed in every environment, so every call site goes through this
module: it detects the platform and the import once, and degrades to a
no-op instead of an exception. Nothing in the app may import
flet_notifications directly.

Every call below is written against the INSTALLED flet-notifications
0.1.3 surface (verified in .venv):
- ``flet_notifications.LocalNotifications`` is an ``ft.Service`` — one
  instance, self-registered with the page, never added to controls
- ``await service.request_permissions() -> bool`` is the permission flow
- ``await service.create_notification_channel(NotificationChannel(...))``
  with ``flet_notifications.types.Importance``
- ``await service.show(id=, title=, body=, payload=, style=, channel_id=)``
  — there is NO ``details=`` kwarg; per-platform detail is ``options=``
- ``BigPictureStyle(image=AndroidIcon(file_path=...))`` — the image is a
  REQUIRED ``AndroidIcon`` with exactly one source set
- ``service.on_tap`` receives the event; ``e.payload`` is the string the
  show() call passed, which is how the deep link comes back
- re-showing the same id UPDATES the notification — that is how a live
  progress bar advances (``show_progress``/``max_progress``/``progress``)

Notification shape (the reference's recommendations):
- per-anime stable id — one tray row per series, updated not piled
- the `new_episodes` channel at HIGH importance, created once
- payload «animepahe://anime/{session}» — the tap deep-links to that
  anime's detail (the payload round-trips verbatim)
- BigPicture needs a LOCAL file, so the poster is written to the app's
  storage dir before the show
"""

from __future__ import annotations

import logging

logger = logging.getLogger("animepahe.notify")

CHANNEL_NEW_EPISODES = "new_episodes"
_PAYLOAD_SCHEME = "animepahe://anime/"

_available: bool | None = None
_service: object | None = None
_tap_handler = None


def _detect() -> bool:
    """Is the extension importable AND on a platform it supports?

    The package raises off-platform, so the import and a platform probe
    both have to pass before anything is called."""
    global _available, _service
    if _available is not None:
        return _available
    try:
        import flet_notifications as fn

        _service = fn.LocalNotifications()
        _available = True
    except Exception as ex:
        logger.info("flet-notifications unavailable: %s", ex)
        _available = False
        _service = None
    return _available


async def request_permissions() -> bool:
    """Ask the OS for notification permission. False (quietly) when the
    extension is unavailable — never raises."""
    if not _detect():
        return False
    try:
        return bool(await _service.request_permissions())
    except Exception as ex:
        logger.info("permission request failed: %s", ex)
        return False


def on_tap(handler) -> None:
    """Install the deep-link handler. The service calls it with the
    payload string a show() passed; the app routes that to the anime."""
    global _tap_handler
    _tap_handler = handler
    if not _detect():
        return

    def _dispatch(e):
        payload = getattr(e, "payload", None)
        # The adapter owns the scheme, so a foreign payload never reaches
        # the app — the handler only ever sees an anime session.
        if _tap_handler is None or not anime_session_from(payload):
            return
        try:
            _tap_handler(payload)
        except Exception as ex:
            logger.info("notification tap handling failed: %s", ex)

    try:
        _service.on_tap = _dispatch
    except Exception as ex:
        logger.info("on_tap install failed: %s", ex)


def handle_payload(payload: str | None) -> str | None:
    """A tap payload -> the anime session to open (None when it isn't
    ours). Kept separate from the routing so it is unit-testable."""
    return anime_session_from(payload)


def payload_for(anime_session: str) -> str:
    return f"{_PAYLOAD_SCHEME}{anime_session}"


def anime_session_from(payload: str | None) -> str | None:
    if not payload or not payload.startswith(_PAYLOAD_SCHEME):
        return None
    return payload[len(_PAYLOAD_SCHEME) :] or None


def stable_id(anime_session: str) -> int:
    """A stable per-anime notification id (one row per series)."""
    import zlib

    return zlib.crc32(anime_session.encode()) % 2_000_000_000


async def ensure_channel() -> bool:
    """The new_episodes channel at HIGH, created once. False (quietly)
    when the extension is unavailable."""
    if not _detect():
        return False
    try:
        from flet_notifications.channels import NotificationChannel
        from flet_notifications.types import Importance

        channel = NotificationChannel(
            id=CHANNEL_NEW_EPISODES,
            name="New episodes",
            description="Alerts when a show you follow gets a new episode",
            importance=Importance.HIGH,
        )
        await _service.create_notification_channel(channel)
        return True
    except Exception as ex:
        logger.info("channel create failed: %s", ex)
        return False


async def show_new_episode(
    *,
    anime_session: str,
    title: str,
    episode: int,
    poster_path: str | None = None,
) -> bool:
    """Show one new-episode notification. No-op off-platform."""
    if not _detect():
        return False
    try:
        from flet_notifications.styles import AndroidIcon, BigPictureStyle

        style = None
        if poster_path:
            # AndroidIcon requires exactly one source; the poster is
            # written to storage before this runs.
            style = BigPictureStyle(
                image=AndroidIcon(file_path=poster_path),
                content_title=f"{title} — Episode {episode}",
                summary_text="New episode on your followed show",
            )
        await _service.show(
            id=stable_id(anime_session),
            title=f"{title} — Episode {episode}",
            body="Tap to watch",
            payload=payload_for(anime_session),
            style=style,
            channel_id=CHANNEL_NEW_EPISODES,
        )
        return True
    except Exception as ex:
        logger.info("show failed: %s", ex)
        return False


async def show_progress(
    *,
    notification_id: int,
    title: str,
    body: str = "",
    payload: str = "",
    progress: int = 0,
    max_progress: int = 0,
    indeterminate: bool = False,
) -> bool:
    """One live-progress notification, advanced by re-showing the same
    id. The download path uses this; kept here so no other module
    imports the package."""
    if not _detect():
        return False
    try:
        await _service.show(
            id=notification_id,
            title=title,
            body=body,
            payload=payload,
            show_progress=True,
            progress=progress,
            max_progress=max_progress,
            indeterminate=indeterminate,
            channel_id=CHANNEL_NEW_EPISODES,
        )
        return True
    except Exception as ex:
        logger.info("progress show failed: %s", ex)
        return False


__all__ = [
    "ensure_channel",
    "show_new_episode",
    "show_progress",
    "request_permissions",
    "on_tap",
    "handle_payload",
    "payload_for",
    "anime_session_from",
    "stable_id",
    "CHANNEL_NEW_EPISODES",
]
