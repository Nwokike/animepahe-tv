"""Player Settings double-open guard (KTV structure).

The settings dialog goes through `page.show_dialog` — the platform owns the
single-dialog surface (a second show while one is open raises, and the
handler swallows it). Tests pin: one sheet per open, a second open while
one is up shows nothing, Close releases the surface, and a failed show is
swallowed (never a crash).
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from flet.controls.context import _context_page

import components.player.immersive_player as ip


class _Page:
    web = False

    def __init__(self, allow=10**9):
        self.dialogs = []
        self._allow = allow

    def show_dialog(self, dialog):
        if len(self.dialogs) >= self._allow:
            raise RuntimeError("Dialog is already opened")
        self.dialogs.append(dialog)

    def pop_dialog(self):
        return self.dialogs.pop() if self.dialogs else None

    def run_task(self, handler, *args):
        async def _run():
            result = handler(*args)
            if hasattr(result, "__await__"):
                await result

        return asyncio.ensure_future(_run())

    def update(self):
        pass


class _Video:
    fit = type("Fit", (), {"name": "CONTAIN"})()


def _player(variants, tracks):
    player = ip.ImmersivePlayer.__new__(ip.ImmersivePlayer)
    player._is_closing = False
    player._current_variant = None
    player._current_audio = None
    player._variants_cache = list(variants)
    player._audio_tracks_cache = list(tracks)
    player.subtitles = []
    player._local_subtitle = None
    player.store = None
    player.video = _Video()

    async def _variants():
        return list(variants)

    async def _tracks():
        return list(tracks)

    player.list_variants = _variants
    player.list_audio_tracks = _tracks
    return player


def test_two_concurrent_opens_show_one_sheet(monkeypatch):
    page = _Page(allow=1)  # the platform rejects a second while one is up
    player = _player(
        variants=[
            {"index": 0, "label": "A"},
            {"index": 1, "label": "B"},
        ],
        tracks=[{"name": "Japanese", "language": ""}, {"name": "English", "language": ""}],
    )
    token = _context_page.set(page)
    try:

        async def scenario():
            await asyncio.gather(
                player.open_player_settings(), player.open_player_settings()
            )

        asyncio.run(scenario())
    finally:
        _context_page.reset(token)
    assert len(page.dialogs) == 1, "the platform surface admits one sheet"


def test_close_releases_the_surface(monkeypatch):
    page = _Page()
    player = _player(
        variants=[
            {"index": 0, "label": "A"},
            {"index": 1, "label": "B"},
        ],
        tracks=[{"name": "Japanese", "language": ""}, {"name": "English", "language": ""}],
    )
    token = _context_page.set(page)
    try:
        asyncio.run(player.open_player_settings())
        assert len(page.dialogs) == 1
        # The dialog's own Done action closes it.
        done_action = page.dialogs[0].actions[0]
        done_action.on_click(None)
        asyncio.run(player.open_player_settings())
    finally:
        _context_page.reset(token)
    assert len(page.dialogs) == 2, "after Done the sheet can open again"


def test_no_page_is_a_silent_noop():
    # No page in context: nothing opens, nothing crashes.
    player = _player(
        variants=[
            {"index": 0, "label": "A"},
            {"index": 1, "label": "B"},
        ],
        tracks=[{"name": "Japanese", "language": ""}, {"name": "English", "language": ""}],
    )
    asyncio.run(player.open_player_settings())


def test_a_failed_show_is_swallowed(monkeypatch):
    page = _Page()
    player = _player(
        variants=[
            {"index": 0, "label": "A"},
            {"index": 1, "label": "B"},
        ],
        tracks=[{"name": "Japanese", "language": ""}, {"name": "English", "language": ""}],
    )

    def _boom(page_, dialog):
        raise RuntimeError("portal down")

    monkeypatch.setattr(_Page, "show_dialog", _boom)
    token = _context_page.set(page)
    try:
        asyncio.run(player.open_player_settings())
    finally:
        _context_page.reset(token)
    assert page.dialogs == []
