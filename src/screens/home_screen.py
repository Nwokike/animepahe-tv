"""Home screen — latest releases, cross-promo, and the CF gate.

Visual craft carried over from the original views: 1.67 landscape cards,
radius 16, the left-to-right gradient, and the primary-colored episode
label. The focus ring is the KTV pattern (flet 1.0.4): cards are flat
``FilledButton``s carrying a FOCUSED side from ``card_button_style`` plus
the on_focus/on_blur micro-zoom — a ``Container`` card cannot take D-pad
focus in 1.0.4, which is what made the old ring invisible. Header follows
the same line: icon + wordmark left, actions right.
"""

import flet as ft

from components.artwork_card import card_frame, card_media
from components.banner_ad import build_banner_ad
from components.cross_promo import PromoHero
from components.focus_styles import (
    attach_focus_zoom,
    card_button_style,
    card_focus_scale,
)
from components.pagination import pager as ft_pager
from core.artwork import LANDSCAPE
from core.constants import (
    APP_NAME,
    APP_VERSION,
    LBL_CF_BLOCKED_BODY,
    LBL_CF_BLOCKED_TITLE,
    LBL_CF_VERIFY_BUTTON,
    LBL_OFFLINE_BODY,
)
from core.theme import AppColors, next_theme_mode
from hooks.use_grid_mode import grid_sources, use_grid_mode
from services.hls_proxy import image_url
from services.providers.base import owner_of
from state.app_state import AppStateCtx
from state.controller_ctx import ControllerMethodsCtx


def _release_card(
    release,
    on_select,
    now_playing: bool,
    col: dict | None = None,
    mode: str = LANDSCAPE,
    provider: str = "",
) -> ft.Control:
    play_icon = ft.Icon(
        ft.Icons.EQUALIZER_ROUNDED if now_playing else ft.Icons.PLAY_CIRCLE_FILL_ROUNDED,
        size=40,
        color=AppColors.PRIMARY if now_playing else ft.Colors.WHITE,
    )
    overlay = [
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
                        # A per-anime release (anikato's new-release
                        # grid) has no episode number — say "New
                        # release" rather than "Episode 0".
                        f"Episode {release.episode}" if release.episode else "New release",
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
    ]
    # The shared frame: a flat FilledButton (in flet 1.0.4 a Container has no
    # on_focus/on_blur and no per-state side, so a Container card can't
    # receive D-pad focus at all on TV). The FOCUSED side from the style
    # plus the focus/blur scale are the focus ring.
    return card_frame(
        mode=mode,
        media=card_media(
            release.snapshot, mode, title=release.anime_title, provider=provider
        ),
        gradient=ft.Container(
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
        overlay=overlay,
        col=col,
        on_click=lambda e: on_select(release.anime_session),
    )


def _version_pill(state, page) -> ft.Control:
    # Morphs into the "Update Available!" pill the original had, wired
    # to the restored update dialog. Until then it's a quiet version tag.
    update_data = state.update_data if state.update_available else None

    if update_data:
        from components.update_dialog import show_update_dialog

        return ft.Container(
            content=ft.Row(
                [
                    ft.Text(
                        "Update Available!",
                        size=11,
                        weight=ft.FontWeight.BOLD,
                        color=AppColors.PRIMARY,
                    ),
                    ft.Container(
                        width=6,
                        height=6,
                        border_radius=3,
                        bgcolor=AppColors.PRIMARY,
                    ),
                ],
                spacing=4,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=8, vertical=6),
            border_radius=6,
            bgcolor=ft.Colors.with_opacity(0.15, AppColors.PRIMARY),
            border=ft.Border.all(1.5, AppColors.PRIMARY),
            ink=True,
            tooltip="A new version is available",
            on_click=lambda e: show_update_dialog(page, update_data) if page else None,
        )
    return ft.Container(
        content=ft.Text(
            f"v{APP_VERSION}",
            size=11,
            color=ft.Colors.ON_SURFACE_VARIANT,
        ),
        padding=ft.Padding.symmetric(horizontal=8, vertical=6),
        border_radius=6,
        border=ft.Border.all(1, ft.Colors.with_opacity(0.2, ft.Colors.ON_SURFACE_VARIANT)),
        tooltip="Version",
    )


def _backend_badge(state, controller) -> ft.Control:
    """The clickable backend badge: which provider is serving, and a state
    colour from its live health. Tapping opens the picker for one-tap
    switching. There is no "auto" label — the badge shows the provider that
    IS serving (the splash covers the app until one resolves)."""
    name = (state.current_source_name or "").strip()
    label = name.capitalize() if name else ""
    colour = AppColors.SUCCESS if name else ft.Colors.ON_SURFACE_VARIANT
    return ft.Container(
        content=ft.Row(
            [
                ft.Container(
                    width=8,
                    height=8,
                    border_radius=4,
                    bgcolor=colour,
                ),
                ft.Container(width=6),
                ft.Text(label or "…", size=12, weight=ft.FontWeight.W_700),
            ],
            spacing=0,
            tight=True,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding.symmetric(horizontal=10, vertical=6),
        border_radius=14,
        bgcolor=ft.Colors.with_opacity(0.1, colour),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.35, colour)),
        ink=True,
        tooltip=f"Served by {label} — tap to switch" if label else "Choosing a source…",
        on_click=lambda e: controller.open_backend_picker(),
    )


