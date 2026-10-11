"""The CF gate must overlay the live Home, not replace it.

Regression coverage for T0.8: the gate used to swap the entire Home screen
for a bare card (header, grid, Continue Watching all gone). The original
1.0.9 app kept the content behind a 60% scrim with the SHIELD card on top,
so the app never looks broken — just gated.
"""

import sys

sys.path.insert(0, __file__.rsplit("tests", 1)[0] + "src")

import flet as ft

from core.constants import (
    LBL_CF_BLOCKED_BODY,
    LBL_CF_BLOCKED_TITLE,
    LBL_CF_VERIFY_BUTTON,
)
from core.state import AppState
from screens.home_screen import _cf_gate, _cf_overlay_card


class _FakeController:
    def __init__(self):
        self.retried = 0

    def retry_cloudflare(self):
        self.retried += 1


def _walk(control):
    yield control
    for child in getattr(control, "controls", None) or []:
        yield from _walk(child)
    content = getattr(control, "content", None)
    if content is not None and not isinstance(content, list):
        yield from _walk(content)


def _overlay_card_matches(card) -> bool:
    texts = [
        c.value
        for c in _walk(card)
        if isinstance(c, ft.Text) and isinstance(c.value, str)
    ]
    texts += [
        c.content
        for c in _walk(card)
        if isinstance(c, ft.Button) and isinstance(c.content, str)
    ]
    return (
        LBL_CF_BLOCKED_TITLE in texts
        and LBL_CF_BLOCKED_BODY in texts
        and LBL_CF_VERIFY_BUTTON in texts
    )


def test_not_blocked_returns_body_untouched():
    body = ft.Column([ft.Text("Recent Episodes")])
    state = AppState()
    state.cf_blocked = False
    assert _cf_gate(body, state, _FakeController()) is body


def test_blocked_keeps_live_body_and_adds_scrim():
    body = ft.Column([ft.Text("Recent Episodes")])
    state = AppState()
    state.cf_blocked = True

    gated = _cf_gate(body, state, _FakeController())
    assert isinstance(gated, ft.Stack)
    assert gated.controls[0] is body, "the live body must stay under the scrim"

    scrim = gated.controls[1]
    assert scrim.bgcolor == ft.Colors.with_opacity(0.6, ft.Colors.BLACK)
    assert _overlay_card_matches(scrim.content)


def test_verify_button_calls_retry():
    controller = _FakeController()
    state = AppState()
    card = _cf_overlay_card(state, controller)
    button = next(
        c
        for c in _walk(card)
        if isinstance(c, ft.Button) and c.content == LBL_CF_VERIFY_BUTTON
    )
    button.on_click(None)
    assert controller.retried == 1
