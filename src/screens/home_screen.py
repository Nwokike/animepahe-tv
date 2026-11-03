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

from components.ad_breaks import grid_with_ads
from components.artwork_card import card_frame, card_media
from components.banner_ad import build_banner_ad
from components.cross_promo import PromoHero
from components.focus_styles import (
    attach_focus_zoom,
    card_button_style,
    card_focus_scale,
)
from components.offline_state import empty_or_offline
from components.pagination import pager as ft_pager
from core.artwork import LANDSCAPE
from core.theme import AppColors
from core.tokens import GRID_COL
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
        media=card_media(release.snapshot, mode, title=release.anime_title, provider=provider),
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


def _home_header(state, page, controller) -> ft.Control:
    """The shared header plus Home's own actions — the schedule, the
    random pick and the search entry. Everything else (the source pill,
    the badge, the version pill, the theme cycle) comes from app_header,
    so the switcher is identical on every screen."""
    from components.app_header import app_header

    def _action(icon, tip, handler, colour=None) -> ft.Control:
        # An ICON BUTTON, not a Container: flet 1.0.4 gives a Container
        # no focus state, so these three header actions (Airing
        # schedule, Surprise me, Search) could never be reached by a TV
        # remote — while the pill beside them lit up (2026-10-19
        # re-audit).
        return ft.IconButton(
            icon=icon,
            icon_size=20,
            icon_color=colour or ft.Colors.ON_SURFACE,
            tooltip=tip,
            on_click=handler,
        )

    blocked = getattr(state, "cf_blocked", False)
    source = (getattr(state, "current_source_name", "") or "").strip().lower()

    # Source-specific header actions: Airing schedule and Surprise me
    # belong ONLY to AniKato (the site's own schedule and /random
    # endpoints). When switching away from AniKato, they disappear — the
    # doctrine's rule: once you switch source, everything that is not for
    # that source disappears (owner, 2026-10-23). Search is the only
    # universal action on Home.
    actions: list[ft.Control] = []
    if source == "anikato":
        actions.extend(
            [
                _action(
                    ft.Icons.CALENDAR_MONTH_ROUNDED,
                    "Airing schedule",
                    lambda e: controller.open_schedule(),
                ),
                _action(
                    ft.Icons.SHUFFLE_ROUNDED,
                    "Surprise me",
                    lambda e: controller.open_random(),
                ),
            ]
        )
    actions.append(
        _action(
            ft.Icons.SEARCH_ROUNDED,
            "Search",
            lambda e: controller.open_search(),
            colour=ft.Colors.OUTLINE if blocked else None,
        )
    )

    return app_header(
        state,
        page,
        controller,
        extra_actions=actions,
    )


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
    of it — the scrim keeps the app's context visible). One shared builder
    with the detail screen's inline gate (components/offline_state)."""
    from components.offline_state import cf_gate_card

    return cf_gate_card(state, controller)


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


def _offline_banner(on_downloads=None) -> ft.Control:
    """Offline strip, shown above the header when the network is down.

    Deliberately distinct from the CF gate: offline means "nothing will
    load", the gate means "verify to continue" — the old build showed the
    SHIELD card for both.
    """
    row_controls: list[ft.Control] = [
        ft.Icon(
            ft.Icons.WIFI_OFF_ROUNDED,
            size=18,
            color=ft.Colors.ON_INVERSE_SURFACE,
        ),
        ft.Text(
            "You're offline — your downloaded episodes are available to watch.",
            size=12,
            color=ft.Colors.ON_INVERSE_SURFACE,
            expand=True,
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
        ),
    ]
    if on_downloads is not None:
        row_controls.append(
            ft.TextButton(
                content=ft.Text(
                    "View Downloads",
                    size=12,
                    color=AppColors.PRIMARY,
                    weight=ft.FontWeight.W_700,
                ),
                on_click=on_downloads,
            )
        )
    return ft.Container(
        content=ft.Row(
            row_controls,
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding.symmetric(horizontal=16, vertical=4),
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

    release_cards = [
        _release_card(
            r,
            controller.open_anime,
            now_playing["anime"] == r.anime_session and now_playing["episode"] == r.session,
            col=GRID_COL,
            mode=grid_mode,
            provider=state.latest_source or state.current_source_name,
        )
        for r in releases
    ]

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

    if not releases and not state.is_online:
        grid_section: list[ft.Control] = [
            empty_or_offline(
                state,
                title="You're offline",
                message="Check your connection, or continue in offline mode with your downloaded episodes.",
                icon=ft.Icons.CLOUD_OFF_ROUNDED,
                on_retry=lambda e: controller.load_latest(1),
                on_downloads=lambda e: controller.open_downloads(),
            )
        ]
    else:
        # The grid + its pager through the shared ad-break helper: a banner
        # every 12 cards, then one before the pager (KTV's shape).
        grid_section = [
            *grid_with_ads(release_cards, page),
            pager,
        ]

    continue_shelf = _continue_watching_row(
        state.continue_watching, controller.open_anime, grid_mode
    )
    content = ft.Container(
        content=ft.Column(
            [
                PromoHero(),
                # KTV's home order, ported: shelf → banner → grid. The
                # owner expects the ad AFTER Continue Watching (his KTV
                # home puts it after the Recently Watched carousel).
                continue_shelf or ft.Container(width=0, height=0),
                build_banner_ad(page, inline=True),
                ft.Text(
                    "Recent Episodes",
                    size=18,
                    weight=ft.FontWeight.W_700,
                    color=ft.Colors.ON_SURFACE,
                ),
                *grid_section,
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
            _home_header(state, page, controller),
            # The offline strip sits UNDER the header: above it, the strip
            # pushed the whole header down and the app read top-heavy
            # (independent audit, 2026-10-16).
            _offline_banner(lambda e: controller.open_downloads())
            if not state.is_online
            else ft.Container(width=0),
            content,
        ],
        spacing=0,
        expand=True,
        scroll=ft.ScrollMode.AUTO,
    )
