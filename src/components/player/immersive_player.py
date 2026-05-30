import flet as ft
import flet_video as fv


class ImmersivePlayer(ft.Stack):
    def __init__(
        self, resource: str, http_headers: dict | None = None, on_close: callable = None
    ):
        super().__init__()
        self.resource = resource
        self.http_headers = http_headers
        self.on_close = on_close
        self.expand = True

        media = fv.VideoMedia(
            self.resource,
            http_headers=self.http_headers or {},
        )

        self.video = fv.Video(
            playlist=[media],
            autoplay=True,
            expand=True,
            show_controls=True,
            volume=100,
            wakelock=True,
            filter_quality=ft.FilterQuality.MEDIUM,
            pause_upon_entering_background_mode=True,
            resume_upon_entering_foreground_mode=True,
        )

        self.back_btn = ft.Container(
            left=12,
            top=40,
            content=ft.IconButton(
                icon=ft.Icons.ARROW_BACK_IOS_NEW_ROUNDED,
                icon_color=ft.Colors.WHITE,
                icon_size=20,
                bgcolor=ft.Colors.BLACK45,
                on_click=self.handle_close,
            ),
        )

        self.controls = [
            ft.Container(expand=True, bgcolor=ft.Colors.BLACK),
            self.video,
            self.back_btn,
        ]

    def handle_close(self, e):
        if self.on_close:
            try:
                self.on_close(e)
            except TypeError:
                self.on_close()
