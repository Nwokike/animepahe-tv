"""Focus-styling helpers — the KTV pattern ported to flet 1.0.4.

The pair of constraints these tests pin:
1. In flet 1.0.4 only the Button family (plus TextField/Switch/Checkbox/
   Radio/Slider/Dropdown) has on_focus/on_blur and per-state sides — a
   Container card is D-pad-unreachable, so cards must be flat buttons.
2. The focus cue is declarative: FOCUSED side in the ButtonStyle plus an
   animate_scale declaration, with on_focus/on_blur moving `scale`.
"""

import flet as ft

from components.focus_styles import (
    attach_focus_zoom,
    card_button_style,
    card_focus_scale,
)
from core.theme import AppColors


def test_focused_side_is_primary_and_thicker_than_default():
    style = card_button_style()
    sides = style.side
    assert sides[ft.ControlState.FOCUSED].width == 2.5
    assert sides[ft.ControlState.FOCUSED].color == AppColors.PRIMARY
    assert sides[ft.ControlState.DEFAULT].width == 1.0
    # Transparent so the artwork shows through.
    assert style.bgcolor == ft.Colors.TRANSPARENT
    assert style.elevation == 0


def test_focused_overlay_is_the_primary_tint():
    style = card_button_style(overlay_alpha=0.5)
    overlay = style.overlay_color[ft.ControlState.FOCUSED]
    assert overlay == ft.Colors.with_opacity(0.5, AppColors.PRIMARY)


def test_style_validation():
    for bad in (-0.1, 1.5):
        try:
            card_button_style(overlay_alpha=bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected ValueError for overlay_alpha={bad}")
    try:
        card_button_style(radius=-1)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for negative radius")


def test_focus_scale_is_a_declared_animation():
    anim = card_focus_scale()
    assert isinstance(anim, ft.Animation)
    # DurationValue keeps the int ms as given.
    assert anim.duration == 150
    assert anim.curve == ft.AnimationCurve.EASE_OUT
    try:
        card_focus_scale(0)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for scale <= 0")


def test_attach_focus_zoom_moves_scale_both_ways():
    button = ft.FilledButton(content="card")
    attach_focus_zoom(button, scale=1.05)
    assert button.scale is None  # untouched until a focus event
    button.on_focus(None)
    assert button.scale == 1.05
    button.on_blur(None)
    assert button.scale == 1.0
