"""Episode-list switch guard — the wrong-episode playback bug.

The flet run log showed `SOURCES session=anime:48968 episode=48025|1`:
load_anime flipped `current_anime_session` to the NEW anime instantly, but
the PREVIOUS anime's episode rows stayed rendered (and clickable) while
the new load ran through resolve + Cloudflare retries for seconds. A tap
in that window paired the new anime with the old anime's episode session.

Fix: the session switch lands with an empty episode list in the same
render (load_anime, plus the same guard in load_episodes for direct
callers). Reloading the SAME anime (pagination) keeps rows visible.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import main as app_main
from core.state import Episode, state


def _episode(session: str) -> Episode:
    return Episode(1, 1, 1, "Ep 1", "", "", "jpn", "", session, False)


class _Router:
    """Records what the episode list held AT FETCH TIME."""

    def __init__(self):
        self.seen: list[list] = []
        self.last_winner = "stub"

    async def episodes(self, session, page):
        self.seen.append(list(state.episodes))
        return ([], False)


def _controller(router):
    controller = app_main.AppController.__new__(app_main.AppController)
    controller.router = router
    controller._loading_locks = {}
    controller._episodes_gen = 0

    async def _resolve(anime_session):
        return None

    controller._resolve_anime = _resolve
    return controller


def _snapshot():
    return (
        state.current_anime_session,
        list(state.episodes),
        state.episodes_has_more,
        state.episodes_page,
        state.is_loading,
        state.selected_anime,
    )


def _restore(snap):
    (
        state.current_anime_session,
        state.episodes,
        state.episodes_has_more,
        state.episodes_page,
        state.is_loading,
        state.selected_anime,
    ) = snap


def test_switching_anime_clears_episodes_before_the_load():
    snap = _snapshot()
    try:
        state.current_anime_session = "kayoanime:48025"
        state.episodes = [_episode("48025|1"), _episode("48025|2")]
        state.selected_anime = {}

        router = _Router()
        controller = _controller(router)
        asyncio.run(controller.load_anime("kayoanime:48968"))

        assert router.seen == [[]], (
            "the previous anime's rows were still present when the new "
            "load started — a tap could pair them with the new session"
        )
        assert state.episodes == []
    finally:
        _restore(snap)


def test_reloading_the_same_anime_keeps_rows_during_pagination():
    snap = _snapshot()
    try:
        state.current_anime_session = "kayoanime:48025"
        rows = [_episode("48025|1")]
        state.episodes = list(rows)

        router = _Router()
        controller = _controller(router)
        asyncio.run(controller.load_episodes("kayoanime:48025", 2))

        # Same session: no pre-fetch clear (pagination keeps rows visible).
        assert router.seen == [list(rows)]
    finally:
        _restore(snap)
