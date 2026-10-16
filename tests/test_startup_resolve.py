"""Resolve the session's source once, at startup — the owner's fixed order.

The order (2026-10-15): the app tries **AniKato, AnimeOut, AnimePahe,
Kusonime, Kayoanime** (PROVIDER_ORDER) and the first one that answers
serves the session. A stored provider name pins directly with no probe.
There is no "automatic" option in any UI — not the picker, not settings,
not the header badge — and this file guards that by scanning the UI
sources. The gate flips ready even when the first fetch fails; a manual
switch re-runs the whole gate behind the splash.
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import main as app_main
from services.providers.base import PROVIDER_ORDER
from state.app_state import state


@pytest.fixture(autouse=True)
def _fresh_gate():
    state.startup_ready = False
    state.startup_stage = ""
    state.current_source_name = ""
    yield
    state.startup_ready = False
    state.startup_stage = ""
    state.current_source_name = ""


class _Store:
    def __init__(self, pref=""):
        self.pref = pref
        self.saved = []

    async def get_backend(self):
        return self.pref

    async def save_backend(self, name):
        # The real store persists; get_backend then returns the new value.
        self.saved.append(name)
        self.pref = name


class _Provider:
    def __init__(self, name):
        self.name = name


class _Router:
    def __init__(self, health=None):
        self.health = dict(health or {})
        self.pin = None
        self.probes = 0
        self.provider_names = list(PROVIDER_ORDER)

    def set_pin(self, name):
        self.pin = name or None

    def get(self, name):
        return _Provider(name) if name in self.provider_names else None

    async def probe_all(self):
        self.probes += 1
        return dict(self.health)


def _controller(pref="", health=None, latest=None):
    controller = app_main.AppController.__new__(app_main.AppController)
    controller.store = _Store(pref)
    controller.router = _Router(health)
    controller._default_owner = "animepahe"
    controller._provider_order = PROVIDER_ORDER
    controller._startup_lock = asyncio.Lock()
    calls = []
    controller.calls = calls

    async def fake_latest(page):
        calls.append(page)
        if latest == "raise":
            raise RuntimeError("boom")

    controller.load_latest = fake_latest
    return controller


# ---------------------------------------------------------------------------
# The order itself
# ---------------------------------------------------------------------------


def test_the_fixed_order_is_the_owners_order():
    assert PROVIDER_ORDER == (
        "anikato",
        "animeout",
        "animepahe",
        "kayoanime",
    )


def test_a_stored_preference_pins_without_probing():
    controller = _controller(pref="kayoanime")
    asyncio.run(controller.resolve_startup())
    assert controller.router.pin == "kayoanime"
    assert controller.router.probes == 0
    assert controller.calls == [1]
    assert state.startup_ready is True
    assert state.startup_stage == ""
    # The header names the active source from the moment it resolves.
    assert state.current_source_name == "kayoanime"


def test_the_header_name_survives_a_failed_first_fetch():
    """AnimePahe's wall: the fetch fails, the badge must still name the
    source the owner chose (this used to blank to '…')."""
    controller = _controller(pref="animepahe", latest="raise")
    with pytest.raises(RuntimeError):
        asyncio.run(controller.resolve_startup())
    assert state.current_source_name == "animepahe"


def test_a_switch_names_the_new_source_immediately():
    controller = _controller(pref="")
    seen = {}

    async def scenario():
        await controller.set_backend_pin("animepahe")
        # Synchronously, before the spawned gate resolves anything.
        seen["name"] = state.current_source_name

    asyncio.run(scenario())
    assert seen["name"] == "animepahe"


def test_the_first_in_order_that_answers_serves():
    controller = _controller(
        health={
            "anikato": True,
            "animeout": True,
            "animepahe": True,
            "kayoanime": True,
        }
    )
    asyncio.run(controller.resolve_startup())
    assert controller.router.probes == 1
    assert controller.router.pin == "anikato"


def test_anikato_down_falls_to_animeout():
    controller = _controller(health={"anikato": False, "animeout": True, "animepahe": True})
    asyncio.run(controller.resolve_startup())
    assert controller.router.pin == "animeout"


def test_animeout_down_falls_to_animepahe():
    """The third of the owner's mains: animepahe IS tried (and can win)
    when the two above it do not answer."""
    controller = _controller(
        health={
            "anikato": False,
            "animeout": False,
            "animepahe": True,
            "kayoanime": True,
        }
    )
    asyncio.run(controller.resolve_startup())
    assert controller.router.pin == "animepahe"


def test_the_rest_follow_after_the_mains():
    controller = _controller(health={"kayoanime": True})
    asyncio.run(controller.resolve_startup())
    assert controller.router.pin == "kayoanime"


def test_all_down_falls_back_to_the_first_in_order():
    controller = _controller(health={})
    asyncio.run(controller.resolve_startup())
    assert controller.router.pin == "anikato", "honest failure beats no session"


def test_a_legacy_auto_value_means_no_preference():
    """1.0.x-era stores hold "auto"; it resolves by order like an absent
    value and is never written back."""
    controller = _controller(pref="auto", health={"anikato": True})
    asyncio.run(controller.resolve_startup())
    assert controller.router.pin == "anikato"
    assert controller.store.saved == []


def test_ready_flips_even_when_the_first_fetch_fails():
    controller = _controller(pref="anikato", latest="raise")
    # The error propagates for spawn()'s done-callback to log; the splash
    # must still unblock (finally), landing on an honest home.
    with pytest.raises(RuntimeError):
        asyncio.run(controller.resolve_startup())
    assert state.startup_ready is True
    assert state.startup_stage == ""


def test_a_manual_switch_reruns_the_gate():
    controller = _controller(pref="")

    async def scenario():
        await controller.set_backend_pin("kayoanime")
        await asyncio.sleep(0.01)  # let the spawned gate resolve run

    asyncio.run(scenario())
    assert controller.store.saved == ["kayoanime"]
    assert controller.router.pin == "kayoanime"
    assert controller.calls == [1]
    assert state.startup_ready is True


# ---------------------------------------------------------------------------
# The word can never come back
# ---------------------------------------------------------------------------


def test_no_automatic_anywhere_in_the_ui():
    """The owner's rule, made mechanical: "Automatic" does not appear in
    any UI source, and the old option literals are gone from the picker and
    settings. (main.py keeps a single legacy-tolerance check on the STORED
    value; nothing renders it.)"""
    root = os.path.join(os.path.dirname(__file__), "..", "src")
    for rel in (
        "app_shell.py",
        "screens/settings_screen.py",
        "screens/home_screen.py",
    ):
        with open(os.path.join(root, rel), encoding="utf-8") as f:
            text = f.read()
        assert "Automatic" not in text, f"{rel} still shows 'Automatic'"
    for rel in ("app_shell.py", "screens/settings_screen.py"):
        with open(os.path.join(root, rel), encoding="utf-8") as f:
            text = f.read()
        assert '"auto"' not in text, f"{rel} still carries an 'auto' option/value"
    # The badge's fallback label is never "Auto".
    with open(os.path.join(root, "screens", "home_screen.py"), encoding="utf-8") as f:
        home = f.read()
    assert '"Auto"' not in home
    assert "'Auto'" not in home
