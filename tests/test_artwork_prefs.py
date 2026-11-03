"""artwork_defaults: the learned per-backend first-paint shapes, persisted.

The hook probes a screen's artwork, decides a mode, and remembers it here —
so the next launch paints correctly before any probe lands. This file pins
the store contract: round-trip, reload, invalid values ignored, corrupt
sections read as empty.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.artwork import default_mode
from services.store import JsonStore


def test_round_trip_and_reload(monkeypatch, tmp_path):
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path))

    async def _run():
        store = JsonStore(filename="prefs.json")
        assert await store.get_artwork_defaults() == {}
        await store.save_artwork_default("anikato", "latest", "portrait")
        await store.save_artwork_default("animeout", "episodes", "landscape")
        return await store.get_artwork_defaults()

    learned = asyncio.run(_run())
    assert learned == {"anikato:latest": "portrait", "animeout:episodes": "landscape"}

    async def _reload():
        return await JsonStore(filename="prefs.json").get_artwork_defaults()

    assert asyncio.run(_reload()) == learned
    # And it feeds the first-paint default the screens call.
    assert default_mode("anikato", "latest", learned) == "portrait"


def test_invalid_modes_and_corrupt_sections_are_ignored(monkeypatch, tmp_path):
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path))

    async def _run():
        store = JsonStore(filename="prefs.json")
        await store.save_artwork_default("anikato", "latest", "square")
        await store.save_artwork_default("anikato", "latest", "")
        assert await store.get_artwork_defaults() == {}
        await store.put_section("artwork_defaults", ["not", "a", "dict"])
        return await store.get_artwork_defaults()

    assert asyncio.run(_run()) == {}


def test_rewriting_the_same_value_is_a_noop(monkeypatch, tmp_path):
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path))

    async def _run():
        store = JsonStore(filename="prefs.json")
        await store.save_artwork_default("kayoanime", "latest", "landscape")
        before = await store.get_artwork_defaults()
        await store.save_artwork_default("kayoanime", "latest", "landscape")
        return before, await store.get_artwork_defaults()

    before, after = asyncio.run(_run())
    assert before == after == {"kayoanime:latest": "landscape"}
