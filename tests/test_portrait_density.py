"""Portrait density regressions — Step 5.

Pins the dials matching nkiri-tv:
- Search and Discover grids use 16px spacing and 24px horizontal screen insets.
- Portrait card_frame defaults to 8px insets (matching nkiri's card padding)
  while landscape cards keep 4px.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import flet as ft

from components.artwork_card import card_frame
from core.artwork import LANDSCAPE, PORTRAIT


def test_card_frame_density_by_mode():
    media = ft.Container()
    portrait_card = card_frame(mode=PORTRAIT, media=media, overlay=[], on_click=lambda e: None)
    landscape_card = card_frame(mode=LANDSCAPE, media=media, overlay=[], on_click=lambda e: None)

    # card_frame returns a Button wrapped by attach_focus_zoom
    assert portrait_card.style.padding == 8
    assert landscape_card.style.padding == 4


def test_search_and_discover_grid_spacing_and_insets():
    import inspect

    import screens.discover_screen as discover
    import screens.search_screen as search

    search_src = inspect.getsource(search)
    assert "spacing=16" in search_src
    assert "run_spacing=16" in search_src
    assert "left=24, right=24" in search_src

    discover_src = inspect.getsource(discover)
    assert "spacing=16" in discover_src
    assert "run_spacing=16" in discover_src
    assert "left=24, right=24" in discover_src
