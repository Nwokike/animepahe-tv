"""Shared page services — one Clipboard and one UrlLauncher, mounted once.

Every tap used to construct its own ``ft.UrlLauncher()`` / ``ft.Clipboard()``
and append it to ``page.services`` (settings copy, update prompt, support
dialog, external-player launch, promo hero). Constructing a service per tap
leaks an entry into the page's service list on every press and makes the
call sites all carry the same mount/teardown dance.

The services are attached to the page object itself, so any call site with
a ``page`` can reach them with :func:`get_shared_services` — mounting lazily
if the controller hasn't run yet.
"""

import logging

import flet as ft

logger = logging.getLogger(__name__)

_ATTR = "_shared_services"


class SharedServices:
    """Launcher + clipboard handles, with guarded async helpers."""

    def __init__(self, page: ft.Page):
        self.page = page
        self.launcher = ft.UrlLauncher()
        self.clipboard = ft.Clipboard()
        # In Flet 1.0.4, Service.__post_init__ auto-registers services
        # when context.page is available. Guarding against duplicate
        # entries ensures we never double-mount on page.services.
        for s in (self.launcher, self.clipboard):
            if s not in page.services:
                page.services.append(s)

    async def launch_url(self, url: str, timeout: float = 1.0) -> bool:
        import asyncio

        try:
            await asyncio.wait_for(
                self.launcher.launch_url(url, mode=ft.LaunchMode.EXTERNAL_APPLICATION),
                timeout=timeout,
            )
            return True
        except TimeoutError:
            # A hand-off to another app never returns on some platforms.
            return True
        except Exception as ex:
            logger.warning("launch_url(%s) failed: %s", url, ex)
            return False

    async def set_clipboard(self, text: str) -> bool:
        try:
            await self.clipboard.set(text)
            return True
        except Exception as ex:
            logger.warning("clipboard set failed: %s", ex)
            return False

    @property
    def haptics(self) -> ft.HapticFeedback:
        if not hasattr(self, "_haptics") or self._haptics is None:
            self._haptics = ft.HapticFeedback()
            if self._haptics not in self.page.services:
                self.page.services.append(self._haptics)
        return self._haptics

    @property
    def share(self) -> ft.Share:
        if not hasattr(self, "_share") or self._share is None:
            self._share = ft.Share()
            if self._share not in self.page.services:
                self.page.services.append(self._share)
        return self._share

    @property
    def file_picker(self) -> ft.FilePicker:
        """Boot-singleton FilePicker — the first picker in the app (the
        player's subtitle file). Mounting per tap leaked a service entry
        every press, the same bug this module exists to kill."""
        if not hasattr(self, "_file_picker") or self._file_picker is None:
            self._file_picker = ft.FilePicker()
            if self._file_picker not in self.page.services:
                self.page.services.append(self._file_picker)
        return self._file_picker


def mount_shared_services(page: ft.Page) -> SharedServices:
    """Attach (once) and return the page's shared services."""
    existing = getattr(page, _ATTR, None)
    if existing is not None:
        return existing
    services = SharedServices(page)
    setattr(page, _ATTR, services)
    return services


def get_shared_services(page: ft.Page) -> SharedServices:
    """Fetch, mounting lazily if init() didn't get there first."""
    if page is None:
        raise ValueError("page is required")
    return mount_shared_services(page)
