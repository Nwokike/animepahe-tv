"""One empty-state chooser: offline is its own answer.

The offline audit finding: the app detects offline (home banner, search
guard) while discover / detail / search just went quietly empty — the
screen blamed the catalogue for the network. This chooser gives every
network-driven grid the same honest card ("You're offline" + Retry) and
otherwise returns the screen's own EmptyState byte for byte. It is plain
(no hooks) like EmptyState itself, so it is testable without a renderer.
"""

import flet as ft

from components.empty_state import EmptyState


def empty_or_offline(
    state,
    *,
    title: str,
    message: str = "",
    icon: ft.IconData | None = None,
    on_retry=None,
) -> ft.Control:
    """The offline card when `state.is_online` is False, else the screen's
    own empty state. Missing `is_online` reads as online (a fake or a
    light state object must never render an offline card by accident)."""
    if not getattr(state, "is_online", True):
        return EmptyState(
            "You're offline",
            message="Check your connection — then Retry.",
            action_label="Retry" if on_retry else None,
            on_action=on_retry,
            icon=ft.Icons.CLOUD_OFF_ROUNDED,
            autofocus_action=True,
        )
    return EmptyState(title, message=message, icon=icon)
