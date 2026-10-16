"""app_header — the ONE header every screen shares (Sherlock's pattern).

Left: the app icon + the source pill — "<Backend> TV ▾", the content-source
switcher — with the screen's own name as a quiet subtitle beneath it.

Right: the backend badge, the version/update pill, the screen's own extra
actions, then the theme cycle. The whole right group rides a
``Row(scroll=AUTO)``: Sherlock's rule is **scroll, never clip** — on a phone
the actions pan instead of shoving the title off the edge, and a screen can
add as many actions as it earns without a layout fight.

Every screen renders it, so switching backends (and theme) never depends on
being on Home or finding Settings — the owner's reuse pattern from Sherlock
and CollabShell.
"""

import contextlib

import flet as ft

from core.constants import APP_NAME, APP_VERSION
from core.theme import AppColors, next_theme_mode

__all__ = ["app_header", "backend_title", "theme_icon_for"]

THEME_ICONS = {
    ft.ThemeMode.DARK: ft.Icons.DARK_MODE_ROUNDED,
    ft.ThemeMode.LIGHT: ft.Icons.LIGHT_MODE_ROUNDED,
    ft.ThemeMode.SYSTEM: ft.Icons.SETTINGS_SYSTEM_DAYDREAM_ROUNDED,
}


def backend_title(state) -> str:
    """`<Backend> TV` — "Anikato TV", "Animepahe TV" — the active source's
    own name for the header. The brand name only stands in before anything
    is resolved (the splash covers that moment)."""
    name = (getattr(state, "current_source_name", "") or "").strip()
    return f"{name.capitalize()} TV" if name else APP_NAME


def theme_icon_for(page) -> ft.IconData:
    """The icon names the mode the tap LANDS ON (the cycle's next mode)."""
    mode = getattr(page, "theme_mode", ft.ThemeMode.SYSTEM) if page else ft.ThemeMode.SYSTEM
    return THEME_ICONS.get(next_theme_mode(mode), ft.Icons.DARK_MODE_ROUNDED)


def _cycle_theme(page, controller) -> ft.IconData:
    """DARK -> LIGHT -> SYSTEM -> DARK, persisted. Returns the icon that
    now names the mode the NEXT tap lands on."""
    if page is None:
        return ft.Icons.DARK_MODE_ROUNDED
    app_controller = getattr(controller, "_app_controller", None)
    nxt = next_theme_mode(getattr(page, "theme_mode", ft.ThemeMode.SYSTEM))
    page.theme_mode = nxt
    if app_controller is not None:
        from core.tasks import spawn

        spawn(app_controller.save_theme_mode(nxt), name="save-theme")
    return THEME_ICONS.get(next_theme_mode(nxt), ft.Icons.DARK_MODE_ROUNDED)


def _version_pill(state, page) -> ft.Control:
    """Quiet "vX.Y.Z" normally; morphs into the update pill when the boot
    check found a newer build."""
    update_data = state.update_data if state.update_available else None
    if update_data:
        from components.update_dialog import show_update_dialog

        return ft.Container(
            content=ft.Row(
                [
                    ft.Text(
                        "Update Available!",
                        size=11,
                        weight=ft.FontWeight.BOLD,
                        color=AppColors.PRIMARY,
                        no_wrap=True,
                    ),
                    ft.Container(width=6, height=6, border_radius=3, bgcolor=AppColors.PRIMARY),
                ],
                spacing=4,
                alignment=ft.MainAxisAlignment.CENTER,
                tight=True,
            ),
            padding=ft.Padding.symmetric(horizontal=8, vertical=6),
            border_radius=6,
            bgcolor=ft.Colors.with_opacity(0.15, AppColors.PRIMARY),
            border=ft.Border.all(1.5, AppColors.PRIMARY),
            ink=True,
            tooltip="A new version is available",
            on_click=lambda e: show_update_dialog(page, update_data) if page else None,
        )
    return ft.Container(
        content=ft.Text(f"v{APP_VERSION}", size=11, color=ft.Colors.ON_SURFACE_VARIANT),
        padding=ft.Padding.symmetric(horizontal=8, vertical=6),
        border_radius=6,
        border=ft.Border.all(1, ft.Colors.with_opacity(0.2, ft.Colors.ON_SURFACE_VARIANT)),
        tooltip="Version",
    )


