"""Theme mode must round-trip through the durable store, and both themes
must carry the full surface ladder (the cards now read scheme colors like
``ft.Colors.ON_SURFACE`` / ``SURFACE_CONTAINER_HIGH``, which are only as
good as the ColorScheme that resolves them).
"""

import sys

sys.path.insert(0, __file__.rsplit("tests", 1)[0] + "src")

import asyncio

import flet as ft

from core.theme import AppTheme, mode_for_token, next_theme_mode, token_for_mode
from services.store import JsonStore


def test_both_themes_carry_every_slot_the_ui_uses():
    """The shell renders a NavigationBar and app bars; both schemes must
    theme them (an unthemed NavigationBar gets Material's purple tint in
    light mode) and pin one page transition so a tab tap feels the same
    on every OS."""
    for theme in (AppTheme.get_dark_theme(), AppTheme.get_light_theme()):
        nav = theme.navigation_bar_theme
        assert nav is not None and nav.bgcolor, "the nav bar has no themed background"
        assert nav.indicator_color, "the nav bar has no selection indicator"
        appbar = theme.appbar_theme
        assert appbar is not None and appbar.bgcolor, "the app bar has no themed background"
        assert appbar.title_text_style is not None
        transitions = theme.page_transitions
        assert transitions is not None
        for platform in ("android", "ios", "linux", "macos", "windows"):
            assert getattr(transitions, platform) == ft.PageTransitionTheme.CUPERTINO


def test_both_themes_carry_surface_roles():
    for theme in (AppTheme.get_dark_theme(), AppTheme.get_light_theme()):
        scheme = theme.color_scheme
        for role in (
            "surface",
            "surface_container",
            "surface_container_high",
            "surface_container_highest",
            "on_surface",
            "on_surface_variant",
            "outline",
        ):
            assert getattr(scheme, role), f"{role} must be pinned to the palette"


def test_themes_differ_on_surface_and_on_surface():
    dark = AppTheme.get_dark_theme().color_scheme
    light = AppTheme.get_light_theme().color_scheme
    assert dark.surface != light.surface
    assert dark.on_surface != light.on_surface


def test_theme_mode_round_trip(tmp_path):
    store = JsonStore(filename=str(tmp_path / "app-state.json"))

    async def _run():
        assert await store.get_theme_mode() is None
        await store.save_theme_mode("light")
        return await store.get_theme_mode()

    assert asyncio.run(_run()) == "light"


def test_theme_names_map_every_mode():
    """token <-> mode is one mapping, shared by the store name, the
    settings picker highlight, and the header cycle — so it is tested
    here as data, not per call site."""
    names = {
        ft.ThemeMode.DARK: "dark",
        ft.ThemeMode.LIGHT: "light",
        ft.ThemeMode.SYSTEM: "system",
    }
    for mode, name in names.items():
        assert token_for_mode(mode) == name
        assert mode_for_token(name) is mode
    # Unknown values degrade, never raise.
    assert token_for_mode(None) == "system"
    assert mode_for_token("banana") is ft.ThemeMode.SYSTEM


def test_theme_cycle_order_is_shared():
    assert next_theme_mode(ft.ThemeMode.DARK) is ft.ThemeMode.LIGHT
    assert next_theme_mode(ft.ThemeMode.LIGHT) is ft.ThemeMode.SYSTEM
    assert next_theme_mode(ft.ThemeMode.SYSTEM) is ft.ThemeMode.DARK
    assert next_theme_mode(None) is ft.ThemeMode.SYSTEM


def test_system_resolves_through_platform_brightness():
    """The one branch every mode-dependent decision shares: SYSTEM is the
    platform's answer, and an unknown platform is dark (a TV default)."""
    from core.theme import AppColors

    assert AppColors.is_dark_mode(ft.ThemeMode.DARK, ft.Brightness.LIGHT) is True
    assert AppColors.is_dark_mode(ft.ThemeMode.LIGHT, ft.Brightness.DARK) is False
    assert AppColors.is_dark_mode(ft.ThemeMode.SYSTEM, ft.Brightness.DARK) is True
    assert AppColors.is_dark_mode(ft.ThemeMode.SYSTEM, ft.Brightness.LIGHT) is False
    assert AppColors.is_dark_mode(None, None) is True
