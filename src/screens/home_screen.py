"""Home screen — latest releases grid.

Phase 1 checkpoint: the first screen on the house architecture. Loads the
latest-release pages through the controller, pages with a Next/Prev nav,
and shows the Cloudflare-gate notice when the solver reports a block.
"""

import flet as ft

from core.theme import AppColors
from hooks.use_debounce import use_debounce  # noqa: F401  (used by later screens)
from state.app_state import AppStateCtx
from state.controller_ctx import ControllerMethodsCtx


def _release_card(release, on_select) -> ft.Control:
    return ft.Container(
        content=ft.Column(
            [
                ft.Container(
                    content=ft.Stack(
                        [
                            ft.Image(
                                src=release.snapshot,
                                fit=ft.BoxFit.COVER,
                                border_radius=8,
                            )
                            if release.snapshot
                            else ft.Container(bgcolor=AppColors.DARK_SURFACE, border_radius=8),
                            ft.Container(
                                content=ft.Text(
                                    f"Episode {release.episode}",
                                    size=11,
                                    color=ft.Colors.WHITE,
                                    weight=ft.FontWeight.W_600,
                                ),
                                bgcolor=ft.Colors.with_opacity(0.7, ft.Colors.BLACK),
                                padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                                border_radius=4,
                                bottom=6,
                                left=6,
                            ),
                        ]
                    ),
                    aspect_ratio=1.67,
                    border_radius=8,
                    clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                ),
                ft.Text(
                    release.anime_title,
                    size=13,
                    max_lines=2,
                    overflow=ft.TextOverflow.ELLIPSIS,
                    color=AppColors.DARK_TEXT,
                ),
            ],
            spacing=6,
        ),
        on_click=lambda e: on_select(release.anime_session),
        width=220,
    )


@ft.component
def HomeScreen() -> ft.Control:
    state = ft.use_context(AppStateCtx)
    controller = ft.use_context(ControllerMethodsCtx)
    _ = state.latest_version  # re-render trigger, bumped by the controller

    if not state.latest_releases and not state.is_loading:
        controller.load_latest()

    if state.cf_blocked:
        return ft.Container(
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.CLOUD_OFF, size=48, color=AppColors.PRIMARY),
                    ft.Text(
                        "Cloudflare check needed",
                        size=18,
                        weight=ft.FontWeight.BOLD,
                        color=AppColors.DARK_TEXT,
                    ),
                    ft.Text(
                        "The site asked for a one-time browser check. Open Search or "
                        "any screen that loads data to complete it.",
                        size=13,
                        color=AppColors.DARK_TEXT_DIM,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.FilledButton(
                        content="Retry",
                        on_click=lambda e: controller.retry_cloudflare(),
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=12,
            ),
            padding=24,
            alignment=ft.Alignment.CENTER,
            expand=True,
        )

    if state.is_loading and not state.latest_releases:
        return ft.Container(
            content=ft.ProgressRing(color=AppColors.PRIMARY),
            alignment=ft.Alignment.CENTER,
            expand=True,
        )

    grid = ft.GridView(
        controls=[
            _release_card(r, controller.open_anime) for r in state.latest_releases
        ],
        runs_count=4,
        max_extent=220,
        spacing=12,
        run_spacing=12,
        expand=True,
    )

    return ft.Column(
        [
            ft.Row(
                [
                    ft.Text(
                        "Latest releases",
                        size=20,
                        weight=ft.FontWeight.BOLD,
                        color=AppColors.DARK_TEXT,
                    ),
                    ft.Row(
                        [
                            ft.OutlinedButton(
                                content="Prev",
                                on_click=lambda e: controller.load_latest(
                                    state.latest_page - 1
                                ),
                                disabled=state.latest_page <= 1,
                            ),
                            ft.Text(f"Page {state.latest_page}", size=13),
                            ft.OutlinedButton(
                                content="Next",
                                on_click=lambda e: controller.load_latest(
                                    state.latest_page + 1
                                ),
                                disabled=not state.latest_has_more,
                            ),
                        ],
                        spacing=8,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            ft.Container(content=grid, expand=True),
        ],
        spacing=12,
        expand=True,
    )
