import flet as ft
from core.state import state, LatestRelease
from core.theme import AppColors


def build_home_view(
    page_obj: ft.Page,
    on_load_latest,
    on_select_anime,
    on_search_click,
    on_page_change: callable = None,
) -> ft.View:

    CARD_HEIGHT = 140

    latest_grid = ft.ResponsiveRow(
        spacing=16,
        run_spacing=16,
        margin=24,
    )



    def build_card(release: LatestRelease, idx: int):
        is_playing = (
            state.current_anime_session == release.anime_session
            and state.current_episode_session == release.session
        )

        play_icon = ft.Icon(
            ft.Icons.EQUALIZER_ROUNDED
            if is_playing
            else ft.Icons.PLAY_CIRCLE_FILL_ROUNDED,
            size=40,
            color=AppColors.PRIMARY if is_playing else ft.Colors.WHITE,
        )

        img = ft.Image(
            src=release.snapshot,
            fit="cover",
            expand=True,
        )

        gradient = ft.Container(
            gradient=ft.LinearGradient(
                begin=ft.Alignment.CENTER_LEFT,
                end=ft.Alignment.CENTER_RIGHT,
                colors=[
                    ft.Colors.with_opacity(0.8, ft.Colors.BLACK),
                    ft.Colors.TRANSPARENT,
                ],
            ),
            expand=True,
        )

        title_text = ft.Text(
            release.anime_title,
            color=ft.Colors.WHITE,
            weight=ft.FontWeight.BOLD,
            size=16,
            max_lines=2,
            overflow=ft.TextOverflow.ELLIPSIS,
        )

        ep_text = ft.Text(
            f"Episode {release.episode}",
            color=AppColors.PRIMARY,
            weight=ft.FontWeight.BOLD,
            size=12,
        )

        content = ft.Stack(
            controls=[
                img,
                gradient,
                ft.Container(
                    padding=16,
                    alignment=ft.Alignment.CENTER_LEFT,
                    content=ft.Column(
                        [title_text, ep_text],
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

        card_container = ft.Container(
            content=content,
            border=ft.Border.all(4, ft.Colors.TRANSPARENT),
            padding=4,
            border_radius=16,
            clip_behavior="antiAlias",
            bgcolor=AppColors.get_glass_bg(page_obj),
            animate_scale=300,
            animate=300,
            ink=True,
            height=CARD_HEIGHT,
            key=f"home_card_{idx}",
            on_click=lambda _: on_select_anime(release.anime_session),
        )
        card_container.tab_index = idx + 3

        wrapper = ft.Container(
            content=card_container,
            col={"xs": 12, "sm": 6, "md": 4, "lg": 4, "xl": 3},
        )
        return wrapper



    def load_page(page_num: int):
        state.is_loading = True
        state.latest_page = page_num
        update_grid()
        page_obj.update()
        page_obj.run_task(on_load_latest, page_num)

    def on_next_page(e):
        load_page(state.latest_page + 1)

    def on_prev_page(e):
        if state.latest_page > 1:
            load_page(state.latest_page - 1)

    def _style_focusable(control, focused):
        if focused:
            control.bgcolor = ft.Colors.with_opacity(0.1, AppColors.PRIMARY)
            control.border = ft.Border.all(2, AppColors.PRIMARY)
        else:
            control.bgcolor = None
            control.border = ft.Border.all(1.5, AppColors.PRIMARY)
        try:
            control.update()
        except Exception:
            pass

    def update_grid():
        latest_grid.controls.clear()
        for i, r in enumerate(state.latest_releases):
            latest_grid.controls.append(build_card(r, i))

        prev_btn = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(
                        ft.Icons.ARROW_BACK_IOS_NEW_ROUNDED,
                        color=ft.Colors.ON_SURFACE
                        if state.latest_page > 1
                        else ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    ft.Text(
                        "Previous",
                        color=ft.Colors.ON_SURFACE
                        if state.latest_page > 1
                        else ft.Colors.ON_SURFACE_VARIANT,
                    ),
                ],
                spacing=8,
            ),
            padding=ft.Padding(15, 10, 15, 10),
            border_radius=10,
            border=ft.Border.all(1.5, AppColors.PRIMARY),
            ink=True,
            on_click=on_prev_page if state.latest_page > 1 else None,
        )
        num_cards = len(state.latest_releases)
        prev_btn.tab_index = num_cards + 3
        prev_btn.on_focus = lambda e: _style_focusable(e.control, True)
        prev_btn.on_blur = lambda e: _style_focusable(e.control, False)

        next_btn = ft.Container(
            content=ft.Row(
                [
                    ft.Text(
                        "Next",
                        color=ft.Colors.ON_SURFACE
                        if state.latest_has_more
                        else ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    ft.Icon(
                        ft.Icons.ARROW_FORWARD_IOS_ROUNDED,
                        color=ft.Colors.ON_SURFACE
                        if state.latest_has_more
                        else ft.Colors.ON_SURFACE_VARIANT,
                    ),
                ],
                spacing=8,
            ),
            padding=ft.Padding(15, 10, 15, 10),
            border_radius=10,
            border=ft.Border.all(1.5, AppColors.PRIMARY),
            ink=True,
            on_click=on_next_page if state.latest_has_more else None,
        )
        next_btn.tab_index = num_cards + 4
        next_btn.on_focus = lambda e: _style_focusable(e.control, True)
        next_btn.on_blur = lambda e: _style_focusable(e.control, False)

        nav_row = ft.Row(
            controls=[
                prev_btn,
                ft.Text(
                    f"Page {state.latest_page}",
                    color=ft.Colors.ON_SURFACE,
                    weight=ft.FontWeight.W_500,
                ),
                next_btn,
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=16,
        )

        section_header = ft.Container(
            padding=ft.Padding.only(left=24, right=24, top=8, bottom=0),
            content=ft.Text(
                "Recent Episodes",
                size=20,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.ON_SURFACE,
            ),
        )

        if state.is_loading and not state.latest_releases:
            scroll_content.controls = [
                header,
                section_header,
                ft.Container(
                    expand=True,
                    alignment=ft.Alignment.CENTER,
                    content=ft.ProgressRing(color=AppColors.PRIMARY, stroke_width=4),
                ),
            ]
        else:
            scroll_content.controls = [header, section_header, latest_grid, nav_row]

        page_obj.update()

    def handle_theme_toggle(e):
        page_obj.theme_mode = (
            ft.ThemeMode.LIGHT
            if page_obj.theme_mode == ft.ThemeMode.DARK
            else ft.ThemeMode.DARK
        )
        page_obj.update()

    def _on_focus_btn(e):
        e.control.bgcolor = ft.Colors.with_opacity(0.1, AppColors.PRIMARY)
        try:
            e.control.update()
        except Exception:
            pass

    def _on_blur_btn(e):
        e.control.bgcolor = None
        try:
            e.control.update()
        except Exception:
            pass

    search_btn = ft.Container(
        content=ft.Icon(ft.Icons.SEARCH_ROUNDED, color=ft.Colors.ON_SURFACE),
        padding=10,
        border_radius=10,
        ink=True,
        on_click=lambda _: on_search_click(),
    )
    search_btn.tab_index = 1
    search_btn.on_focus = _on_focus_btn
    search_btn.on_blur = _on_blur_btn

    theme_btn = ft.Container(
        content=ft.Icon(
            ft.Icons.LIGHT_MODE_ROUNDED
            if page_obj.theme_mode == ft.ThemeMode.DARK
            else ft.Icons.DARK_MODE_ROUNDED,
            color=ft.Colors.ON_SURFACE,
        ),
        padding=10,
        border_radius=10,
        ink=True,
        on_click=handle_theme_toggle,
    )
    theme_btn.tab_index = 2
    theme_btn.on_focus = _on_focus_btn
    theme_btn.on_blur = _on_blur_btn

    header = ft.Container(
        padding=ft.Padding.only(left=24, right=24, top=24, bottom=8),
        content=ft.Row(
            controls=[
                ft.Row(
                    controls=[
                        ft.Image(src="icon.png", width=32, height=32, fit="contain"),
                        ft.Text("AnimePahe TV", size=24, weight=ft.FontWeight.BOLD),
                    ],
                    spacing=12,
                ),
                ft.Row(
                    controls=[search_btn, theme_btn],
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        ),
    )

    scroll_content = ft.Column(
        controls=[header, latest_grid],
        expand=False,
        spacing=0,
    )

    scrollable = ft.ListView(
        expand=True,
        controls=[scroll_content],
        padding=0,
        spacing=0,
        auto_scroll=True,
    )

    view = ft.View(
        route="/home",
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

    if not state.latest_releases and not state.is_loading:
        page_obj.run_task(on_load_latest)

    page_obj.update_home_grid = update_grid
    update_grid()

    return view
