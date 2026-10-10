"""Theme mode must round-trip through the durable store, and both themes
must carry the full surface ladder (the cards now read scheme colors like
``ft.Colors.ON_SURFACE`` / ``SURFACE_CONTAINER_HIGH``, which are only as
good as the ColorScheme that resolves them).
"""

import sys

sys.path.insert(0, __file__.rsplit("tests", 1)[0] + "src")

import asyncio

import flet as ft

from core.theme import AppTheme
from services.store import JsonStore


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


def test_theme_mode_round_trip(tmp_path, monkeypatch):
    store = JsonStore(filename=str(tmp_path / "app-state.json"))
    monkeypatch.setattr(
        "services.store._data_dir", lambda: str(tmp_path), raising=False
    )

    async def _run():
        assert await store.get_theme_mode() is None
        await store.save_theme_mode("light")
        return await store.get_theme_mode()

    assert asyncio.run(_run()) == "light"


def test_theme_names_map_every_mode():
    from main import AppController

    class _Page:
        pass

    controller = AppController(_Page())
    names = {
        ft.ThemeMode.DARK: "dark",
        ft.ThemeMode.LIGHT: "light",
        ft.ThemeMode.SYSTEM: "system",
    }
    for mode, name in names.items():
        assert controller._theme_name(mode) == name
