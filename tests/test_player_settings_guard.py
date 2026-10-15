"""Player Stream Settings double-open guard — Phase 4 Step 3.

The quality/audio chips re-spawn `open_stream_settings` on every tap with
no latch, so two quick taps (or one tap while the options were still being
fetched) stacked two modal sheets. Tests pin: one sheet per open, the latch
held while it is up, released by Close, released on early returns (no page,
empty options), and released when showing raises.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import components.player.immersive_player as ip  # noqa: E402
import core.dialogs as dialogs  # noqa: E402
from flet.controls.context import _context_page  # noqa: E402


class _Page:
    web = False

    def __init__(self):
        self.dialogs = []

    def show_dialog(self, dialog):
        self.dialogs.append(dialog)

    def pop_dialog(self):
        return self.dialogs.pop() if self.dialogs else None

    def update(self):
        pass


def _player(variants, tracks, subtitles=None):
    player = ip.ImmersivePlayer.__new__(ip.ImmersivePlayer)
    player._settings_open = False
    player._is_closing = False
    player.subtitles = subtitles or []
    player._local_subtitle = None

    async def _variants():
        return variants

    async def _tracks():
        return tracks

    player.list_variants = _variants
    player.list_audio_tracks = _tracks
    return player


def _shows(monkeypatch):
    shown = []
    monkeypatch.setattr(dialogs, "show_app_dialog", lambda page, dialog: shown.append(dialog))
    return shown


def test_two_concurrent_opens_show_one_sheet(monkeypatch):
    page = _Page()
    shown = _shows(monkeypatch)
    player = _player(variants=[{"index": 0, "label": "A"}], tracks=[{"name": "Japanese", "language": ""}, {"name": "English", "language": ""}])
    token = _context_page.set(page)
    try:

        async def scenario():
            await asyncio.gather(
                player.open_stream_settings(), player.open_stream_settings()
            )

        asyncio.run(scenario())
    finally:
        _context_page.reset(token)
    assert len(shown) == 1
    assert player._settings_open is True, "the latch holds while the sheet is up"


def test_close_releases_the_latch(monkeypatch):
    page = _Page()
    shown = _shows(monkeypatch)
    player = _player(variants=[{"index": 0, "label": "A"}], tracks=[{"name": "Japanese", "language": ""}, {"name": "English", "language": ""}])
    token = _context_page.set(page)
    try:
        asyncio.run(player.open_stream_settings())
        assert len(shown) == 1
        # The dialog's own Close action flips the latch back.
        close_action = shown[0].actions[0]
        close_action.on_click(None)
        assert player._settings_open is False
        asyncio.run(player.open_stream_settings())
    finally:
        _context_page.reset(token)
    assert len(shown) == 2, "after Close the sheet can open again"


def test_early_returns_release_the_latch(monkeypatch):
    _shows(monkeypatch)
    # No page in context: nothing opens, nothing stays locked.
    player = _player(variants=[{"index": 0, "label": "A"}], tracks=[{"name": "Japanese", "language": ""}, {"name": "English", "language": ""}])
    asyncio.run(player.open_stream_settings())
    assert player._settings_open is False

    # One variant, one track, no subtitles: the honest empty-options return.
    page = _Page()
    player = _player(variants=[{"index": 0, "label": "A"}], tracks=[{"name": "Japanese", "language": ""}])
    token = _context_page.set(page)
    try:
        asyncio.run(player.open_stream_settings())
    finally:
        _context_page.reset(token)
    assert player._settings_open is False


def test_a_failed_show_releases_the_latch(monkeypatch):
    page = _Page()
    player = _player(variants=[{"index": 0, "label": "A"}], tracks=[{"name": "Japanese", "language": ""}, {"name": "English", "language": ""}])

    def _boom(page_, dialog):
        raise RuntimeError("portal down")

    monkeypatch.setattr(dialogs, "show_app_dialog", _boom)
    token = _context_page.set(page)
    try:
        asyncio.run(player.open_stream_settings())
    finally:
        _context_page.reset(token)
    assert player._settings_open is False, "a sheet that never showed must not lock"
