"""Native notifications — ONE service over flet-notifications 1.1.0.

Channels: ``new_episodes`` (HIGH), ``downloads`` (MIN, in-place progress),
``app_updates`` (DEFAULT). Tap payloads route to the app via the ``on_tap``
handler wired in main.py. Every call degrades to a log line when the
package is absent or the platform refuses — a notification must never
break the feature that spawned it.

flet-notifications facts this module relies on (read from the installed
1.1.0.dev3 source, every file):
- ``Notifications`` is an ``ft.Service`` that registers itself; construct
  it with ``on_tap`` ONCE so taps that launch the app are delivered.
- ``show(id=...)`` with a REUSED id updates in place — combined with
  ``AndroidOptions(only_alert_once=True)`` it advances a progress bar
  without re-alerting.
- Android ids must fit a 32-bit signed int — ``_stable_id`` maps any key
  into that range deterministically.
- ``request_permissions`` prompts on Android 13+ (POST_NOTIFICATIONS);
  it is called once at setup.
- Background taps are queued by a native Dart handler and replayed on
  the next service init; Python never runs in the background isolate.
"""

import hashlib
import logging

from core.constants import APP_NAME

logger = logging.getLogger(__name__)

try:
    import flet_notifications as ftn

    _HAS_NOTIFICATIONS = True
except ImportError:
    ftn = None
    _HAS_NOTIFICATIONS = False

CHANNEL_EPISODES = "new_episodes"
CHANNEL_DOWNLOADS = "downloads"
CHANNEL_UPDATES = "app_updates"


def _stable_id(text: str) -> int:
    """Deterministic 32-bit signed notification id for a stable key."""
    return int(hashlib.sha256(text.encode()).hexdigest()[:8], 16) & 0x7FFFFFF0


def _on_mobile(page) -> bool:
    try:
        return page.platform in (
            page.platform.ANDROID,
            page.platform.ANDROID_TV,
            page.platform.IOS,
        )
    except Exception:
        return False


class NotifyService:
    """Owns the flet-notifications service and every notification the app
    posts. Construct once per page."""

    def __init__(self, page, on_tap=None):
        self.page = page
        self._on_tap = on_tap
        self._notifs = None
        if not _HAS_NOTIFICATIONS or page is None:
            return
        try:
            self._notifs = ftn.Notifications(on_tap=self._dispatch_tap)
        except Exception as ex:
            logger.warning("notifications service unavailable: %s", ex)

    @property
    def available(self) -> bool:
        return self._notifs is not None

    def _dispatch_tap(self, e):
        payload = getattr(e, "payload", None) or ""
        if self._on_tap is None:
            return
        try:
            self._on_tap(payload)
        except Exception as ex:
            logger.warning("notification tap handling failed: %s", ex)

    async def setup(self) -> None:
        """Channels + the one permission prompt. Android 8+ only for
        channels; other platforms skip them silently."""
        if self._notifs is None:
            return
        try:
            await self._notifs.create_channel(
                ftn.NotificationChannel(
                    id=CHANNEL_EPISODES,
                    name="New episodes",
                    description="New episodes of anime you follow",
                    importance=ftn.AndroidImportance.HIGH,
                )
            )
            await self._notifs.create_channel(
                ftn.NotificationChannel(
                    id=CHANNEL_DOWNLOADS,
                    name="Downloads",
                    description="Download progress and completion",
                    importance=ftn.AndroidImportance.MIN,
                )
            )
            await self._notifs.create_channel(
                ftn.NotificationChannel(
                    id=CHANNEL_UPDATES,
                    name="App updates",
                    importance=ftn.AndroidImportance.DEFAULT,
                )
            )
            await self._notifs.request_permissions()
        except Exception as ex:
            logger.warning("notification setup failed: %s", ex)

    async def new_episode(self, anime_session: str, title: str, episode: int) -> None:
        if self._notifs is None or not _on_mobile(self.page):
            return
        try:
            await self._notifs.show(
                id=_stable_id(f"follow:{anime_session}"),
                title=title or APP_NAME,
                body=f"Episode {episode} is out",
                payload=f"follow:{anime_session}",
                options=ftn.NotificationOptions(
                    android=ftn.AndroidOptions(channel=CHANNEL_EPISODES, only_alert_once=True)
                ),
            )
        except Exception as ex:
            logger.warning("new-episode notification failed: %s", ex)

    async def download_progress(
        self, episode_session: str, title: str, percent: float, bytes_done: int
    ) -> None:
        if self._notifs is None or not _on_mobile(self.page):
            return
        try:
            await self._notifs.show(
                id=_stable_id(f"download:{episode_session}"),
                title=title or APP_NAME,
                body=f"{percent:.0f}% · downloading",
                payload=f"download:{episode_session}",
                options=ftn.NotificationOptions(
                    android=ftn.AndroidOptions(
                        channel=CHANNEL_DOWNLOADS,
                        progress=ftn.AndroidProgress(value=max(0, min(int(percent), 100)), max=100),
                        only_alert_once=True,
                        ongoing=True,
                    )
                ),
            )
        except Exception as ex:
            logger.debug("download progress notification skipped: %s", ex)

    async def download_done(self, episode_session: str, title: str) -> None:
        if self._notifs is None or not _on_mobile(self.page):
            return
        try:
            # The in-place progress bar ends its job: post the completion
            # as a fresh, auto-cancelling alert on the same channel.
            await self._notifs.cancel(_stable_id(f"download:{episode_session}"))
            await self._notifs.show(
                id=_stable_id(f"download-done:{episode_session}"),
                title=title or APP_NAME,
                body="Download complete",
                payload=f"download:{episode_session}",
                options=ftn.NotificationOptions(
                    android=ftn.AndroidOptions(channel=CHANNEL_DOWNLOADS, auto_cancel=True)
                ),
            )
        except Exception as ex:
            logger.warning("download-complete notification failed: %s", ex)

    async def download_failed(self, episode_session: str, title: str) -> None:
        if self._notifs is None or not _on_mobile(self.page):
            return
        try:
            await self._notifs.cancel(_stable_id(f"download:{episode_session}"))
        except Exception as ex:
            logger.debug("download progress cancel failed: %s", ex)

    async def update_available(self, version: str) -> None:
        if self._notifs is None or not _on_mobile(self.page):
            return
        try:
            await self._notifs.show(
                id=_stable_id("app-update"),
                title=APP_NAME,
                body=f"Version {version} is available",
                payload="update:open",
                options=ftn.NotificationOptions(
                    android=ftn.AndroidOptions(channel=CHANNEL_UPDATES)
                ),
            )
        except Exception as ex:
            logger.warning("update notification failed: %s", ex)
