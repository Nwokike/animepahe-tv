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


# ---------------------------------------------------------------------------
# 2026-10-19 — the owner's header pass: live version pill, badge on wide only
# ---------------------------------------------------------------------------


def test_the_version_pill_is_always_tappable():
    """'If you check my other apps here in the fort, the version number is
    clickable with change log. Maybe we have to wire that too.' Both states
    of the pill must carry a click handler: the update state opens the
    update dialog, the quiet state opens the bundled changelog."""
    from components import app_header

    source = inspect.getsource(app_header)
    # The house's own tooltip wording (Sherlock/DDGS/KTV all use it).
    assert 'tooltip="What\'s New — version & changelog"' in source
    # The quiet pill's destination is the up-to-date dialog (no data).
    assert "show_update_dialog(page, None)" in source
    # The update state opens the update dialog with its data.
    assert "show_update_dialog(page, update_data)" in source


def test_the_up_to_date_dialog_serves_the_bundled_changelog():
    from components import update_dialog
    from core.changelog import latest_version, notes_for

    # The changelog is bundled (works offline) and keyed by APP_VERSION.
    from core.constants import APP_VERSION

    assert latest_version() == APP_VERSION
    assert notes_for(APP_VERSION)
    # The dialog's up-to-date branch reads the bundle.
    assert "notes_for(APP_VERSION)" in inspect.getsource(update_dialog)
    assert "You're up to date" in inspect.getsource(update_dialog)
    assert "update_data: dict | None = None" in inspect.getsource(
        update_dialog
    ).replace("update_data: dict | None = None", "update_data: dict | None = None")


def test_the_redundant_badge_is_hidden_on_a_narrow_screen():
    """'The version... and also anime out TV that can be clicked... should we
    remove one so that the space will be enough for small phones? For big
    screens, leave it as it is.' The title pill and the badge open the same
    picker, so the badge rides only at/above the tablet breakpoint."""
    from components import app_header
    from core.tokens import BREAKPOINT_TABLET

    source = inspect.getsource(app_header)
    assert "BREAKPOINT_TABLET" in source
    # Badge on wide, a zero-size container on narrow — never clipping.
    assert "ft.Container(width=0, height=0)" in source
    assert BREAKPOINT_TABLET == 600
