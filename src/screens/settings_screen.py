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
        bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.ON_SURFACE),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE)),
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
    )


def _setting_row(icon, title, subtitle, trailing=None) -> ft.Control:
    return ft.Container(
        content=ft.Row(
            [
                ft.Container(
                    content=ft.Icon(icon, size=20, color=ft.Colors.ON_SURFACE_VARIANT),
                    width=36,
                    height=36,
                    border_radius=10,
                    alignment=ft.Alignment.CENTER,
                    bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE),
                ),
                ft.Column(
                    [
                        ft.Text(
                            title,
                            size=14,
                            weight=ft.FontWeight.W_500,
                            color=ft.Colors.ON_SURFACE,
                        ),
                        ft.Text(
                            subtitle,
                            size=11,
                            color=ft.Colors.with_opacity(0.6, ft.Colors.ON_SURFACE),
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
            from core.shared_services import get_shared_services

            page.run_task(
                get_shared_services(page).set_clipboard, log_text.value
            )

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

    # Playback target: the in-app player, or KTV Player via ktv:// (the
    # old app's only mode). The store is the source of truth; the switch
    # mirrors it and writes back on change.
    external_player, set_external_player = ft.use_state(False)

    def _load_external_player():
        from services.store import get_store

        async def _read():
            enabled = await get_store().get_external_player()
            set_external_player(enabled)

        from core.tasks import spawn

        spawn(_read(), name="load-external-player")

    ft.use_effect(_load_external_player, [])

    def _on_external_player_change(e):
        enabled = bool(e.control.value)
        set_external_player(enabled)

        async def _save():
            from services.store import get_store

            await get_store().save_external_player(enabled)
            from core.notify import show_snack

            show_snack(
                page,
                "External player enabled."
                if enabled
                else "In-app player enabled.",
            )

        from core.tasks import spawn

        spawn(_save(), name="save-external-player")

    external_player_row = _setting_row(
        ft.Icons.OPEN_IN_NEW_ROUNDED,
        "Play in external player",
        "Hand streams to KTV Player instead of the in-app player",
        trailing=ft.Switch(
            value=external_player,
            on_change=_on_external_player_change,
        ),
    )


    # ------------------------------------------------------------------
    # Content source — auto (recommended) vs pinned provider, with live
    # per-provider status. The router still fails over when a pinned
    # source is down; the pin only changes who goes first.
    # ------------------------------------------------------------------
    controller_ref = getattr(controller, "_app_controller", None) or controller
    _ = state.sources_test_version
    backend, set_backend = ft.use_state("auto")
    source_status, set_source_status = ft.use_state({})

    def _load_backend():
        from services.store import get_store

        async def _read():
            set_backend(await get_store().get_backend())
            set_source_status(controller_ref.sources_status())

        from core.tasks import spawn

        spawn(_read(), name="load-backend")

    ft.use_effect(_load_backend, [])

    def _on_backend_change(e):
        name = e.control.value or "auto"
        set_backend(name)
        from core.tasks import spawn

        spawn(controller.set_backend_pin(name), name="save-backend-pin")

    provider_names = (controller_ref.router.provider_names if controller_ref else []) or []
    backend_dropdown = ft.Dropdown(
        value=backend,
        options=[ft.dropdown.Option("auto", "Automatic (recommended)")]
        + [ft.dropdown.Option(name, name.capitalize()) for name in provider_names],
        on_change=_on_backend_change,
        text_size=13,
        content_padding=ft.Padding.symmetric(horizontal=12, vertical=8),
    )
    backend_row = _setting_row(
        ft.Icons.LAYERS_ROUNDED,
        "Content source",
        "Automatic tries every source in order and never locks. Pinning only changes who goes first.",
        trailing=backend_dropdown,
    )

    _STATE_COLORS = {
        "closed": AppColors.SUCCESS,
        "half_open": AppColors.WARNING,
        "open": AppColors.ERROR,
        "unknown": AppColors.WARNING,
    }
    test_rows = {r.get("name"): r for r in (state.source_test_results or [])}
    status_rows = []
    for name in provider_names:
        rec = (source_status or {}).get(name) or {}
        state_name = rec.get("state") or "unknown"
        latency = rec.get("latency_ms")
        latency_text = f"{latency:.0f} ms" if latency else "—"
        error = rec.get("last_error") or ""
        subtitle = f"{state_name} · {latency_text}" + (f" · {error[:60]}" if error else "")
        tested = test_rows.get(name)
        if tested is not None:
            bits = ["probe OK" if tested.get("probe_ok") else "probe FAIL"]
            if tested.get("search_count") is not None:
                bits.append(f"{tested['search_count']} results in {tested.get('search_ms')} ms")
            if tested.get("error"):
                bits.append(tested["error"])
            subtitle = " · ".join(bits)
        status_rows.append(
            _setting_row(
                ft.Icons.CIRCLE,
                name.capitalize(),
                subtitle,
                trailing=ft.Container(
                    width=10,
                    height=10,
                    border_radius=5,
                    bgcolor=_STATE_COLORS.get(state_name, AppColors.WARNING),
                ),
            )
        )
    test_button = ft.TextButton(
        content="Test all sources",
        on_click=lambda e: controller.test_all_sources(),
    )
    source_section = [
        _section_header("CONTENT SOURCE"),
        _settings_card([backend_row]),
        _settings_card([*status_rows, test_button]) if status_rows else ft.Container(height=0),
    ]

    return ft.Column(
        controls=[
            *source_section,
            _section_header("PLAYBACK"),

            _settings_card([external_player_row]),
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


# (_do_copy was the per-tap Clipboard dance; settings now uses the shared
# service from core.shared_services, mounted once at init.)