def _app_title(state) -> str:
    """`<Backend> TV` — "Anikato TV", "Animepahe TV" — the active source's
    own name for the header. The brand name only stands in before anything
    is resolved (the splash covers that moment)."""
    name = (getattr(state, "current_source_name", "") or "").strip()
    return f"{name.capitalize()} TV" if name else APP_NAME


def _header(state, page, controller, on_theme, theme_icon) -> ft.Control:
    """Icon + title-pill left; badge, version, actions right.

    The title is the source switcher: "<Backend> TV ▾" — tapping it (like
    the badge) opens the content-source picker, so changing backends never
    depends on finding Settings."""

    def action(icon, tip, handler, icon_color=None) -> ft.Control:
        return ft.Container(
            content=ft.Icon(icon, color=icon_color or ft.Colors.ON_SURFACE, size=20),
            padding=10,
            border_radius=10,
            ink=True,
            tooltip=tip,
            on_click=handler,
        )

    # The original dimmed the search action while the CF gate was up.
    blocked = getattr(state, "cf_blocked", False)
    search_color = ft.Colors.OUTLINE if blocked else None
    return ft.Container(
        padding=ft.Padding.only(left=16, right=16, top=12, bottom=8),
        content=ft.Row(
            [
                ft.Row(
                    [
                        ft.Image(src="icon.png", width=32, height=32, fit="contain"),
                        ft.Container(
                            content=ft.Row(
                                [
                                    ft.Text(
                                        _app_title(state),
                                        size=20,
                                        weight=ft.FontWeight.W_800,
                                        color=ft.Colors.ON_SURFACE,
                                    ),
                                    ft.Icon(
                                        ft.Icons.ARROW_DROP_DOWN,
                                        size=20,
                                        color=ft.Colors.ON_SURFACE_VARIANT,
                                    ),
                                ],
                                spacing=2,
                                tight=True,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            padding=ft.Padding.symmetric(horizontal=6, vertical=4),
                            border_radius=10,
                            ink=True,
                            tooltip="Change content source",
                            on_click=lambda e: controller.open_backend_picker(),
                        ),
                    ],
                    spacing=10,
                ),
                ft.Row(
                    [
                        _backend_badge(state, controller),
                        _version_pill(state, page),
                        action(
                            ft.Icons.CALENDAR_MONTH_ROUNDED,
                            "Airing schedule",
                            lambda e: controller.open_schedule(),
                        ),
                        action(
                            ft.Icons.SHUFFLE_ROUNDED,
                            "Surprise me",
                            lambda e: controller.open_random(),
                        ),
                        action(
                            ft.Icons.SEARCH_ROUNDED,
                            "Search",
                            lambda e: controller.open_search(),
                            icon_color=search_color,
                        ),
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


_THEME_ICONS = {
    ft.ThemeMode.DARK: ft.Icons.DARK_MODE_ROUNDED,
    ft.ThemeMode.LIGHT: ft.Icons.LIGHT_MODE_ROUNDED,
    ft.ThemeMode.SYSTEM: ft.Icons.SETTINGS_SYSTEM_DAYDREAM_ROUNDED,
}


def _theme_cycle(page) -> tuple[str, object]:
    """3-way cycle: DARK -> LIGHT -> SYSTEM (Sherlock's pattern), on the
    shared order. The icon names the mode the tap lands on."""
    mode = getattr(page, "theme_mode", ft.ThemeMode.SYSTEM) if page else ft.ThemeMode.SYSTEM
    nxt = next_theme_mode(mode)
    return _THEME_ICONS.get(nxt, ft.Icons.DARK_MODE_ROUNDED), nxt


def _continue_watching_row(entries: dict, on_open, mode: str = LANDSCAPE) -> ft.Control | None:
    """Continue Watching shelf — newest first, capped."""
    if not entries:
        return None
    cards = []
    for record in list(entries.values())[:20]:
        if not isinstance(record, dict) or not record.get("anime_session"):
            continue
        poster = record.get("poster")
        total = record.get("total_episodes") or 0
        progress = f"Ep {record.get('episode_num', '?')}"
        if total:
            progress += f" · of {total}"
        body = ft.Column(
            [
                ft.Container(
                    content=ft.Image(
                        src=image_url(poster, owner_of(record["anime_session"])),
                        fit=ft.BoxFit.COVER,
                        expand=True,
                    )
                    if poster
                    else ft.Container(
                        content=ft.Icon(
                            ft.Icons.MOVIE_ROUNDED,
                            size=32,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        alignment=ft.Alignment.CENTER,
                        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
                    ),
                    width=120,
                    height=68 if mode == LANDSCAPE else 170,
                    border_radius=8,
                    clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                ),
                ft.Text(
                    record.get("title", ""),
                    size=12,
                    weight=ft.FontWeight.W_600,
                    color=ft.Colors.ON_SURFACE,
                    max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
                ft.Text(progress, size=11, color=AppColors.PRIMARY),
            ],
            spacing=6,
            width=120,
        )
        cards.append(
            attach_focus_zoom(
                ft.FilledButton(
                    content=body,
                    # Flat card style (unlike the grid cards these sit on the
                    # page background, so the DEFAULT side stays hairline).
                    style=card_button_style(
                        padding=4,
                        radius=12,
                        overlay_alpha=0.18,
                    ),
                    animate_scale=card_focus_scale(1.03),
                    on_click=lambda e, record=record: (
                        on_open(record.get("anime_session", ""))
                        if record.get("anime_session")
                        else None
                    ),
                )
            )
        )
    return ft.Column(
        [
            ft.Text(
                "Continue Watching",
                size=16,
                weight=ft.FontWeight.W_700,
                color=ft.Colors.ON_SURFACE,
            ),
            ft.Row(controls=cards, spacing=8, wrap=False, scroll=ft.ScrollMode.AUTO),
        ],
        spacing=8,
    )


def _cf_overlay_card(state, controller) -> ft.Control:
    """The SHIELD card the original showed over the live grid (not instead
    of it — the scrim keeps the app's context visible)."""
    return ft.Container(
        content=ft.Column(
            [
                ft.Container(
                    content=ft.Icon(ft.Icons.SHIELD_ROUNDED, size=64, color=AppColors.PRIMARY),
                    alignment=ft.Alignment.CENTER,
                ),
                ft.Container(height=8),
                ft.Text(
                    LBL_CF_BLOCKED_TITLE,
                    size=20,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.ON_SURFACE,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Container(height=4),
                ft.Text(
                    LBL_CF_BLOCKED_BODY,
                    size=13,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Container(height=20),
                ft.FilledButton(
                    content=ft.ProgressRing(
                        width=16, height=16, stroke_width=2, color=ft.Colors.WHITE
                    )
                    if getattr(state, "cf_retrying", False)
                    else LBL_CF_VERIFY_BUTTON,
                    icon=None
                    if getattr(state, "cf_retrying", False)
                    else ft.Icons.VERIFIED_ROUNDED,
                    disabled=bool(getattr(state, "cf_retrying", False)),
                    style=ft.ButtonStyle(
                        bgcolor=AppColors.PRIMARY,
                        color=ft.Colors.WHITE,
                        shape=ft.RoundedRectangleBorder(radius=10),
                    ),
                    on_click=lambda e: controller.retry_cloudflare(),
                ),
                ft.Container(height=6),
                # The wall must never trap the user: swapping sources is
                # one tap from the card itself (the header's title/arrow
                # and badge do the same).
                ft.TextButton(
                    content="Change source",
                    on_click=lambda e: controller.open_backend_picker(),
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=0,
            tight=True,
        ),
        padding=32,
        width=320,
        border_radius=20,
        bgcolor=ft.Colors.SURFACE,
        border=ft.Border.all(1, ft.Colors.OUTLINE),
        shadow=ft.BoxShadow(
            blur_radius=30,
            color=ft.Colors.with_opacity(0.4, ft.Colors.BLACK),
            offset=ft.Offset(0, 10),
        ),
    )


def _cf_gate(body: ft.Control, state, controller) -> ft.Control:
    """Gate the live body behind the 60% scrim + SHIELD card.

    The original 1.0.9 app kept the content behind the scrim instead of
    replacing the screen, so the app never looks broken — just gated. This
    used to swap the whole Home for a bare card, losing the header, grid
    and Continue Watching shelf until verification succeeded.
    """
    if not getattr(state, "cf_blocked", False):
        return body
    return ft.Stack(
        [
            body,
            ft.Container(
                expand=True,
                bgcolor=ft.Colors.with_opacity(0.6, ft.Colors.BLACK),
                alignment=ft.Alignment.CENTER,
                content=_cf_overlay_card(state, controller),
            ),
        ],
        expand=True,
    )


def _offline_banner() -> ft.Control:
    """Offline strip, shown above the header when the network is down.

    Deliberately distinct from the CF gate: offline means "nothing will
    load", the gate means "verify to continue" — the old build showed the
    SHIELD card for both.
    """
    return ft.Container(
        content=ft.Row(
            [
                ft.Icon(
                    ft.Icons.WIFI_OFF_ROUNDED,
                    size=18,
                    color=ft.Colors.ON_INVERSE_SURFACE,
                ),
                ft.Text(
                    LBL_OFFLINE_BODY,
                    size=12,
                    color=ft.Colors.ON_INVERSE_SURFACE,
                    expand=True,
                    max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
            ],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding.symmetric(horizontal=16, vertical=8),
        bgcolor=ft.Colors.INVERSE_SURFACE,
    )


@ft.component
def HomeScreen() -> ft.Control:
    state = ft.use_context(AppStateCtx)
    controller = ft.use_context(ControllerMethodsCtx)
    _ = state.latest_version  # re-render trigger, bumped by the controller
    _ = state.continue_version

    # The detected grid shape for this screen (its own backend's own art).
    latest_sources = grid_sources(state.latest_releases, lambda r: r.snapshot)
    grid_mode = use_grid_mode(
        "latest",
        latest_sources,
        state.latest_source or state.current_source_name,
        state,
    )

    from flet import context as flet_context

    try:
        page = flet_context.page
    except Exception:
        page = None

    if (
        not state.latest_releases
        and not state.is_loading
        and state.is_online
        and not state.cf_blocked
    ):
        controller.load_latest()

    theme_icon, next_mode = _theme_cycle(page)

    def _toggle_theme():
        if page:
            page.theme_mode = next_mode
            page.update()
            from core.tasks import spawn

            spawn(
                controller._app_controller.save_theme_mode(next_mode),
                name="save-theme",
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
            _release_card(
                r,
                controller.open_anime,
                now_playing["anime"] == r.anime_session and now_playing["episode"] == r.session,
                col={"xs": 12, "sm": 6, "md": 4, "lg": 4, "xl": 3},
                mode=grid_mode,
                provider=state.latest_source or state.current_source_name,
            )
            for r in releases
        ],
        spacing=12,
        run_spacing=12,
    )

    pager = ft_pager(
        page=state.latest_page,
        has_more=state.latest_has_more,
        on_prev=lambda e: (
            controller.load_latest(state.latest_page - 1) if not state.is_loading else None
        ),
        on_next=lambda e: (
            controller.load_latest(state.latest_page + 1) if not state.is_loading else None
        ),
        is_loading=state.is_loading,
    )

    content = ft.Container(
        content=ft.Column(
            [
                PromoHero(),
                build_banner_ad(page, inline=True),
                _continue_watching_row(state.continue_watching, controller.open_anime, grid_mode)
                or ft.Container(width=0, height=0),
                ft.Text(
                    "Recent Episodes",
                    size=18,
                    weight=ft.FontWeight.W_700,
                    color=ft.Colors.ON_SURFACE,
                ),
                grid,
                pager,
                build_banner_ad(page, inline=True),
                ft.Container(height=32),
            ],
            spacing=16,
        ),
        expand=True,
        padding=ft.Padding.only(left=16, right=16, bottom=16),
    )

    # The CF gate scrims the CONTENT only — the header (title/arrow, badge,
    # actions) stays live so the owner can always swap to another backend
    # while one source is walled (owner's run, 2026-10-15).
    if state.cf_blocked:
        content = _cf_gate(content, state, controller)
    return ft.Column(
        [
            _offline_banner() if not state.is_online else ft.Container(width=0),
            _header(state, page, controller, _toggle_theme, theme_icon),
            content,
        ],
        spacing=0,
        expand=True,
        scroll=ft.ScrollMode.AUTO,
    )
