"""The player spec must survive the controller -> state -> shell hop.

Regression test for the blank-player bug: main.py used to write
self._player_spec while app_shell read state.player_spec (a field that
did not exist), so the player always opened with resource="".
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.state import AppState


def test_player_spec_defaults_empty():
    state = AppState()
    assert state.player_open is False
    assert state.player_spec is None
    assert state.quality_dialog_open is False
    assert state.quality_choices is None
    assert state.pending_playback is None


def test_player_spec_round_trip():
    """What the controller writes, the shell must be able to read."""
    state = AppState()
    spec = {
        "resource": "https://cdn.example.com/index.m3u8",
        "variants": [{"label": "720p", "uri": "https://cdn.example.com/720.m3u8"}],
        "title": "Frieren",
        "episode_session": "ep123",
        "anime_session": "abc",
        "source_headers": {"User-Agent": "UA", "Referer": "https://kwik.cx/"},
    }
    state.player_spec = spec
    state.player_open = True

    # The shell reads it exactly like _build_player does.
    read = getattr(state, "player_spec", None) or {}
    assert read["resource"] == spec["resource"]
    assert read["title"] == "Frieren"
    assert read["source_headers"]["Referer"] == "https://kwik.cx/"
    assert len(read["variants"]) == 1


def test_quality_choice_flags_toggle():
    state = AppState()
    state.quality_choices = [
        {"label": "Auto (1080p)", "kind": "variant", "index": 0},
        {"label": "1080p", "kind": "variant", "index": 1},
        {
            "label": "720p - jpn (SubsPlease)",
            "kind": "source",
            "url": "https://kwik.si/e/x",
        },
    ]
    state.quality_dialog_open = True
    assert state.quality_dialog_open is True
    assert state.quality_choices[2]["kind"] == "source"
    # choose_quality clears the flag first thing.
    state.quality_dialog_open = False
    assert state.quality_dialog_open is False
