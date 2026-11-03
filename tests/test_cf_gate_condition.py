"""The CF solver condition — the owner's live run, 2026-10-16.

Report: "I selected an animepahe recent. It swapped in the header nicely
but no Cloudflare solver and no episode found. We need to perfect the
condition for cf solver."

Log evidence: the episodes API answered 403 "Just a moment…", the solver
logged "DDoS solve suppressed: no user action requested it" on every call,
and the app rendered "No episodes found" — the wall read as an empty
catalogue, and no user path could open the verification window.

Three contracts close that hole:
1. A challenge response is a SIGNAL (CloudflareBlocked), never data: the
   provider raises, the router passes it through WITHOUT tripping the
   breaker or failing over, the controller raises the gate (Verify card).
2. Every user-driven load (home/switching, opening an anime, search,
   Verify, play) opens the solver window for its own duration —
   ref-counted so overlapping loads cannot close it on each other.
   Background work (probes, the episode checker) still may not.
3. The window gate never leaks: after the load, solve_allowed returns to
   exactly what it was.
"""

import asyncio
import contextlib
import os
import sys
from typing import ClassVar

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from flet.controls.context import _context_page

import main as app_main
from core.state import Episode, state
from services.providers.base import CloudflareBlocked
from services.router import ProviderRouter


class _LivePage:
    """A page whose session is alive — the loaders commit state only for
    a live session (see tests/test_session_alive.py for the guard itself)."""

    session = object()


@contextlib.contextmanager
def _live_session():
    token = _context_page.set(_LivePage())
    try:
        yield
    finally:
        _context_page.reset(token)


# ---------------------------------------------------------------------------
# 1. The provider raises on a challenge, never fakes an empty answer
# ---------------------------------------------------------------------------


class _Resp:
    def __init__(self, status_code, text):
        self.status_code = status_code
        self.text = text


def _fetch_with(resp):
    """Run AnimePaheScraper._fetch_api against a fake ddos.get."""
    from services.animepahe import AnimePaheScraper

    scraper = AnimePaheScraper()

    class _FakeDdos:
        async def get(self, url, params=None, headers=None):
            return resp

    scraper.ddos = _FakeDdos()
    return asyncio.run(scraper._fetch_api({"m": "release"}))


def test_a_403_challenge_raises_cloudflare_blocked():
    resp = _Resp(403, "<!DOCTYPE html><title>Just a moment...</title>")
    try:
        _fetch_with(resp)
        raise AssertionError("expected CloudflareBlocked")
    except CloudflareBlocked:
        pass


def test_a_503_challenge_raises_cloudflare_blocked():
    resp = _Resp(503, "<html><title>Just a moment...</title></html>")
    try:
        _fetch_with(resp)
        raise AssertionError("expected CloudflareBlocked")
    except CloudflareBlocked:
        pass


def test_a_200_html_interstitial_stays_a_soft_none():
    # A 200 interstitial may be a transient mid-redirect page: the old
    # soft-None path is kept (no gate for it); only explicit challenge
    # statuses raise.
    resp = _Resp(200, "<html><title>Just a moment...</title></html>")
    assert _fetch_with(resp) is None


def test_a_200_json_body_is_returned_untouched():
    resp = _Resp(200, '{"data": []}')
    assert _fetch_with(resp) is resp


# ---------------------------------------------------------------------------
# 2. The router passes the wall through; the breaker stays closed
# ---------------------------------------------------------------------------


class _BlockedProvider:
    name = "animepahe"
    capabilities: ClassVar[dict] = {"files": True, "episodes": True}

    def __init__(self):
        self.episode_calls = 0

    async def episodes(self, session, page):
        self.episode_calls += 1
        raise CloudflareBlocked("wall")


class _AnsweringProvider:
    name = "kayoanime"
    capabilities: ClassVar[dict] = {"files": True, "episodes": True}

    def __init__(self):
        self.calls = 0

    async def episodes(self, session, page):
        self.calls += 1
        return ([Episode(1, 1, 1, "Ep 1", "", "", "jpn", "", "e1", False)], False)


def test_the_wall_is_not_a_breaker_failure():
    """Counting the challenge as a provider failure opened the breaker and
    turned the next retry into "no provider available (all circuits open)"."""
    from services.router import CLOSED, RouterError

    p = _BlockedProvider()
    r = ProviderRouter([p])
    r.set_pin("animepahe")
    for _ in range(4):
        try:
            asyncio.run(r.episodes("sess-1", 1))
        except CloudflareBlocked:
            pass
        except RouterError as ex:
            raise AssertionError(f"the wall tripped the breaker: {ex}") from ex
        else:
            raise AssertionError("expected CloudflareBlocked")
    assert r.health()["animepahe"].state in ("unknown", CLOSED), (
        "the wall must not open the breaker"
    )
    assert p.episode_calls == 4, "each call must reach the provider (no circuit)"


def test_the_wall_never_fails_over_for_an_owned_session():
    """A bare session belongs to AnimePahe — another provider must not be
    asked for it, and its own catalogue is not an answer to the wall."""
    blocked, other = _BlockedProvider(), _AnsweringProvider()
    r = ProviderRouter([blocked, other])
    try:
        asyncio.run(r.episodes("sess-1", 1))
    except CloudflareBlocked:
        pass
    else:
        raise AssertionError("expected CloudflareBlocked")
    assert other.calls == 0, "no foreign provider may answer for another owner's session"


# ---------------------------------------------------------------------------
# 3. The controller's window: opens for user loads, ref-counted, restored
# ---------------------------------------------------------------------------


