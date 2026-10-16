"""Shared focus-aware styling for card-like tiles (KTV pattern, 1.0.4).

Cards mount through ``@ft.component`` trees, so focus cues must be
declarative too: the FOCUSED border/overlay in :func:`card_button_style`
plus an implicit ``animate_scale`` on the card control itself.

Why buttons and not containers (verified against the installed flet 1.0.4):
``ft.Container`` exposes only ``on_hover``/``on_click`` — no ``on_focus``,
no ``on_blur``, no per-state ``side``. A ``Container(on_click=...)`` card
therefore cannot receive D-pad focus at all on Android TV: the remote can
never highlight it, let alone activate it. The focusable controls in 1.0.4
are the Button family, TextField, Switch, Checkbox, Radio, Slider and
Dropdown — so a focusable card is a ``FilledButton``/``OutlinedButton``
styled flat, exactly as KTV Player does it.
"""

from __future__ import annotations

import contextlib

import flet as ft


def card_button_style(
    *,
    padding: ft.PaddingValue | None = None,
    radius: float = 16,
    overlay_alpha: float = 0.25,
) -> ft.ButtonStyle:
    """ButtonStyle for transparent cards with a D-pad focus highlight.

    Args:
        padding: inner padding of the card (defaults to 12 all around).
        radius: corner radius in logical px.
        overlay_alpha: ripple alpha for the FOCUSED state (0-1); HOVERED
            uses half, PRESSED uses full for unmistakable touch feedback.

    Raises:
        ValueError: if ``overlay_alpha`` is outside 0-1 or ``radius`` is
            negative.
    """
    if not 0 <= overlay_alpha <= 1:
        raise ValueError(f"overlay_alpha must be 0-1, got {overlay_alpha!r}")
    if radius < 0:
        raise ValueError(f"radius must be >= 0, got {radius!r}")

    from core.theme import AppColors

    primary = AppColors.PRIMARY
    return ft.ButtonStyle(
        padding=padding if padding is not None else ft.Padding.all(12),
        shape=ft.RoundedRectangleBorder(radius=radius),
        bgcolor=ft.Colors.TRANSPARENT,
        color=ft.Colors.ON_SURFACE,
        side={
            ft.ControlState.FOCUSED: ft.BorderSide(2.5, primary),
            ft.ControlState.HOVERED: ft.BorderSide(2.0, ft.Colors.with_opacity(0.6, primary)),
            ft.ControlState.PRESSED: ft.BorderSide(2.5, primary),
            ft.ControlState.DISABLED: ft.BorderSide(
                1.0, ft.Colors.with_opacity(0.12, ft.Colors.ON_SURFACE_VARIANT)
            ),
            ft.ControlState.DEFAULT: ft.BorderSide(
                1.0, ft.Colors.with_opacity(0.15, ft.Colors.ON_SURFACE_VARIANT)
            ),
        },
        overlay_color={
            ft.ControlState.FOCUSED: ft.Colors.with_opacity(overlay_alpha, primary),
            ft.ControlState.HOVERED: ft.Colors.with_opacity(overlay_alpha / 2, primary),
            ft.ControlState.PRESSED: ft.Colors.with_opacity(overlay_alpha, primary),
            ft.ControlState.DEFAULT: ft.Colors.TRANSPARENT,
        },
        elevation=0,
    )


def card_focus_scale(scale: float = 1.04) -> ft.Animation:
    """The implicit scale animation for focusable cards.

    ``scale`` is the TARGET the focus/blur handlers apply (via
    :func:`attach_focus_zoom`, which owns the setattr) — it is validated
    here so both sides agree on one number; this function contributes the
    Animation interpolation, not the scale value itself. Keep the two
    defaults in sync.

    Raises:
        ValueError: if ``scale`` is not positive.
    """
    if scale <= 0:
        raise ValueError(f"scale must be positive, got {scale!r}")
    return ft.Animation(duration=150, curve=ft.AnimationCurve.EASE_OUT)


def attach_focus_zoom(button: ft.Control, scale: float = 1.04) -> ft.Control:
    """Wire the focus/blur micro-zoom onto a card button and return it.

    Assigned after construction on the local object (KTV's documented
    idiom): the handlers close over the button itself, so the scale change
    targets the exact control the remote just focused.

    A handler the caller already installed (e.g.
    ``FocusManager.make_scroll_on_focus``) is CHAINED, not dropped —
    overwriting it silently killed the scroll-on-focus behavior.
    The setattr is guarded: a card built inside a component tree is
    frozen after mount, and the FOCUSED border from ``card_button_style``
    is the primary cue; the zoom is a bonus, never a crash.
    """
    previous_focus = getattr(button, "on_focus", None)
    previous_blur = getattr(button, "on_blur", None)

    def _on_focus(e):
        _call(previous_focus, e)
        _safe_scale(button, scale)

    def _on_blur(e):
        _call(previous_blur, e)
        _safe_scale(button, 1.0)

    button.on_focus = _on_focus
    button.on_blur = _on_blur
    return button


def _call(handler, e) -> None:
    if handler is None:
        return
    # A prior handler's failure must not break focus dispatch.
    with contextlib.suppress(Exception):
        handler(e)


def _safe_scale(button: ft.Control, value: float) -> None:
    try:
        # Nothing changed: skip the redraw entirely (the old code pushed
        # an update on every focus AND blur event).
        if getattr(button, "scale", None) == value:
            return
        button.scale = value
        button.update()
    except (RuntimeError, AttributeError):
        # frozen/unmounted (frozen raises FrozenInstanceError, an
        # AttributeError): the FOCUSED border already carries focus.
        pass


__all__ = [
    "attach_focus_zoom",
    "card_button_style",
    "card_focus_scale",
]
