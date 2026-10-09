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
from screens.home_screen import HomeScreen
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
    active_tab, set_active_tab = ft.use_state("Home")

    from flet import context as flet_context

    try:
        page = flet_context.page
    except Exception:
        page = None

    # The controller drives navigation by mutating these closures in place
    # (identity must survive — see controller_ctx.py).
    controller.go_home = lambda: set_active_tab("Home")
    controller.open_search = lambda: set_active_tab("Browse")
    controller.open_downloads = lambda: set_active_tab("Downloads")
    controller.open_settings = lambda: set_active_tab("Settings")

    def _on_tab(name: str):
        set_active_tab(name)

    if active_tab == "Home":
        body = HomeScreen()
    elif active_tab == "Browse":
        body = _placeholder("Browse", "Search lands here — Phase 2.")
    elif active_tab == "Downloads":
        body = _placeholder("Downloads", "Your offline episodes will live here — Phase 4.")
    else:
        body = _placeholder("Settings", "Settings + activity terminal — Phase 5.")

    destinations = [
        ft.NavigationRailDestination(icon=icon, label=label)
        for icon, label in zip(_TAB_ICONS, _TABS, strict=True)
    ]
    selected = _TABS.index(active_tab)

    if _use_rail(page):
        return ft.Row(
            [
                ft.NavigationRail(
                    destinations=destinations,
                    selected_index=selected,
                    on_change=lambda e: _on_tab(_TABS[e.control.selected_index]),
                    min_width=72,
                    bgcolor=AppColors.DARK_SURFACE,
                    use_indicator=True,
                    indicator_color=ft.Colors.with_opacity(0.15, AppColors.PRIMARY),
                ),
                ft.VerticalDivider(width=1),
                ft.Container(content=body, expand=True),
            ],
            spacing=0,
            expand=True,
        )

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
