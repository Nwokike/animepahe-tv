"""One empty-state chooser: offline is its own answer.

The offline audit finding: the app detects offline (home banner, search
guard) while discover / detail / search just went quietly empty — the
screen blamed the catalogue for the network. This chooser gives every
network-driven grid the same honest card ("You're offline" + Retry) and
otherwise returns the screen's own EmptyState byte for byte. It is plain
(no hooks) like EmptyState itself, so it is testable without a renderer.

The same module carries the Cloudflare card: every screen that can meet
the wall (Home through its scrim, the detail screen inline) shows the
SAME control — Verify, spinner while the challenge runs, and the
"Change source" escape — so the wall never reads as an empty catalogue.
"""

import flet as ft

from components.empty_state import EmptyState
from core.constants import LBL_CF_BLOCKED_BODY, LBL_CF_BLOCKED_TITLE, LBL_CF_VERIFY_BUTTON
from core.theme import AppColors


def cf_gate_card(state, controller, *, width: int = 320) -> ft.Control:
    """The SHIELD card: Verify (with the busy spinner) + Change source.

    One builder for every screen — the home scrim and the detail screen's
    inline card must never drift apart. `state.cf_retrying` flips the
    button into its spinner for the whole re-challenge.
    """
    retrying = bool(getattr(state, "cf_retrying", False))
    return ft.Container(
        content=ft.Column(
            [
                ft.Container(
                    content=ft.Icon(ft.Icons.SHIELD_ROUNDED, size=64, color=AppColors.PRIMARY),
                    alignment=ft.Alignment.CENTER,
                ),
                ft.Container(height=8),
                ft.Text(
                    LBL_CF_BLOCKED_TITLE,
                    size=20,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.ON_SURFACE,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Container(height=4),
                ft.Text(
                    LBL_CF_BLOCKED_BODY,
                    size=13,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Container(height=20),
                ft.FilledButton(
                    content=ft.ProgressRing(
                        width=16, height=16, stroke_width=2, color=ft.Colors.WHITE
                    )
                    if retrying
                    else LBL_CF_VERIFY_BUTTON,
                    icon=None if retrying else ft.Icons.VERIFIED_ROUNDED,
                    disabled=retrying,
                    style=ft.ButtonStyle(
                        bgcolor=AppColors.PRIMARY,
                        color=ft.Colors.WHITE,
                        shape=ft.RoundedRectangleBorder(radius=10),
                    ),
                    on_click=lambda e: controller.retry_cloudflare(),
                ),
                ft.Container(height=6),
                # The wall must never trap the user: swapping sources is
                # one tap from the card itself (the header's title/arrow
                # and badge do the same).
                ft.TextButton(
                    content="Change source",
                    on_click=lambda e: controller.open_backend_picker(),
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=0,
            tight=True,
        ),
        padding=32,
        width=width,
        border_radius=20,
        bgcolor=ft.Colors.SURFACE,
        border=ft.Border.all(1, ft.Colors.OUTLINE),
        shadow=ft.BoxShadow(
            blur_radius=30,
            color=ft.Colors.with_opacity(0.4, ft.Colors.BLACK),
            offset=ft.Offset(0, 10),
        ),
    )


def cf_reason(state) -> str:
    """One honest sentence for why the wall is up on a catalog-only
    source (the provider's own host answers the challenge)."""
    source = (getattr(state, "current_source_name", "") or "this source").strip()
    return (
        f"{source.capitalize()} asks every device to prove it's human before "
        "its catalogue loads. Press Verify once — the session keeps the "
        "clearance afterwards."
    )


def empty_or_offline(
    state,
    *,
    title: str,
    message: str = "",
    icon: ft.IconData | None = None,
    on_retry=None,
    action_label: str | None = None,
    on_downloads=None,
) -> ft.Control:
    """The offline card when `state.is_online` is False, else the screen's
    own empty state. Missing `is_online` reads as online (a fake or a
    light state object must never render an offline card by accident).

    ``action_label`` names a caller's own action (e.g. "Switch to
    Animepahe"); without it a retry shows as "Retry", and no handler means
    no button at all.
    """
    if not getattr(state, "is_online", True):
        return EmptyState(
            "You're offline",
            message="Check your connection, or continue in offline mode with your downloaded episodes.",
            action_label="Retry Connection" if on_retry else None,
            on_action=on_retry,
            secondary_label="View Downloads" if on_downloads else None,
            on_secondary=on_downloads,
            icon=ft.Icons.CLOUD_OFF_ROUNDED,
            autofocus_action=True,
        )
    label = action_label or ("Retry" if on_retry else None)
    return EmptyState(
        title,
        message=message,
        icon=icon,
        action_label=label,
        on_action=on_retry,
        autofocus_action=bool(on_retry),
    )
