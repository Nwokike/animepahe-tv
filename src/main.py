"""animepahe-tv — entry point and application controller.

House architecture (KTV/Sherlock on flet 1.0.4): the controller owns the
services and exposes data actions; `AppShell` owns navigation state and
renders `@ft.component` screens through contexts. This module is the only
place services are constructed.
"""

import asyncio
import logging

import flet as ft

from app_shell import AppShell
from core.constants import APP_NAME
from core.tasks import spawn
from core.theme import AppColors, AppTheme
from services.animepahe import AnimePaheScraper
from services.cache import Cache
from services.kwik_resolver import KwikResolver
from services.update_service import UpdateService
from state.app_state import state
from state.controller_ctx import ControllerMethods, ControllerMethodsCtx

logger = logging.getLogger(__name__)


class AppController:
    """Owns services + data actions. Navigation lives in AppShell."""

    def __init__(self, page: ft.Page):
        self.page = page
        self.scraper: AnimePaheScraper | None = None
        self.kwik: KwikResolver | None = None
        self.cache: Cache | None = None
        self.update_service: UpdateService | None = None
        self._loading_locks: dict[str, asyncio.Lock] = {}

    async def init(self):
        self.page.title = APP_NAME
        self.page.padding = 0
        self.page.spacing = 0

        self.page.fonts = {"Outfit": "assets/outfit.css"}
        self.page.theme = AppTheme.get_light_theme()
        self.page.dark_theme = AppTheme.get_dark_theme()
        self.page.theme.font_family = "Outfit"
        self.page.dark_theme.font_family = "Outfit"
        self.page.theme_mode = ft.ThemeMode.SYSTEM

        self.cache = Cache()
        self.scraper = AnimePaheScraper()
        self.kwik = KwikResolver()
        self.update_service = UpdateService()

        await self.cache.start_sweep(interval=300)

        state.scraper = self.scraper
        state.cache = self.cache
        state.page = self.page

        spawn(self._check_for_updates_bg(), name="update-check")

    async def _check_for_updates_bg(self):
        await asyncio.sleep(2.0)
        update_data = await self.update_service.check_for_update()
        if update_data:
            state.update_available = True
            state.update_data = update_data

    def _show_error_snackbar(self):
        try:
            snack = ft.SnackBar(ft.Text("Network error"), bgcolor=AppColors.ERROR)
            self.page.show_dialog(snack)
        except Exception:
            pass

    def _get_lock(self, key: str) -> asyncio.Lock:
        if key not in self._loading_locks:
            self._loading_locks[key] = asyncio.Lock()
        return self._loading_locks[key]

    # ------------------------------------------------------------------
    # Data actions — called by screens through ControllerMethods
    # ------------------------------------------------------------------

    async def load_latest(self, page_num: int = 1):
        lock = self._get_lock(f"latest_{page_num}")
        if lock.locked():
            return

        async with lock:
            state.is_loading = True
            state.latest_page = page_num
            state.latest_version += 1

            try:
                results, has_more = await self.scraper.latest_releases(page_num)
                logger.info(
                    "load_latest page=%d got %d items, has_more=%s",
                    page_num,
                    len(results),
                    has_more,
                )
                state.latest_releases = results
                state.latest_has_more = has_more
                if page_num == 1 and results:
                    state.cf_blocked = False
            except Exception as ex:
                logger.error("load_latest page=%d failed: %s", page_num, ex)
                state.latest_releases = []
                state.latest_has_more = False
            finally:
                state.is_loading = False
                if page_num == 1 and not state.latest_releases:
                    state.cf_blocked = True
                state.latest_version += 1

    async def retry_cloudflare(self):
        """Clear the Cloudflare session + caches, then reload the home feed."""
        state.cf_blocked = False
        state.latest_version += 1
        try:
            await self.scraper.ddos.reset()
            self.scraper.clear_cache()
            await self.cache.clear()
        except Exception as ex:
            logger.error("retry_cloudflare failed: %s", ex)
        await self.load_latest(1)

    async def load_episodes(self, anime_session: str, page_num: int = 1):
        lock = self._get_lock(f"episodes_{anime_session}")
        if lock.locked():
            return

        async with lock:
            state.is_loading = True
            state.current_anime_session = anime_session
            state.episodes_page = page_num
            state.episodes_version += 1

            try:
                episodes, has_more = await self.scraper.episodes(anime_session, page_num)
                logger.info(
                    "load_episodes session=%s page=%d got %d",
                    anime_session,
                    page_num,
                    len(episodes),
                )
                state.episodes = episodes
                state.episodes_has_more = has_more
                state.cf_blocked = False
            except Exception as ex:
                logger.error("load_episodes session=%s failed: %s", anime_session, ex)
                state.episodes = []
                state.episodes_has_more = False
            finally:
                state.is_loading = False
                state.episodes_version += 1

    async def play_episode(self, anime_session: str, episode_session: str):
        # Phase 3 replaces this with the in-app flet-video player (quality
        # selector, resume, next/prev). Phase 1 wires the screen to the
        # controller so the flow exists end to end.
        state.current_anime_session = anime_session
        state.current_episode_session = episode_session
        state.episodes_version += 1
        logger.info("play_episode %s/%s (player lands in Phase 3)", anime_session, episode_session)


async def main(page: ft.Page):
    controller = AppController(page)
    await controller.init()

    methods = ControllerMethods()
    methods.load_latest = lambda page_num=1: spawn(
        controller.load_latest(page_num), name="load-latest"
    )
    methods.retry_cloudflare = lambda: spawn(
        controller.retry_cloudflare(), name="retry-cf"
    )
    methods.load_episodes = lambda session, page_num=1: spawn(
        controller.load_episodes(session, page_num), name="load-episodes"
    )
    methods.play_episode = lambda anime_session, episode_session: spawn(
        controller.play_episode(anime_session, episode_session), name="play-episode"
    )

    page.render(lambda: ControllerMethodsCtx(methods, lambda: AppShell()))


if __name__ == "__main__":
    ft.run(main, assets_dir="assets")
