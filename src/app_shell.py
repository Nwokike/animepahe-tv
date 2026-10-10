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
from screens.settings_screen import SettingsScreen
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

    # Dialog portal (Sherlock pattern): one dialog whose identity survives
    # re-renders; screens open sheets through the controller instead of
    # calling page.show_dialog ad hoc.
    active_dialog, set_active_dialog = ft.use_state(None)
    if state.quality_dialog_open and active_dialog is None:
        set_active_dialog(_build_quality_dialog(state, controller))
    if not state.quality_dialog_open and active_dialog is not None:
        set_active_dialog(None)
    try:
        ft.use_dialog(active_dialog)
    except RuntimeError:
        pass
    controller.open_sheet = lambda d: set_active_dialog(d)
    controller.close_dialog = lambda: set_active_dialog(None)

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
            body = SettingsScreen()
        chrome = None
        show_nav = True

    rail_destinations = [
        ft.NavigationRailDestination(icon=icon, label=label)
        for icon, label in zip(_TAB_ICONS, _TABS, strict=True)
    ]
    # The bar takes NavigationBarDestination objects — feeding it rail
    # destinations serializes the wrong wire type and the bottom bar
    # renders empty on phones.
    bar_destinations = [
        ft.NavigationBarDestination(icon=icon, label=label)
        for icon, label in zip(_TAB_ICONS, _TABS, strict=True)
    ]
    selected = _TABS.index(active_tab)

    if _use_rail(page):
        rail_or_bar = ft.NavigationRail(
            destinations=rail_destinations,
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
                destinations=bar_destinations,
                selected_index=selected,
                on_change=lambda e: _on_tab(_TABS[e.control.selected_index]),
            ),
        ],
        spacing=0,
        expand=True,
    )


# Reference to the live player so the FocusScope back key can run its
# bounded position save before the shell flips state. Without this, a
# remote/system Back discards the resume position for that episode.
_active_player = None


def _build_player(state) -> ft.Control:
    """The in-app player branch, wrapped in FocusScope so Back/Escape
    always reaches it (without autofocus the overlay swallows the first
    remote press)."""
    from components.player.immersive_player import ImmersivePlayer
    from hooks.use_focus_scope import FocusScope

    spec = getattr(state, "player_spec", None) or {}
    from services.store import get_store

    global _active_player

    player = ImmersivePlayer(
        resource=spec.get("resource", ""),
        title=spec.get("title", ""),
        http_headers=spec.get("headers"),
        resume_key=spec.get("episode_session"),
        store=get_store(),
        variants=spec.get("variants") or [],
        on_close=lambda: _close_player(),
    )
    _active_player = player
    return FocusScope(content=player, on_back=_player_back)


async def _player_back():
    # Back from the remote/keyboard: let the player save its position
    # (bounded, 3s) before the shell tears it down.
    player = _active_player
    if player is not None:
        try:
            await player.handle_close()
        except Exception:
            pass
    await _async_close_player()


async def _async_close_player():
    global _active_player

    from state.app_state import state

    _active_player = None
    state.player_open = False
    state.episodes_version += 1


def _close_player():
    from flet import context as flet_context

    page = flet_context.page
    if page is None:
        return
    page.run_task(_player_back())


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


def _build_quality_dialog(state, controller) -> ft.Control:
    """Select Quality & Audio — restored from the original build, extended
    with the m3u8 variants the player can switch to."""
    choices = state.quality_choices or []
    buttons = [
        ft.OutlinedButton(
            content=choice["label"],
            on_click=lambda e, i=i: controller.choose_quality(i),
        )
        for i, choice in enumerate(choices)
    ]
    return ft.AlertDialog(
        modal=True,
        title=ft.Text("Select Quality & Audio", weight=ft.FontWeight.BOLD),
        content=ft.Column(controls=buttons, tight=True, spacing=8),
        actions=[
            ft.TextButton(
                content="Cancel",
                on_click=lambda e: controller.close_dialog(),
            )
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
