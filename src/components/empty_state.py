"""EmptyState — centered icon + title + optional message + optional action.

Plain function (not ``@ft.component``) — no hooks needed, testable without
a renderer context. Ported from the house standard (KTV/Sherlock).
"""

from collections.abc import Callable

import flet as ft

from core.theme import AppColors


def EmptyState(
    title: str,
    message: str = "",
    action_label: str | None = None,
    on_action: Callable | None = None,
    icon: ft.IconData | None = None,
    autofocus_action: bool = False,
) -> ft.Control:
    items = [
        ft.Icon(
            icon or ft.Icons.INBOX_ROUNDED,
            size=64,
            color=ft.Colors.ON_SURFACE_VARIANT,
            semantics_label=title,
        ),
        ft.Text(
            title,
            size=20,
            weight=ft.FontWeight.W_600,
            color=ft.Colors.ON_SURFACE,
            text_align=ft.TextAlign.CENTER,
            max_lines=2,
            overflow=ft.TextOverflow.ELLIPSIS,
        ),
    ]
    if message:
        items.append(
            ft.Text(
                message,
                size=14,
                color=ft.Colors.ON_SURFACE_VARIANT,
                text_align=ft.TextAlign.CENTER,
                width=320,
                max_lines=4,
                overflow=ft.TextOverflow.ELLIPSIS,
            )
        )
    if action_label and on_action:
        items.append(
            ft.FilledButton(
                content=ft.Text(action_label),
                on_click=on_action,
                autofocus=autofocus_action,
                style=ft.ButtonStyle(
                    bgcolor=AppColors.PRIMARY,
                    color=ft.Colors.WHITE,
                    shape=ft.RoundedRectangleBorder(radius=10),
                ),
            )
        )
    return ft.Container(
        expand=True,
        alignment=ft.Alignment.CENTER,
        content=ft.Column(
            items,
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=12,
        ),
    )
