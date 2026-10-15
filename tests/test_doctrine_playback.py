"""Phase 2 Step 4 — playback never hops backends on its own.

The automatic title-hop inside _play_episode_resolve is gone (it produced
the bogus ktv:// launch and the CF-churn cascade in the live log).
Owner-empty playback is an honest result. The detail screen's old manual
"Try another source" button was removed on the owner's order (2026-10-15,
it did not work): switching backends happens in the header — the
"<Backend> TV ▾" title pill and the badge picker — and nowhere else.
"""

import inspect
import os
import sys
import textwrap

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import main as app_main  # noqa: E402


def test_playback_resolution_has_no_automatic_title_hop():
    source = textwrap.dedent(
        inspect.getsource(app_main.AppController._play_episode_resolve)
    )
    assert "sources_for_title_any" not in source, (
        "owner-empty playback must never ask another backend on its own"
    )
    assert "This source has no playable stream for this episode." in source


def test_the_detail_screen_has_no_source_switcher():
    import screens.anime_detail_screen as detail

    source = inspect.getsource(detail)
    assert "try_another_source" not in source, (
        "the header's title pill / badge picker is the only switcher"
    )
    assert "Try another source" not in source