class _Solver:
    def __init__(self):
        self.solve_allowed = False
        self.solves = 0

    async def solve(self):
        self.solves += 1
        return self.solve_allowed


def _bind_solver(controller, solver):
    """Expose the REAL resolver chain (`_ddos` -> `scraper.ddos`) on a
    bare AppController instance — a `_solver` attribute would be read by
    nobody and the test would pass vacuously."""
    controller.scraper = type("S", (), {"ddos": solver})()
    return controller


class _OneCallController:
    """The minimum AppController surface _user_action touches."""

    def __init__(self, solver):
        _bind_solver(self, solver)
        self._gate_depth = 0

    _ddos = app_main.AppController._ddos
    _gate_solver = app_main.AppController._gate_solver
    _user_action = app_main.AppController._user_action


def test_user_action_opens_the_window_and_restores_it():
    solver = _Solver()
    controller = _OneCallController(solver)

    async def run():
        assert not solver.solve_allowed, "background state: closed"
        async with controller._user_action():
            assert solver.solve_allowed, "the user's load opens the window"
        assert not solver.solve_allowed, "the window closes again afterwards"

    asyncio.run(run())


def test_user_action_is_ref_counted_across_overlapping_loads():
    """Two overlapping loads (resolve + episodes) must not close the gate
    on each other — the inner exit restores to True while one still runs."""
    solver = _Solver()
    controller = _OneCallController(solver)

    async def run():
        async with controller._user_action():
            async with controller._user_action():
                assert solver.solve_allowed
            assert solver.solve_allowed, "the outer load still holds the window"
        assert not solver.solve_allowed

    asyncio.run(run())


def test_user_action_restores_a_previously_open_gate():
    """A pinned AnimePahe session has the gate open for the whole run; a
    load on top of it must restore True, not force it shut."""
    solver = _Solver()
    solver.solve_allowed = True
    controller = _OneCallController(solver)

    async def run():
        async with controller._user_action():
            pass
        assert solver.solve_allowed is True

    asyncio.run(run())


# ---------------------------------------------------------------------------
# 4. A blocked episodes load raises the gate instead of "No episodes"
# ---------------------------------------------------------------------------


class _BlockedRouter:
    def __init__(self, blocks: int):
        self.blocks = blocks
        self.last_winner = "animepahe"

    async def episodes(self, session, page):
        if self.blocks > 0:
            self.blocks -= 1
            raise CloudflareBlocked("wall")
        return ([Episode(1, 1, 1, "Ep 1", "", "", "jpn", "", "e1", False)], False)


def _controller(router, solver=None):
    controller = app_main.AppController.__new__(app_main.AppController)
    controller.router = router
    controller._loading_locks = {}
    controller._episodes_gen = 0
    controller._gate_depth = 0
    _bind_solver(controller, solver or _Solver())

    async def _resolve(anime_session):
        return None

    controller._resolve_anime = _resolve
    return controller


def _snapshot():
    return (
        state.current_anime_session,
        list(state.episodes),
        state.cf_blocked,
        state.is_loading,
        state.is_online,
    )


def _restore(snap):
    (
        state.current_anime_session,
        _episodes,
        state.cf_blocked,
        state.is_loading,
        state.is_online,
    ) = snap


def test_a_blocked_episode_load_raises_the_gate():
    snap = _snapshot()
    try:
        state.cf_blocked = False
        state.is_online = True
        state.current_anime_session = "2f26e8df"
        controller = _controller(_BlockedRouter(1))
        with _live_session():
            asyncio.run(controller.load_episodes("2f26e8df", 1))

        assert state.cf_blocked is True, (
            "the wall rendered as 'No episodes found' — the owner's report"
        )
        assert state.episodes == []
    finally:
        _restore(snap)


def test_a_blocked_load_while_offline_does_not_claim_a_challenge():
    snap = _snapshot()
    try:
        state.cf_blocked = False
        state.is_online = False
        state.current_anime_session = "2f26e8df"
        controller = _controller(_BlockedRouter(1))
        with _live_session():
            asyncio.run(controller.load_episodes("2f26e8df", 1))

        assert state.cf_blocked is False, "offline is not a Cloudflare challenge"
    finally:
        _restore(snap)


def test_an_episodes_load_opens_the_window_even_when_unpinned():
    """The owner's exact scenario: the session belongs to AnimePahe while
    the pin is elsewhere (a cross-source link). The owner-scoped fetch
    still reaches pahe, so its window must open for it."""
    snap = _snapshot()
    try:
        solver = _Solver()
        state.current_anime_session = "2f26e8df"

        class _RecordingRouter(_BlockedRouter):
            def __init__(self):
                super().__init__(0)
                self.open_at_call = []

            async def episodes(self, session, page):
                self.open_at_call.append(solver.solve_allowed)
                return await _BlockedRouter.episodes(self, session, page)

        router = _RecordingRouter()
        controller = _controller(router, solver=solver)
        with _live_session():
            asyncio.run(controller.load_episodes("2f26e8df", 1))

        assert router.open_at_call == [True], (
            "the solver window was closed while the owner's fetch ran — "
            "the 403 then logged 'suppressed: no user action requested it'"
        )
        assert solver.solve_allowed is False, "the window closes after the load"
    finally:
        _restore(snap)


def test_a_successful_load_closes_the_gate():
    snap = _snapshot()
    try:
        state.cf_blocked = True
        state.is_online = True
        state.current_anime_session = "2f26e8df"
        controller = _controller(_BlockedRouter(0))
        with _live_session():
            asyncio.run(controller.load_episodes("2f26e8df", 1))

        assert state.cf_blocked is False, "success clears the gate"
        assert len(state.episodes) == 1
    finally:
        _restore(snap)
