"""Phase 2 Step 2 — resolve the session's backend once, at startup.

A stored preference pins directly with no probe; "auto" probes the OPEN
backends in editorial order and never picks AnimePahe (selecting it is the
owner's pin); the gate flips ready even when the first fetch fails; and a
manual switch re-runs the whole gate behind the splash.
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import main as app_main
from state.app_state import state


@pytest.fixture(autouse=True)
def _fresh_gate():
    state.startup_ready = False
    state.startup_stage = ""
    yield
    state.startup_ready = False
    state.startup_stage = ""


class _Store:
    def __init__(self, pref="auto"):
        self.pref = pref
        self.saved = []

    async def get_backend(self):
        return self.pref

    async def save_backend(self, name):
        # The real store persists; get_backend then returns the new value.
        self.saved.append(name)
        self.pref = name


class _Router:
    def __init__(self, health=None):
        self.health = dict(health or {})
        self.pin = None
        self.probes = 0
        self.provider_names = [
            "anikato",
            "animeout",
            "kusonime",
            "kayoanime",
            "animepahe",
        ]

    def set_pin(self, name):
        self.pin = None if not name or name == "auto" else name

    async def probe_all(self):
        self.probes += 1
        return dict(self.health)


def _controller(pref="auto", health=None, latest=None):
    controller = app_main.AppController.__new__(app_main.AppController)
    controller.store = _Store(pref)
    controller.router = _Router(health)
    controller._default_owner = "animepahe"
    controller._startup_lock = asyncio.Lock()
    calls = []
    controller.calls = calls

    async def fake_latest(page):
        calls.append(page)
        if latest == "raise":
            raise RuntimeError("boom")

    controller.load_latest = fake_latest
    return controller


def test_a_stored_preference_pins_without_probing():
    controller = _controller(pref="kayoanime")
    asyncio.run(controller.resolve_startup())
    assert controller.router.pin == "kayoanime"
    assert controller.router.probes == 0
    assert controller.calls == [1]
    assert state.startup_ready is True
    assert state.startup_stage == ""


def test_auto_picks_the_first_healthy_open_backend():
    controller = _controller(
        health={
            "anikato": False,
            "animeout": True,
            "kusonime": True,
            "kayoanime": True,
            "animepahe": True,
        }
    )
    asyncio.run(controller.resolve_startup())
    assert controller.router.probes == 1
    assert controller.router.pin == "animeout"


def test_auto_never_chooses_animepahe_even_when_only_it_answers():
    controller = _controller(health={"animepahe": True})
    asyncio.run(controller.resolve_startup())
    assert controller.router.pin == "anikato", "first OPEN backend, never pahe"


def test_ready_flips_even_when_the_first_fetch_fails():
    controller = _controller(pref="anikato", latest="raise")
    # The error propagates for spawn()'s done-callback to log; the splash
    # must still unblock (finally), landing on an honest home.
    with pytest.raises(RuntimeError):
        asyncio.run(controller.resolve_startup())
    assert state.startup_ready is True
    assert state.startup_stage == ""


def test_a_manual_switch_reruns_the_gate():
    controller = _controller(pref="auto")

    async def scenario():
        await controller.set_backend_pin("kusonime")
        await asyncio.sleep(0.01)  # let the spawned gate resolve run

    asyncio.run(scenario())
    assert controller.store.saved == ["kusonime"]
    assert controller.router.pin == "kusonime"
    assert controller.calls == [1]
    assert state.startup_ready is True
