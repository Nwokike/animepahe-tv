"""AppShell — the top-level component tree (house pattern, Sherlock/KTV).

Owns the tab state and the navigation closures the controller fills in.
Screens are `@ft.component` functions that read state + controller methods
through contexts; this shell decides which one is mounted.

Navigation on flet 1.0.4 is component state (there is no `page.views` any
more) — the Only additions are the player/detail overlays, which mount as
full-tree branches exactly like Sherlock's results view.
"""

import flet as ft

from core.theme import AppColors
from screens.home_screen import HomeScreen
from state.app_state import AppStateCtx
from state.controller_ctx import ControllerMethodsCtx

_TABS = ["Home", "Search", "Downloads", "Settings"]


@ft.component
def AppShell() -> ft.Control:
    active_tab, set_active_tab = ft.use_state("Home")
    state = ft.use_context(AppStateCtx)
    controller = ft.use_context(ControllerMethodsCtx)

    # The controller drives navigation by mutating these closures in place
    # (identity must survive — see controller_ctx.py).
    controller.go_home = lambda: set_active_tab("Home")
    controller.open_search = lambda: set_active_tab("Search")
    controller.open_downloads = lambda: set_active_tab("Downloads")
    controller.open_settings = lambda: set_active_tab("Settings")

    if active_tab == "Home":
        body = HomeScreen()
    elif active_tab == "Search":
        body = _placeholder("Search", "Phase 2 — debounced live search lands here.")
    elif active_tab == "Downloads":
        body = _placeholder(
            "Downloads", "Phase 4 — your offline episodes will live here."
        )
    else:
        body = _placeholder("Settings", "Phase 5 — settings + activity terminal.")

    return ft.Column(
        [
            ft.Container(
                content=ft.Row(
                    [
                        ft.Text(
                            "AnimePahe",
                            size=20,
                            weight=ft.FontWeight.BOLD,
                            color=AppColors.PRIMARY,
                        ),
                        ft.Row(
                            [
                                ft.IconButton(
                                    icon=ft.Icons.SEARCH,
                                    on_click=lambda e: set_active_tab("Search"),
                                ),
                                ft.IconButton(
                                    icon=ft.Icons.DOWNLOAD,
                                    on_click=lambda e: set_active_tab("Downloads"),
                                ),
                                ft.IconButton(
                                    icon=ft.Icons.SETTINGS,
                                    on_click=lambda e: set_active_tab("Settings"),
                                ),
                            ],
                            spacing=4,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                padding=ft.Padding.symmetric(horizontal=16, vertical=10),
                bgcolor=AppColors.DARK_SURFACE,
            ),
            ft.Container(content=body, expand=True, padding=12),
        ],
        spacing=0,
        expand=True,
    )


def _placeholder(title: str, message: str) -> ft.Control:
    return ft.Container(
        content=ft.Column(
            [
                ft.Text(title, size=22, weight=ft.FontWeight.BOLD, color=AppColors.DARK_TEXT),
                ft.Text(message, size=13, color=AppColors.DARK_TEXT_DIM),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=8,
        ),
        alignment=ft.Alignment.CENTER,
        expand=True,
    )
