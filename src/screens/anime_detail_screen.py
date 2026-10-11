"""Anime detail — backdrop, poster, metadata, episode grid.

Craft carried from the original view: the blurred-poster backdrop (poster at
30% + surface wash), 200x300 poster with shadow, responsive title, bullet
metadata row, and 1.67 episode cards with the focus-ring border reserve.

Data comes from the controller (Phase 1). Phase 2 makes this screen fetch
its own anime by session — today it reads state.episodes like the old view.
"""

import flet as ft

from components.banner_ad import build_banner_ad
from components.empty_state import EmptyState
from components.focus_styles import (
    attach_focus_zoom,
    card_button_style,
    card_focus_scale,
)
from components.pagination import pager as ft_pager
from components.focus_styles import attach_focus_zoom, card_button_style, card_focus_scale
from core.theme import AppColors
from state.app_state import AppStateCtx
from state.controller_ctx import ControllerMethodsCtx


def _episode_card(
    ep,
    on_play,
    anime_session: str,
    now_playing: bool,
    state_glyph=None,
    menu_items=None,
) -> ft.Control:
    image = (
        ft.Image(src=ep.snapshot, fit=ft.BoxFit.COVER, expand=True)
        if ep.snapshot
        else ft.Container(bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH)
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
                        ft.Row(
                            [
                                ft.Text(
                                    f"Episode {ep.episode}",
                                    color=ft.Colors.WHITE,
                                    weight=ft.FontWeight.BOLD,
                                    size=16,
                                ),
                                ft.Container(width=6),
                                ft.Container(
                                    content=ft.Text(
                                        "Filler",
                                        size=9,
                                        weight=ft.FontWeight.W_700,
                                        color=AppColors.WARNING,
                                    ),
                                    padding=ft.Padding.symmetric(horizontal=5, vertical=1),
                                    border_radius=4,
                                    border=ft.Border.all(
                                        1, ft.Colors.with_opacity(0.4, AppColors.WARNING)
                                    ),
                                    visible=bool(ep.filler),
                                ),
                            ],
                            spacing=4,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Text(
                            ep.duration or "24m",
                            size=12,
                            color=ft.Colors.with_opacity(0.7, ft.Colors.WHITE),
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=4,
                ),
            ),
            ft.Container(
                alignment=ft.Alignment.CENTER_RIGHT,
                padding=16,
                content=ft.Row(
                    [
                        state_glyph or ft.Container(width=0),
                        ft.Icon(
                            ft.Icons.EQUALIZER_ROUNDED
                            if now_playing
                            else ft.Icons.PLAY_CIRCLE_FILL_ROUNDED,
                            size=40,
                            color=AppColors.PRIMARY if now_playing else ft.Colors.WHITE,
                        ),
                        # Compact three-dot overflow (the KTV full-dialog
                        # treatment was rejected): items are built per
                        # episode state, so the menu never shows an action
                        # the current state can't honour.
                        ft.PopupMenuButton(
                            icon=ft.Icons.MORE_VERT_ROUNDED,
                            icon_size=20,
                            icon_color=ft.Colors.WHITE,
                            menu_position=ft.PopupMenuPosition.UNDER,
                            tooltip="Episode options",
                            items=menu_items
                            or [
                                ft.PopupMenuItem(
                                    content="Play",
                                    icon=ft.Icons.PLAY_CIRCLE_FILL_ROUNDED,
                                    height=40,
                                    on_click=lambda e: on_play(
                                        anime_session, ep.session
                                    ),
                                )
                            ],
                        ),
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ),
        ],
        expand=True,
    )
    # Flat FilledButton so the D-pad can focus the episode (Container cards
    # are unreachable on TV in flet 1.0.4); the FOCUSED side + scale are
    # the focus ring.
    return attach_focus_zoom(
        ft.FilledButton(
            content=content,
            style=card_button_style(radius=16),
            aspect_ratio=1.67,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            animate_scale=card_focus_scale(),
            on_click=lambda e: on_play(anime_session, ep.session),
        )
    )


@ft.component
def AnimeDetailScreen() -> ft.Control:
    state = ft.use_context(AppStateCtx)
    controller = ft.use_context(ControllerMethodsCtx)
    _ = state.episodes_version
    _ = state.busy_version  # download-start spinners, quality resolving

    from flet import context as flet_context

    try:
        page = flet_context.page
    except Exception:
        page = None

    anime_session = state.current_anime_session
    episodes = state.episodes

    # Title/poster come from the controller's resolution chain (in-memory
    # → Continue Watching store → nothing for a cold link). Phase 3 adds a
    # metadata endpoint that removes the last fallback.
    anime = state.selected_anime or {}
    title = anime.get("title") or "Loading..."
    poster = anime.get("poster")

    if not episodes and state.is_loading:
        return ft.Container(
            content=ft.ProgressRing(color=AppColors.PRIMARY),
            alignment=ft.Alignment.CENTER,
            expand=True,
        )

    if not episodes:
        return EmptyState(
            "No episodes found",
            message="This series may have no releases yet — try again later.",
            icon=ft.Icons.MOVIE_FILTER_ROUNDED,
        )

    backdrop = ft.Stack(
        [
            ft.Image(src=poster, fit=ft.BoxFit.COVER, expand=True, opacity=0.3)
            if poster
            else ft.Container(bgcolor=ft.Colors.SURFACE),
            ft.Container(
                expand=True,
                bgcolor=ft.Colors.with_opacity(0.85, ft.Colors.SURFACE),
            ),
        ],
        expand=True,
    )

    poster_box = ft.Container(
        width=200,
        height=300,
        border_radius=16,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        shadow=ft.BoxShadow(
            spread_radius=2,
            blur_radius=20,
            color=ft.Colors.with_opacity(0.3, ft.Colors.BLACK),
            offset=ft.Offset(0, 10),
        ),
        content=ft.Image(src=poster, fit=ft.BoxFit.COVER, expand=True)
        if poster
        else ft.Container(
            content=ft.Icon(ft.Icons.MOVIE_ROUNDED, size=64, color=ft.Colors.ON_SURFACE_VARIANT),
            alignment=ft.Alignment.CENTER,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
        ),
    )

    now_playing = {
        "anime": state.current_anime_session,
        "episode": state.current_episode_session,
    }
    downloads = state.downloads or {}
    download_progress = state.download_progress or {}

    def _episode_state(ep) -> tuple[object, list]:
        """(trailing state control, overflow menu items) for one episode.

        Download moved out from under the card and into a compact three-dot
        menu carried inside the row — one tap for play, one for everything
        else. The trailing slot only ever shows a *passive* state glyph
        (done check, or a spinner while a job is starting/running), never a
        second tappable button.
        """
        row = downloads.get(ep.session) or {}
        active = ep.session in download_progress
        starting = ep.session in state.starting_downloads
        done = row.get("state") == "complete"

        trailing: object = ft.Container(width=0)
        if done:
            trailing = ft.Icon(
                ft.Icons.DOWNLOAD_DONE_ROUNDED,
                size=18,
                color=AppColors.SUCCESS,
            )
        elif starting or active:
            # Source + kwik resolve before the job starts — spin instead of
            # looking like the tap did nothing.
            trailing = ft.ProgressRing(width=16, height=16, stroke_width=2)

        items = [
            ft.PopupMenuItem(
                content="Play",
                icon=ft.Icons.PLAY_CIRCLE_FILL_ROUNDED,
                height=40,
                on_click=lambda e, s=ep.session: controller.play_episode(
                    anime_session, s
                ),
            ),
        ]
        if done:
            items.append(
                ft.PopupMenuItem(
                    content="Play offline",
                    icon=ft.Icons.DOWNLOAD_DONE_ROUNDED,
                    height=40,
                    on_click=lambda e, s=ep.session: controller.play_downloaded(s),
                )
            )
            items.append(
                ft.PopupMenuItem(
                    content="Delete download",
                    icon=ft.Icons.DELETE_OUTLINE_ROUNDED,
                    height=40,
                    on_click=lambda e, s=ep.session: controller.delete_download(s),
                )
            )
        elif active or starting:
            items.append(
                ft.PopupMenuItem(
                    content="Cancel download",
                    icon=ft.Icons.CLOSE_ROUNDED,
                    height=40,
                    on_click=lambda e, s=ep.session: controller.cancel_download(s),
                )
            )
        else:
            items.append(
                ft.PopupMenuItem(
                    content="Download",
                    icon=ft.Icons.DOWNLOAD_ROUNDED,
                    height=40,
                    on_click=lambda e, s=ep.session: controller.download_episode(
                        anime_session, s
                    ),
                )
            )
        return trailing, items

    grid = ft.ResponsiveRow(
        controls=[
            ft.Container(
                content=_episode_card(
                    ep,
                    controller.play_episode,
                    anime_session,
                    now_playing["anime"] == anime_session
                    and now_playing["episode"] == ep.session,
                    state_glyph=_episode_state(ep)[0],
                    menu_items=_episode_state(ep)[1],
                ),
                col={"xs": 12, "sm": 6, "md": 4, "lg": 4, "xl": 3},
            )
            for ep in episodes
        ],
        spacing=12,
        run_spacing=12,
    )

    pager = ft_pager(
        page=state.episodes_page,
        has_more=state.episodes_has_more,
        on_prev=lambda e: controller.load_episodes(
            anime_session, state.episodes_page - 1
        ),
        on_next=lambda e: controller.load_episodes(
            anime_session, state.episodes_page + 1
        ),
        is_loading=state.is_loading,
    )

    # Favorites are per-ANIME, never per episode: one button in the header.
    _ = state.favorites_version
    favorited = anime_session in (state.favorites or {})

    def _toggle_favorite():
        controller.toggle_favorite(
            {
                "anime_session": anime_session,
                "title": title,
                "poster": poster or "",
                "type": anime.get("type", ""),
                "year": anime.get("year", 0),
                "status": anime.get("status", ""),
                "score": anime.get("score", 0),
            }
        )

    favorite_button = attach_focus_zoom(
        ft.FilledButton(
            content=ft.Text("Favorited" if favorited else "Favorite"),
            icon=ft.Icons.FAVORITE_ROUNDED
            if favorited
            else ft.Icons.FAVORITE_BORDER_ROUNDED,
            style=ft.ButtonStyle(
                bgcolor=AppColors.PRIMARY
                if favorited
                else ft.Colors.TRANSPARENT,
                color=ft.Colors.WHITE if favorited else ft.Colors.ON_SURFACE,
                shape=ft.RoundedRectangleBorder(radius=10),
                side=ft.BorderSide(1 if not favorited else 0, AppColors.PRIMARY),
            ),
            on_click=lambda e: _toggle_favorite(),
        )
    )

    def _metadata_row(anime: dict) -> ft.Control:
        """year / type / status / N Episodes / score, as the original."""
        parts = []
        if anime.get("year"):
            parts.append(str(anime["year"]))
        if anime.get("type"):
            parts.append(anime["type"])
        if anime.get("status"):
            parts.append(anime["status"])
        if anime.get("episodes"):
            parts.append(f"{anime['episodes']} Episodes")
        if anime.get("score"):
            parts.append(f"★ {float(anime['score']):.1f}")
        if not parts:
            return ft.Container(width=0, height=0)
        return ft.Text(
            " • ".join(parts),
            size=14,
            weight=ft.FontWeight.W_500,
            color=ft.Colors.ON_SURFACE_VARIANT,
        )

    return ft.Stack(
        [
            backdrop,
            ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                poster_box,
                                ft.Container(width=24),
                                ft.Column(
                                    [
                                        ft.Text(
                                            title,
                                            size=28,
                                            weight=ft.FontWeight.BOLD,
                                            color=ft.Colors.ON_SURFACE,
                                            max_lines=2,
                                            overflow=ft.TextOverflow.ELLIPSIS,
                                        ),
                                        ft.Container(height=8),
                                        _metadata_row(anime),
                                        ft.Container(height=12),
                                        favorite_button,
                                    ],
                                    expand=True,
                                    alignment=ft.MainAxisAlignment.CENTER,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.START,
                        ),
                        ft.Container(height=24),
                        ft.Row(
                            [
                                ft.Text(
                                    "Episodes",
                                    size=20,
                                    weight=ft.FontWeight.W_700,
                                    color=ft.Colors.ON_SURFACE,
                                ),
                                ft.Container(expand=True),
                                # Which provider served these episodes, and
                                # one-tap failover when this source misses.
                                ft.Text(
                                    f"Source: {state.current_source_name.capitalize()}"
                                    if state.current_source_name
                                    else "",
                                    size=12,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                                ft.TextButton(
                                    content="Try another source",
                                    on_click=lambda e: controller.try_another_source(
                                        anime_session
                                    ),
                                ),
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Container(height=8),
                        grid,
                        build_banner_ad(page, inline=True),
                        pager,
                        ft.Container(height=32),
                    ],
                    spacing=0,
                    scroll=ft.ScrollMode.AUTO,
                    expand=True,
                ),
                padding=ft.Padding.all(24),
                expand=True,
            ),
        ],
        expand=True,
    )
