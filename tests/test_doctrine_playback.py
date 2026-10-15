"""Phase 2 Step 4 — playback never hops backends on its own.

The automatic title-hop inside _play_episode_resolve is gone (it produced
the bogus ktv:// launch and the CF-churn cascade in the live log). Owner-
empty playback is an honest result; the manual "Try another source"
re-enters on the match's OWN session instead of splicing another backend's
episodes under the old one.
"""

import asyncio
import inspect
import os
import sys
import textwrap

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import main as app_main
from core.state import Anime
from state.app_state import state


@pytest.fixture(autouse=True)
def _fresh_state():
    saved = (list(state.episodes), state.selected_anime, state.is_loading)
    yield
    state.episodes = saved[0]
    state.selected_anime = saved[1]
    state.is_loading = saved[2]


def test_playback_resolution_has_no_automatic_title_hop():
    source = textwrap.dedent(
        inspect.getsource(app_main.AppController._play_episode_resolve)
    )
    assert "sources_for_title_any" not in source, (
        "owner-empty playback must never ask another backend on its own"
    )
    assert "This source has no playable stream for this episode." in source


class _Provider:
    def __init__(self, results):
        self._results = results

    async def search(self, query, page):
        return (list(self._results), False)


class _Router:
    def __init__(self, episodes, results):
        self._episodes = episodes
        self.last_winner = "anikato"
        self._provider = _Provider(results)

    async def episodes_for_title_any(self, title, skip=None):
        return (list(self._episodes), False)

    def get(self, name):
        return self._provider if name == "anikato" else None


def _controller(router):
    controller = app_main.AppController.__new__(app_main.AppController)
    controller.router = router
    controller._owner_of = lambda session: session.split(":")[0]
    snacks = []
    controller._show_error_snackbar = snacks.append
    shells = []
    controller._shell_action = lambda name, *args: shells.append((name, args))
    controller.snacks = snacks
    controller.shells = shells
    return controller


def _match():
    return Anime(
        1,
        "Black Clover",
        "TV",
        170,
        "Finished",
        "fall",
        2017,
        7.3,
        "p",
        "anikato:black-clover-g7tjy",
    )


def test_try_another_source_re_enters_on_the_matchs_own_session():
    controller = _controller(_Router(["episode-row"], [_match()]))
    state.selected_anime = {"title": "Black Clover"}
    state.episodes = ["old-row"]
    asyncio.run(controller.try_another_source("kusonime:9538"))
    assert controller.shells == [
        ("open_anime", ("anikato:black-clover-g7tjy",))
    ], "the app re-enters on the other backend's own session"
    assert state.episodes == ["old-row"], "no splice under the old session"
    assert controller.snacks == []


def test_try_another_source_is_honest_when_nobody_has_it():
    controller = _controller(_Router([], []))
    state.selected_anime = {"title": "Nope"}
    asyncio.run(controller.try_another_source("kusonime:1"))
    assert controller.shells == []
    assert controller.snacks == ["No other source has this title."]
