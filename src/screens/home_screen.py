"""Home screen — latest releases, cross-promo, and the CF gate.

Visual craft carried over from the original views: 1.67 landscape cards with
a 4px transparent border reserving the focus ring, radius 16, the
left-to-right gradient, and the primary-colored episode label. Header follows
the same line: icon + wordmark left, actions right.
"""

import flet as ft

from components.cross_promo import PromoHero, PromoShelf
from core.constants import APP_NAME, APP_VERSION
from core.theme import AppColors
from state.app_state import AppStateCtx
from state.controller_ctx import ControllerMethodsCtx


def _release_card(release, on_select, now_playing: bool) -> ft.Control:
    play_icon = ft.Icon(
        ft.Icons.EQUALIZER_ROUNDED if now_playing else ft.Icons.PLAY_CIRCLE_FILL_ROUNDED,
        size=40,
        color=AppColors.PRIMARY if now_playing else ft.Colors.WHITE,
    )
    image = (
        ft.Image(src=release.snapshot, fit=ft.BoxFit.COVER, expand=True)
        if release.snapshot
        else ft.Container(bgcolor=AppColors.DARK_SURFACE_VARIANT)
    )
    content = ft.Stack(
        [
            image,
            ft.Container(
                gradient=ft.LinearGradient(
                    begin=ft.Alignment.CENTER_LEFT,
                    end=ft.Alignment.CENTER_RIGHT,
                    colors=[
                        ft.Colors.with_opacity(0.8, ft.Colors.BLACK),
                        ft.Colors.TRANSPARENT,
                    ],
                ),
                expand=True,
            ),
            ft.Container(
                padding=16,
                alignment=ft.Alignment.CENTER_LEFT,
                content=ft.Column(
                    [
                        ft.Text(
                            release.anime_title,
                            color=ft.Colors.WHITE,
                            weight=ft.FontWeight.BOLD,
                            size=16,
                            max_lines=2,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        ft.Text(
                            f"Episode {release.episode}",
                            color=AppColors.PRIMARY,
                            weight=ft.FontWeight.BOLD,
                            size=12,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=4,
                ),
            ),
            ft.Container(
                alignment=ft.Alignment.CENTER_RIGHT,
                padding=16,
                content=play_icon,
            ),
        ],
        expand=True,
    )
    return ft.Container(
        content=content,
        border=ft.Border.all(4, ft.Colors.TRANSPARENT),
        padding=4,
        border_radius=16,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.WHITE),
        animate_scale=300,
        animate=300,
        ink=True,
        aspect_ratio=1.67,
        on_click=lambda e: on_select(release.anime_session),
    )


def _header(controller, on_theme, theme_icon) -> ft.Control:
    """Icon + wordmark left; search, version, theme right — the original line."""
    action = lambda icon, tip, handler: ft.Container(
        content=ft.Icon(icon, color=AppColors.DARK_TEXT, size=20),
        padding=10,
        border_radius=10,
        ink=True,
        tooltip=tip,
        on_click=handler,
    )
    return ft.Container(
        padding=ft.Padding.only(left=16, right=16, top=12, bottom=8),
        content=ft.Row(
            [
                ft.Row(
                    [
                        ft.Image(src="icon.png", width=32, height=32, fit="contain"),
                        ft.Text(
                            APP_NAME,
                            size=20,
                            weight=ft.FontWeight.W_800,
                            color=AppColors.DARK_TEXT,
                        ),
                    ],
                    spacing=10,
                ),
                ft.Row(
                    [
                        ft.Container(
                            content=ft.Text(
                                f"v{APP_VERSION}",
                                size=11,
                                color=AppColors.DARK_TEXT_DIM,
                            ),
                            padding=ft.Padding.symmetric(horizontal=8, vertical=6),
                            border_radius=6,
                            border=ft.Border.all(
                                1, ft.Colors.with_opacity(0.2, AppColors.DARK_TEXT_DIM)
                            ),
                            tooltip="Version",
                        ),
                        action(ft.Icons.SEARCH_ROUNDED, "Search", lambda e: controller.open_search()),
                        action(
                            theme_icon,
                            "Switch theme",
                            lambda e: on_theme(),
                        ),
                    ],
                    spacing=4,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        ),
    )


def _theme_cycle(page) -> tuple[str, object]:
    """3-way cycle: DARK -> LIGHT -> SYSTEM (Sherlock's pattern)."""
    mode = getattr(page, "theme_mode", ft.ThemeMode.SYSTEM) if page else ft.ThemeMode.SYSTEM
    order = (ft.ThemeMode.DARK, ft.ThemeMode.LIGHT, ft.ThemeMode.SYSTEM)
    nxt = order[(order.index(mode) + 1) % 3] if mode in order else ft.ThemeMode.SYSTEM
    icon = {
        ft.ThemeMode.DARK: ft.Icons.LIGHT_MODE_ROUNDED,
        ft.ThemeMode.LIGHT: ft.Icons.SETTINGS_SYSTEM_DAYDREAM_ROUNDED,
        ft.ThemeMode.SYSTEM: ft.Icons.DARK_MODE_ROUNDED,
    }[mode]
    return icon, nxt


@ft.component
def HomeScreen() -> ft.Control:
    state = ft.use_context(AppStateCtx)
    controller = ft.use_context(ControllerMethodsCtx)
    _ = state.latest_version  # re-render trigger, bumped by the controller

    from flet import context as flet_context

    try:
        page = flet_context.page
    except Exception:
        page = None

    if not state.latest_releases and not state.is_loading:
        controller.load_latest()

    theme_icon, next_mode = _theme_cycle(page)

    def _toggle_theme():
        if page:
            page.theme_mode = next_mode
            page.update()

    if state.cf_blocked:
        return ft.Container(
            content=ft.Column(
                [
                    ft.Container(
                        content=ft.Icon(ft.Icons.SHIELD_ROUNDED, size=64, color=AppColors.PRIMARY),
                        alignment=ft.Alignment.CENTER,
                    ),
                    ft.Text(
                        "Cloudflare Security Check",
                        size=20,
                        weight=ft.FontWeight.BOLD,
                        color=AppColors.DARK_TEXT,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Text(
                        "Search and browsing are disabled until you verify.",
                        size=13,
                        color=AppColors.DARK_TEXT_DIM,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.FilledButton(
                        content="Verify You're Human",
                        icon=ft.Icons.VERIFIED_ROUNDED,
                        style=ft.ButtonStyle(bgcolor=AppColors.PRIMARY, color=ft.Colors.WHITE),
                        on_click=lambda e: controller.retry_cloudflare(),
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=12,
                tight=True,
            ),
            padding=32,
            width=320,
            border_radius=20,
            bgcolor=AppColors.DARK_SURFACE,
            border=ft.Border.all(1, AppColors.DARK_TEXT_MUTED),
            alignment=ft.Alignment.CENTER,
        )

    if state.is_loading and not state.latest_releases:
        return ft.Container(
            content=ft.ProgressRing(color=AppColors.PRIMARY),
            alignment=ft.Alignment.CENTER,
            expand=True,
        )

    releases = state.latest_releases
    now_playing = {
        "anime": state.current_anime_session,
        "episode": state.current_episode_session,
    }

    grid = ft.ResponsiveRow(
        controls=[
            ft.Container(
                content=_release_card(
                    r,
                    controller.open_anime,
                    now_playing["anime"] == r.anime_session
                    and now_playing["episode"] == r.session,
                ),
                col={"xs": 12, "sm": 6, "md": 4, "lg": 4, "xl": 3},
            )
            for r in releases
        ],
        spacing=12,
        run_spacing=12,
    )

    pager = ft.Row(
        [
            ft.OutlinedButton(
                content="Prev",
                on_click=lambda e: controller.load_latest(state.latest_page - 1),
                disabled=state.latest_page <= 1,
            ),
            ft.Text(f"Page {state.latest_page}", size=13, color=AppColors.DARK_TEXT_DIM),
            ft.OutlinedButton(
                content="Next",
                on_click=lambda e: controller.load_latest(state.latest_page + 1),
                disabled=not state.latest_has_more,
            ),
        ],
        alignment=ft.MainAxisAlignment.CENTER,
        spacing=16,
    )

    body = ft.Column(
        [
            _header(controller, _toggle_theme, theme_icon),
            ft.Container(
                content=ft.Column(
                    [
                        PromoHero(),
                        ft.Text(
                            "Recent Episodes",
                            size=18,
                            weight=ft.FontWeight.W_700,
                            color=AppColors.DARK_TEXT,
                        ),
                        grid,
                        pager,
                        ft.Container(height=16),
                        PromoShelf(),
                        ft.Container(height=32),
                    ],
                    spacing=16,
                ),
                expand=True,
                padding=ft.Padding.only(left=16, right=16, bottom=16),
            ),
        ],
        spacing=0,
        expand=True,
        scroll=ft.ScrollMode.AUTO,
    )
    return body
