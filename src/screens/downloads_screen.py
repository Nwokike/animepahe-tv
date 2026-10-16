"""Downloads — series-grouped offline episodes.

Per-episode rows carry the job's state and an inline progress bar inside
the file-name row (the YouTube shape): Pause/Cancel while downloading,
Resume/Delete when paused, Retry/Delete when failed, Play/Delete when
complete. The download flow itself starts on the series detail screen;
this screen only lists and manages what exists.
"""

import flet as ft

from components.banner_ad import build_banner_ad
from components.empty_state import EmptyState
from core.theme import AppColors
from services.hls_proxy import image_url
from services.providers.base import owner_of
from state.app_state import AppStateCtx
from state.controller_ctx import ControllerMethodsCtx

# The manager's job states (Media3's set) as the screens see them.
STATE_DOWNLOADING = "downloading"
STATE_QUEUED = "queued"
STATE_STOPPED = "stopped"
STATE_FAILED = "failed"


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
    """One episode row: the state word, an inline bar while it runs, and
    the actions that state allows."""
    job_state = (progress or {}).get("state") or ""
    percent = (progress or {}).get("percent")
    row_state = row.get("state", "partial")
    complete = row_state == "complete"

    # The bar is inside the name row when it runs — YouTube's inline
    # progress — and absent otherwise. An unknown length is indeterminate
    # rather than a lie at 0%.
    running = job_state in (STATE_DOWNLOADING, STATE_QUEUED)
    bar_value = (
        min(max(float(percent), 0.0), 100.0) / 100.0 if isinstance(percent, (int, float)) else None
    )
    if job_state == STATE_DOWNLOADING:
        status_text = f"{percent:.0f}%" if isinstance(percent, (int, float)) else "Downloading…"
    elif job_state == STATE_QUEUED:
        status_text = "Waiting…"
    elif job_state == STATE_STOPPED:
        status_text = f"Paused · {_fmt_size((progress or {}).get('bytes'))} saved"
    elif job_state == STATE_FAILED:
        status_text = "Failed"
    elif complete:
        status_text = _fmt_size(row.get("size_bytes"))
    else:
        status_text = "Paused" if row.get("error") else "Not started"

    status = ft.Text(
        status_text,
        size=12,
        color=AppColors.WARNING if job_state == STATE_FAILED else ft.Colors.ON_SURFACE_VARIANT,
    )

    trailing: list[ft.Control] = [status]
    if running:
        # Pause keeps the partials (a Range resume continues from them).
        trailing.append(
            ft.IconButton(
                icon=ft.Icons.PAUSE_ROUNDED,
                icon_size=20,
                tooltip="Pause",
                on_click=lambda e: controller.pause_download(session),
            )
        )
        trailing.append(
            ft.IconButton(
                icon=ft.Icons.CLOSE_ROUNDED,
                icon_size=20,
                tooltip="Cancel",
                on_click=lambda e: controller.cancel_download(session),
            )
        )
    else:
        if job_state in (STATE_STOPPED, STATE_FAILED):
            trailing.append(
                ft.IconButton(
                    icon=ft.Icons.PLAY_ARROW_ROUNDED
                    if job_state == STATE_STOPPED
                    else ft.Icons.REFRESH_ROUNDED,
                    icon_size=20,
                    tooltip="Resume" if job_state == STATE_STOPPED else "Retry",
                    on_click=lambda e: controller.resume_download(session),
                )
            )
        # Play is a real focusable button: on TV the row itself can't take
        # focus (a Container has no focus events), and the IconButton
        # family does — same reason the card builders are buttons.
        if complete:
            trailing.append(
                ft.IconButton(
                    icon=ft.Icons.PLAY_CIRCLE_FILL_ROUNDED,
                    icon_size=20,
                    tooltip="Play",
                    on_click=lambda e: controller.play_downloaded(session),
                )
            )
        trailing.append(
            ft.IconButton(
                icon=ft.Icons.DELETE_OUTLINE_ROUNDED,
                icon_size=20,
                tooltip="Delete",
                on_click=lambda e: controller.delete_download(session),
            )
        )

    name_column = ft.Column(
        [
            ft.Text(
                f"Episode {row.get('episode_num', '?')}",
                size=13,
                weight=ft.FontWeight.W_600,
                color=ft.Colors.ON_SURFACE,
            ),
        ],
        spacing=2,
        expand=True,
    )
    if running:
        # The inline bar lives inside the name row, under the title.
        name_column.controls.append(
            ft.ProgressBar(
                value=bar_value,
                bar_height=3,
                color=AppColors.PRIMARY,
                bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.ON_SURFACE),
            )
        )

    return ft.Container(
        content=ft.Row(
            [
                ft.Container(
                    content=ft.Icon(
                        ft.Icons.DOWNLOAD_DONE_ROUNDED
                        if complete
                        else ft.Icons.DOWNLOADING_ROUNDED
                        if running
                        else ft.Icons.PAUSE_CIRCLE_OUTLINE_ROUNDED
                        if job_state == STATE_STOPPED
                        else ft.Icons.ERROR_OUTLINE_ROUNDED
                        if job_state == STATE_FAILED
                        else ft.Icons.DOWNLOAD_OUTLINE_ROUNDED,
                        size=20,
                        color=AppColors.SUCCESS
                        if complete
                        else AppColors.WARNING
                        if running or job_state == STATE_STOPPED
                        else AppColors.ERROR
                        if job_state == STATE_FAILED
                        else ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    width=36,
                    height=36,
                    border_radius=8,
                    alignment=ft.Alignment.CENTER,
                    bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE),
                ),
                name_column,
                *trailing,
            ],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding.symmetric(horizontal=12, vertical=8),
        border_radius=8,
        # The actions live in `trailing` as focusable buttons; the row
        # itself is display-only (tap-through would double-fire with the
        # button on touch devices).
        ink=False,
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
        return EmptyState(
            "Downloads appear here",
            message="Tap the download icon on any episode to save it for offline.",
            icon=ft.Icons.CLOUD_DOWNLOAD_ROUNDED,
        )

    # Group by anime session, newest first.
    groups: dict[str, dict] = {}
    for session, row in downloads.items():
        key = row.get("anime_session") or session
        group = groups.setdefault(
            key,
            {
                "title": row.get("title", "Unknown"),
                "poster": row.get("poster"),
                "rows": [],
            },
        )
        group["rows"].append((session, row))

    sections = []
    for session_key, group in groups.items():
        rows = sorted(group["rows"], key=lambda r: r[1].get("episode_num", 0), reverse=True)
        total_size = sum(
            (r[1].get("size_bytes") or 0) for r in rows if r[1].get("state") == "complete"
        )
        header = ft.Row(
            [
                ft.Container(
                    content=ft.Image(
                        src=image_url(group["poster"] or "", owner_of(session_key)),
                        fit=ft.BoxFit.COVER,
                        expand=True,
                    )
                    if group["poster"]
                    else ft.Icon(
                        ft.Icons.MOVIE_ROUNDED,
                        size=20,
                        color=ft.Colors.ON_SURFACE_VARIANT,
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
                            color=ft.Colors.ON_SURFACE,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        ft.Text(
                            f"{len(rows)} episode{'s' if len(rows) != 1 else ''} · {_fmt_size(total_size)}",
                            size=11,
                            color=ft.Colors.ON_SURFACE_VARIANT,
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
                bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.ON_SURFACE),
                border=ft.Border.all(1, ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE)),
            )
        )

    sections.append(build_banner_ad(page))
    # Column takes no padding in flet 1.0.4 — the screen inset lives on the
    # wrapper so the scrollable keeps its margin.
    return ft.Container(
        content=ft.Column(
            controls=sections,
            spacing=12,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        ),
        expand=True,
        padding=ft.Padding.all(16),
    )
