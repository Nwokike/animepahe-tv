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
    """The grids ride the shared ad-break helper (12 per chunk, banner
    between) at the house 16px density, and the screens keep their 24px
    insets."""
    import inspect

    import screens.discover_screen as discover
    import screens.search_screen as search
    from components import ad_breaks

    helper = inspect.getsource(ad_breaks)
    # The density is the ONE token, not a per-screen literal (owner, 2026-10-19:
    # "fix once and it's solved everywhere").
    assert "spacing: int = GRID_SPACING" in helper
    assert "run_spacing: int = GRID_RUN_SPACING" in helper
    # One ad every 24 cards (KTV's AD_ROW_INTERVAL), by the shared constant.
    assert "AD_EVERY = 24" in helper
    from core.tokens import GRID_COL, GRID_RUN_SPACING, GRID_SPACING

    assert GRID_COL == {"xs": 6, "sm": 4, "md": 3, "lg": 2, "xl": 2}
    assert GRID_SPACING == 16 and GRID_RUN_SPACING == 16

    search_src = inspect.getsource(search)
    assert "grid_with_ads(" in search_src, "search uses the shared grid helper"
    assert "left=24, right=24" in search_src

    discover_src = inspect.getsource(discover)
    assert "grid_with_ads(" in discover_src, "discover uses the shared grid helper"
    # The house's gutters: the filter bar owns its own 8/4 padding and the
    # page's inset is 16 (ktv-player's gutter), not the old 24.
    assert "padding=ft.Padding.only(left=16, right=16, bottom=16)" in discover_src
