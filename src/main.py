import flet as ft
import asyncio
import base64
import urllib.parse

from core.theme import AppTheme, AppColors
from core.state import state
from core.config import (
    USE_EXTERNAL_PLAYER,
    KTV_PLAY_STORE_URL,
    KTV_UPTODOWN_URL,
    KTV_DEEP_LINK_SCHEME,
    EXTERNAL_PLAYER_NAMES,
)
from core.focus_manager import FocusManager
from services.animepahe import AnimePaheScraper
from views.splash import build_splash_view
from views.home import build_home_view
from views.search import build_search_view
from views.anime_detail import build_anime_detail_view
from views.player import build_player_view


def _theme_button_style(page: ft.Page, is_primary: bool = False):
    return ft.ButtonStyle(
        bgcolor={
            ft.ControlState.FOCUSED: AppColors.PRIMARY,
            ft.ControlState.DEFAULT: AppColors.PRIMARY
            if is_primary
            else ft.Colors.SURFACE,
        },
        color={
            ft.ControlState.FOCUSED: ft.Colors.WHITE,
            ft.ControlState.DEFAULT: ft.Colors.WHITE
            if is_primary
            else ft.Colors.ON_SURFACE,
        },
    )


def show_ktv_install_dialog(page: ft.Page):
    def open_store(e):
        page.run_task(page.launch_url, KTV_PLAY_STORE_URL)

    def open_uptodown(e):
        page.run_task(page.launch_url, KTV_UPTODOWN_URL)

    def dismiss(e):
        try:
            page.pop_dialog()
        except Exception:
            pass

    player_buttons = []
    for name in EXTERNAL_PLAYER_NAMES:
        player_buttons.append(
            ft.Button(
                content=ft.Text(name),
                icon=ft.Icons.PLAY_CIRCLE_ROUNDED,
                on_click=open_store,
                style=_theme_button_style(page, is_primary=(name == "KTV Player")),
            )
        )

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text("Install a Player", weight=ft.FontWeight.BOLD),
        content=ft.Column(
            [
                ft.Text(
                    "To stream this episode, please install one of the following players. "
                    "We recommend KTV Player for the best experience.",
                    size=14,
                ),
                ft.Container(height=16),
                ft.Column(player_buttons, spacing=10),
            ],
            tight=True,
        ),
        actions=[
            ft.Button(content=ft.Text("Not now"), on_click=dismiss),
            ft.Button(
                content=ft.Text("Download from Uptodown"), on_click=open_uptodown
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
    )

    page.show_dialog(dlg)


async def main(page: ft.Page):
    page.title = "AnimePahe TV"
    page.padding = 0
    page.spacing = 0

    def global_error_handler(e):
        page.snack_bar = ft.SnackBar(
            ft.Text("Network error or stream unavailable."),
            bgcolor=AppColors.ERROR,
        )
        page.snack_bar.open = True
        page.update()

    page.on_error = global_error_handler

    page.fonts = {
        "Outfit": "https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap"
    }
    page.theme = AppTheme.get_light_theme()
    page.dark_theme = AppTheme.get_dark_theme()
    page.theme.font_family = "Outfit"
    page.dark_theme.font_family = "Outfit"
    page.theme_mode = ft.ThemeMode.SYSTEM

    scraper = AnimePaheScraper()

    focus_manager = FocusManager(page)

    state.scraper = scraper

    def handle_global_back():
        if page.dialog and page.dialog.open:
            page.dialog.open = False
            page.update()
            return
        if len(page.views) > 1:
            top_view = page.views[-1]
            route = getattr(top_view, "route", "")

            if route.startswith("/play"):
                page.run_task(navigate, "/anime?session=" + state.current_anime_session)
            elif route in ("/anime", "/search"):
                page.run_task(navigate, "/home")
            else:
                page.run_task(navigate, "/home")

    focus_manager.set_back_handler(handle_global_back)

    async def navigate(route: str):
        await page.push_route(route)

    async def load_latest(page_num: int = 1):
        state.is_loading = True
        state.latest_page = page_num
        if hasattr(page, "update_home_grid"):
            page.update_home_grid()
        page.update()

        results, has_more = scraper.latest_releases(page_num)
        state.latest_releases = results
        state.latest_has_more = has_more
        state.is_loading = False
        if hasattr(page, "update_home_grid"):
            page.update_home_grid()
        page.update()

    async def load_search(query: str):
        state.is_loading = True
        state.search_query = query
        if hasattr(page, "refresh_search_results"):
            page.refresh_search_results()
        page.update()

        results, has_more = scraper.search(query, 1)
        state.search_results = results
        state.search_has_more = has_more
        state.is_loading = False
        if hasattr(page, "refresh_search_results"):
            page.refresh_search_results()
        page.update()

    async def load_episodes(anime_session: str, page_num: int = 1):
        state.is_loading = True
        state.episodes_page = page_num
        if hasattr(page, "refresh_episodes"):
            page.refresh_episodes()
        page.update()

        episodes, has_more = scraper.episodes(anime_session, page_num)
        state.episodes = episodes
        state.episodes_has_more = has_more
        state.is_loading = False
        if hasattr(page, "refresh_episodes"):
            page.refresh_episodes()
        page.update()

    async def play_episode(anime_session: str, episode_session: str):
        page.snack_bar = ft.SnackBar(ft.Text("Fetching available qualities..."))
        page.snack_bar.open = True
        page.update()

        sources = scraper.sources(anime_session, episode_session)
        if not sources:
            page.snack_bar = ft.SnackBar(
                ft.Text("No sources found."), bgcolor=AppColors.ERROR
            )
            page.snack_bar.open = True
            page.update()
            return

        sources.sort(key=lambda s: s.resolution, reverse=True)

        def on_select(e, src):
            state.selected_source = src
            state.current_anime_session = anime_session
            state.current_episode_session = episode_session

            if hasattr(page, "refresh_episodes"):
                try:
                    page.refresh_episodes()
                except Exception:
                    pass
            page.update()

            try:
                page.pop_dialog()
            except Exception:
                pass
            if USE_EXTERNAL_PLAYER:
                page.run_task(play_episode_external, anime_session, episode_session)
            else:
                page.run_task(_start_playback)

        async def _start_playback():
            page.snack_bar = ft.SnackBar(
                ft.Text("Resolving stream..."), bgcolor=AppColors.SUCCESS
            )
            page.snack_bar.open = True
            page.update()
            await navigate("/play")

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
                    style=_theme_button_style(page),
                )
            )

        dlg = ft.AlertDialog(
            title=ft.Text("Select Quality & Audio", weight=ft.FontWeight.BOLD),
            content=ft.ListView(controls=buttons, spacing=10),
            actions=[
                ft.Button(
                    content=ft.Text("Cancel"), on_click=lambda e: page.pop_dialog()
                )
            ],
            modal=True,
        )
        page.show_dialog(dlg)

    async def play_episode_external(anime_session: str, episode_session: str):
        if not state.selected_source:
            return

        m3u8_url = state.selected_source.url

        encoded_m3u8 = base64.urlsafe_b64encode(m3u8_url.encode()).decode()
        deep_link = f"{KTV_DEEP_LINK_SCHEME}{encoded_m3u8}"

        try:
            await page.launch_url(deep_link)
        except Exception:
            pass

        show_ktv_install_dialog(page)

    async def splash_complete():
        await asyncio.sleep(1.5)
        await navigate("/home")

    async def route_change(e: ft.RouteChangeEvent | None = None):
        route = page.route
        parsed = urllib.parse.urlparse(route)

        if parsed.path in ["/", "/home", "/search"]:
            page.views.clear()

        if parsed.path == "/":
            page.views.append(build_splash_view())
            page.run_task(splash_complete)

        elif parsed.path == "/home":
            page.views.append(
                build_home_view(
                    page_obj=page,
                    on_load_latest=load_latest,
                    on_select_anime=lambda a: page.run_task(
                        navigate, f"/anime?session={a}"
                    ),
                    on_search_click=lambda: page.run_task(navigate, "/search"),
                )
            )

        elif parsed.path == "/search":
            page.views.append(
                build_search_view(
                    page_obj=page,
                    on_search=load_search,
                    on_select_anime=lambda a: page.run_task(
                        navigate, f"/anime?session={a.session}"
                    ),
                    on_back=lambda: page.run_task(navigate, "/home"),
                )
            )

        elif parsed.path == "/anime":
            params = urllib.parse.parse_qs(parsed.query)
            session = params.get("session", [None])[0]
            if session:
                state.episodes_page = 1
                page.views.append(
                    build_anime_detail_view(
                        page_obj=page,
                        anime_session=session,
                        on_load_episodes=load_episodes,
                        on_play=play_episode,
                    )
                )
                page.run_task(load_episodes, session, 1)

        elif parsed.path == "/play":
            try:
                page.pop_dialog()
            except Exception:
                pass
            if state.current_anime_session and state.current_episode_session:
                page.views.append(
                    build_player_view(
                        page_obj=page,
                    )
                )
            else:
                await navigate("/search")

        page.update()

    def view_pop(e: ft.ViewPopEvent):
        if len(page.views) > 1:
            top_view = page.views[-1]
            route = getattr(top_view, "route", "")
            if route.startswith("/play"):
                for control in top_view.controls:
                    if hasattr(control, "pause"):
                        try:
                            control.pause()
                        except Exception:
                            pass

            page.views.pop()
            if route.startswith("/play") and hasattr(page, "refresh_episodes"):
                try:
                    page.refresh_episodes()
                except Exception:
                    pass
            page.update()

    page.on_route_change = route_change
    page.on_view_pop = view_pop

    await route_change()


if __name__ == "__main__":
    ft.run(main, assets_dir="assets")
