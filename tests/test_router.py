"""Router failover — the table-driven contract for "an app that cannot
fail because it never relies on one thing", now with the racing path.

Fake providers only: no network, injected clock, injected failures. The
race returns the first ANSWER (non-empty) and cancels the rest; an empty
answer from one provider is not an answer — different catalogs mean the
chain continues; only the last provider's empty is final.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.state import Anime, Episode, Source
from services.router import ProviderRouter, RouterError


class FakeProvider:
    def __init__(self, name, *, probe_ok=True, latency=0.0):
        self.name = name
        self.capabilities = {"files": True, "episodes": True}
        self._probe_ok = probe_ok
        self._latency = latency
        self.calls: list[tuple] = []
        self.fail_latest = 0
        self.latest_data = (
            [Anime(1, "T", "TV", 1, "Airing", "fall", 2024, 8.0, "p", f"{name}:a1")],
            True,
        )
        self.search_data = (
            [Anime(2, "S", "TV", 1, "Airing", "fall", 2024, 8.0, "p", f"{name}:a2")],
            True,
        )
        self.episodes_data = [
            Episode(1, 1, 1, "Ep 1", "snap", "", "jpn", "24m", "e1", False)
        ]
        self.sources_data = [Source("https://x/e.mkv", 1080, "jpn", "SubsPlease")]

    async def probe(self):
        await asyncio.sleep(self._latency)
        return self._probe_ok

    async def latest_releases(self, page):
        self.calls.append(("latest", page))
        await asyncio.sleep(self._latency)
        if self.fail_latest > 0:
            self.fail_latest -= 1
            raise RuntimeError(f"{self.name} down")
        return self.latest_data

    async def search(self, query, page):
        self.calls.append(("search", query, page))
        if self.fail_latest > 0:
            self.fail_latest -= 1
            raise RuntimeError(f"{self.name} down")
        return self.search_data

    async def episodes(self, session, page):
        self.calls.append(("episodes", session, page))
        if self.fail_latest > 0:
            self.fail_latest -= 1
            raise RuntimeError(f"{self.name} down")
        return (list(self.episodes_data), False)

    async def sources(self, anime_session, episode_session):
        self.calls.append(("sources", anime_session, episode_session))
        if self.fail_latest > 0:
            self.fail_latest -= 1
            raise RuntimeError(f"{self.name} down")
        return list(self.sources_data)

    async def episodes_for_title(self, title):
        return list(self.episodes_data)

    async def sources_for_title(self, title, episode):
        self.calls.append(("sources_for_title", title, episode))
        if self.fail_latest > 0:
            self.fail_latest -= 1
            raise RuntimeError(f"{self.name} down")
        return list(self.sources_data)

    async def close(self):
        pass


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


def _router(*providers, clock=None):
    return ProviderRouter(list(providers), clock=clock)


# ---------------------------------------------------------------------
# The failover table
# ---------------------------------------------------------------------


def test_primary_down_secondary_serves():
    p1, p2 = FakeProvider("p1"), FakeProvider("p2")
    p1.fail_latest = 1
    r = _router(p1, p2)
    releases, has_more = asyncio.run(r.latest_releases(1))
    assert releases[0].title == "T" and has_more is True


def test_all_down_raises_router_error_with_wrapped_cause():
    p1, p2 = FakeProvider("p1"), FakeProvider("p2")
    p1.fail_latest = p2.fail_latest = 99
    r = _router(p1, p2)
    try:
        asyncio.run(r.latest_releases(1))
        assert False, "expected RouterError"
    except RouterError as ex:
        assert isinstance(ex.__cause__, RuntimeError)


def test_empty_answer_falls_through_to_next_provider():
    p1, p2 = FakeProvider("p1"), FakeProvider("p2")
    p1.latest_data = ([], False)
    r = _router(p1, p2)
    releases, has_more = asyncio.run(r.latest_releases(1))
    assert releases[0].title == "T"  # p2 served
    assert p2.calls


def test_all_empty_returns_the_last_answer():
    p1, p2 = FakeProvider("p1"), FakeProvider("p2")
    p1.latest_data = ([], False)
    p2.latest_data = ([], False)
    r = _router(p1, p2)
    releases, has_more = asyncio.run(r.latest_releases(1))
    assert releases == [] and has_more is False


def test_first_answer_wins_the_race():
    """Both providers answer; the first in editorial order wins — the
    race returns the first ANSWER, and a slow second is cancelled."""
    p1, p2 = FakeProvider("p1"), FakeProvider("p2", latency=0.05)
    r = _router(p1, p2)
    releases, _ = asyncio.run(r.latest_releases(1))
    assert releases[0].session == "p1:a1"


def test_editorial_order_governs_the_healthy_path():
    """A slower-but-preferred provider must not lose to a faster
    lower-priority one: the first eligible provider answers alone."""
    p1, p2 = FakeProvider("p1", latency=0.05), FakeProvider("p2", latency=0.0)
    r = _router(p1, p2)
    releases, _ = asyncio.run(r.latest_releases(1))
    assert releases[0].session == "p1:a1"
    assert not p2.calls  # the second is never asked while the first answers


def test_race_only_bounds_the_failure_tail():
    """When the first provider fails, the rest race — the slow failure
    does not sit at the front of the wait."""
    p1, p2, p3 = (
        FakeProvider("p1", latency=0.3),
        FakeProvider("p2", latency=0.0),
        FakeProvider("p3", latency=0.3),
    )
    p1.fail_latest = 1
    r = _router(p1, p2, p3)
    releases, _ = asyncio.run(r.latest_releases(1))
    assert releases[0].session == "p2:a1"
    assert r.last_winner == "p2"


# ---------------------------------------------------------------------
# Breaker states
# ---------------------------------------------------------------------


def test_three_consecutive_failures_open_the_circuit():
    from core.config import BREAKER_FAIL_THRESHOLD

    p1, p2 = FakeProvider("p1"), FakeProvider("p2")
    p1.fail_latest = 99
    r = _router(p1, p2)
    for _ in range(BREAKER_FAIL_THRESHOLD):
        try:
            asyncio.run(r.latest_releases(1))
        except RouterError:
            pass
    assert r.health()["p1"].state == "open"
    assert r.health()["p2"].state == "closed"
    calls_before = len(p1.calls)
    asyncio.run(r.latest_releases(1))
    assert len(p1.calls) == calls_before  # skipped without being called


def test_half_open_trial_recovers_and_failure_doubles_cooldown():
    from core.config import (
        BREAKER_FAIL_THRESHOLD,
        BREAKER_OPEN_MAX_SECONDS,
        BREAKER_OPEN_SECONDS,
    )

    clock = Clock()
    p1, p2 = FakeProvider("p1"), FakeProvider("p2")
    p1.fail_latest = BREAKER_FAIL_THRESHOLD
    r = _router(p1, p2, clock=clock)
    for _ in range(BREAKER_FAIL_THRESHOLD + 1):
        try:
            asyncio.run(r.latest_releases(1))
        except RouterError:
            pass
    assert r.health()["p1"].state == "open"
    p1.fail_latest = 0
    clock.advance(BREAKER_OPEN_SECONDS + 1)
    asyncio.run(r.latest_releases(1))
    assert r.health()["p1"].state == "closed"
    p1.fail_latest = 99
    for _ in range(BREAKER_FAIL_THRESHOLD):
        try:
            asyncio.run(r.latest_releases(1))
        except RouterError:
            pass
    clock.advance(BREAKER_OPEN_SECONDS + 1)
    asyncio.run(r.latest_releases(1))  # the failed trial
    breaker = r._breakers["p1"]
    assert breaker.cooldown == min(BREAKER_OPEN_SECONDS * 2, BREAKER_OPEN_MAX_SECONDS)


def test_force_bypasses_open_circuit_for_explicit_user_retry():
    from core.config import BREAKER_FAIL_THRESHOLD

    p1, p2 = FakeProvider("p1"), FakeProvider("p2")
    p1.fail_latest = 99
    r = _router(p1, p2)
    for _ in range(BREAKER_FAIL_THRESHOLD + 1):
        try:
            asyncio.run(r.latest_releases(1))
        except RouterError:
            pass
    assert r.health()["p1"].state == "open"
    calls = len(p1.calls)
    # The owner's circuit is open and the session names p1 alone: asking
    # the others is meaningless (they cannot resolve "p1:a1"), so the
    # honest answer is a fast RouterError.
    try:
        asyncio.run(r.sources("p1:a1", "e1"))
        assert False, "expected RouterError for an open owner circuit"
    except RouterError:
        pass
    # the pin path: force the open provider explicitly
    asyncio.run(r._run("sources", "p1:a1", "e1", force=True))
    assert len(p1.calls) > calls


# ---------------------------------------------------------------------
# Owner-first routing (session prefixes)
# ---------------------------------------------------------------------


def test_session_owner_is_tried_first():
    p1, p2 = FakeProvider("p1"), FakeProvider("p2")
    r = _router(p1, p2)
    asyncio.run(r.episodes("p2:a1", 1))
    assert p2.calls and not p1.calls  # owner first
    p2.fail_latest = 1
    r2 = _router(p1, p2)
    # A session that NAMES its provider is only asked of it: a foreign
    # provider cannot resolve "p2:a1", and (the flet run log bug) one that
    # returns unvalidated answers could WIN the race with garbage.
    try:
        asyncio.run(r2.episodes("p2:a1", 1))
        assert False, "expected RouterError when the owner fails"
    except RouterError:
        pass
    assert not p1.calls  # the non-owner was never asked


def test_a_namespaced_session_is_never_raced_against_other_providers():
    """The flet-run failure: kayoanime was pinned, got asked for a
    kusonime session, and returned an UNVALIDATED stream (drive URL built
    from "48025|1") that won the race over the real owner."""
    kayo, kuso = FakeProvider("kayoanime"), FakeProvider("kusonime")
    r = _router(kayo, kuso)
    r.set_pin("kayoanime")  # the pin must NOT pull a foreign provider in
    asyncio.run(r.sources("kusonime:48968", "48968|1"))
    assert kayo.calls == []  # never asked
    assert ("sources", "kusonime:48968", "48968|1") in kuso.calls


def test_an_unknown_session_owner_fails_fast():
    p1 = FakeProvider("p1")
    r = _router(p1)
    try:
        asyncio.run(r.episodes("nosuchprovider:1", 1))
        assert False, "expected RouterError"
    except RouterError as ex:
        assert "owns the session" in str(ex)
    assert p1.calls == []


def test_health_records_latency_and_errors():
    p1 = FakeProvider("p1")
    p1.fail_latest = 1
    r = _router(p1)
    try:
        asyncio.run(r.latest_releases(1))
    except RouterError:
        pass
    h = r.health()["p1"]
    assert h.last_error and h.checked_at > 0


# ---------------------------------------------------------------------
# Startup race + pin
# ---------------------------------------------------------------------


def test_startup_probe_is_parallel_and_deadline_scoped():
    fast = FakeProvider("fast", probe_ok=True, latency=0.0)
    slow_dead = FakeProvider("slowdead", probe_ok=False, latency=0.05)
    r = _router(fast, slow_dead)
    ok = asyncio.run(r.probe_all())
    assert ok["fast"] is True
    assert ok["slowdead"] is False


def test_a_hanging_probe_times_out_without_killing_the_race(monkeypatch):
    """The fail_after path: a provider that never answers must be recorded
    as a timeout failure while the OTHER providers' probes still finish
    (asyncio.wait_for's cancel would have raced the attribution)."""
    from services import router as router_mod

    monkeypatch.setattr(router_mod, "STARTUP_PROBE_TIMEOUT", 0.1)

    class _Hanging(FakeProvider):
        async def probe(self):
            await asyncio.sleep(10.0)
            return True

    fast = FakeProvider("fast", probe_ok=True)
    hang = _Hanging("hang")
    r = _router(fast, hang)

    async def scenario():
        import time as _time

        t0 = _time.monotonic()
        ok = await r.probe_all()
        elapsed = _time.monotonic() - t0
        assert ok == {"fast": True, "hang": False}
        assert elapsed < 2.0  # the race ended at the timeout, not the sleep
        rec = r.health()["hang"]
        assert rec.last_error == "timeout"

    asyncio.run(scenario())


def test_probe_answers_are_not_fabricated_by_the_budget(monkeypatch):
    """A provider that the BUDGET cancelled before it answered is left out
    of the result entirely — the pre-anyio code wrote False for every
    provider, poisoning breaker health with spurious failures."""
    from services import router as router_mod

    monkeypatch.setattr(router_mod, "STARTUP_PROBE_BUDGET", 0.05)
    monkeypatch.setattr(router_mod, "STARTUP_PROBE_TIMEOUT", 5.0)

    class _SlowButAlive(FakeProvider):
        async def probe(self):
            await asyncio.sleep(2.0)
            return True

    slow = _SlowButAlive("slow")
    r = _router(slow)
    ok = asyncio.run(r.probe_all())
    assert ok == {}  # never answered → absent, not False


def test_pin_sends_one_provider_first():
    p1, p2 = FakeProvider("p1"), FakeProvider("p2")
    r = _router(p1, p2)
    r.set_pin("p2")
    asyncio.run(r.latest_releases(1))
    assert r.last_winner == "p2"
    assert p1.calls == [], "the pin is the app now: nothing else is asked"


def test_a_pinned_catalog_asks_only_the_pin_owner():
    """Phase 2 doctrine: once a backend is chosen, the catalog never
    silently comes from another source."""
    p1, p2 = FakeProvider("p1"), FakeProvider("p2")
    r = _router(p1, p2)
    r.set_pin("p2")
    asyncio.run(r.search("black clover", 1))
    assert p1.calls == []
    assert [c for c in p2.calls if c[0] == "search"]


def test_a_pinned_catalog_fails_honestly_when_the_owner_is_down():
    p1, p2 = FakeProvider("p1"), FakeProvider("p2")
    p2.fail_latest = 1
    r = _router(p1, p2)
    r.set_pin("p2")
    try:
        asyncio.run(r.latest_releases(1))
        assert False, "expected RouterError"
    except RouterError:
        pass
    assert p1.calls == [], "no silent catalog from another backend"


def test_empty_router_is_inert_not_fatal():
    r = _router()
    assert asyncio.run(r.probe_all()) == {}
    try:
        asyncio.run(r.latest_releases(1))
        assert False, "expected RouterError"
    except RouterError as ex:
        assert "no providers" in str(ex)


# ---------------------------------------------------------------------
# sources_for_title_any — the playback half of failover by title
# ---------------------------------------------------------------------


def test_sources_for_title_any_skips_the_owner_and_names_the_winner():
    owner, other = FakeProvider("owner"), FakeProvider("other")
    r = _router(owner, other)
    result = asyncio.run(r.sources_for_title_any("Frieren", 3, skip="owner"))
    assert result == other.sources_data
    assert r.last_winner == "other"
    # the owner is never asked
    assert not [c for c in owner.calls if c[0] == "sources_for_title"]
    assert ("sources_for_title", "Frieren", 3) in other.calls


def test_sources_for_title_any_stops_at_the_first_answer():
    first, second = FakeProvider("first"), FakeProvider("second")
    r = _router(first, second)
    asyncio.run(r.sources_for_title_any("Frieren", 3))
    # first answered, so second is never asked
    assert not [c for c in second.calls if c[0] == "sources_for_title"]


def test_sources_for_title_any_empty_when_everyone_is_empty():
    empty = FakeProvider("empty")
    empty.sources_data = []
    r = _router(empty)
    assert asyncio.run(r.sources_for_title_any("Frieren", 3)) == []


def test_sources_for_title_any_skips_an_open_breaker_unless_forced():
    down, up = FakeProvider("down"), FakeProvider("up")
    r = _router(down, up)
    # Trip 'down''s breaker: three failures opens it for 30s.
    for _ in range(3):
        down.fail_latest = 1
        asyncio.run(r.latest_releases(1))
    assert [c for c in down.calls if c[0] == "sources_for_title"] == []

    # force=True: the user asking to watch overrides the tripped breaker.
    result = asyncio.run(r.sources_for_title_any("Frieren", 3, force=True))
    assert result == down.sources_data
    assert ("sources_for_title", "Frieren", 3) in down.calls


def test_sources_for_title_any_survives_a_provider_that_raises():
    broken, good = FakeProvider("broken"), FakeProvider("good")
    broken.sources_for_title = _raiser
    r = _router(broken, good)
    result = asyncio.run(r.sources_for_title_any("Frieren", 3))
    assert result == good.sources_data


async def _raiser(title, episode):
    raise RuntimeError("provider exploded")
