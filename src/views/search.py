import flet as ft
from core.theme import AppColors
from core.state import state


def build_search_view(
    page_obj: ft.Page,
    on_search: callable,
    on_select_anime: callable,
    on_back: callable,
) -> ft.View:

    CARD_HEIGHT = 240

    search_field = ft.TextField(
        hint_text="Search for anime...",
        color=ft.Colors.ON_SURFACE,
        bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.ON_SURFACE),
        border_color=ft.Colors.TRANSPARENT,
        border_radius=16,
        prefix_icon=ft.Icons.SEARCH_ROUNDED,
        content_padding=20,
        text_size=16,
        on_submit=lambda e: page_obj.run_task(on_search, e.data.strip()),
        focused_border_color=AppColors.PRIMARY,
        focused_bgcolor=ft.Colors.with_opacity(0.1, AppColors.PRIMARY),
    )

    results_grid = ft.ResponsiveRow(
        spacing=16,
        run_spacing=16,
    )





    def _build_card(anime, idx: int):
        is_playing = state.current_anime_session == anime.session

        img = ft.Image(
            src=anime.poster if anime.poster else "",
            fit="cover",
            expand=True,
            opacity=0.5 if is_playing else 1.0,
        )
        if not anime.poster:
            img = ft.Container(
                content=ft.Icon(
                    ft.Icons.MOVIE_ROUNDED, size=48, color=ft.Colors.ON_SURFACE_VARIANT
                ),
                expand=True,
                bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE),
                alignment=ft.Alignment.CENTER,
            )

        gradient = ft.Container(
            gradient=ft.LinearGradient(
                begin=ft.Alignment.TOP_CENTER,
                end=ft.Alignment.BOTTOM_CENTER,
                colors=[
                    ft.Colors.TRANSPARENT,
                    ft.Colors.with_opacity(0.85, ft.Colors.BLACK),
                ],
            ),
            expand=True,
        )

        title_text = ft.Text(
            anime.title,
            color=ft.Colors.WHITE,
            weight=ft.FontWeight.BOLD,
            size=14,
            max_lines=2,
            overflow=ft.TextOverflow.ELLIPSIS,
        )

        year_text = ft.Text(
            str(anime.year) if anime.year else "",
            size=12,
            color=ft.Colors.WHITE_70,
        )

        type_text = ft.Text(
            anime.type if anime.type else "",
            size=12,
            color=ft.Colors.WHITE_70,
        )

        score_text = ft.Text(
            f"\u2605 {anime.score:.1f}" if anime.score else "",
            size=12,
            weight=ft.FontWeight.BOLD,
            color=AppColors.SUCCESS if anime.score >= 7.5 else AppColors.WARNING,
        )

        play_badge = ft.Container(
            alignment=ft.Alignment.CENTER,
            content=ft.Icon(
                ft.Icons.PLAY_CIRCLE_FILL_ROUNDED
                if not is_playing
                else ft.Icons.EQUALIZER_ROUNDED,
                size=48,
                color=AppColors.PRIMARY if is_playing else ft.Colors.WHITE,
            ),
        )

        content_stack = ft.Stack(
            controls=[
                img,
                gradient,
                play_badge,
                ft.Container(
                    padding=12,
                    alignment=ft.Alignment.BOTTOM_LEFT,
                    content=ft.Column(
                        [
                            title_text,
                            ft.Row(
                                [
                                    year_text,
                                    ft.Container(expand=True),
                                    type_text,
                                    ft.Container(width=4),
                                    score_text,
                                ],
                                spacing=4,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.END,
                        spacing=4,
                    ),
                ),
            ],
            expand=True,
        )

        card_inner = ft.Container(
            content=content_stack,
            border_radius=12,
            clip_behavior="antiAlias",
            height=CARD_HEIGHT,
        )

        card_container = ft.Container(
            content=card_inner,
            border=ft.Border.all(4, ft.Colors.TRANSPARENT),
            padding=4,
            border_radius=16,
            animate_scale=300,
            animate=300,
            ink=True,
            key=f"search_card_{idx}",
            on_click=lambda _: on_select_anime(anime),
        )
        card_container.tab_index = idx + 2

        wrapper = ft.Container(
            content=card_container,
            padding=4,
            col={"xs": 6, "sm": 4, "md": 3, "lg": 2, "xl": 2},
        )
        return wrapper

    def refresh_results():
        results_grid.controls.clear()
        if state.is_loading:
            loading_indicator.visible = True
            empty_state.visible = False
            results_grid.visible = False
        elif not state.search_results:
            loading_indicator.visible = False
            empty_state.visible = True
            results_grid.visible = False
            if state.search_query:
                empty_state.content.controls[
                    1
                ].value = f"No results found for '{state.search_query}'"
            else:
                empty_state.content.controls[
                    1
                ].value = "Search for an anime to get started."
        else:
            loading_indicator.visible = False
            empty_state.visible = False
            results_grid.visible = True
            for i, anime in enumerate(state.search_results):
                results_grid.controls.append(_build_card(anime, i))
        page_obj.update()

    page_obj.refresh_search_results = refresh_results

    loading_indicator = ft.Container(
        alignment=ft.Alignment.CENTER,
        content=ft.ProgressRing(color=AppColors.PRIMARY, stroke_width=4),
        visible=False,
    )

    empty_state = ft.Container(
        expand=True,
        alignment=ft.Alignment.CENTER,
        content=ft.Column(
            [
                ft.Icon(
                    ft.Icons.SEARCH_OFF_ROUNDED,
                    size=64,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.Text(
                    "Search for an anime to get started.",
                    size=16,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=16,
        ),
    )

    back_btn = ft.Container(
        content=ft.Icon(
            ft.Icons.ARROW_BACK_IOS_NEW_ROUNDED, color=ft.Colors.ON_SURFACE
        ),
        padding=10,
        border_radius=10,
        ink=True,
        on_click=lambda _: on_back(),
    )
    back_btn.tab_index = 1

    header = ft.Container(
        padding=ft.Padding.only(left=24, right=24, top=24, bottom=16),
        content=ft.Column(
            [
                ft.Row(
                    [
                        back_btn,
                        ft.Container(
                            width=36,
                            height=36,
                            border_radius=10,
                            alignment=ft.Alignment.CENTER,
                            content=ft.Image(
                                src="icon.png", width=24, height=24, fit="contain"
                            ),
                        ),
                        ft.Text("Search", size=24, weight=ft.FontWeight.BOLD),
                    ],
                    spacing=12,
                ),
                ft.Container(height=8),
                search_field,
            ],
            spacing=0,
        ),
    )

    grid_area = ft.Container(
        expand=True,
        padding=ft.Padding.only(left=24, right=24, bottom=24),
        content=ft.Stack(
            [results_grid, loading_indicator, empty_state],
            expand=True,
        ),
    )

    scroll_content = ft.Column(
        [
            header,
            grid_area,
        ],
        spacing=0,
        expand=False,
    )

    scrollable = ft.ListView(
        expand=True,
        controls=[scroll_content],
        padding=0,
        spacing=0,
        auto_scroll=True,
    )

    view = ft.View(
        route="/search",
        controls=[
            ft.SafeArea(
                ft.Container(
                    content=scrollable,
                    expand=True,
                    bgcolor=ft.Colors.SURFACE,
                ),
                expand=True,
            )
        ],
        padding=0,
    )

    refresh_results()

    return view
