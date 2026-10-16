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
    from components.app_header import backend_title

    assert backend_title(_State("anikato")) == "Anikato TV"
    assert backend_title(_State("animepahe")) == "Animepahe TV"
    # Nothing resolved yet: the brand name stands in.
    from core.constants import APP_NAME

    assert backend_title(_State("")) == APP_NAME
    assert backend_title(_State("  ")) == APP_NAME


def test_the_title_pill_is_the_picker_and_the_gate_offers_a_swap():
    from components import app_header, offline_state

    source = inspect.getsource(app_header)
    # The tappable title pill exists with the dropdown affordance (now in
    # the SHARED header, so every screen's title is the switcher)…
    assert "backend_title(state)" in source
    assert "ARROW_DROP_DOWN" in source
    # …and the wall is escapable from the gate card itself. The card is one
    # shared builder (offline_state.cf_gate_card) — Home renders it through
    # its scrim, the detail screen inline, so the two can never drift.
    card = inspect.getsource(offline_state)
    assert 'content="Change source"' in card
    assert "LBL_CF_VERIFY_BUTTON" in card
    assert "cf_gate_card" in inspect.getsource(home), "Home renders the shared card"


def test_the_gate_scrims_the_content_not_the_header():
    source = inspect.getsource(home)
    assert "_cf_gate(content" in source, "the scrim wraps the content column"
    # The old call site scrimmed the whole body (header included); the
    # function's own `def _cf_gate(body, …)` signature is not a call site.
    assert "return _cf_gate(body" not in source
    # The header is composed into the returned column AFTER the gate wraps
    # only the content.
    tail = source[source.index("if state.cf_blocked:") :]
    # Home composes the SHARED header after the gate wraps the content:
    # the header (with the backend switcher) stays live above the scrim.
    assert "_home_header(state, page, controller)" in tail
