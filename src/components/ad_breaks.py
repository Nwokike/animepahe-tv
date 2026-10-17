"""Grid ad breaks — the owner's rule, in one place.

Every grid in the app is chunked into blocks of ``AD_EVERY`` (12) cards
with a banner between blocks: KTV's page shape (grid → banner → pager)
applied at 12-item granularity, on Home, Discover, Search and the episode
grid. The break is a full-width sibling of the `ResponsiveRow` chunks, so
an ad can never break a row.

``page`` may be None (a render without a page context); the banner
builder already degrades to a zero-size control on non-mobile platforms,
so a failed lookup is never a crash.
"""

import flet as ft

from components.banner_ad import build_banner_ad

AD_EVERY = 12


def grid_with_ads(
    cards: list[ft.Control],
    page,
    *,
    every: int = AD_EVERY,
    spacing: int = 16,
    run_spacing: int = 16,
) -> list[ft.Control]:
    """ResponsiveRow chunks with a banner between them."""
    sections: list[ft.Control] = []
    for start in range(0, len(cards), every):
        chunk = cards[start : start + every]
        if start:
            sections.append(build_banner_ad(page, inline=True))
        sections.append(ft.ResponsiveRow(controls=chunk, spacing=spacing, run_spacing=run_spacing))
    return sections
