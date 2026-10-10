"""animepahe-tv — entry point and application controller.

House architecture (KTV/Sherlock on flet 1.0.4): the controller owns the
services and exposes data actions; `AppShell` owns navigation state and
renders `@ft.component` screens through contexts. This module is the only
place services are constructed.
"""

import asyncio
import logging
import os

import flet as ft

from app_shell import AppShell
from core.constants import APP_NAME
from core.tasks import spawn
from core.theme import AppColors, AppTheme
from services.animepahe import AnimePaheScraper
from services.cache import Cache
from services.kwik_resolver import KwikResolver
from services.store import JsonStore
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
        self.store = JsonStore()
        self.scraper = AnimePaheScraper()
        self.kwik = KwikResolver(ddos_solver=self.scraper.ddos)
        self.update_service = UpdateService()
        self._search_gen = 0
        from services.downloads import DownloadManager

        self.downloads = DownloadManager(store=self.store)
        self.downloads.on_progress = self._on_download_progress

        await self.cache.start_sweep(interval=300)

        state.scraper = self.scraper
        state.cache = self.cache
        state.page = self.page
        state.search_history = await self.store.get_search_history()
        state.continue_watching = await self.store.get_continue_watching()
        state.downloads = await self.store.get_downloads()

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
        # Resolve the stream, then open the in-app player. The ktv:// deep
        # link stays as the fallback for when resolution fails.
        state.current_anime_session = anime_session
        state.current_episode_session = episode_session
        state.episodes_version += 1

        anime = await self._resolve_anime(anime_session)
        ep = next((e for e in state.episodes if e.session == episode_session), None)
        if anime and ep:
            record = {
                "anime_session": anime_session,
                "anime_id": ep.anime_id,
                "title": anime.get("title", ""),
                "poster": anime.get("poster", ""),
                "episode_num": ep.episode,
                "episode_session": episode_session,
                "total_episodes": anime.get("episodes", 0),
            }
            await self.store.record_watch(record)
            state.continue_watching = await self.store.get_continue_watching()
            state.continue_version += 1

        # Interstitial between episodes (the full-map cadence).
        try:
            from services.ads import show_interstitial

            await show_interstitial(self.page)
        except Exception as ex:
            logger.warning("interstitial skip: %s", ex)

        # 1. Stream sources.
        try:
            sources = await self.scraper.sources(anime_session, episode_session)
        except Exception as ex:
            logger.error("sources(%s/%s) failed: %s", anime_session, episode_session, ex)
            sources = []
        if not sources:
            logger.warning("no sources — external player fallback")
            await self._open_external_player(anime_session, episode_session)
            return
        state.selected_source = sources[0]

        # 2. Resolve kwik -> m3u8.
        m3u8 = await self.kwik.resolve(sources[0].url)
        if not m3u8:
            logger.warning("kwik resolve failed — external player fallback")
            await self._open_external_player(anime_session, episode_session)
            return

        # 3. Master playlist -> variants (empty = single quality).
        variants = await self._fetch_variants(m3u8)
        if len(variants) > 1:
            state.pending_playback = {
                "m3u8": m3u8,
                "variants": variants,
                "anime_session": anime_session,
                "episode_session": episode_session,
            }
            state.quality_dialog = True
        else:
            await self._open_player(m3u8, [], anime_session, episode_session)

    async def _fetch_variants(self, m3u8: str) -> list[dict]:
        from components.player.immersive_player import KWIK_USER_AGENT, _stream_variants

        try:
            client = self.kwik._get_client()
            resp = await client.get(
                m3u8,
                headers={
                    "User-Agent": KWIK_USER_AGENT,
                    "Referer": "https://kwik.cx/",
                },
            )
            if resp.status_code == 200 and resp.text:
                return _stream_variants(resp.text)
        except Exception as ex:
            logger.warning("variant fetch failed: %s", ex)
        return []

    async def choose_quality(self, variant_index: int):
        """0 = Auto (top variant), 1..N = variants[index-1]."""
        pending = state.pending_playback
        if not pending:
            return
        state.quality_dialog = False
        variants = pending.get("variants") or []
        if variant_index == 0 or not variants:
            await self._open_player(
                pending["m3u8"], [], pending["anime_session"], pending["episode_session"]
            )
            return
        variant = variants[variant_index - 1]
        await self._open_player(
            variant["uri"], variants, pending["anime_session"], pending["episode_session"]
        )

    async def _open_player(
        self,
        resource: str,
        variants: list[dict],
        anime_session: str,
        episode_session: str,
    ):
        from components.player.immersive_player import KWIK_USER_AGENT

        anime = await self._resolve_anime(anime_session)
        self._player_spec = {
            "resource": resource,
            "variants": variants,
            "title": (anime or {}).get("title") or "AnimePahe",
            "episode_session": episode_session,
            "anime_session": anime_session,
            "headers": {
                "User-Agent": KWIK_USER_AGENT,
                "Referer": "https://kwik.cx/",
            },
        }
        state.player_open = True
        state.episodes_version += 1
        logger.info("player opening for %s/%s", anime_session, episode_session)

    async def close_player(self):
        state.player_open = False
        state.episodes_version += 1

    async def play_adjacent(self, delta: int):
        """Next/previous episode within the loaded page."""
        current = state.current_episode_session
        episodes = state.episodes or []
        if not episodes or not current:
            return
        index = next((i for i, e in enumerate(episodes) if e.session == current), None)
        if index is None:
            return
        target = index + delta
        if target < 0 or target >= len(episodes):
            return
        nxt = episodes[target]
        await self.close_player()
        await self.play_episode(state.current_anime_session, nxt.session)

    async def _open_external_player(self, anime_session: str, episode_session: str):
        """Fallback: hand the episode to KTV Player via deep link, as before."""
        try:
            await asyncio.wait_for(
                ft.UrlLauncher().launch_url(
                    f"ktv://play/?url=https://animepahe.com/play/{anime_session}/{episode_session}"
                ),
                timeout=1.5,
            )
        except Exception as ex:
            logger.warning("external player launch failed: %s", ex)
            state.player_error = "Could not open a player for this episode."
            state.episodes_version += 1

    # ------------------------------------------------------------------
    # Downloads
    # ------------------------------------------------------------------

    async def download_episode(self, anime_session: str, episode_session: str):
        rows = await self.store.get_downloads()
        row = rows.get(episode_session)
        if row and row.get("state") == "complete":
            return
        if episode_session in self.downloads.active_jobs:
            return

        anime = await self._resolve_anime(anime_session)
        ep = next((e for e in state.episodes if e.session == episode_session), None)
        try:
            sources = await self.scraper.sources(anime_session, episode_session)
        except Exception as ex:
            logger.error("download: sources failed: %s", ex)
            return
        if not sources:
            return
        m3u8 = await self.kwik.resolve(sources[0].url)
        if not m3u8:
            return

        metadata = {
            "anime_session": anime_session,
            "anime_id": ep.anime_id if ep else 0,
            "title": (anime or {}).get("title", ""),
            "poster": (anime or {}).get("poster", ""),
            "episode_num": ep.episode if ep else 0,
        }
        row = dict(metadata)
        row.update({"state": "partial"})
        await self.store.save_download(episode_session, row)
        state.downloads = rows | {episode_session: row}
        state.downloads_version += 1

        from components.player.immersive_player import KWIK_USER_AGENT

        await self.downloads.start(
            episode_session,
            m3u8,
            {
                "User-Agent": KWIK_USER_AGENT,
                "Referer": "https://kwik.cx/",
            },
            metadata,
        )

    async def cancel_download(self, episode_session: str):
        self.downloads.cancel(episode_session)

    async def delete_download(self, episode_session: str):
        rows = await self.store.get_downloads()
        row = rows.get(episode_session) or {}
        anime_session = row.get("anime_session", "unknown")
        job_dir = os.path.join(
            self.downloads.downloads_dir, anime_session, episode_session
        )
        import shutil

        shutil.rmtree(job_dir, ignore_errors=True)
        await self.store.remove_download(episode_session)
        rows.pop(episode_session, None)
        state.downloads = rows
        state.downloads_version += 1

    async def play_downloaded(self, episode_session: str):
        rows = await self.store.get_downloads()
        row = rows.get(episode_session) or {}
        playlist = row.get("playlist")
        if not playlist or not os.path.exists(playlist):
            state.player_error = "Downloaded file is missing."
            state.episodes_version += 1
            return
        from components.player.immersive_player import KWIK_USER_AGENT

        self._player_spec = {
            "resource": playlist,
            "variants": [],
            "title": row.get("title", "AnimePahe"),
            "episode_session": episode_session,
            "anime_session": row.get("anime_session", ""),
            "headers": {
                "User-Agent": KWIK_USER_AGENT,
                "Referer": "https://kwik.cx/",
            },
        }
        state.player_open = True
        state.episodes_version += 1

    def _on_download_progress(self, episode_session: str, progress: dict):
        state.download_progress = dict(state.download_progress or {})
        state.download_progress[episode_session] = progress
        state.downloads_version += 1

    async def _resolve_anime(self, anime_session: str) -> dict | None:
        """Title/poster for an anime, cheapest source first.

        Order: in-memory releases/search results → Continue Watching store →
        (only then, for cold deep links) a title search. Episodes never need
        this — they load by session — but the detail screen's header does.
        """
        for release in state.latest_releases:
            if release.anime_session == anime_session:
                return {
                    "title": release.anime_title,
                    "poster": release.snapshot,
                    "episodes": 0,
                }
        for anime in state.search_results:
            if anime.session == anime_session:
                return {
                    "title": anime.title,
                    "poster": anime.poster,
                    "episodes": anime.episodes,
                }
        entry = (await self.store.get_continue_watching()).get(anime_session)
        if entry:
            return {
                "title": entry.get("title", ""),
                "poster": entry.get("poster", ""),
                "episodes": entry.get("total_episodes", 0),
            }
        # Cold link: the only case that pays a network round-trip. Reuse the
        # episodes' anime_id? No — the API needs a title; use the newest
        # episode snapshot as a poster and a generic title until Phase 3's
        # metadata endpoint arrives.
        return None

    async def load_anime(self, anime_session: str):
        """Open the detail screen: resolve the header, then load episodes."""
        state.current_anime_session = anime_session
        state.episodes_version += 1
        anime = await self._resolve_anime(anime_session)
        state.selected_anime = anime
        await self.load_episodes(anime_session, 1)

    async def load_search(self, query: str, page: int = 1):
        if not query:
            return
        lock = self._get_lock("search")
        async with lock:
            # Generation counter: a slow response for an older query must
            # never overwrite a newer one's results.
            self._search_gen += 1
            gen = self._search_gen

            state.is_loading = True
            state.search_query = query
            state.search_page = page
            state.search_error = None
            state.search_version += 1

            try:
                results, has_more = await self.scraper.search(query, page)
                if gen != self._search_gen:
                    logger.info("load_search discarding stale response for %r", query)
                    return
                state.search_results = results
                state.search_has_more = has_more
                if page == 1:
                    state.cf_blocked = False
                    await self.store.add_search(query)
                    state.search_history = await self.store.get_search_history()
            except Exception as ex:
                logger.error("load_search q=%r page=%d failed: %s", query, page, ex)
                if gen == self._search_gen:
                    state.search_results = []
                    state.search_has_more = False
                    state.search_error = str(ex)
            finally:
                if gen == self._search_gen:
                    state.is_loading = False
                    state.search_version += 1

    async def clear_search_history(self):
        await self.store.clear_search_history()
        state.search_history = []
        state.search_version += 1


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
    methods.load_anime = lambda session: spawn(
        controller.load_anime(session), name="load-anime"
    )
    methods.play_episode = lambda anime_session, episode_session: spawn(
        controller.play_episode(anime_session, episode_session), name="play-episode"
    )
    methods.load_search = lambda query, page=1: spawn(
        controller.load_search(query, page), name="load-search"
    )
    methods.clear_search_history = lambda: spawn(
        controller.clear_search_history(), name="clear-search-history"
    )
    methods.choose_quality = lambda index: spawn(
        controller.choose_quality(index), name="choose-quality"
    )
    methods.close_player = lambda: spawn(controller.close_player(), name="close-player")
    methods.play_adjacent = lambda delta: spawn(
        controller.play_adjacent(delta), name="play-adjacent"
    )
    methods.download_episode = lambda a, e: spawn(
        controller.download_episode(a, e), name="download-episode"
    )
    methods.cancel_download = lambda e: spawn(
        controller.cancel_download(e), name="cancel-download"
    )
    methods.delete_download = lambda e: spawn(
        controller.delete_download(e), name="delete-download"
    )
    methods.play_downloaded = lambda e: spawn(
        controller.play_downloaded(e), name="play-downloaded"
    )

    # The shell's player branch reaches the controller through this handle
    # (its ControllerMethods copy is the shell-owned navigation half).
    methods._app_controller = controller

    # Ads: one SDK service on the page, guarded to the mobile family.
    try:
        from services.ads import build_ad_service, show_app_open

        ad_service = build_ad_service(
            page,
            on_initialized=lambda e: spawn(show_app_open(page), name="app-open"),
            on_init_failed=lambda e: logger.warning(
                "ad init failed: %s", getattr(e, "data", e)
            ),
        )
        if ad_service is not None and not isinstance(ad_service, ft.Container):
            page.services.append(ad_service)
    except Exception as ex:
        logger.warning("ad service setup skipped: %s", ex)

    page.render(lambda: ControllerMethodsCtx(methods, lambda: AppShell()))


if __name__ == "__main__":
    ft.run(main, assets_dir="assets")