def _backend_badge(state, controller) -> ft.Control:
    """The clickable backend badge: which provider is serving, with a state
    colour from its live health. Tapping opens the picker for one-tap
    switching. There is no "auto" label — the badge shows the provider that
    IS serving (the splash covers the app until one resolves)."""
    name = (state.current_source_name or "").strip()
    label = name.capitalize() if name else ""
    colour = AppColors.SUCCESS if name else ft.Colors.ON_SURFACE_VARIANT
    return ft.Container(
        content=ft.Row(
            [
                ft.Container(width=8, height=8, border_radius=4, bgcolor=colour),
                ft.Container(width=6),
                ft.Text(label or "…", size=12, weight=ft.FontWeight.W_700, no_wrap=True),
            ],
            spacing=0,
            tight=True,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding.symmetric(horizontal=10, vertical=6),
        border_radius=14,
        bgcolor=ft.Colors.with_opacity(0.1, colour),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.35, colour)),
        ink=True,
        tooltip=f"Served by {label} — tap to switch" if label else "Choosing a source…",
        on_click=lambda e: controller.open_backend_picker(),
    )


def app_header(
    state,
    page,
    controller,
    *,
    subtitle: str = "",
    extra_actions: list[ft.Control] | None = None,
    on_theme=None,
) -> ft.Control:
    """The shared header. ``subtitle`` names the screen ("Settings",
    "Downloads"); ``extra_actions`` are the screen's own buttons, rendered
    left of the theme cycle inside the scrolling group."""

    def _action(icon, tip, handler, colour=None) -> ft.Control:
        return ft.Container(
            content=ft.Icon(icon, color=colour or ft.Colors.ON_SURFACE, size=20),
            padding=10,
            border_radius=10,
            ink=True,
            tooltip=tip,
            on_click=handler,
        )

    def _default_theme(_e=None):
        icon = _cycle_theme(page, controller)
        # The header may live inside a frozen component subtree, so the
        # action repaints its OWN icon instead of relying on a re-render.
        theme_action.content.icon = icon
        with contextlib.suppress(Exception):
            theme_action.update()
        if page is not None:
            with contextlib.suppress(Exception):
                page.update()
        if on_theme is not None:
            on_theme(icon)

    theme_action = _action(theme_icon_for(page), "Switch theme", _default_theme)

    right = ft.Row(
        [
            _backend_badge(state, controller),
            _version_pill(state, page),
            *(extra_actions or []),
            theme_action,
        ],
        spacing=4,
        tight=True,
        scroll=ft.ScrollMode.AUTO,  # Sherlock's rule: scroll, never clip.
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    left = ft.Row(
        [
            ft.Image(src="icon.png", width=32, height=32, fit="contain"),
            ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Text(
                                    backend_title(state),
                                    size=18,
                                    weight=ft.FontWeight.W_800,
                                    color=ft.Colors.ON_SURFACE,
                                    no_wrap=True,
                                ),
                                ft.Icon(
                                    ft.Icons.ARROW_DROP_DOWN,
                                    size=20,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                            ],
                            spacing=2,
                            tight=True,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Text(
                            subtitle,
                            size=10,
                            color=ft.Colors.with_opacity(0.55, ft.Colors.ON_SURFACE),
                            visible=bool(subtitle),
                        ),
                    ],
                    spacing=0,
                    tight=True,
                ),
                padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                border_radius=10,
                ink=True,
                tooltip="Change content source",
                on_click=lambda e: controller.open_backend_picker(),
            ),
        ],
        spacing=10,
        tight=True,
    )

    return ft.Container(
        padding=ft.Padding.only(left=16, right=16, top=12, bottom=8),
        content=ft.Row(
            [left, right],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )
