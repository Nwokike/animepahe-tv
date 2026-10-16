"""Notifications adapter — flet-notifications behind a safe seam.

The package RAISES off-platform (its documented behavior) and is not
installed in every environment, so every call site goes through this
module: it detects the platform and the import once, and degrades to a
no-op instead of an exception. Nothing in the app may import
flet_notifications directly.

Every call below is written against the INSTALLED flet-notifications
0.1.4 surface (verified in .venv, and its README):
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
- the package supports Web (Chrome/Edge, gesture-gated permissions), so
  there is NO platform gate here. What there is instead: plain
  ``flet run`` ships no Dart half, so the service is unknown in dev and
  every invoke times out. The FIRST failure is remembered for the session
  and every later call is a cheap no-op — one slow probe at most, never
  a stall.
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

import asyncio
import contextlib
import logging

logger = logging.getLogger("animepahe.notify")

CHANNEL_NEW_EPISODES = "new_episodes"
_PAYLOAD_SCHEME = "animepahe://anime/"

_available: bool | None = None
_service: object | None = None
# True once a call has proven the service can't answer (dev-mode flet run
# has no Dart half). Remembered for the session.
_unavailable = False
_tap_handler = None


def _detect() -> bool:
    """Is the extension importable AND on a platform it supports?

    The package raises off-platform, so the import and a platform probe
    both have to pass before anything is called. Web is included in "not
    supported": there is no native listener there, so a call would wait
    its full invoke timeout (10s) and fail — which is why the permission
    ask is skipped rather than attempted."""
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


def _ready() -> bool:
    """Importable, and not already known-broken this session. Cheap: a
    cached import plus a bool read."""
    return _detect() and not _unavailable


def _permission_guard() -> asyncio.Lock:
    """A lock per RUNNING LOOP (attached to the loop, not a module global):
    a module-level Lock binds to the first loop it sees and raises on any
    later one — which is also every pytest test's fresh loop."""
    loop = asyncio.get_running_loop()
    lock = getattr(loop, "_animepahe_permission_lock", None)
    if lock is None:
        lock = asyncio.Lock()
        loop._animepahe_permission_lock = lock  # loop-scoped state
    return lock


async def request_permissions() -> bool:
    """Ask the OS for notification permission. False (quietly) when the
    extension is unavailable — never raises.

    Serialized: boot fires this and the channel create together, and
    without a shared gate the second caller paid its OWN 10s timeout in
    dev right after the first failed (observed live). A waiter re-checks
    readiness after the first probe settles and returns without dialing.
    """
    if not _ready():
        return False
    global _unavailable
    async with _permission_guard():
        if not _ready():
            return False
        try:
            return bool(await _service.request_permissions())
        except Exception as ex:
            # Plain `flet run` ships no Dart half: the service is unknown, and
            # every invoke waits its full timeout. Remember it once — this is
            # the one slow probe the session pays.
            _unavailable = True
            logger.info("notifications unavailable this run (%s)", ex)
            return False


def on_tap(handler) -> None:
    """Install the deep-link handler. The service calls it with the
    payload string a show() passed; the app routes that to the anime."""
    global _tap_handler
    _tap_handler = handler
    if not _ready():
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
        # Push the change: a handler assigned AFTER registration is not
        # sent to Dart until the control updates, so the taps silently
        # never arrived. Guarded — an unmounted service raises here.
        with contextlib.suppress(Exception):
            _service.update()
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

    return zlib.crc32(anime_session.encode()) % 1_000_000_000


def stable_filename(anime_session: str, suffix: str = ".img") -> str:
    """A stable, filesystem-safe FILE name for a per-anime artifact (the
    cached poster art). Session strings contain ':', '|', '/', '*' —
    all illegal or awkward in paths on some platform — so the name is the
    session's crc32 plus the suffix. Stable across runs, so a re-cache
    overwrites the same file instead of accumulating.

    This helper used to be referenced from main.py but never defined —
    the first follow-with-poster notification raised NameError."""
    return f"notify-{stable_id(anime_session):010d}{suffix}"


def download_id(episode_session: str) -> int:
    """A stable per-DOWNLOAD notification id. Its own band, so a
    download's progress row can never collide with a series' alert."""
    import zlib

    return 1_000_000_000 + (zlib.crc32(episode_session.encode()) % 1_000_000_000)


async def ensure_channel() -> bool:
    """The new_episodes channel at HIGH, created once. False (quietly)
    when the extension is unavailable.

    Settles the permission probe FIRST: boot fires both paths together,
    and a create running concurrently with the permissions timeout paid a
    second 10s invoke in dev ("channel create failed" right after
    "notifications unavailable", observed live)."""
    if not await request_permissions():
        return False
    if not _ready():
        return False
    global _unavailable
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
        _unavailable = True
        logger.info("channel create failed: %s", ex)
        return False


async def show_new_episode(
    *,
    anime_session: str,
    title: str,
    episode: int,
    poster_path: str | None = None,
    download_complete: bool = False,
    episode_session: str = "",
) -> bool:
    """Show one new-episode notification. No-op off-platform.

    `download_complete` re-shapes the same row for a finished download
    (id from the download's own band, body words 'download'), so a
    download never replaces a series' alert row."""
    if not _ready():
        return False
    global _unavailable
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
            id=download_id(episode_session) if download_complete else stable_id(anime_session),
            title=f"{title} — Episode {episode}",
            body="Download complete — tap to play" if download_complete else "Tap to watch",
            payload=payload_for(anime_session),
            style=style,
            channel_id=CHANNEL_NEW_EPISODES,
        )
        return True
    except Exception as ex:
        _unavailable = True
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
    if not _ready():
        return False
    global _unavailable
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
        _unavailable = True
        logger.info("progress show failed: %s", ex)
        return False


__all__ = [
    "CHANNEL_NEW_EPISODES",
    "anime_session_from",
    "download_id",
    "ensure_channel",
    "handle_payload",
    "on_tap",
    "payload_for",
    "request_permissions",
    "show_new_episode",
    "show_progress",
    "stable_filename",
    "stable_id",
]
