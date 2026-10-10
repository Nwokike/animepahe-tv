"""AppShell — adaptive navigation + content (house pattern, Sherlock/KTV).

Navigation follows Material 3 window classes:
- <600dp (phone portrait): bottom NavigationBar
- 600-839dp: compact left NavigationRail
- >=840dp and every Android TV: left NavigationRail (TV forces the rail
  regardless of measured width — no TV app puts primary nav at the bottom)

Cross-promo lives in native slots (hero card + "More from us" shelf), never
between content and navigation — an ad sandwiched against nav is the pattern
both AdMob policy and TV focus design call out as wrong.
"""

import flet as ft

from core.theme import AppColors
from screens.anime_detail_screen import AnimeDetailScreen
from screens.downloads_screen import DownloadsScreen
from screens.home_screen import HomeScreen
from screens.search_screen import SearchScreen
from state.app_state import AppStateCtx
from state.controller_ctx import ControllerMethodsCtx

_TABS = ("Home", "Browse", "Downloads", "Settings")
_TAB_ICONS = (
    ft.Icons.HOME_ROUNDED,
    ft.Icons.EXPLORE_ROUNDED,
    ft.Icons.DOWNLOAD_ROUNDED,
    ft.Icons.SETTINGS_ROUNDED,
)

# Material 3 window size class boundary (dp): below it, bottom bar.
_RAIL_MIN_WIDTH = 600


def _is_tv(page) -> bool:
    if page is None:
        return False
    platform = getattr(page, "platform", None)
    return platform is not None and platform == ft.PagePlatform.ANDROID_TV


def _use_rail(page) -> bool:
    if _is_tv(page):
        return True
    width = getattr(page, "width", None) or 0
    return width >= _RAIL_MIN_WIDTH


@ft.component
def AppShell() -> ft.Control:
    controller = ft.use_context(ControllerMethodsCtx)
    state = ft.use_context(AppStateCtx)
    active_tab, set_active_tab = ft.use_state("Home")
    active_view, set_active_view = ft.use_state("tabs")  # tabs | anime | player
    _ = state.episodes_version
    _ = state.player_open

    from flet import context as flet_context

    try:
        page = flet_context.page
    except Exception:
        page = None

    def _open_anime(session: str):
        # Full-screen branch (Sherlock's results-view pattern): nav bar
        # hides, an AppBar with a back button appears.
        set_active_view("anime")
        controller.load_episodes(session)

    # The controller drives navigation by mutating these closures in place
    # (identity must survive — see controller_ctx.py).
    controller.go_home = lambda: set_active_tab("Home")
    controller.open_search = lambda: set_active_tab("Browse")
    controller.open_downloads = lambda: set_active_tab("Downloads")
    controller.open_settings = lambda: set_active_tab("Settings")
    controller.open_anime = _open_anime
    controller.back = lambda: set_active_view("tabs")
    controller.close_player = lambda: set_active_view("anime")
    controller.play_adjacent = lambda delta: _play_adjacent(delta)
    controller.choose_quality = lambda idx: _choose_quality(idx)

    def _play_adjacent(delta):
        from core.tasks import spawn

        spawn(controller._app_controller.play_adjacent(delta), name="play-adjacent")

    def _choose_quality(index):
        from core.tasks import spawn

        spawn(controller._app_controller.choose_quality(index), name="choose-quality")

    def _on_tab(name: str):
        set_active_tab(name)

    if state.player_open:
        body = _build_player(state)
        chrome = None
        show_nav = False
    elif active_view == "anime":
        body = AnimeDetailScreen()
        chrome = _detail_appbar(controller)
        show_nav = False
    else:
        if active_tab == "Home":
            body = HomeScreen()
        elif active_tab == "Browse":
            body = SearchScreen()
        elif active_tab == "Downloads":
            body = DownloadsScreen()
        else:
            body = _placeholder("Settings", "Settings + activity terminal — Phase 5.")
        chrome = None
        show_nav = True

    destinations = [
        ft.NavigationRailDestination(icon=icon, label=label)
        for icon, label in zip(_TAB_ICONS, _TABS, strict=True)
    ]
    selected = _TABS.index(active_tab)

    if _use_rail(page):
        rail_or_bar = ft.NavigationRail(
            destinations=destinations,
            selected_index=selected,
            on_change=lambda e: _on_tab(_TABS[e.control.selected_index]),
            min_width=72,
            bgcolor=AppColors.DARK_SURFACE,
            use_indicator=True,
            indicator_color=ft.Colors.with_opacity(0.15, AppColors.PRIMARY),
        )
        content = ft.Column(
            [
                chrome if chrome is not None else ft.Container(width=0, height=0),
                ft.Container(content=body, expand=True),
            ],
            spacing=0,
            expand=True,
        )
        if show_nav:
            return ft.Row(
                [rail_or_bar, ft.VerticalDivider(width=1), content],
                spacing=0,
                expand=True,
            )
        return ft.Column([content], spacing=0, expand=True)

    return ft.Column(
        [
            ft.Container(content=body, expand=True),
            ft.NavigationBar(
                destinations=destinations,
                selected_index=selected,
                on_change=lambda e: _on_tab(_TABS[e.control.selected_index]),
            ),
        ],
        spacing=0,
        expand=True,
    )


def _build_player(state) -> ft.Control:
    """The in-app player branch, wrapped in FocusScope so Back/Escape
    always reaches it (without autofocus the overlay swallows the first
    remote press)."""
    from components.player.immersive_player import ImmersivePlayer
    from hooks.use_focus_scope import FocusScope

    spec = getattr(state, "player_spec", None) or {}
    from services.store import get_store

    player = ImmersivePlayer(
        resource=spec.get("resource", ""),
        title=spec.get("title", ""),
        http_headers=spec.get("headers"),
        resume_key=spec.get("episode_session"),
        store=get_store(),
        variants=spec.get("variants") or [],
        on_close=lambda: _close_player(),
    )
    return FocusScope(content=player, on_back=lambda: _close_player())


def _close_player():
    from flet import context as flet_context

    page = flet_context.page
    if page is None:
        return
    # The player saves its own position in handle_close(); we only flip the
    # shell back to the detail screen.
    page.run_task(_async_close)


async def _async_close():
    from flet import context as flet_context
    from state.app_state import state

    state.player_open = False
    state.episodes_version += 1


def _detail_appbar(controller) -> ft.Control:
    return ft.AppBar(
        leading=ft.IconButton(
            icon=ft.Icons.ARROW_BACK_ROUNDED,
            on_click=lambda e: controller.back(),
            tooltip="Back",
        ),
        title=ft.Text("Anime", weight=ft.FontWeight.W_600),
        bgcolor=ft.Colors.TRANSPARENT,
        center_title=False,
    )


def _placeholder(title: str, message: str) -> ft.Control:
    return ft.Container(
        content=ft.Column(
            [
                ft.Text(
                    title,
                    size=22,
                    weight=ft.FontWeight.BOLD,
                    color=AppColors.DARK_TEXT,
                ),
                ft.Text(message, size=13, color=AppColors.DARK_TEXT_DIM),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=8,
        ),
        alignment=ft.Alignment.CENTER,
        expand=True,
    )
