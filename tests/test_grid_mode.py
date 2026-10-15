"""The automatic grid decision — pure parts (the hook itself needs a render
context, which this suite has no harness for; everything it decides through
lives in core.artwork and is tested here)."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.artwork import LANDSCAPE, PORTRAIT, artwork_default_key
from hooks import use_grid_mode
from hooks.use_grid_mode import PROBE_COUNT, grid_sources, resolve_mode


class _Release:
    def __init__(self, snapshot):
        self.snapshot = snapshot


def test_grid_sources_keeps_order_and_blanks():
    items = [_Release("a"), _Release(""), _Release(None), _Release("d")]
    assert grid_sources(items, lambda r: r.snapshot) == ["a", "", "", "d"]


def test_resolve_mode_returns_a_strong_detection(monkeypatch):
    async def fake_shapes_for(srcs, provider="", referer=None, cache=None, client=None):
        return [PORTRAIT, PORTRAIT, PORTRAIT, None]

    monkeypatch.setattr(use_grid_mode.artwork_probe, "shapes_for", fake_shapes_for)
    mode, strong = asyncio.run(resolve_mode(["u1", "u2", "u3", "u4"], "kayoanime", "latest"))
    assert mode == PORTRAIT
    assert strong == PORTRAIT


def test_resolve_mode_falls_back_to_the_default(monkeypatch):
    calls = {}

    async def fake_shapes_for(srcs, provider="", referer=None, cache=None, client=None):
        calls["urls"] = srcs
        return [None, None]

    monkeypatch.setattr(use_grid_mode.artwork_probe, "shapes_for", fake_shapes_for)
    learned = {artwork_default_key("anikato", "latest"): LANDSCAPE}
    mode, strong = asyncio.run(resolve_mode(["u1", "u2"], "anikato", "latest", learned))
    assert mode == LANDSCAPE  # learned beats the seed
    assert strong is None
    assert calls["urls"] == ["u1", "u2"]


def test_resolve_mode_probes_at_most_probe_count(monkeypatch):
    seen = {}

    async def fake_shapes_for(srcs, provider="", referer=None, cache=None, client=None):
        seen["n"] = len(srcs)
        return []

    monkeypatch.setattr(use_grid_mode.artwork_probe, "shapes_for", fake_shapes_for)
    urls = [f"u{i}" for i in range(PROBE_COUNT + 20)]
    asyncio.run(resolve_mode(urls, "anikato", "search"))
    assert seen["n"] == PROBE_COUNT


def test_square_abstentions_do_not_vote(monkeypatch):
    async def fake_shapes_for(srcs, provider="", referer=None, cache=None, client=None):
        return [None, None, None]  # all abstained

    monkeypatch.setattr(use_grid_mode.artwork_probe, "shapes_for", fake_shapes_for)
    mode, strong = asyncio.run(resolve_mode(["a", "b", "c"], "animeout", "episodes"))
    assert (mode, strong) == (LANDSCAPE, None)  # the animeout seed
