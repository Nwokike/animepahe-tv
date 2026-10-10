"""Downloads — series-grouped offline episodes.

Per-episode rows carry progress while active, a size once complete, and
play/delete actions. The download flow itself starts on the series detail
screen; this screen only lists and manages what exists.
"""

import flet as ft

from components.banner_ad import build_banner_ad
from core.theme import AppColors
from state.app_state import AppStateCtx
from state.controller_ctx import ControllerMethodsCtx


def _fmt_size(num_bytes) -> str:
    try:
        value = float(num_bytes or 0)
    except (TypeError, ValueError):
        return "?"
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f}{unit}" if unit == "B" else f"{value:.1f}{unit}"
        value /= 1024
    return f"{value:.1f}GB"


def _episode_row(row: dict, session: str, controller, progress) -> ft.Control:
    state = row.get("state", "partial")
    active = progress is not None
    done = progress.get("done", 0) if active else 0
    total = progress.get("total", 0) if active else 0
    percent = (done / total) if total else 0

    status = ft.Text(
        f"{percent:.0%}" if active else _fmt_size(row.get("size_bytes")),
        size=12,
        color=AppColors.DARK_TEXT_DIM,
    )
    trailing: list[ft.Control] = [status]
    if active:
        trailing.append(
            ft.IconButton(
                icon=ft.Icons.CLOSE_ROUNDED,
                icon_size=20,
                tooltip="Cancel",
                on_click=lambda e: controller.cancel_download(session),
            )
        )
    else:
        trailing.append(
            ft.IconButton(
                icon=ft.Icons.DELETE_OUTLINE_ROUNDED,
                icon_size=20,
                tooltip="Delete",
                on_click=lambda e: controller.delete_download(session),
            )
        )

    return ft.Container(
        content=ft.Row(
            [
                ft.Container(
                    content=ft.Icon(
                        ft.Icons.DOWNLOAD_DONE_ROUNDED
                        if state == "complete"
                        else ft.Icons.DOWNLOADING_ROUNDED,
                        size=20,
                        color=AppColors.SUCCESS
                        if state == "complete"
                        else AppColors.WARNING,
                    ),
                    width=36,
                    height=36,
                    border_radius=8,
                    alignment=ft.Alignment.CENTER,
                    bgcolor=ft.Colors.with_opacity(0.08, AppColors.DARK_TEXT),
                ),
                ft.Column(
                    [
                        ft.Text(
                            f"Episode {row.get('episode_num', '?')}",
                            size=13,
                            weight=ft.FontWeight.W_600,
                            color=AppColors.DARK_TEXT,
                        ),
                        ft.ProgressBar(value=percent, height=3)
                        if active
                        else ft.Container(height=3),
                    ],
                    spacing=4,
                    expand=True,
                ),
                *trailing,
            ],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding.symmetric(horizontal=12, vertical=8),
        border_radius=8,
        ink=True,
        on_click=None
        if active
        else (lambda e: controller.play_downloaded(session)),
    )


@ft.component
def DownloadsScreen() -> ft.Control:
    state = ft.use_context(AppStateCtx)
    controller = ft.use_context(ControllerMethodsCtx)
    _ = state.downloads_version

    from flet import context as flet_context

    try:
        page = flet_context.page
    except Exception:
        page = None

    downloads = state.downloads or {}
    if not downloads:
        return ft.Container(
            content=ft.Column(
                [
                    ft.Icon(
                        ft.Icons.CLOUD_DOWNLOAD_ROUNDED,
                        size=64,
                        color=AppColors.DARK_TEXT_DIM,
                    ),
                    ft.Text(
                        "Downloads appear here",
                        size=17,
                        weight=ft.FontWeight.W_600,
                        color=AppColors.DARK_TEXT,
                    ),
                    ft.Text(
                        "Tap the download icon on any episode to save it for offline.",
                        size=13,
                        color=AppColors.DARK_TEXT_DIM,
                        text_align=ft.TextAlign.CENTER,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=10,
            ),
            alignment=ft.Alignment.CENTER,
            expand=True,
        )

    # Group by anime session, newest first.
    groups: dict[str, dict] = {}
    for session, row in downloads.items():
        key = row.get("anime_session") or session
        group = groups.setdefault(
            key, {"title": row.get("title", "Unknown"), "poster": row.get("poster"), "rows": []}
        )
        group["rows"].append((session, row))

    sections = []
    for group in groups.values():
        rows = sorted(
            group["rows"], key=lambda r: r[1].get("episode_num", 0), reverse=True
        )
        total_size = sum(r[1].get("size_bytes", 0) for r in rows if r[1].get("state") == "complete")
        header = ft.Row(
            [
                ft.Container(
                    content=ft.Image(
                        src=group["poster"], fit=ft.BoxFit.COVER, expand=True
                    )
                    if group["poster"]
                    else ft.Icon(
                        ft.Icons.MOVIE_ROUNDED, size=20, color=AppColors.DARK_TEXT_DIM
                    ),
                    width=40,
                    height=40,
                    border_radius=6,
                    clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                ),
                ft.Column(
                    [
                        ft.Text(
                            group["title"],
                            size=15,
                            weight=ft.FontWeight.W_700,
                            color=AppColors.DARK_TEXT,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        ft.Text(
                            f"{len(rows)} episode{'s' if len(rows) != 1 else ''} · {_fmt_size(total_size)}",
                            size=11,
                            color=AppColors.DARK_TEXT_DIM,
                        ),
                    ],
                    spacing=2,
                    expand=True,
                ),
            ],
            spacing=12,
        )
        episode_rows = [
            _episode_row(
                row,
                session,
                controller,
                (state.download_progress or {}).get(session),
            )
            for session, row in rows
        ]
        sections.append(
            ft.Container(
                content=ft.Column([header, *episode_rows], spacing=4),
                padding=ft.Padding.all(12),
                border_radius=12,
                bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.WHITE),
                border=ft.Border.all(1, ft.Colors.with_opacity(0.08, ft.Colors.WHITE)),
            )
        )

    sections.append(build_banner_ad(page))
    return ft.Column(
        controls=sections,
        spacing=12,
        expand=True,
        scroll=ft.ScrollMode.AUTO,
        padding=ft.Padding.all(16),
    )
