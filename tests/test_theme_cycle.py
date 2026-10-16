"""Theme — the 3-way persisted cycle (the gap nkiri's 2-way toggle left)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import flet as ft

from core.theme import mode_from_token, next_theme_token, token_from_mode


def test_cycle_order_is_dark_light_system_dark():
    assert next_theme_token("dark") == "light"
    assert next_theme_token("light") == "system"
    assert next_theme_token("system") == "dark"


def test_junk_token_falls_back_to_system_then_cycles():
    assert next_theme_token("rainbow") == "dark"


def test_token_mode_round_trip():
    for token in ("system", "light", "dark"):
        assert token_from_mode(mode_from_token(token)) == token
    assert mode_from_token("nonsense") == ft.ThemeMode.SYSTEM
