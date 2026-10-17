"""UI corrections from the owner's walkthrough — 2026-10-16 (night).

His report, item by item:
1. "I can't even enter any screen from the navigation bar in the anime
   detail page" — the shell set `show_nav = False` for the detail view,
   so the bottom bar/rail vanished.
2. "The episode cards are just big… the discover page looks good" — the
   episode grid must match Discover's card size on every breakpoint.
3. "Remove the 'via' in the discover page, it's already in the header."
4. "Genre, type, status, season, sort can all be dropdowns" — not a wall
   of chips.
5. "An ad after every 12, both in home, discover, in fact every screen."
6. "Your app doesn't know what a safe area is" — status-bar/notch insets.
7. Settings: house section cards with three banners (DDGS/Sherlock).
"""

import inspect
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import flet as ft

# ---------------------------------------------------------------------------
# 1. The nav bar stays on the detail view
# ---------------------------------------------------------------------------


def test_the_nav_bar_stays_visible_on_the_detail_view():
    import app_shell

    source = inspect.getsource(app_shell)
    detail_branch = source[source.index('if active_view == "anime"') :][:700]
    assert "show_nav = True" in detail_branch, (
        "hiding the nav on the detail view stranded the owner — his report"
    )
    assert "show_nav = False" not in detail_branch


# ---------------------------------------------------------------------------
# 2. SafeArea wraps the whole shell
# ---------------------------------------------------------------------------


def test_the_shell_root_is_a_safe_area():
    import app_shell

    source = inspect.getsource(app_shell)
    # Every shell return path (rail + bar) must carry the inset.
    assert source.count("ft.SafeArea(") >= 3, (
        "the rail, the full-bleed fallback and the phone bar must all be "
        "within SafeArea (house standard: KTV/Sherlock/DDGS shells)"
    )


# ---------------------------------------------------------------------------
# 3. Episode cards match Discover's sizing on every breakpoint
# ---------------------------------------------------------------------------


class _Ep:
    session = "e1"
    episode = 1
    snapshot = ""
    duration = "24m"
    filler = False
    subs = True
    dub = False


def test_episode_card_is_portrait_like_discover():
    from screens.anime_detail_screen import _episode_card

    card = _episode_card(_Ep(), lambda a, e: None, "sess", now_playing=False)
    # Stack(button, menu) — grab the button.
    button = card.controls[0]
    assert button.content.aspect_ratio == 0.67, "portrait = Discover's card shape"


def test_the_episode_grid_uses_discover_spans():
    import screens.anime_detail_screen as detail

    source = inspect.getsource(detail)
    assert '"xs": 6, "sm": 4, "md": 3, "lg": 2, "xl": 2' in source, (
        "episodes ride the Discover spans — 2 up on a phone, same on TV"
    )
    assert '"xs": 12, "sm": 6, "md": 4, "lg": 4, "xl": 3' not in source, (
        "the old one-giant-card-per-row phone layout is gone"
    )


# ---------------------------------------------------------------------------
# 4. Discover: no "via", dropdowns
# ---------------------------------------------------------------------------


def test_discover_drops_the_via_line_and_uses_dropdowns():
    import screens.discover_screen as discover

    source = inspect.getsource(discover)
    assert "via {" not in source, "the header already names the source — no 'via'"
    assert "ft.Dropdown(" in source, "filters are dropdowns"
    assert "_filter_choices" not in source, "the chip wall is gone"


# ---------------------------------------------------------------------------
# 5. Ad breaks every 12 items — one helper, every grid
# ---------------------------------------------------------------------------


def test_grid_with_ads_breaks_every_twelve(monkeypatch):
    from components import ad_breaks

    pages: list = []

    def _banner(page=None, inline=False):
        marker = ft.Container(height=50, data="ad")
        pages.append(marker)
        return marker

    monkeypatch.setattr(ad_breaks, "build_banner_ad", _banner)
    cards = [ft.Container(key=f"c{i}") for i in range(25)]
    sections = ad_breaks.grid_with_ads(cards, None, spacing=16, run_spacing=16)

    rows = [s for s in sections if isinstance(s, ft.ResponsiveRow)]
    assert [len(r.controls) for r in rows] == [12, 12, 1]
    # A break between chunks — never before the first.
    kinds = ["ad" if getattr(s, "data", None) == "ad" else "row" for s in sections]
    assert kinds == ["row", "ad", "row", "ad", "row"]


def test_every_grid_screen_uses_the_shared_helper():
    import screens.anime_detail_screen as detail
    import screens.discover_screen as discover
    import screens.home_screen as home
    import screens.search_screen as search

    for module in (home, discover, search, detail):
        assert "grid_with_ads(" in inspect.getsource(module), (
            f"{module.__name__} must ride the shared 12-item ad-break helper"
        )


# ---------------------------------------------------------------------------
# 6. Settings: three banners, house section cards
# ---------------------------------------------------------------------------


def test_settings_has_three_banners_separating_sections():
    import screens.settings_screen as settings

    source = inspect.getsource(settings)
    body = source[source.index("return ft.Column(") :]
    assert body.count("build_banner_ad(page, inline=True)") == 3, (
        "the house pattern (DDGS/Sherlock): three banners in Settings"
    )
    # Pinned order: after the source section, after Playback, before About.
    first = body.index("build_banner_ad(page, inline=True)")
    second = body.index("build_banner_ad(page, inline=True)", first + 1)
    third = body.index("build_banner_ad(page, inline=True)", second + 1)
    assert body.index('_section_header("PLAYBACK"') > first
    assert body.index('_section_header("DIAGNOSTICS"') > second
    assert body.index('_section_header("ABOUT"') > third


# ---------------------------------------------------------------------------
# 7. The detail hero is banner-first on a phone
# ---------------------------------------------------------------------------


def test_the_compact_hero_is_banner_first_and_only_under_720px():
    import screens.anime_detail_screen as detail

    source = inspect.getsource(detail)
    assert "compact = bool(page is not None and not is_tv and 0 < width < 720)" in source
    assert "compact_cover" in source and "compact_poster" in source, (
        "the compact hero is a cover with the poster over its edge"
    )
    # The poster sits INSIDE the cover's Stack (absolute over the art),
    # not in a side-by-side row.
    assert "ft.Stack(\n        [hero_cover, compact_poster]" in source
