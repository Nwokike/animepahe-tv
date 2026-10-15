"""The one result card: poster, gradient, play/equalizer, title + year +
type + score, focus ring, D-pad reachable. Search and Discover share it —
the two grids can never drift apart.
"""

import flet as ft

from components.focus_styles import (
    attach_focus_zoom,
    card_button_style,
    card_focus_scale,
)
from core.theme import AppColors


def result_card(
    anime, on_select, col: dict | None = None, now_playing: bool = False
) -> ft.Control:
    poster = (
        ft.Image(
            src=anime.poster,
            fit=ft.BoxFit.COVER,
            expand=True,
            opacity=0.5 if now_playing else 1.0,
            error_content=ft.Container(
                content=ft.Icon(
                    ft.Icons.BROKEN_IMAGE_ROUNDED,
                    size=48,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                alignment=ft.Alignment.CENTER,
                bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE),
            ),
        )
        if anime.poster
        else ft.Container(
            content=ft.Icon(
                ft.Icons.MOVIE_ROUNDED, size=48, color=ft.Colors.ON_SURFACE_VARIANT
            ),
            alignment=ft.Alignment.CENTER,
            bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE),
        )
    )
    # score can be missing from the site payload — never format a None.
    score = anime.score if getattr(anime, "score", None) is not None else None
    score_color = AppColors.SUCCESS if (score or 0) >= 7.5 else AppColors.WARNING
    content = ft.Stack(
        [
            poster,
            ft.Container(
                gradient=ft.LinearGradient(
                    begin=ft.Alignment.TOP_CENTER,
                    end=ft.Alignment.BOTTOM_CENTER,
                    colors=[
                        ft.Colors.TRANSPARENT,
                        ft.Colors.with_opacity(0.85, ft.Colors.BLACK),
                    ],
                ),
                expand=True,
            ),
            ft.Container(
                alignment=ft.Alignment.CENTER,
                content=ft.Icon(
                    ft.Icons.EQUALIZER_ROUNDED
                    if now_playing
                    else ft.Icons.PLAY_CIRCLE_FILL_ROUNDED,
                    size=48,
                    color=AppColors.PRIMARY if now_playing else ft.Colors.WHITE,
                ),
            ),
            ft.Container(
                alignment=ft.Alignment.BOTTOM_LEFT,
                padding=12,
                content=ft.Column(
                    [
                        ft.Text(
                            anime.title,
                            size=14,
                            weight=ft.FontWeight.BOLD,
                            color=ft.Colors.WHITE,
                            max_lines=2,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        ft.Row(
                            [
                                ft.Text(
                                    str(anime.year or "—"),
                                    size=12,
                                    color=ft.Colors.with_opacity(0.7, ft.Colors.WHITE),
                                ),
                                ft.Container(expand=True),
                                ft.Text(
                                    anime.type or "",
                                    size=12,
                                    color=ft.Colors.with_opacity(0.7, ft.Colors.WHITE),
                                ),
                                ft.Container(width=4),
                                ft.Text(
                                    f"★ {score:.1f}" if score is not None else "★ —",
                                    size=12,
                                    weight=ft.FontWeight.BOLD,
                                    color=score_color,
                                ),
                            ],
                            spacing=4,
                        ),
                    ],
                    spacing=4,
                ),
            ),
        ],
        expand=True,
    )
    # Flat FilledButton (not a Container) — only the Button family takes
    # on_focus/on_blur and per-state sides in flet 1.0.4, so only it can
    # show a focus ring and be reached by a D-pad on TV.
    return attach_focus_zoom(
        ft.FilledButton(
            content=ft.Container(
                content=content,
                border_radius=12,
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                aspect_ratio=0.67,
            ),
            style=card_button_style(padding=4, radius=16),
            animate_scale=card_focus_scale(),
            col=col,
            # The session STRING, not the Anime object: open_anime/load_anime
            # compare it against release/anime sessions and hash it into a
            # dict lookup — passing the dataclass broke detail from search.
            on_click=lambda e: on_select(anime.session),
        )
    )
