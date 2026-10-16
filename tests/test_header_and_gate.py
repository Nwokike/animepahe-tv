"""Header + CF gate from the owner's live run — 2026-10-15.

Two report items made mechanical:
1. The header title is the source switcher: "<Backend> TV ▾" (tappable →
   picker), and the gate card carries a "Change source" escape, because a
   walled backend must never trap the user.
2. The CF gate scrims the CONTENT only — the header stays live (before,
   `_cf_gate` wrapped `body`, which contained the header, so the scrim
   covered the title, the badge and the actions).
"""

import inspect
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import screens.home_screen as home


class _State:
    def __init__(self, name=""):
        self.current_source_name = name


def test_the_title_names_the_active_backend():
    assert home._app_title(_State("anikato")) == "Anikato TV"
    assert home._app_title(_State("animepahe")) == "Animepahe TV"
    # Nothing resolved yet: the brand name stands in.
    assert home._app_title(_State("")) == home.APP_NAME
    assert home._app_title(_State("  ")) == home.APP_NAME


def test_the_title_pill_is_the_picker_and_the_gate_offers_a_swap():
    source = inspect.getsource(home)
    # The tappable title pill exists with the dropdown affordance…
    assert "_app_title(state)" in source
    assert "ARROW_DROP_DOWN" in source
    # …and the wall is escapable from the gate card itself.
    assert 'content="Change source"' in source


def test_the_gate_scrims_the_content_not_the_header():
    source = inspect.getsource(home)
    assert "_cf_gate(content" in source, "the scrim wraps the content column"
    # The old call site scrimmed the whole body (header included); the
    # function's own `def _cf_gate(body, …)` signature is not a call site.
    assert "return _cf_gate(body" not in source
    # The header is composed into the returned column AFTER the gate wraps
    # only the content.
    tail = source[source.index("if state.cf_blocked:") :]
    assert "_header(state, page, controller, _toggle_theme, theme_icon)" in tail
