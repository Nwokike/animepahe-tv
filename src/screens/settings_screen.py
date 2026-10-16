"""Settings — activity terminal and app info.

The terminal ports the Sherlock spec exactly: Courier New on #0D0D0D,
Monokai-green text, last 500 lines of the in-memory log buffer, with
copy/clear/close actions and a telemetry strip.
"""

import contextlib

import flet as ft

from components.banner_ad import build_banner_ad
from core.logger_handler import (
    get_telemetry_snapshot,
    in_memory_log_handler,
)
from core.theme import AppColors, mode_for_token, token_for_mode
from state.app_state import AppStateCtx
from state.controller_ctx import ControllerMethodsCtx

TERMINAL_DISPLAY_LINES = 500


def _section_header(text: str, subtitle: str = "") -> ft.Control:
    """The ffmpeg-app header shape: the label, then a quiet one-line
    subtitle that says what the section is FOR. A bare label makes the
    user read the rows to guess the section's job."""
    rows: list[ft.Control] = [
        ft.Text(
            text,
            size=12,
            weight=ft.FontWeight.W_700,
            color=AppColors.PRIMARY,
        )
    ]
    if subtitle:
        rows.append(
            ft.Text(
                subtitle,
                size=10,
                color=ft.Colors.with_opacity(0.55, ft.Colors.ON_SURFACE),
            )
        )
    return ft.Container(
        padding=ft.Padding.only(left=16, right=16, top=12, bottom=4),
        content=ft.Column(rows, spacing=1, tight=True),
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
    _ = state.storage_version  # the Storage row's size re-render trigger

    # Measure once per mount: a directory walk behind the row's size text.
    ft.use_effect(lambda: controller.measure_cache(), [])

    from flet import context as flet_context

    try:
        page = flet_context.page
    except Exception:
        page = None

    def _open_terminal(e):
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
        # FIXED height (not expand=True): expand inside a dialog grows
        # the box without bound as logs accumulate — the dialog-burst
        # bug Sherlock already documented.
        log_box = ft.Container(
            content=ft.Column(controls=[log_text], scroll=ft.ScrollMode.AUTO),
            bgcolor="#0D0D0D",
            border=ft.Border.all(1, ft.Colors.with_opacity(0.2, ft.Colors.WHITE)),
            border_radius=8,
            padding=12,
            height=320,
        )

        def _refresh(e=None):
            log_text.value = (
                "\n".join(in_memory_log_handler.get_logs()[-TERMINAL_DISPLAY_LINES:])
                or "No activity recorded yet."
            )
            telemetry_text.value = get_telemetry_snapshot()
            page.update(log_text, telemetry_text)

        def _copy(e):
            from core.notify import show_snack
            from core.shared_services import get_shared_services

            page.run_task(get_shared_services(page).set_clipboard, log_text.value)
            show_snack(page, "Logs copied")

        def _clear(e):
            in_memory_log_handler.clear_logs()
            log_text.value = "Logs cleared."
            page.update(log_text)

        def _close(e):
            from core.dialogs import close_app_dialog

            if page and not close_app_dialog(page):
                with contextlib.suppress(Exception):
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
                "External player enabled." if enabled else "In-app player enabled.",
            )

        from core.tasks import spawn

        spawn(_save(), name="save-external-player")

    external_player_row = _setting_row(
        ft.Icons.OPEN_IN_NEW_ROUNDED,
        "Play in external player",
        # The honest default note (owner's call): in-app playback is the
        # one still being finished, and handing streams to KTV is what the
        # app ships doing today.
        "Default · hands streams to KTV Player — the in-app player is coming soon",
        trailing=ft.Switch(
            value=external_player,
            on_change=_on_external_player_change,
        ),
    )

    # ------------------------------------------------------------------
    # Theme: the house 3-way (Dark / Light / System), persisted. The
    # header toggle cycles the same order; this is the direct picker.
    # ------------------------------------------------------------------
    _THEME_OPTIONS = [
        ("dark", "Dark", ft.Icons.DARK_MODE_ROUNDED),
        ("light", "Light", ft.Icons.LIGHT_MODE_ROUNDED),
        ("system", "System", ft.Icons.SETTINGS_SYSTEM_DAYDREAM_ROUNDED),
    ]
    _current_theme = token_for_mode(state.theme_mode)

    def _pick_theme(token, mode):
        from core.tasks import spawn

        spawn(controller_ref.save_theme_mode(mode), name="save-theme")

    theme_picker = ft.Row(
        [
            ft.OutlinedButton(
                content=ft.Row(
                    [ft.Icon(icon, size=16), ft.Text(label, size=13)],
                    spacing=6,
                    tight=True,
                ),
                style=ft.ButtonStyle(
                    bgcolor=ft.Colors.with_opacity(0.15, AppColors.PRIMARY)
                    if _current_theme == token
                    else ft.Colors.TRANSPARENT,
                    side={
                        ft.ControlState.DEFAULT: ft.BorderSide(
                            1.5,
                            AppColors.PRIMARY
                            if _current_theme == token
                            else ft.Colors.with_opacity(0.3, AppColors.PRIMARY),
                        )
                    },
                ),
                on_click=lambda e, tk=token: _pick_theme(tk, mode_for_token(tk)),
            )
            for token, label, icon in _THEME_OPTIONS
        ],
        spacing=8,
    )

    # ------------------------------------------------------------------
    # Content source — the provider the owner picked, or the fixed launch
    # order (AniKato first) when none was picked. There is no "automatic"
    # entry: the order is simply how the app works.
    # ------------------------------------------------------------------
    controller_ref = getattr(controller, "_app_controller", None) or controller
    _ = state.sources_test_version
    backend, set_backend = ft.use_state("")
    source_status, set_source_status = ft.use_state({})

    def _load_backend():
        from services.store import get_store

        async def _read():
            stored = await get_store().get_backend()
            names = set((controller_ref.router.provider_names if controller_ref else []) or [])
            # Show the provider actually serving; a legacy/empty stored
            # value never renders (a 1.0.x-era leftover is treated as
            # "no preference").
            active = (getattr(controller_ref, "router", None) and controller_ref.router.pin) or (
                stored if stored in names else ""
            )
            set_backend(active)
            set_source_status(controller_ref.sources_status())

        from core.tasks import spawn

        spawn(_read(), name="load-backend")

    ft.use_effect(_load_backend, [])

    def _on_backend_change(e):
        name = e.control.value or ""
        if not name:
            return
        set_backend(name)
        if hasattr(controller, "set_backend_pin"):
            controller.set_backend_pin(name)

    provider_names = (controller_ref.router.provider_names if controller_ref else []) or []
    backend_dropdown = ft.Dropdown(
        value=backend,
        # Providers only, in the app's fixed launch order — there is no
        # "pick automatically" row any more.
        options=[ft.dropdown.Option(name, name.capitalize()) for name in provider_names],
        # 0.85.3's Dropdown has no on_change — on_select fires when the
        # user picks an option (on_text_change is the editable case).
        on_select=_on_backend_change,
        text_size=13,
        content_padding=ft.Padding.symmetric(horizontal=12, vertical=8),
    )
    backend_row = _setting_row(
        ft.Icons.LAYERS_ROUNDED,
        "Content source",
        "The app tries them in this order at launch. What you choose is the app.",
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
    from core.storage import format_size

    # Regenerable-only: a cleared cache costs a few refetches and an
    # artwork re-probe; history, resume positions, favorites, downloads
    # and the Cloudflare clearance all live in the durable tier and are
    # deliberately not touchable from here.
    cache_row = _setting_row(
        ft.Icons.CLEANING_SERVICES_ROUNDED,
        "Cache",
        f"{format_size(state.cache_bytes)} · artwork & catalogue, rebuilt automatically",
        trailing=ft.TextButton(
            content="Clear",
            on_click=lambda e: (controller.clear_cache(), controller.measure_cache()),
        ),
    )
    test_button = ft.TextButton(
        content="Test all sources",
        on_click=lambda e: controller.test_all_sources(),
    )
    source_section = [
        _section_header("CONTENT SOURCE", "Which backend is the app"),
        _settings_card([backend_row]),
        _settings_card([*status_rows, test_button]) if status_rows else ft.Container(height=0),
    ]

    from components.app_header import app_header

    return ft.Column(
        controls=[
            app_header(state, page, controller, subtitle="Settings"),
            _section_header("APPEARANCE", "Theme preference"),
            _settings_card([theme_picker]),
            *source_section,
            _section_header("PLAYBACK", "How episodes play"),
            _settings_card([external_player_row]),
            _section_header("DIAGNOSTICS", "Logs and engine status"),
            _settings_card([terminal_row]),
            build_banner_ad(page, inline=True),
            _section_header("STORAGE", "Regenerable data only"),
            _settings_card([cache_row]),
            _section_header("ABOUT", "Application and credits"),
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
