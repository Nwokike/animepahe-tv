import flet as ft
import asyncio
from core.state import state, LatestRelease
from core.theme import AppColors
from core.config import WORKER_BASE_URL
from core.constants import APP_NAME, APP_VERSION, LBL_PREVIOUS, LBL_NEXT, LBL_PAGE


def build_home_view(
    page_obj: ft.Page,
    on_load_latest,
    on_select_anime,
    on_search_click,
    on_page_change: callable = None,
) -> ft.View:

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
            aspect_ratio=1.67,
            key=f"home_card_{idx}",
            on_click=lambda _: on_select_anime(release.anime_session),
        )
        card_container.tab_index = idx + 3

        wrapper = ft.Container(
            content=card_container,
            col={"xs": 12, "sm": 6, "md": 4, "lg": 4, "xl": 3},
        )
        return wrapper

    loading_spinner = ft.ProgressRing(
        color=AppColors.PRIMARY, stroke_width=3, width=20, height=20, visible=False
    )

    def load_page(page_num: int):
        state.is_loading = True
        state.latest_page = page_num
        update_grid()
        page_obj.update()
        page_obj.run_task(on_load_latest, page_num)

    def on_next_page(e):
        next_btn.disabled = True
        loading_spinner.visible = True
        page_obj.update()
        load_page(state.latest_page + 1)

    def on_prev_page(e):
        if state.latest_page > 1:
            prev_btn.disabled = True
            loading_spinner.visible = True
            page_obj.update()
            load_page(state.latest_page - 1)

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
        on_click=on_prev_page,
    )
    prev_btn.tab_index = 3

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
        on_click=on_next_page,
    )
    next_btn.tab_index = 4

    def update_grid():
        latest_grid.controls.clear()
        for i, r in enumerate(state.latest_releases):
            latest_grid.controls.append(build_card(r, i))

        prev_btn.content = ft.Row(
            [
                ft.Icon(
                    ft.Icons.ARROW_BACK_IOS_NEW_ROUNDED,
                    color=ft.Colors.ON_SURFACE
                    if state.latest_page > 1
                    else ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.Text(
                    LBL_PREVIOUS,
                    color=ft.Colors.ON_SURFACE
                    if state.latest_page > 1
                    else ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
            spacing=8,
        )
        prev_btn.disabled = state.latest_page <= 1
        num_cards = len(state.latest_releases)
        prev_btn.tab_index = num_cards + 3

        next_btn.content = ft.Row(
            [
                ft.Text(
                    LBL_NEXT,
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
        )
        next_btn.disabled = not state.latest_has_more
        next_btn.tab_index = num_cards + 4

        nav_row = ft.Row(
            controls=[
                prev_btn,
                loading_spinner,
                ft.Text(
                    f"{LBL_PAGE} {state.latest_page}",
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

    search_btn = ft.Container(
        content=ft.Icon(ft.Icons.SEARCH_ROUNDED, color=ft.Colors.ON_SURFACE),
        padding=10,
        border_radius=10,
        ink=True,
        on_click=lambda _: on_search_click(),
    )
    search_btn.tab_index = 1

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

    def _update_version_btn(update_data):
        version_btn.content = ft.Row(
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
        )
        version_btn.bgcolor = ft.Colors.with_opacity(0.15, AppColors.PRIMARY)
        version_btn.border = ft.Border.all(1.5, AppColors.PRIMARY)
        version_btn.on_click = lambda e: (
            page_obj._show_update_dialog(update_data)
            if hasattr(page_obj, "_show_update_dialog")
            else None
        )
        version_btn.update()

    page_obj.on_update_found = _update_version_btn

    version_btn = ft.Container(
        content=ft.Text(
            f"v{APP_VERSION}",
            size=11,
            color=ft.Colors.ON_SURFACE_VARIANT,
        ),
        padding=ft.Padding(8, 6, 8, 6),
        border_radius=6,
        border=ft.Border.all(
            1, ft.Colors.with_opacity(0.2, ft.Colors.ON_SURFACE_VARIANT)
        ),
        ink=True,
        on_click=lambda e: (
            page_obj._show_update_dialog(state.update_data)
            if state.update_available
            and state.update_data
            and hasattr(page_obj, "_show_update_dialog")
            else None
        ),
    )
    version_btn.tab_index = 2

    theme_btn.tab_index = 3

    header = ft.Container(
        padding=ft.Padding.only(left=24, right=24, top=24, bottom=8),
        content=ft.Row(
            controls=[
                ft.Row(
                    controls=[
                        ft.Image(src="icon.png", width=32, height=32, fit="contain"),
                        ft.Text(APP_NAME, size=24, weight=ft.FontWeight.BOLD),
                    ],
                    spacing=12,
                ),
                ft.Row(
                    controls=[search_btn, version_btn, theme_btn],
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

    # Local Button Style with high-contrast D-pad focus state
    def local_button_style():
        return ft.ButtonStyle(
            bgcolor={
                ft.ControlState.FOCUSED: AppColors.PRIMARY,
                ft.ControlState.DEFAULT: ft.Colors.SURFACE_CONTAINER_HIGHEST
                if hasattr(ft.Colors, "SURFACE_CONTAINER_HIGHEST")
                else ft.Colors.SURFACE,
            },
            color={
                ft.ControlState.FOCUSED: ft.Colors.WHITE,
                ft.ControlState.DEFAULT: ft.Colors.ON_SURFACE,
            },
        )

    # Developer Feedback and Support Dialog
    def show_support_dialog():
        page_obj.dialog_open = True

        async def open_email(e):
            page_obj.dialog_open = False
            try:
                page_obj.pop_dialog()
            except Exception:
                pass
            try:
                await asyncio.wait_for(
                    ft.UrlLauncher().launch_url(
                        "mailto:kalerosemary7@gmail.com?subject=AnimePahe%20TV%20Support%20and%20Feedback"
                    ),
                    timeout=1.0,
                )
            except Exception:
                pass
            page_obj.update()

        def dismiss(e):
            page_obj.dialog_open = False
            try:
                page_obj.pop_dialog()
            except Exception:
                pass
            page_obj.update()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Contact Support & Feedback", weight=ft.FontWeight.BOLD),
            content=ft.Column(
                [
                    ft.Text(
                        "We would love to hear your suggestions, feature requests, or bug reports. "
                        "We value your feedback.",
                        size=13,
                    ),
                ],
                tight=True,
            ),
            actions=[
                ft.Button(content=ft.Text("Close"), on_click=dismiss),
                ft.Button(
                    content=ft.Text("Send Email"),
                    on_click=lambda e: page_obj.run_task(open_email, e),
                    style=local_button_style(),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page_obj.show_dialog(dlg)

    # Secure asynchronous URL launcher using modern UrlLauncher
    async def launch_url_async(url: str):
        try:
            await ft.UrlLauncher().launch_url(url)
        except Exception:
            pass

    # Dynamic Banner Slides Generator
    def build_slide(slide_idx: int) -> ft.Control:
        if slide_idx == 0:
            logo_src = "nkiri_logo.png"
            title = "Nkiri TV"
            tagline = "Watch your favorite Movies, Series & Dramas for free on TV"
            badge_text = "Watch Movies"

            def on_click_action(_):
                page_obj.run_task(launch_url_async, f"{WORKER_BASE_URL}/movies")
        elif slide_idx == 1:
            logo_src = "socolive_logo.png"
            title = "Socolive TV"
            tagline = "Live football streams, match scores & highlights on your TV"
            badge_text = "Live Sports"

            def on_click_action(_):
                page_obj.run_task(launch_url_async, f"{WORKER_BASE_URL}/sports")
        else:
            logo_src = None
            title = "Contact Support & Send Feedback"
            tagline = "Suggest features, report bugs, or request content directly to us"
            badge_text = "Contact Support"

            def on_click_action(_):
                show_support_dialog()

        # Leading Logo Icon / Container
        if logo_src:
            leading = ft.Container(
                content=ft.Image(src=logo_src, width=38, height=38, fit="contain"),
                border_radius=8,
                clip_behavior="antiAlias",
            )
        else:
            leading = ft.Container(
                content=ft.Icon(
                    ft.Icons.MARK_CHAT_UNREAD_ROUNDED, size=24, color=AppColors.PRIMARY
                ),
                bgcolor=ft.Colors.with_opacity(0.1, AppColors.PRIMARY),
                border_radius=8,
                width=38,
                height=38,
                alignment=ft.Alignment.CENTER,
            )

        # Slide Card Component
        slide_card = ft.Container(
            key=f"slide_card_{slide_idx}",
            padding=ft.Padding(16, 12, 16, 12),
            bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.ON_SURFACE),
            border_radius=12,
            border=ft.Border.all(1.5, ft.Colors.TRANSPARENT),
            animate=200,
            animate_scale=200,
            on_click=on_click_action,
            content=ft.Row(
                controls=[
                    ft.Row(
                        controls=[
                            leading,
                            ft.Column(
                                controls=[
                                    ft.Row(
                                        controls=[
                                            ft.Text(
                                                title,
                                                size=13,
                                                weight=ft.FontWeight.BOLD,
                                                color=ft.Colors.ON_SURFACE,
                                            ),
                                            ft.Container(
                                                content=ft.Text(
                                                    badge_text,
                                                    size=9,
                                                    weight=ft.FontWeight.BOLD,
                                                    color=AppColors.PRIMARY,
                                                ),
                                                padding=ft.Padding(6, 2, 6, 2),
                                                border_radius=6,
                                                border=ft.Border.all(
                                                    1,
                                                    ft.Colors.with_opacity(
                                                        0.3, AppColors.PRIMARY
                                                    ),
                                                ),
                                            ),
                                        ],
                                        spacing=8,
                                        vertical_alignment=ft.VerticalAlignment.CENTER,
                                    ),
                                    ft.Text(
                                        tagline,
                                        size=11,
                                        color=ft.Colors.ON_SURFACE_VARIANT,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                        max_lines=1,
                                    ),
                                ],
                                spacing=2,
                                alignment=ft.MainAxisAlignment.CENTER,
                                expand=True,
                            ),
                        ],
                        spacing=12,
                        expand=True,
                    ),
                    ft.Icon(
                        ft.Icons.ARROW_FORWARD_IOS_ROUNDED,
                        size=14,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.VerticalAlignment.CENTER,
            ),
        )

        # Remote D-pad focus visual triggers
        def on_focus_change(e):
            if e.control.focused:
                e.control.border = ft.Border.all(1.5, AppColors.PRIMARY)
                e.control.scale = 1.01
                e.control.bgcolor = ft.Colors.with_opacity(0.12, AppColors.PRIMARY)
            else:
                e.control.border = ft.Border.all(1.5, ft.Colors.TRANSPARENT)
                e.control.scale = 1.0
                e.control.bgcolor = ft.Colors.with_opacity(0.05, ft.Colors.ON_SURFACE)
            e.control.update()

        slide_card.on_focus = on_focus_change
        slide_card.tab_index = 1000
        return slide_card

    current_slide_idx = 0
    switcher = ft.AnimatedSwitcher(
        content=build_slide(0),
        transition=ft.AnimatedSwitcherTransition.FADE,
        duration=300,
        expand=True,
    )

    async def auto_rotate():
        nonlocal current_slide_idx
        try:
            while True:
                await asyncio.sleep(10)
                if "/home" not in [v.route for v in page_obj.views]:
                    break
                current_slide_idx = (current_slide_idx + 1) % 3
                switcher.content = build_slide(current_slide_idx)
                page_obj.update()
        except Exception:
            pass

    # Start banner slide loop background task
    page_obj.run_task(auto_rotate)

    banner_container = ft.Container(
        padding=ft.Padding(24, 8, 24, 16),
        bgcolor=ft.Colors.SURFACE,
        content=ft.Row(
            controls=[switcher],
            expand=True,
        ),
    )

    view = ft.View(
        route="/home",
        controls=[
            ft.SafeArea(
                ft.Column(
                    controls=[
                        ft.Container(
                            content=scrollable,
                            expand=True,
                            bgcolor=ft.Colors.SURFACE,
                        ),
                        banner_container,
                    ],
                    expand=True,
                    spacing=0,
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
