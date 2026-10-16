"""Phase 2 Step 5 — Discover and Schedule follow the CHOSEN backend.

Discover asks the pinned source for its own filter vocabulary and browse;
a pin that cannot browse yields the honest empty state, never another
backend's catalog. The schedule is anikato's own extra — any other chosen
source gets the honest message instead of silently querying anikato.
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import main as app_main
from state.app_state import state


@pytest.fixture(autouse=True)
def _fresh_discover():
    saved = (
        state.discover_source,
        state.discover_filters,
        state.discover_results,
        state.schedule_tabs,
        state.schedule_entries,
    )
    yield
    (
        state.discover_source,
        state.discover_filters,
        state.discover_results,
        state.schedule_tabs,
        state.schedule_entries,
    ) = saved


class _Router:
    def __init__(self, pin, schedule_provider=None, browse_spec=None):
        self.pin = pin
        self._schedule_provider = schedule_provider
        self._browse_spec = browse_spec or []
        self.filters_called_with = None
        self.browse_called_with = None

    async def discover_filters(self, name=None):
        self.filters_called_with = name
        if name == "kayoanime" or (name is None and self._browse_spec):
            return ("kayoanime", self._browse_spec)
        return ("", [])

    async def browse(self, name, filters, page):
        self.browse_called_with = name
        return (name or "", [], False)

    def get(self, name):
        if name == "anikato" and self._schedule_provider is not None:
            return self._schedule_provider
        return None


def _controller(router):
    controller = app_main.AppController.__new__(app_main.AppController)
    controller.router = router
    snacks = []
    controller._show_error_snackbar = snacks.append
    controller.snacks = snacks
    return controller


def test_discover_filters_are_asked_of_the_chosen_source():
    router = _Router(
        "kayoanime",
        browse_spec=[{"key": "genre", "label": "Genre", "kind": "choice", "options": []}],
    )
    controller = _controller(router)
    asyncio.run(controller.load_discover_filters())
    assert router.filters_called_with == "kayoanime"
    assert state.discover_source == "kayoanime"


def test_discover_browse_uses_the_chosen_source():
    router = _Router("kayoanime")
    controller = _controller(router)
    state.discover_source = "kayoanime"
    asyncio.run(controller.load_discover({}, 1))
    assert router.browse_called_with == "kayoanime"


def test_a_pin_that_cannot_browse_yields_an_honest_empty_state():
    router = _Router("animepahe")  # no browse surface
    controller = _controller(router)
    asyncio.run(controller.load_discover_filters())
    assert router.filters_called_with == "animepahe"
    assert state.discover_source == ""
    assert state.discover_filters == []
    asyncio.run(controller.load_discover({}, 1))
    # browse is asked of the pin; the router answers empty (no fallback)
    assert router.browse_called_with == "animepahe"


class _ScheduleProvider:
    def __init__(self):
        self.called = False

    async def schedule_tabs(self):
        self.called = True
        return [{"time": "t1", "label": "Mon"}]

    async def schedule_entries(self, time):
        return []


def test_schedule_answers_only_for_a_source_that_has_one():
    provider = _ScheduleProvider()
    controller = _controller(_Router("anikato", schedule_provider=provider))
    asyncio.run(controller.load_schedule())
    assert provider.called is True
    assert state.schedule_tabs


def test_schedule_is_honest_for_any_other_source():
    controller = _controller(_Router("kayoanime"))
    state.schedule_tabs = ["unchanged"]
    asyncio.run(controller.load_schedule())
    assert controller.snacks == ["This source has no schedule."]
    assert state.schedule_tabs == ["unchanged"]
