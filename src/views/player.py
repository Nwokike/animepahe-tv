import flet as ft
import flet_video as fv
from core.theme import AppColors
from core.state import state
from services.kwik_resolver import KwikResolver


def build_player_view(
    page_obj: ft.Page,
) -> ft.View:
    kwik = KwikResolver()

    video = fv.Video(
        autoplay=True,
        expand=True,
        aspect_ratio=16 / 9,
        wakelock=True,
        filter_quality=ft.FilterQuality.MEDIUM,
        pause_upon_entering_background_mode=True,
        resume_upon_entering_foreground_mode=True,
        on_error=lambda e: _on_error(e, page_obj),
        on_complete=lambda e: _on_ended(page_obj),
    )

    status_text = ft.Text(
        "Resolving High Quality Stream...",
        size=16,
        color=ft.Colors.WHITE,
        weight=ft.FontWeight.W_500,
        text_align=ft.TextAlign.CENTER,
    )

    loading = ft.ProgressRing(
        width=40, height=40, stroke_width=4, color=AppColors.PRIMARY
    )

    overlay = ft.Container(
        expand=True,
        bgcolor=ft.Colors.with_opacity(0.8, ft.Colors.BLACK),
        alignment=ft.Alignment.CENTER,
        content=ft.Column(
            [
                loading,
                ft.Container(height=24),
                status_text,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
        ),
    )

    def on_back(e):
        if len(page_obj.views) > 1:
            page_obj.views.pop()
            if hasattr(page_obj, "refresh_episodes"):
                try:
                    page_obj.refresh_episodes()
                except Exception:
                    pass
            page_obj.update()



    back_btn = ft.Container(
        left=24,
        top=40,
        content=ft.IconButton(
            icon=ft.Icons.ARROW_BACK_IOS_NEW_ROUNDED,
            icon_color=ft.Colors.WHITE,
            icon_size=24,
            bgcolor=ft.Colors.with_opacity(0.3, ft.Colors.BLACK),
            on_click=on_back,
            tooltip="Back",
        ),
    )
    back_btn.tab_index = 1

    async def resolve_and_play():
        try:
            if state.selected_source:
                m3u8 = kwik.resolve(state.selected_source.url)
                if m3u8:
                    video.playlist = [
                        fv.VideoMedia(
                            m3u8, http_headers={"Referer": state.selected_source.url}
                        )
                    ]
                    video.autoplay = True
                    overlay.visible = False
                else:
                    status_text.value = "Failed to resolve stream"
                    loading.visible = False
            else:
                status_text.value = "No source selected"
                loading.visible = False
            page_obj.update()
        except Exception:
            status_text.value = "An error occurred while resolving"
            loading.visible = False
            page_obj.update()

    view = ft.View(
        route="/play",
        controls=[
            ft.Stack(
                [
                    ft.Container(expand=True, bgcolor=ft.Colors.BLACK),
                    video,
                    overlay,
                    back_btn,
                ],
                expand=True,
            ),
        ],
        padding=0,
    )

    page_obj.run_task(resolve_and_play)

    return view


def _on_error(e, page_obj: ft.Page):
    try:
        page_obj.snack_bar = ft.SnackBar(
            ft.Text("Playback error", color=ft.Colors.WHITE),
            bgcolor=AppColors.ERROR,
            duration=3000,
        )
        page_obj.snack_bar.open = True
        page_obj.update()
    except Exception:
        pass


def _on_ended(page_obj: ft.Page):
    try:
        page_obj.snack_bar = ft.SnackBar(
            ft.Text("Playback ended", color=ft.Colors.WHITE),
            bgcolor=AppColors.SUCCESS,
            duration=3000,
        )
        page_obj.snack_bar.open = True
        page_obj.update()
    except Exception:
        pass
