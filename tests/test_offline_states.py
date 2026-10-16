"""Offline retry cards — Phase 4 Step 4.

The finding: the app detects offline (home banner, search guard) while the
network-driven grids (detail episodes, discover, search results) went
quietly empty and blamed the catalogue. `empty_or_offline` now gives those
sites one honest card — "You're offline" + Retry — and returns the screen's
own empty state byte for byte when online. Downloads is deliberately NOT
wired: its list is local, offline does not empty it, and an offline card
there would be a lie.
"""

import inspect
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import flet as ft

from components.offline_state import empty_or_offline


class _State:
    def __init__(self, online):
        self.is_online = online


def _texts(control, found=None):
    found = [] if found is None else found
    if control is None:
        return found
    if isinstance(control, ft.Text):
        found.append(str(control.value))
    for attr in ("content", "controls", "actions"):
        child = getattr(control, attr, None)
        if child is None:
            continue
        if isinstance(child, list):
            for item in child:
                _texts(item, found)
        elif isinstance(child, ft.Control):
            _texts(child, found)
    return found


def _buttons(control, found=None):
    found = [] if found is None else found
    if control is None:
        return found
    if isinstance(control, ft.FilledButton):
        found.append(control)
    for attr in ("content", "controls", "actions"):
        child = getattr(control, attr, None)
        if child is None:
            continue
        if isinstance(child, list):
            for item in child:
                _buttons(item, found)
        elif isinstance(child, ft.Control):
            _buttons(child, found)
    return found


# ---------------------------------------------------------------------------
# The chooser
# ---------------------------------------------------------------------------


def test_offline_renders_the_card_and_retry_fires():
    retries = []
    control = empty_or_offline(
        _State(online=False),
        title="No episodes found",
        message="release blurb",
        icon=ft.Icons.MOVIE_FILTER_ROUNDED,
        on_retry=lambda e: retries.append(True),
    )
    texts = _texts(control)
    assert "You're offline" in texts
    assert "No episodes found" not in texts, "the catalogue is not blamed"
    buttons = _buttons(control)
    assert len(buttons) == 1
    buttons[0].on_click(None)
    assert retries == [True]


def test_online_returns_the_screens_own_empty_state():
    control = empty_or_offline(
        _State(online=True),
        title="No episodes found",
        message="release blurb",
        icon=ft.Icons.MOVIE_FILTER_ROUNDED,
        on_retry=lambda e: None,
    )
    texts = _texts(control)
    assert "No episodes found" in texts and "release blurb" in texts
    assert "You're offline" not in texts
    # The caller's action now rides the online empty too (it is the only
    # way a screen can offer something better than "nothing matched" —
    # e.g. the detail screen's "Switch to Animepahe"). A caller with no
    # action still gets a bare card.
    buttons = _buttons(control)
    assert len(buttons) == 1 and "Retry" in " ".join(_texts(buttons[0]))

    bare = empty_or_offline(
        _State(online=True), title="Nothing matched", message="loosen a filter"
    )
    assert _buttons(bare) == []


def test_a_state_without_is_online_reads_as_online():
    control = empty_or_offline(object(), title="Nothing matched")
    assert "Nothing matched" in _texts(control)


def test_the_offline_card_omits_retry_when_there_is_no_callback():
    control = empty_or_offline(_State(online=False), title="x")
    assert _buttons(control) == []


# ---------------------------------------------------------------------------
# The wiring can't silently disappear
# ---------------------------------------------------------------------------


def test_the_network_grids_use_the_chooser():
    import screens.anime_detail_screen as detail
    import screens.discover_screen as discover
    import screens.search_screen as search

    for module in (detail, discover, search):
        source = inspect.getsource(module)
        assert "empty_or_offline(" in source, module.__name__
    # Downloads is local data — it must NOT claim offline.
    import screens.downloads_screen as downloads

    assert "empty_or_offline" not in inspect.getsource(downloads)
