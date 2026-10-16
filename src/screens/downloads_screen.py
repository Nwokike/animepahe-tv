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


def _progress_label(progress: dict, *, complete: bool, row: dict) -> str:
    """The one line the owner expects to SEE MOVING: "42% · 78.2/186.4 MB".

    House format (Sherlock's scan / DDGS's downloader): the percent first,
    then the counter it came from once a denominator exists — segment jobs
    count segments, file jobs count bytes. "Starting…" is reserved for the
    honest pre-first-byte window, and every non-running state is a WORD,
    never a spinner pretending to be progress.
    """
    job_state = (progress or {}).get("state") or ""
    percent = (progress or {}).get("percent")
    done = (progress or {}).get("done")
    total = (progress or {}).get("total")
    if job_state == STATE_DOWNLOADING:
        if isinstance(percent, (int, float)):
            if isinstance(total, (int, float)) and total > 1 and isinstance(done, (int, float)):
                # A segment job counts SEGMENTS (144 max); a file job
                # counts BYTES. The unit follows the counter's own scale.
                if total > 20_000:
                    return f"{percent:.0f}% · {_fmt_size(done)} / {_fmt_size(total)}"
                return f"{percent:.0f}% · {int(done)}/{int(total)} segments"
            return f"{percent:.0f}%"
        return "Starting…"
    if job_state == STATE_QUEUED:
        return "Queued"
    if job_state == STATE_STOPPED:
        return f"Paused · {_fmt_size((progress or {}).get('bytes'))} saved"
    if job_state == STATE_FAILED:
        return "Failed — tap Retry"
    if complete:
        return _fmt_size(row.get("size_bytes"))
    return "Failed — tap Retry" if row.get("error") else "Not started"


def _episode_row(row: dict, session: str, controller, progress) -> ft.Control:
    """One episode row: the state word, an inline bar while it runs, and
    the actions that state allows."""
    job_state = (progress or {}).get("state") or ""
    percent = (progress or {}).get("percent")
    row_state = row.get("state", "partial")
    complete = row_state == "complete"

    # The bar is inside the name row when it runs — the house shape — and
    # absent otherwise. It goes DETERMINATE the moment a percent exists;
    # only the genuine pre-first-byte window stays indeterminate.
    running = job_state in (STATE_DOWNLOADING, STATE_QUEUED)
    bar_value = (
        min(max(float(percent), 0.0), 100.0) / 100.0 if isinstance(percent, (int, float)) else None
    )
    status_text = _progress_label(progress or {}, complete=complete, row=row)

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
                        else ft.Icons.DOWNLOAD_ROUNDED,
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
    # Which series cards are open. The first is expanded by default (the
    # newest group — the one the user most likely came to watch); every
    # other series collapses to its header until tapped.
    expanded, set_expanded = ft.use_state(None)

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
    # Most-recently-updated series first: the row's updated_at when the
    # store has one, the dict order otherwise (the store is newest-first).
    def _recency(item):
        first_row = item[1]["rows"][0][1]
        return float(first_row.get("updated_at") or first_row.get("ts") or 0.0)

    default_open = max(groups.items(), key=_recency)[0] if groups else None

    for session_key, group in groups.items():
        is_open = (expanded if expanded is not None else default_open) == session_key
        rows = sorted(group["rows"], key=lambda r: r[1].get("episode_num", 0), reverse=True)
        complete = [r for r in rows if r[1].get("state") == "complete"]
        total_size = sum((r[1].get("size_bytes") or 0) for r in complete)

        # Live aggregate for the whole series: "3/11 · 42%" while jobs are
        # running (the per-item bars below say which one is where).
        progress_map = state.download_progress or {}
        live = [progress_map.get(s) for s, _ in rows]
        running = [p_ for p_ in live if p_ and p_.get("state") in ("downloading", "queued")]
        if running:
            done_items = sum(1 for p_ in live if p_ and p_.get("state") == "complete")
            done_items += sum(1 for _, r in rows if r.get("state") == "complete")
            percent_sum = sum(
                float(p_.get("percent") or 0.0)
                for p_ in running
                if isinstance(p_.get("percent"), (int, float))
            )
            overall = percent_sum / len(rows) if rows else 0.0
            summary = f"{done_items}/{len(rows)} done · {overall:.0f}%"
        else:
            summary = f"{len(rows)} episode{'s' if len(rows) != 1 else ''} · {_fmt_size(total_size)}"

        chevron = ft.Icon(
            ft.Icons.EXPAND_LESS_ROUNDED if is_open else ft.Icons.EXPAND_MORE_ROUNDED,
            size=20,
            color=ft.Colors.ON_SURFACE_VARIANT,
        )
        header_rows: list[ft.Control] = [
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
                        summary,
                        size=11,
                        color=AppColors.PRIMARY if running else ft.Colors.ON_SURFACE_VARIANT,
                    ),
                ],
                spacing=2,
                expand=True,
            ),
            chevron,
        ]

        def _toggle(e=None, key=session_key, open_now=is_open):
            set_expanded(None if open_now else key)

        header = ft.Container(
            content=ft.Row(header_rows, spacing=12),
            padding=ft.Padding.symmetric(horizontal=4, vertical=6),
            border_radius=8,
            ink=True,
            tooltip="Collapse" if is_open else "Expand",
            on_click=_toggle,
        )

        episode_rows = [
            _episode_row(
                row,
                session,
                controller,
                progress_map.get(session),
            )
            for session, row in rows
        ]
        # Only the expanded series renders its rows: a 3-series library
        # stays scannable, and a long series costs nothing until opened.
        body = [header, *(episode_rows if is_open else [])]
        sections.append(
            ft.Container(
                content=ft.Column(body, spacing=4),
                padding=ft.Padding.all(12),
                border_radius=12,
                bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.ON_SURFACE),
                border=ft.Border.all(1, ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE)),
            )
        )

    sections.append(build_banner_ad(page))
    # Column takes no padding in flet 1.0.4 — the screen inset lives on the
    # wrapper so the scrollable keeps its margin.
    from components.app_header import app_header

    return ft.Container(
        content=ft.Column(
            controls=[
                app_header(state, page, controller, subtitle="Downloads"),
                *sections,
            ],
            spacing=12,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        ),
        expand=True,
        padding=ft.Padding.all(16),
    )
