"""Search — submit-driven, debounced suggestions, paginated results.

Input follows the Sherlock pattern: typing updates local state only, and
Enter/submit fires the search. Debounce lives where it belongs — filtering
the recent-search suggestions, never the network call. Portrait cards keep
the original craft: top-to-bottom gradient, centre play icon, bottom-left
title/year/type/score, 4px border reserve for the focus ring.
"""

import flet as ft

from components.banner_ad import build_banner_ad
from components.focus_styles import (
    attach_focus_zoom,
    card_button_style,
    card_focus_scale,
)
from core.theme import AppColors
from hooks.use_debounce import use_debounce
from state.app_state import AppStateCtx
from state.controller_ctx import ControllerMethodsCtx


def _result_card(anime, on_select, col: dict | None = None) -> ft.Control:
    poster = (
        ft.Image(src=anime.poster, fit=ft.BoxFit.COVER, expand=True, opacity=0.6)
        if anime.poster
        else ft.Container(
            content=ft.Icon(
                ft.Icons.MOVIE_ROUNDED, size=48, color=AppColors.DARK_TEXT_DIM
            ),
            alignment=ft.Alignment.CENTER,
            bgcolor=ft.Colors.with_opacity(0.1, AppColors.DARK_TEXT),
        )
    )
    score_color = AppColors.SUCCESS if anime.score >= 7.5 else AppColors.WARNING
    content = ft.Stack(
        [
            poster,
            ft.Container(
                gradient=ft.LinearGradient(
                    begin=ft.Alignment.TOP_CENTER,
                    end=ft.Alignment.BOTTOM_CENTER,
                    colors=[ft.Colors.TRANSPARENT, ft.Colors.with_opacity(0.85, ft.Colors.BLACK)],
                ),
                expand=True,
            ),
            ft.Container(
                alignment=ft.Alignment.CENTER,
                content=ft.Icon(
                    ft.Icons.PLAY_CIRCLE_FILL_ROUNDED, size=48, color=ft.Colors.WHITE
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
                                    str(anime.year),
                                    size=12,
                                    color=ft.Colors.with_opacity(0.7, ft.Colors.WHITE),
                                ),
                                ft.Container(expand=True),
                                ft.Text(
                                    anime.type,
                                    size=12,
                                    color=ft.Colors.with_opacity(0.7, ft.Colors.WHITE),
                                ),
                                ft.Container(width=4),
                                ft.Text(
                                    f"★ {anime.score:.1f}",
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
            on_click=lambda e: on_select(anime),
        )
    )


@ft.component
def SearchScreen() -> ft.Control:
    state = ft.use_context(AppStateCtx)
    controller = ft.use_context(ControllerMethodsCtx)
    _ = state.search_version

    from flet import context as flet_context

    try:
        page = flet_context.page
    except Exception:
        page = None
    _ = state.search_query

    query, set_query = ft.use_state("")
    debounced_query = use_debounce(query, 250)

    def _submit(e=None):
        q = query.strip()
        if q:
            controller.load_search(q, 1)

    def _pick(q: str):
        set_query(q)
        controller.load_search(q, 1)

    # Suggestions: recent history filtered by what has been typed (debounced).
    history = state.search_history or []
    needle = (debounced_query or "").strip().lower()
    suggestions = [h for h in history if needle in h.lower()] if needle else history[:8]

    field = ft.TextField(
        hint_text="Search anime...",
        border_radius=16,
        bgcolor=ft.Colors.with_opacity(0.05, AppColors.DARK_TEXT),
        border_color=ft.Colors.TRANSPARENT,
        focused_border_color=AppColors.PRIMARY,
        focused_bgcolor=ft.Colors.with_opacity(0.1, AppColors.PRIMARY),
        prefix_icon=ft.Icons.SEARCH_ROUNDED,
        content_padding=16,
        text_size=16,
        value=query,
        on_submit=_submit,
        on_change=lambda e: set_query(e.control.value),
    )

    header = ft.Row(
        [
            ft.Container(content=field, expand=True),
            ft.FilledButton(
                content="Search",
                on_click=_submit,
                style=ft.ButtonStyle(bgcolor=AppColors.PRIMARY, color=ft.Colors.WHITE),
            ),
        ],
        spacing=8,
    )

    suggestion_rows = ft.Column(
        controls=[
            ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(ft.Icons.HISTORY_ROUNDED, size=18, color=AppColors.DARK_TEXT_DIM),
                        ft.Container(width=8),
                        ft.Text(q, size=13, color=AppColors.DARK_TEXT, expand=True),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.Padding.symmetric(horizontal=12, vertical=10),
                border_radius=8,
                ink=True,
                on_click=lambda e, q=q: _pick(q),
            )
            for q in suggestions
        ],
        spacing=2,
        visible=bool(suggestions) and not state.search_results,
    )

    clear_btn = (
        ft.TextButton(content="Clear recent", on_click=lambda e: controller.clear_search_history())
        if history
        else ft.Container(width=0, height=0)
    )

    if state.is_loading and not state.search_results:
        results = ft.Container(
            content=ft.ProgressRing(color=AppColors.PRIMARY),
            alignment=ft.Alignment.CENTER,
            expand=True,
        )
    elif state.search_error:
        results = ft.Container(
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.CLOUD_OFF_ROUNDED, size=56, color=AppColors.ERROR),
                    ft.Text("Search failed", size=16, weight=ft.FontWeight.W_600, color=AppColors.DARK_TEXT),
                    ft.Text(state.search_error, size=12, color=AppColors.DARK_TEXT_DIM),
                    ft.OutlinedButton(content="Retry", on_click=_submit),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=10,
            ),
            alignment=ft.Alignment.CENTER,
            expand=True,
        )
    elif state.search_results:
        pager = ft.Row(
            [
                ft.OutlinedButton(
                    content="Prev",
                    on_click=lambda e: controller.load_search(state.search_query, state.search_page - 1),
                    disabled=state.search_page <= 1,
                ),
                ft.Text(f"Page {state.search_page}", size=13, color=AppColors.DARK_TEXT_DIM),
                ft.OutlinedButton(
                    content="Next",
                    on_click=lambda e: controller.load_search(state.search_query, state.search_page + 1),
                    disabled=not state.search_has_more,
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=16,
        )
        results = ft.Column(
            [
                ft.ResponsiveRow(
                    controls=[
                        _result_card(
                            a,
                            controller.open_anime,
                            col={"xs": 6, "sm": 4, "md": 3, "lg": 2, "xl": 2},
                        )
                        for a in state.search_results
                    ],
                    spacing=12,
                    run_spacing=12,
                ),
                build_banner_ad(page, inline=True),
                pager,
            ],
            spacing=16,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )
    elif state.search_query:
        results = ft.Container(
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.SEARCH_OFF_ROUNDED, size=56, color=AppColors.DARK_TEXT_DIM),
                    ft.Text(
                        f"No results found for '{state.search_query}'",
                        size=15,
                        color=AppColors.DARK_TEXT_DIM,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=12,
            ),
            alignment=ft.Alignment.CENTER,
            expand=True,
        )
    else:
        results = ft.Container(
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.SEARCH_ROUNDED, size=56, color=AppColors.DARK_TEXT_DIM),
                    ft.Text(
                        "Search for anime to get started",
                        size=15,
                        color=AppColors.DARK_TEXT_DIM,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=12,
            ),
            alignment=ft.Alignment.CENTER,
            expand=True,
        )

    return ft.Column(
        [
            header,
            ft.Row([ft.Container(expand=True), clear_btn], spacing=8),
            suggestion_rows,
            ft.Container(content=results, expand=True),
        ],
        spacing=8,
        expand=True,
        padding=ft.Padding.only(left=16, right=16, top=16, bottom=8),
    )
