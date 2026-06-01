import flet as ft
import flet_video as ftv


def build_player_view(
    page_obj: ft.Page,
    m3u8_url: str,
    title: str = "",
    http_headers: dict[str, str] | None = None,
) -> ft.View:

    video = ftv.Video(
        expand=True,
        autoplay=True,
        playlist=[ftv.VideoMedia(m3u8_url, http_headers=http_headers)],
        playlist_mode=ftv.PlaylistMode.LOOP,
        fill_color=ft.Colors.BLACK,
        wakelock=True,
    )

    view = ft.View(
        route="/player",
        controls=[video],
        padding=0,
        bgcolor=ft.Colors.BLACK,
    )

    return view
