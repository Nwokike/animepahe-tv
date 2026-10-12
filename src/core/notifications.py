"""Notifications adapter — flet-notifications behind a safe seam.

The package RAISES off-platform (its documented behavior) and is not
installed in every environment yet, so every call site goes through
this module: it detects the platform and the import once, and degrades
to a no-op instead of an exception. Nothing in the app may import
flet_notifications directly.

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
        from flet_notifications.types import AndroidNotificationChannel, Importance

        channel = AndroidNotificationChannel(
            id=CHANNEL_NEW_EPISODES,
            name="New episodes",
            importance=Importance.HIGH,
            description="Alerts when a show you follow gets a new episode",
        )
        await _service.create_channel(channel)
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
        from flet_notifications.types import (
            AndroidNotificationDetails,
            BigPictureStyle,
            NotificationDetails,
        )

        android = AndroidNotificationDetails(
            channel_id=CHANNEL_NEW_EPISODES,
        )
        style = BigPictureStyle(
            image_file_path=poster_path or "",
            content_title=f"{title} — Episode {episode}",
            summary_text="New episode on your followed show",
        )
        details = NotificationDetails(android=android)
        await _service.show(
            id=stable_id(anime_session),
            title=f"{title} — Episode {episode}",
            body="Tap to watch",
            payload=payload_for(anime_session),
            details=details,
            style=style,
        )
        return True
    except TypeError:
        # Older/newer signatures: fall back to the minimal show.
        try:
            await _service.show(
                id=stable_id(anime_session),
                title=f"{title} — Episode {episode}",
                body="Tap to watch",
                payload=payload_for(anime_session),
            )
            return True
        except Exception as ex:
            logger.info("show failed: %s", ex)
            return False
    except Exception as ex:
        logger.info("show failed: %s", ex)
        return False


__all__ = [
    "ensure_channel",
    "show_new_episode",
    "payload_for",
    "anime_session_from",
    "stable_id",
    "CHANNEL_NEW_EPISODES",
]
