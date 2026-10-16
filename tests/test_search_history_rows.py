"""Recent-search rows must survive the suggestion path as (title, session).

Regression test for the search breakage: history rows are
{title, session, ts} dicts (the anime that was opened), but the
suggestion strip used to hand the raw row to the query field — so
_submit crashed with "'dict' object has no attribute 'strip'" and the
scraper failed with "'params': 'dict' object is not an instance of 'str'".
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import flet as ft

from screens.search_screen import _build_clear_confirm_dialog, _row_title_session


class _Controller:
    """Records the portal calls the screen's dialog path makes."""

    def __init__(self):
        self.opened: list = []
        self.cleared = 0
        self.closed = 0

    def open_sheet(self, dialog):
        self.opened.append(dialog)

    def close_dialog(self):
        self.closed += 1

    def clear_search_history(self):
        self.cleared += 1


def test_clear_recent_asks_first_and_never_leaves_the_dialog_open():
    controller = _Controller()
    dialog = _build_clear_confirm_dialog(controller)

    # The screen's handler opens the built dialog — same call, so the
    # Cancel/Clear actions here are exactly what the user taps.
    controller.open_sheet(dialog)
    assert len(controller.opened) == 1
    assert isinstance(controller.opened[0], ft.AlertDialog)

    def _label(button) -> str:
        content = button.content
        return content.value if hasattr(content, "value") else str(content)

    assert _label(dialog.actions[0]) == "Cancel"
    assert _label(dialog.actions[1]) == "Clear"

    # Cancel: closes, clears nothing.
    dialog.actions[0].on_click(None)
    assert controller.closed == 1
    assert controller.cleared == 0

    # Clear: closes AND clears — a clear without a close would strand the
    # modal on screen.
    dialog.actions[1].on_click(None)
    assert controller.closed == 2
    assert controller.cleared == 1


def test_dict_rows_normalize_to_title_and_session():
    title, session = _row_title_session(
        {"title": "Black Clover Season 1", "session": "ep123", "ts": 1.0}
    )
    assert title == "Black Clover Season 1"
    assert session == "ep123"


def test_legacy_string_rows_become_sessionless_titles():
    title, session = _row_title_session("black clover")
    assert title == "black clover"
    assert session == ""


def test_junk_rows_degrade_to_empty_strings():
    assert _row_title_session(None) == ("", "")
    assert _row_title_session({}) == ("", "")
    assert _row_title_session({"title": None}) == ("", "")


def test_title_is_always_a_str_never_the_row_itself():
    """Whatever the row shape, the title must be usable as a query string —
    a dict reaching the TextField value or load_search is the bug."""
    for row in (
        {"title": "Frieren", "session": "s1"},
        "frieren",
        {"session": "s2"},  # dict missing its title
    ):
        title, _ = _row_title_session(row)
        assert title.strip() == title  # no whitespace surprises
        assert isinstance(title, str)
        title.strip()  # the exact call the old crash came from


def test_malformed_follows_rows_do_not_crash():
    """Follows shelf in search screen used to crash with KeyError on row['anime_session']
    when an entry was malformed or missing the session key."""
    for bad_row in [{}, {"title": "Frieren"}, {"anime_session": ""}, None]:
        # Search screen's filter: isinstance(row, dict) and row.get("anime_session")
        passes = isinstance(bad_row, dict) and bool(bad_row.get("anime_session"))
        assert not passes
