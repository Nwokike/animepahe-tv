"""Pagination pills — the original's 15/10 padding, radius 10, 1.5 PRIMARY
border, icon+text craft.

The 1.0.9 build drew these as ``Container(ink=True)``; in flet 1.0.4 a
Container can't take D-pad focus, so the pill is an ``OutlinedButton``
styled flat instead — same visual contract (border recolours to
ON_SURFACE_VARIANT when the direction is unavailable), plus a real focus
ring from the FOCUSED side.
"""

import flet as ft

from components.focus_styles import attach_focus_zoom
from core.theme import AppColors


def page_pill(
    label: str,
    icon: str,
    on_click,
    enabled: bool,
) -> ft.Control:
    """One pill. Disabled directions keep their place but recolour."""
    return attach_focus_zoom(
        ft.OutlinedButton(
            content=ft.Row(
                [
                    ft.Icon(
                        icon,
                        size=16,
                        color=ft.Colors.ON_SURFACE_VARIANT
                        if not enabled
                        else ft.Colors.ON_SURFACE,
                    ),
                    ft.Text(
                        label,
                        size=13,
                        weight=ft.FontWeight.W_500,
                        color=ft.Colors.ON_SURFACE_VARIANT
                        if not enabled
                        else ft.Colors.ON_SURFACE,
                    ),
                ],
                spacing=8,
                tight=True,
            ),
            style=ft.ButtonStyle(
                padding=ft.Padding(15, 10, 15, 10),
                shape=ft.RoundedRectangleBorder(radius=10),
                bgcolor=ft.Colors.TRANSPARENT,
                color=ft.Colors.ON_SURFACE,
                side={
                    ft.ControlState.DEFAULT: ft.BorderSide(1.5, AppColors.PRIMARY),
                    ft.ControlState.FOCUSED: ft.BorderSide(2.5, AppColors.PRIMARY),
                    ft.ControlState.HOVERED: ft.BorderSide(
                        2.0, ft.Colors.with_opacity(0.6, AppColors.PRIMARY)
                    ),
                    ft.ControlState.DISABLED: ft.BorderSide(
                        1.5,
                        ft.Colors.with_opacity(0.25, AppColors.PRIMARY),
                    ),
                },
                overlay_color={
                    ft.ControlState.FOCUSED: ft.Colors.with_opacity(
                        0.2, AppColors.PRIMARY
                    ),
                    ft.ControlState.HOVERED: ft.Colors.with_opacity(
                        0.1, AppColors.PRIMARY
                    ),
                },
                elevation=0,
            ),
            disabled=not enabled,
            on_click=on_click,
        )
    )


def pager(
    *,
    page: int,
    has_more: bool,
    on_prev,
    on_next,
    is_loading: bool = False,
) -> ft.Control:
    """Prev pill · page indicator (spinner while loading) · Next pill."""
    indicator = (
        ft.ProgressRing(width=16, height=16, stroke_width=2, color=AppColors.PRIMARY)
        if is_loading
        else ft.Text(
            f"Page {page}",
            size=13,
            weight=ft.FontWeight.W_500,
            color=ft.Colors.ON_SURFACE,
        )
    )
    return ft.Row(
        [
            page_pill(
                "Prev",
                ft.Icons.ARROW_BACK_IOS_NEW_ROUNDED,
                on_prev,
                page > 1,
            ),
            indicator,
            page_pill(
                "Next",
                ft.Icons.ARROW_FORWARD_IOS_ROUNDED,
                on_next,
                has_more,
            ),
        ],
        alignment=ft.MainAxisAlignment.CENTER,
        spacing=16,
    )


__all__ = ["page_pill", "pager"]
