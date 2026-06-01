import flet as ft
from core.theme import AppColors
from core.state import state, Anime


def build_anime_detail_view(
    page_obj: ft.Page,
    anime_session: str,
    on_load_episodes: callable,
    on_play: callable,
) -> ft.View:
    anime = next((a for a in state.search_results if a.session == anime_session), None)
    if not anime:
        lr = next(
            (a for a in state.latest_releases if a.anime_session == anime_session), None
        )
        if lr:
            anime = Anime(
                id=lr.anime_id,
                title=lr.anime_title,
                type="",
                episodes=0,
                status="",
                season="",
                year=0,
                score=0.0,
                poster=lr.snapshot,
                session=lr.anime_session,
            )

    def on_back(e):
        if len(page_obj.views) > 1:
            page_obj.views.pop()
            if page_obj.views:
                page_obj.route = page_obj.views[-1].route
            page_obj.update()

    bg_image_url = anime.poster if anime and anime.poster else ""

    bg_container = ft.Stack(
        expand=True,
        controls=[
            ft.Image(
                src=bg_image_url,
                fit="cover",
                expand=True,
                opacity=0.3,
            ),
            ft.Container(
                expand=True,
                bgcolor=ft.Colors.with_opacity(0.85, ft.Colors.SURFACE),
            ),
        ],
    )

    bg_overlay = ft.Container(expand=True, bgcolor=ft.Colors.TRANSPARENT)

    title_text = ft.Text(
        anime.title if anime else "Loading...",
        size=28,
        weight=ft.FontWeight.BOLD,
        color=ft.Colors.ON_SURFACE,
        max_lines=2,
        overflow=ft.TextOverflow.ELLIPSIS,
    )

    title_container = ft.Container(
        content=title_text,
        expand=True,
        size_change_interval=100,
        on_size_change=lambda e: (
            setattr(title_text, "size", max(14, min(36, int(e.width * 0.07))))
            or title_text.update()
        ),
    )

    info_text = ft.Text(
        "",
        size=14,
        color=ft.Colors.ON_SURFACE_VARIANT,
        weight=ft.FontWeight.W_500,
    )

    if anime:
        parts = []
        if anime.year:
            parts.append(str(anime.year))
        if anime.type:
            parts.append(anime.type)
        if anime.status:
            parts.append(anime.status)
        if anime.episodes:
            parts.append(f"{anime.episodes} Episodes")
        if anime.score:
            parts.append(f"\u2605 {anime.score:.1f}")
        info_text.value = " \u2022 ".join(parts)

    episode_grid = ft.ResponsiveRow(
        spacing=16,
        run_spacing=16,
    )

    loading_indicator = ft.Container(
        alignment=ft.Alignment.CENTER,
        content=ft.ProgressRing(color=AppColors.PRIMARY, stroke_width=4),
        visible=False,
    )

    prev_spinner = ft.ProgressRing(
        color=AppColors.PRIMARY, stroke_width=3, width=20, height=20, visible=False
    )
    next_spinner = ft.ProgressRing(
        color=AppColors.PRIMARY, stroke_width=3, width=20, height=20, visible=False
    )

    def _build_episode_card(ep, idx: int) -> ft.Container:
        is_playing = (
            state.current_anime_session == anime_session
            and state.current_episode_session == ep.session
        )

        play_icon = ft.Icon(
            ft.Icons.EQUALIZER_ROUNDED
            if is_playing
            else ft.Icons.PLAY_CIRCLE_FILL_ROUNDED,
            size=40,
            color=AppColors.PRIMARY if is_playing else ft.Colors.WHITE,
        )

        img = ft.Image(
            src=ep.snapshot if ep.snapshot else "",
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

        ep_text = ft.Text(
            f"Episode {ep.episode}",
            color=ft.Colors.WHITE,
            weight=ft.FontWeight.BOLD,
            size=16,
        )

        duration_text = ft.Text(
            ep.duration if ep.duration else "24m",
            color=ft.Colors.WHITE_70,
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
                        [ep_text, duration_text],
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
            aspect_ratio=1.67,
            key=f"ep_card_{idx}",
            on_click=lambda _, a=anime_session, es=ep.session: page_obj.run_task(
                on_play, a, es
            ),
        )
        card_container.tab_index = idx + 2

        wrapper = ft.Container(
            content=card_container,
            col={"xs": 12, "sm": 6, "md": 4, "lg": 4, "xl": 3},
        )
        return wrapper

    def on_next_ep_page(e):
        next_btn.disabled = True
        next_spinner.visible = True
        page_obj.update()
        state.is_loading = True
        state.episodes_page += 1
        page_obj.run_task(on_load_episodes, anime_session, state.episodes_page)

    def on_prev_ep_page(e):
        if state.episodes_page > 1:
            prev_btn.disabled = True
            prev_spinner.visible = True
            page_obj.update()
            state.is_loading = True
            state.episodes_page -= 1
            page_obj.run_task(on_load_episodes, anime_session, state.episodes_page)

    prev_btn = ft.Container(
        content=ft.Row(
            [
                ft.Icon(
                    ft.Icons.ARROW_BACK_IOS_NEW_ROUNDED,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.Text("Previous", color=ft.Colors.ON_SURFACE_VARIANT),
            ],
            spacing=8,
        ),
        padding=ft.Padding(15, 10, 15, 10),
        border_radius=10,
        border=ft.Border.all(1.5, AppColors.PRIMARY),
        ink=True,
        on_click=on_prev_ep_page,
    )
    prev_btn.tab_index = 2

    next_btn = ft.Container(
        content=ft.Row(
            [
                ft.Text("Next", color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Icon(
                    ft.Icons.ARROW_FORWARD_IOS_ROUNDED,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
            spacing=8,
        ),
        padding=ft.Padding(15, 10, 15, 10),
        border_radius=10,
        border=ft.Border.all(1.5, AppColors.PRIMARY),
        ink=True,
        on_click=on_next_ep_page,
    )
    next_btn.tab_index = 3

    def refresh_episodes():
        episode_grid.controls.clear()
        prev_spinner.visible = False
        next_spinner.visible = False
        if state.is_loading:
            loading_indicator.visible = True
        else:
            loading_indicator.visible = False
            for i, ep in enumerate(state.episodes):
                episode_grid.controls.append(_build_episode_card(ep, i))

        prev_btn.content = ft.Row(
            [
                ft.Icon(
                    ft.Icons.ARROW_BACK_IOS_NEW_ROUNDED,
                    color=ft.Colors.ON_SURFACE
                    if state.episodes_page > 1
                    else ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.Text(
                    "Previous",
                    color=ft.Colors.ON_SURFACE
                    if state.episodes_page > 1
                    else ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
            spacing=8,
        )
        prev_btn.disabled = state.episodes_page <= 1
        num_eps = len(state.episodes)
        prev_btn.tab_index = num_eps + 2

        next_btn.content = ft.Row(
            [
                ft.Text(
                    "Next",
                    color=ft.Colors.ON_SURFACE
                    if state.episodes_has_more
                    else ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.Icon(
                    ft.Icons.ARROW_FORWARD_IOS_ROUNDED,
                    color=ft.Colors.ON_SURFACE
                    if state.episodes_has_more
                    else ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
            spacing=8,
        )
        next_btn.disabled = not state.episodes_has_more
        next_btn.tab_index = num_eps + 3

        ep_nav = ft.Row(
            controls=[
                prev_btn,
                prev_spinner,
                ft.Text(
                    f"Page {state.episodes_page}",
                    color=ft.Colors.ON_SURFACE,
                    weight=ft.FontWeight.W_500,
                ),
                next_spinner,
                next_btn,
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=16,
        )

        episodes_section.controls = [
            episodes_header,
            episode_grid,
            ep_nav,
            loading_indicator,
        ]
        page_obj.update()

    page_obj.refresh_episodes = refresh_episodes

    poster = ft.Container(
        width=200,
        height=300,
        border_radius=16,
        shadow=ft.BoxShadow(
            spread_radius=2,
            blur_radius=20,
            color=ft.Colors.with_opacity(0.3, ft.Colors.BLACK),
            offset=ft.Offset(0, 10),
        ),
        content=(
            ft.Image(src=anime.poster, fit="cover", border_radius=16)
            if anime and anime.poster
            else ft.Container(
                content=ft.Icon(
                    ft.Icons.MOVIE_ROUNDED, size=64, color=ft.Colors.ON_SURFACE_VARIANT
                ),
                bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE),
                border_radius=16,
                alignment=ft.Alignment.CENTER,
            )
        ),
    )

    back_btn = ft.Container(
        content=ft.Icon(
            ft.Icons.ARROW_BACK_IOS_NEW_ROUNDED, color=ft.Colors.ON_SURFACE
        ),
        padding=10,
        border_radius=10,
        ink=True,
        on_click=on_back,
    )
    back_btn.tab_index = 1

    header = ft.Container(
        padding=ft.Padding.all(32),
        content=ft.Row(
            [
                poster,
                ft.Container(width=32),
                ft.Column(
                    expand=True,
                    controls=[
                        back_btn,
                        ft.Container(height=16),
                        title_container,
                        ft.Container(height=8),
                        info_text,
                    ],
                    alignment=ft.MainAxisAlignment.START,
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.START,
        ),
    )

    episodes_header = ft.Container(
        padding=ft.Padding.only(left=32, right=32, bottom=16),
        content=ft.Text(
            "Episodes",
            size=24,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.ON_SURFACE,
        ),
    )

    episodes_section = ft.Container(
        expand=False,
        padding=ft.Padding.only(left=32, right=32, bottom=32),
        content=ft.Column([episode_grid, loading_indicator], spacing=16),
    )

    scroll_content = ft.Column(
        [
            header,
            episodes_header,
            episodes_section,
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

    content = ft.Stack(
        [
            bg_container,
            bg_overlay,
            scrollable,
        ],
        expand=True,
    )

    view = ft.View(
        route=f"/anime?session={anime_session}",
        controls=[content],
        padding=0,
    )

    refresh_episodes()

    return view
