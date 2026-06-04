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
from core.constants import (
    APP_NAME,
    ERR_LOAD_EPISODE,
    ERR_NETWORK,
    ERR_NO_STREAM,
    LBL_DOWNLOAD_UPTODOWN,
    LBL_INSTALL_PLAYER_BODY,
    LBL_INSTALL_PLAYER_TITLE,
    LBL_NOT_NOW,
)
from core.focus_manager import FocusManager
from core.state import state
from core.theme import AppColors, AppTheme
from services.animepahe import AnimePaheScraper
from services.cache import Cache
from services.kwik_resolver import KwikResolver
from services.update_service import UpdateService
from views.anime_detail import build_anime_detail_view
from views.home import build_home_view
from views.search import build_search_view

logger = logging.getLogger(__name__)


def _theme_button_style():
    return ft.ButtonStyle(
        bgcolor={
            ft.ControlState.FOCUSED: AppColors.PRIMARY,
            ft.ControlState.DEFAULT: ft.Colors.SURFACE,
        },
        color={
            ft.ControlState.FOCUSED: ft.Colors.WHITE,
            ft.ControlState.DEFAULT: ft.Colors.ON_SURFACE,
        },
    )


def show_ktv_install_dialog(page: ft.Page):
    page.dialog_open = True

    async def open_store(e):
        page.dialog_open = False
        try:
            page.pop_dialog()
        except Exception:
            pass
        try:
            await asyncio.wait_for(
                ft.UrlLauncher().launch_url(KTV_PLAY_STORE_URL), timeout=1.0
            )
        except Exception:
            pass
        page.update()

    async def open_uptodown(e):
        page.dialog_open = False
        try:
            page.pop_dialog()
        except Exception:
            pass
        try:
            await asyncio.wait_for(
                ft.UrlLauncher().launch_url(KTV_UPTODOWN_URL), timeout=1.0
            )
        except Exception:
            pass
        page.update()

    def dismiss(e):
        page.dialog_open = False
        try:
            page.pop_dialog()
        except Exception:
            pass
        page.update()

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text(LBL_INSTALL_PLAYER_TITLE, weight=ft.FontWeight.BOLD),
        content=ft.Column(
            [
                ft.Text(LBL_INSTALL_PLAYER_BODY, size=14),
            ],
            tight=True,
        ),
        actions=[
            ft.Button(content=ft.Text(LBL_NOT_NOW), on_click=dismiss),
            ft.Button(
                content=ft.Text("Get it on Play Store"),
                on_click=lambda e: page.run_task(open_store, e),
                style=_theme_button_style(),
            ),
            ft.Button(
                content=ft.Text(LBL_DOWNLOAD_UPTODOWN),
                on_click=lambda e: page.run_task(open_uptodown, e),
                style=_theme_button_style(),
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    page.show_dialog(dlg)


def show_update_dialog(page: ft.Page, update_data: dict):
    page.dialog_open = True

    async def open_download(e):
        page.dialog_open = False
        try:
            page.pop_dialog()
        except Exception:
            pass
        try:
            await asyncio.wait_for(
                ft.UrlLauncher().launch_url(update_data["apk_url"]), timeout=1.0
            )
        except Exception:
            pass
        page.update()

    def dismiss(e):
        page.dialog_open = False
        try:
            page.pop_dialog()
        except Exception:
            pass
        page.update()

    dlg = ft.AlertDialog(
        modal=update_data["mandatory"],
        title=ft.Text("New Version Available! 🎉", weight=ft.FontWeight.BOLD),
        content=ft.Column(
            [
                ft.Text(
                    f"Version {update_data['version']} is ready for installation.",
                    size=14,
                ),
                ft.Container(height=8),
                ft.Text("Highlights:", weight=ft.FontWeight.W_600, size=13),
                ft.Text(
                    update_data["release_notes"],
                    size=12,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
            tight=True,
        ),
        actions=[
            ft.Button(
                content=ft.Text("Update Now"),
                on_click=lambda e: page.run_task(open_download, e),
                style=_theme_button_style(),
            ),
        ]
        + (
            []
            if update_data["mandatory"]
            else [
                ft.Button(
                    content=ft.Text("Later"),
                    on_click=dismiss,
                )
            ]
        ),
        actions_alignment=ft.MainAxisAlignment.END,
    )

    page.show_dialog(dlg)


class AppController:
    def __init__(self, page: ft.Page):
        self.page = page
        self.scraper: AnimePaheScraper | None = None
        self.kwik: KwikResolver | None = None
        self.cache: Cache | None = None
        self.focus_manager: FocusManager | None = None
        self._loading_locks: dict[str, asyncio.Lock] = {}

    async def init(self):
        self.page.title = APP_NAME
        self.page.padding = 0
        self.page.spacing = 0

        self.page.on_error = lambda e: self._show_error_snackbar()

        self.page.fonts = {"Outfit": "assets/outfit.css"}
        self.page.theme = AppTheme.get_light_theme()
        self.page.dark_theme = AppTheme.get_dark_theme()
        self.page.theme.font_family = "Outfit"
        self.page.dark_theme.font_family = "Outfit"
        self.page.theme_mode = ft.ThemeMode.SYSTEM

        self.cache = Cache()
        self.scraper = AnimePaheScraper()
        self.kwik = KwikResolver()

        await self.cache.start_sweep(interval=300)

        state.scraper = self.scraper
        state.cache = self.cache
        state.page = self.page

        self.focus_manager = FocusManager(self.page)
        self.focus_manager.set_back_handler(self._handle_global_back)

        self.update_service = UpdateService()
        self.page._show_update_dialog = lambda data: show_update_dialog(self.page, data)
        self.page.run_task(self._check_for_updates_bg)

    async def _check_for_updates_bg(self):
        await asyncio.sleep(2.0)
        update_data = await self.update_service.check_for_update()
        if update_data:
            state.update_available = True
            state.update_data = update_data
            if hasattr(self.page, "on_update_found"):
                self.page.on_update_found(update_data)

    def _show_error_snackbar(self):
        try:
            self.page.snack_bar = ft.SnackBar(
                ft.Text(ERR_NETWORK),
                bgcolor=AppColors.ERROR,
            )
            self.page.snack_bar.open = True
            self.page.update()
        except Exception:
            pass

    def _get_lock(self, key: str) -> asyncio.Lock:
        if key not in self._loading_locks:
            self._loading_locks[key] = asyncio.Lock()
        return self._loading_locks[key]

    def _handle_global_back(self):
        if getattr(self.page, "dialog_open", False):
            self.page.dialog_open = False
            try:
                self.page.pop_dialog()
            except Exception:
                pass
            self.page.update()
            return
        if len(self.page.views) > 1:
            self.page.views.pop()
            if self.page.views:
                self.page.route = self.page.views[-1].route
            self.page.update()

    async def navigate(self, route: str):
        await self.page.push_route(route)

    def _open_anime_detail(self, anime):
        session = anime if isinstance(anime, str) else anime.session
        state.episodes_page = 1
        self.page.views.append(
            build_anime_detail_view(
                page_obj=self.page,
                anime_session=session,
                on_load_episodes=self.load_episodes,
                on_play=self.play_episode,
            )
        )
        self.page.route = f"/anime?session={session}"
        self.page.run_task(self.load_episodes, session, 1)
        self.page.update()

    async def load_latest(self, page_num: int = 1):
        task_key = f"latest_{page_num}"
        lock = self._get_lock(task_key)
        if lock.locked():
            return

        async with lock:
            state.is_loading = True
            state.latest_page = page_num
            self._update_home_grid()

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
            except Exception as ex:
                logger.error("load_latest page=%d failed: %s", page_num, ex)
                state.latest_releases = []
                state.latest_has_more = False
            finally:
                state.is_loading = False
                self._update_home_grid()

    async def load_search(self, query: str):
        if not query:
            return
        task_key = f"search_{query}"
        lock = self._get_lock(task_key)
        if lock.locked():
            return

        async with lock:
            state.is_loading = True
            state.search_query = query
            self._refresh_search_results()

            try:
                results, has_more = await self.scraper.search(query, 1)
                logger.info(
                    "load_search q=%s got %d items, has_more=%s",
                    query,
                    len(results),
                    has_more,
                )
                state.search_results = results
                state.search_has_more = has_more
            except Exception as ex:
                logger.error("load_search q=%s failed: %s", query, ex)
                state.search_results = []
                state.search_has_more = False
            finally:
                state.is_loading = False
                self._refresh_search_results()

    async def load_episodes(self, anime_session: str, page_num: int = 1):
        task_key = f"episodes_{anime_session}"
        lock = self._get_lock(task_key)
        if lock.locked():
            return

        async with lock:
            state.is_loading = True
            state.episodes_page = page_num
            self._refresh_episodes()

            try:
                episodes_task = self.scraper.episodes(anime_session, page_num)

                # Check if we need to resolve the poster concurrently
                anime_in_search = next(
                    (a for a in state.search_results if a.session == anime_session),
                    None,
                )
                needs_poster_resolution = (
                    not anime_in_search
                    or "/snapshots/" in getattr(anime_in_search, "poster", "")
                )

                if needs_poster_resolution:
                    title_to_search = ""
                    if anime_in_search:
                        title_to_search = anime_in_search.title
                    else:
                        lr = next(
                            (
                                a
                                for a in state.latest_releases
                                if a.anime_session == anime_session
                            ),
                            None,
                        )
                        if lr:
                            title_to_search = lr.anime_title

                    if title_to_search:

                        async def resolve_poster_task():
                            try:
                                logger.info(
                                    "Resolving real poster for %s...", title_to_search
                                )
                                search_results, _ = await self.scraper.search(
                                    title_to_search, 1
                                )
                                matched = next(
                                    (
                                        a
                                        for a in search_results
                                        if a.session == anime_session
                                    ),
                                    None,
                                )
                                if matched:
                                    state.search_results = [
                                        a
                                        for a in state.search_results
                                        if a.session != anime_session
                                    ]
                                    state.search_results.append(matched)
                                    logger.info("Resolved poster: %s", matched.poster)
                            except Exception as ex:
                                logger.error("Failed to resolve poster: %s", ex)

                        results = await asyncio.gather(
                            episodes_task, resolve_poster_task(), return_exceptions=True
                        )
                        ep_res = results[0]
                        if isinstance(ep_res, Exception):
                            raise ep_res
                        episodes, has_more = ep_res
                    else:
                        episodes, has_more = await episodes_task
                else:
                    episodes, has_more = await episodes_task

                logger.info(
                    "load_episodes session=%s page=%d got %d items, has_more=%s",
                    anime_session,
                    page_num,
                    len(episodes),
                    has_more,
                )
                state.episodes = episodes
                state.episodes_has_more = has_more
            except Exception as ex:
                logger.error(
                    "load_episodes session=%s page=%d failed: %s",
                    anime_session,
                    page_num,
                    ex,
                )
                state.episodes = []
                state.episodes_has_more = False
            finally:
                state.is_loading = False
                self._refresh_episodes()

    async def play_episode(self, anime_session: str, episode_session: str):
        self._show_snackbar("Fetching available qualities...", AppColors.PRIMARY)

        try:
            sources = await self.scraper.sources(anime_session, episode_session)
        except Exception as ex:
            print(f"[DEBUG] sources() failed: {ex}")
            self._show_snackbar(ERR_LOAD_EPISODE, AppColors.ERROR)
            return

        print(f"[DEBUG] sources returned {len(sources)} items:")
        for s in sources:
            print(f"  -> {s.resolution}p | audio={s.audio} | url={s.url}")

        if not sources:
            self._show_snackbar(ERR_NO_STREAM, AppColors.ERROR)
            return

        sources.sort(key=lambda s: s.resolution, reverse=True)

        def on_select(e, src):
            self.page.dialog_open = False
            state.selected_source = src
            state.current_anime_session = anime_session
            state.current_episode_session = episode_session

            self._refresh_episodes()

            try:
                self.page.pop_dialog()
            except Exception:
                pass
            self.page.run_task(
                self._play_episode_external, anime_session, episode_session
            )

        buttons = []
        for src in sources:
            audio_label = (
                "DUB (ENG)"
                if "eng" in src.audio.lower()
                else f"SUB ({src.audio.upper()})"
            )
            label = f"{src.resolution}p - {audio_label}"
            if src.fansub:
                label += f" ({src.fansub})"

            buttons.append(
                ft.Button(
                    content=ft.Text(label),
                    on_click=lambda e, s=src: on_select(e, s),
                    style=_theme_button_style(),
                )
            )

        info_text = ft.Text(
            "Tip: If the player does not start, try again. Make sure you already have the player installed.",
            size=12,
            color=ft.Colors.ON_SURFACE_VARIANT,
            italic=True,
        )
        content_col = ft.Column(
            [info_text, ft.ListView(controls=buttons, spacing=10)],
            spacing=10,
        )

        dlg = ft.AlertDialog(
            title=ft.Text("Select Quality & Audio", weight=ft.FontWeight.BOLD),
            content=content_col,
            actions=[
                ft.Button(
                    content=ft.Text("Cancel"),
                    on_click=lambda e: (
                        setattr(self.page, "dialog_open", False),
                        self.page.pop_dialog(),
                    ),
                )
            ],
            modal=True,
        )
        self.page.dialog_open = True
        self.page.show_dialog(dlg)

    async def _play_episode_external(self, anime_session: str, episode_session: str):
        if not state.selected_source:
            print("[DEBUG] No selected source")
            return

        kwik_url = state.selected_source.url
        print(f"[DEBUG] kwik_url = {kwik_url}")

        if not kwik_url.startswith("http"):
            print("[DEBUG] kwik_url does not start with http")
            return

        loading_dlg = ft.AlertDialog(
            modal=True,
            content=ft.Container(
                padding=40,
                content=ft.Column(
                    [
                        ft.ProgressRing(color=AppColors.PRIMARY, stroke_width=4),
                        ft.Container(height=16),
                        ft.Text(
                            "Resolving stream...",
                            size=14,
                            color=ft.Colors.ON_SURFACE,
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ),
            bgcolor=ft.Colors.SURFACE,
        )
        self.page.dialog_open = True
        self.page.show_dialog(loading_dlg)
        self.page.update()

        m3u8_url = await self.kwik.resolve(kwik_url)
        print(f"[DEBUG] Resolved m3u8_url = {m3u8_url}")
        self.page.dialog_open = False
        try:
            self.page.pop_dialog()
        except Exception:
            pass

        if not m3u8_url:
            print("[DEBUG] m3u8_url is None — resolve failed")
            self._show_snackbar("Failed to resolve stream.", AppColors.ERROR)
            return

        encoded = base64.urlsafe_b64encode(m3u8_url.encode()).decode().rstrip("=")
        deep_link = f"{KTV_DEEP_LINK_SCHEME}{encoded}"
        print(f"[DEBUG] deep_link = {deep_link}")

        try:
            await asyncio.wait_for(ft.UrlLauncher().launch_url(deep_link), timeout=1.0)
        except asyncio.TimeoutError:
            print("[DEBUG] KTV launched (TimeoutError is expected success)")
            pass
        except Exception as ex:
            print(f"[DEBUG] KTV launch failed: {ex}")
            show_ktv_install_dialog(self.page)

    async def route_change(self, e: ft.RouteChangeEvent | None = None):
        route = self.page.route
        parsed = urllib.parse.urlparse(route)

        if parsed.path in ["/", "/home", "/search"]:
            self.page.views.clear()

        if parsed.path in ["/", "/home"]:
            self.page.views.append(
                build_home_view(
                    page_obj=self.page,
                    on_load_latest=self.load_latest,
                    on_select_anime=self._open_anime_detail,
                    on_search_click=lambda: self.page.run_task(
                        self.navigate, "/search"
                    ),
                )
            )

        elif parsed.path == "/search":
            self.page.views.append(
                build_search_view(
                    page_obj=self.page,
                    on_search=self.load_search,
                    on_select_anime=self._open_anime_detail,
                    on_back=lambda: self.page.run_task(self.navigate, "/home"),
                )
            )

        self.page.update()

    def view_pop(self, e: ft.ViewPopEvent):
        if len(self.page.views) > 1:
            self.page.views.pop()
            if self.page.views:
                self.page.route = self.page.views[-1].route
            self.page.update()

    def _update_home_grid(self):
        if hasattr(self.page, "update_home_grid"):
            self.page.update_home_grid()
        else:
            self.page.update()

    def _refresh_search_results(self):
        if hasattr(self.page, "refresh_search_results"):
            self.page.refresh_search_results()
        else:
            self.page.update()

    def _refresh_episodes(self):
        if hasattr(self.page, "refresh_episodes"):
            self.page.refresh_episodes()
        else:
            self.page.update()

    def _show_snackbar(self, message: str, color: str):
        try:
            self.page.snack_bar = ft.SnackBar(
                ft.Text(message),
                bgcolor=color,
            )
            self.page.snack_bar.open = True
            self.page.update()
        except Exception:
            pass

    async def cleanup(self):
        if self.scraper:
            await self.scraper.close()
        if self.kwik:
            await self.kwik.close()
        if self.cache:
            await self.cache.close()


async def main(page: ft.Page):
    controller = AppController(page)
    await controller.init()

    page.on_route_change = controller.route_change
    page.on_view_pop = controller.view_pop

    await controller.route_change()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    ft.run(main, assets_dir="assets")
