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

from screens.search_screen import _row_title_session


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
