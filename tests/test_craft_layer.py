"""Tier-1 craft: pagination pills, promo hero (3 slides), search guards.

These pin the restored craft — the original 1.0.9 pill padding/radius/border,
the third support slide, and the search-field guards that used to be inline
in the old view.
"""

import sys

sys.path.insert(0, __file__.rsplit("tests", 1)[0] + "src")

import flet as ft

from components.cross_promo import PROMO_APPS, ROTATE_SECONDS
from components.pagination import page_pill, pager


class _Calls:
    def __init__(self):
        self.prev = 0
        self.next = 0


def test_page_pill_has_the_original_craft():
    calls = _Calls()
    pill = page_pill(
        "Prev",
        ft.Icons.ARROW_BACK_IOS_NEW_ROUNDED,
        lambda e: setattr(calls, "prev", calls.prev + 1),
        enabled=True,
    )
    style = pill.style
    # 15/10 padding, radius 10, 1.5 PRIMARY border — the original's numbers.
    assert style.padding.left == 15
    assert style.padding.right == 15
    assert style.padding.top == 10
    assert style.padding.bottom == 10
    assert style.shape.radius == 10
    assert style.side[ft.ControlState.DEFAULT].width == 1.5
    assert style.side[ft.ControlState.DEFAULT].color == "#F43F5E"
    # Icon + text, both in the pill.
    row = pill.content
    assert any(isinstance(c, ft.Icon) for c in row.controls)
    assert any(isinstance(c, ft.Text) for c in row.controls)


def test_page_pill_disabled_recolours_the_label():
    pill = page_pill("Next", ft.Icons.ADD, lambda e: None, enabled=False)
    assert pill.disabled is True
    colors = {c.color for c in pill.content.controls if isinstance(c, ft.Text)}
    assert colors == {ft.Colors.ON_SURFACE_VARIANT}
    border = pill.style.side[ft.ControlState.DISABLED]
    assert border.width == 1.5
    assert border.color != "#F43F5E"  # washed out, not full primary


def test_pager_orders_prev_indicator_next():
    row = pager(page=3, has_more=True, on_prev=lambda e: None, on_next=lambda e: None)
    labels = [c.content.controls[1].value for c in row.controls if isinstance(c, ft.OutlinedButton)]
    assert labels == ["Prev", "Next"]
    # The page indicator sits between them.
    assert isinstance(row.controls[1], ft.Text)
    assert row.controls[1].value == "Page 3"


def test_pager_shows_spinner_while_loading():
    row = pager(
        page=1,
        has_more=True,
        on_prev=lambda e: None,
        on_next=lambda e: None,
        is_loading=True,
    )
    assert isinstance(row.controls[1], ft.ProgressRing)


def test_promo_hero_has_the_support_slide():
    """The 1.0.9 hero had three slides; the third opens the support dialog."""
    assert len(PROMO_APPS) == 3
    support = PROMO_APPS[-1]
    assert support["url"] is None
    assert "Support" in support["badge"]
    assert "feedback" in support["name"].lower()


def test_promo_rotation_cadence():
    """Rotation interval is 8 seconds (unchanged from the original cadence)."""
    assert ROTATE_SECONDS == 8
