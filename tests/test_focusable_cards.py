"""Card builders must produce D-pad-focusable cards.

Regression coverage for the TV focus regression: every card used to be a
``ft.Container(on_click=...)``. In flet 1.0.4 a Container has no on_focus,
no on_blur and no per-state ``side`` — the remote can never focus it, so
the "focus ring" reserved by the old 4px transparent border could never
appear and the card could never be activated by D-pad. These tests assert
each builder returns a focusable Button carrying the KTV focus styling.

The focus cue is DECLARATIVE (``card_button_style``'s FOCUSED
border/overlay). The audit of 2026-10-16 pinned the house standard: KTV
removed the imperative on-focus scale mutation after the frozen-controls
crash class, so no card carries on_focus/on_blur handlers or
animate_scale any more.
"""
import sys

sys.path.insert(0, __file__.rsplit("tests", 1)[0] + "src")

import flet as ft

from core.state import LatestRelease
from screens.anime_detail_screen import _episode_card
from screens.home_screen import _release_card
from screens.search_screen import _result_card


def _release():
    return LatestRelease(
        anime_id=1,
        anime_title="Frieren",
        anime_session="sess",
        episode=3,
        snapshot="https://example/x.jpg",
        session="ep",
        created_at="",
    )


class _Anime:
    def __init__(self):
        self.title = "Frieren"
        self.poster = "https://example/p.jpg"
        self.year = 2023
        self.type = "TV"
        self.episodes = 28
        self.status = "Finished"
        self.season = "Fall"
        self.score = 9.3
        self.session = "sess"


class _Episode:
    def __init__(self):
        self.episode = 3
        self.session = "ep"
        self.snapshot = "https://example/e.jpg"
        self.duration = "24m"
        self.filler = False


def _assert_focusable_card(card, aspect=1.67):
    # A Button is the only focusable family among the card-ish controls.
    # The episode card wraps its button in a Stack (the overflow menu is a
    # sibling, not button content — see _episode_card), so unwrap it.
    if isinstance(card, ft.Stack):
        assert card.controls, "a Stack card must carry its button"
        card = card.controls[0]
    assert isinstance(card, ft.Button), type(card).__name__
    # The D-pad cue is the DECLARATIVE per-state border in card_button_style:
    # a FOCUSED side the Flutter focus system paints by itself. No
    # imperative on_focus/on_blur handler, no animate_scale (the house
    # standard after the frozen-controls crash class, 2026-10-16).
    assert card.on_focus is None
    assert card.on_blur is None
    assert card.animate_scale is None
    sides = card.style.side
    assert sides[ft.ControlState.FOCUSED].width == 2.5
    assert sides[ft.ControlState.FOCUSED].color == "#F43F5E"
    # Artwork keeps its shape on the inner container (default: the 1.67
    # landscape grid contract; the detected mode can swap it to 0.67).
    assert card.content.aspect_ratio == aspect


def test_episode_card_overflow_is_a_sibling_not_button_content():
    """The overflow menu must NOT sit inside the play button's content:
    nested, it swallowed the card's on_play and was unreachable on D-pad."""
    import flet as ft

    from screens.anime_detail_screen import _episode_card

    card = _episode_card(_Episode(), lambda a, e: None, "sess", now_playing=False)
    assert isinstance(card, ft.Stack)
    button, menu_slot = card.controls
    assert isinstance(button, ft.FilledButton)
    assert isinstance(menu_slot.content, ft.PopupMenuButton)

    # The button's own content tree carries no activatable menu.
    def _walk(control):
        yield control
        for child in getattr(control, "controls", []) or []:
            yield from _walk(child)
        content = getattr(control, "content", None)
        if content is not None:
            yield from _walk(content)

    for node in _walk(button):
        assert not isinstance(node, ft.PopupMenuButton)


def test_release_card_is_focusable():
    card = _release_card(_release(), lambda s: None, now_playing=False)
    _assert_focusable_card(card)


def test_episode_card_is_focusable():
    # Portrait now — the episode grid matches Discover's card on every
    # source (owner's order, 2026-10-16): same shape, same anatomy.
    card = _episode_card(_Episode(), lambda a, e: None, "sess", now_playing=False)
    _assert_focusable_card(card, aspect=0.67)


def test_result_card_is_focusable():
    card = _result_card(_Anime(), lambda a: None)
    assert isinstance(card, ft.Button)
    assert card.on_focus is None
    assert card.on_blur is None
    assert card.animate_scale is None
    sides = card.style.side
    assert sides[ft.ControlState.FOCUSED].width == 2.5
    assert sides[ft.ControlState.FOCUSED].color == "#F43F5E"


def test_cards_pass_col_through_for_responsive_rows():
    col = {"xs": 12, "sm": 6}
    card = _release_card(_release(), lambda s: None, now_playing=False, col=col)
    assert card.col == col


def _walk_controls(control):
    yield control
    for child in getattr(control, "controls", []) or []:
        yield from _walk_controls(child)
    content = getattr(control, "content", None)
    if content is not None:
        yield from _walk_controls(content)


def test_release_card_portrait_mode_swaps_the_shape():
    card = _release_card(_release(), lambda s: None, now_playing=False, mode="portrait")
    assert card.content.aspect_ratio == 0.67


def test_episode_card_portrait_mode_swaps_the_shape():
    card = _episode_card(_Episode(), lambda a, e: None, "sess", now_playing=False, mode="portrait")
    assert card.controls[0].content.aspect_ratio == 0.67


def test_episode_card_uses_the_series_fallback_when_the_episode_has_no_art():
    ep = _Episode()
    ep.snapshot = ""
    card = _episode_card(
        ep,
        lambda a, e: None,
        "sess",
        now_playing=False,
        fallback_src="https://example/series.jpg",
    )
    images = [n for n in _walk_controls(card.controls[0]) if isinstance(n, ft.Image)]
    assert images and images[0].src == "https://example/series.jpg"
