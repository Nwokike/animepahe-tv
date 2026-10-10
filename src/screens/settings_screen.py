"""Settings — activity terminal and app info.

The terminal ports the Sherlock spec exactly: Courier New on #0D0D0D,
Monokai-green text, last 500 lines of the in-memory log buffer, with
copy/clear/close actions and a telemetry strip.
"""

import flet as ft

from components.banner_ad import build_banner_ad
from core.logger_handler import (
    get_telemetry_snapshot,
    in_memory_log_handler,
)
from core.theme import AppColors
from state.app_state import AppStateCtx
from state.controller_ctx import ControllerMethodsCtx

TERMINAL_DISPLAY_LINES = 500


def _section_header(text: str) -> ft.Control:
    return ft.Container(
        padding=ft.Padding.only(left=16, right=16, top=12, bottom=4),
        content=ft.Text(
            text,
            size=12,
            weight=ft.FontWeight.W_700,
            color=AppColors.PRIMARY,
        ),
    )


def _settings_card(controls: list) -> ft.Control:
    return ft.Container(
        content=ft.Column(controls=controls, spacing=0, tight=True),
        margin=ft.Margin.only(left=16, right=16, bottom=8),
        border_radius=12,
        bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.WHITE),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.08, ft.Colors.WHITE)),
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
    )


def _setting_row(icon, title, subtitle, trailing=None) -> ft.Control:
    return ft.Container(
        content=ft.Row(
            [
                ft.Container(
                    content=ft.Icon(icon, size=20, color=AppColors.DARK_TEXT_DIM),
                    width=36,
                    height=36,
                    border_radius=10,
                    alignment=ft.Alignment.CENTER,
                    bgcolor=ft.Colors.with_opacity(0.08, AppColors.DARK_TEXT),
                ),
                ft.Column(
                    [
                        ft.Text(
                            title,
                            size=14,
                            weight=ft.FontWeight.W_500,
                            color=AppColors.DARK_TEXT,
                        ),
                        ft.Text(
                            subtitle,
                            size=11,
                            color=ft.Colors.with_opacity(0.6, AppColors.DARK_TEXT),
                        ),
                    ],
                    spacing=2,
                    expand=True,
                ),
                trailing or ft.Container(width=0, height=0),
            ],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding.symmetric(horizontal=12, vertical=8),
    )


@ft.component
def SettingsScreen() -> ft.Control:
    state = ft.use_context(AppStateCtx)
    controller = ft.use_context(ControllerMethodsCtx)

    from flet import context as flet_context

    try:
        page = flet_context.page
    except Exception:
        page = None

    def _open_terminal(e):
        log_count = len(in_memory_log_handler.get_logs())

        log_text = ft.Text(
            value="\n".join(in_memory_log_handler.get_logs()[-TERMINAL_DISPLAY_LINES:])
            or "No activity recorded yet.\nEngine, network, and UI logs will appear here.",
            size=11,
            font_family="Courier New",
            color="#A6E22E",
            selectable=True,
        )
        telemetry_text = ft.Text(
            get_telemetry_snapshot(),
            size=11,
            font_family="Courier New",
            color=AppColors.PRIMARY,
            weight=ft.FontWeight.W_600,
        )
        log_box = ft.Container(
            content=ft.Column(controls=[log_text], scroll=ft.ScrollMode.AUTO, expand=True),
            bgcolor="#0D0D0D",
            border=ft.Border.all(1, ft.Colors.with_opacity(0.2, ft.Colors.WHITE)),
            border_radius=8,
            padding=12,
            expand=True,
        )

        def _refresh(e=None):
            log_text.value = "\n".join(
                in_memory_log_handler.get_logs()[-TERMINAL_DISPLAY_LINES:]
            ) or "No activity recorded yet."
            telemetry_text.value = get_telemetry_snapshot()
            page.update(log_text, telemetry_text)

        def _copy(e):
            import flet as _ft

            clipboard = _ft.Clipboard()
            page.services.append(clipboard)
            page.run_task(_do_copy, page, clipboard, log_text.value)

        def _clear(e):
            in_memory_log_handler.clear_logs()
            log_text.value = "Logs cleared."
            page.update(log_text)

        def _close(e):
            page.pop_dialog()

        dlg = ft.AlertDialog(
            modal=False,
            title=ft.Row(
                [
                    ft.Icon(ft.Icons.TERMINAL_ROUNDED, color=AppColors.PRIMARY),
                    ft.Text(
                        "Live Activity Terminal",
                        size=14,
                        weight=ft.FontWeight.BOLD,
                        color=AppColors.PRIMARY,
                        expand=True,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.REFRESH_ROUNDED,
                        tooltip="Refresh",
                        on_click=_refresh,
                    ),
                ],
                spacing=8,
            ),
            content=ft.Container(
                width=420,
                height=480,
                content=ft.Column(
                    [telemetry_text, ft.Container(height=8), log_box],
                    spacing=0,
                    expand=True,
                ),
            ),
            actions=[
                ft.TextButton(content="Copy Logs", on_click=_copy),
                ft.TextButton(content="Clear", on_click=_clear),
                ft.TextButton(content="Close", on_click=_close),
            ],
        )
        page.show_dialog(dlg)

    terminal_row = _setting_row(
        ft.Icons.TERMINAL_ROUNDED,
        "Live Activity Terminal",
        f"{len(in_memory_log_handler.get_logs())} entries recorded · Real-time engine diagnostics",
        trailing=ft.FilledButton(
            content="Open Terminal",
            icon=ft.Icons.TERMINAL_ROUNDED,
            on_click=_open_terminal,
        ),
    )

    return ft.Column(
        controls=[
            _section_header("DIAGNOSTICS"),
            _settings_card([terminal_row]),
            build_banner_ad(page, inline=True),
            _section_header("ABOUT"),
            _settings_card(
                [
                    _setting_row(
                        ft.Icons.INFO_OUTLINE_ROUNDED,
                        "AnimePahe TV",
                        "Unofficial client for AnimePahe. Streams are provided by the site.",
                    ),
                    _setting_row(
                        ft.Icons.SECURITY_ROUNDED,
                        "Source",
                        "This app only scrapes public pages; it hosts no content.",
                    ),
                ]
            ),
        ],
        spacing=0,
        expand=True,
        scroll=ft.ScrollMode.AUTO,
    )


async def _do_copy(page, clipboard, text: str):
    from flet import context

    try:
        await clipboard.set(text)
    except Exception:
        pass
    finally:
        try:
            current = context.page
            if current is not None and clipboard in current.services:
                current.services.remove(clipboard)
        except Exception:
            pass
