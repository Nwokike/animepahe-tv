"""AnimeOut's files: the wall, the clearance, and no-crash degradation.

The wall is a real Cloudflare JS challenge (docs/decisions.md), so the
provider leans on the same WebView solver that clears AnimePahe's — solve
once, persist per host, re-probe before use. What these tests pin: the
clearance is host-keyed (one host's solve can't clobber another's), the
re-probe short-circuits inside the process, and a missing clearance is a
no-stream rather than an exception or a hammered request.
"""

import asyncio
import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="animepahe-animeout-test-")
os.environ["FLET_APP_STORAGE_DATA"] = _TMP

import itertools

import pytest

from services.animeout_solver import AnimeOutSolver
from services.store import JsonStore


class _Resp:
    def __init__(self, status_code: int, text: str):
        self.status_code = status_code
        self.text = text


@pytest.fixture
def store():
    n = next(_counter)
    return JsonStore(filename=f"animeout-clear-{n}.json")


_counter = itertools.count()


# ---------------------------------------------------------------------------
# The store keeps one clearance per host
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clearances_are_host_keyed(store):
    await store.save_clearance("cf=animepahe", "UA/1.0")
    await store.save_clearance("cf=animeout", "UA/2.0", "public.animeout.xyz")
    # each host reads its own, and the default host is unchanged
    assert (await store.get_clearance())["cookies"] == "cf=animepahe"
    assert (await store.get_clearance("public.animeout.xyz"))["cookies"] == "cf=animeout"


@pytest.mark.asyncio
async def test_the_pre_host_flat_record_still_migrates(store):
    """A 1.0.x file has one flat clearance record — it belongs to animepahe
    and must keep working after the host split."""
    import json

    def _write() -> None:
        with open(store.path, "w", encoding="utf-8") as f:
            json.dump({"clearance": {"cookies": "cf=legacy", "user_agent": "UA/9"}}, f)

    await asyncio.to_thread(_write)
    assert (await store.get_clearance())["cookies"] == "cf=legacy"
    assert await store.get_clearance("public.animeout.xyz") is None
    # writing a second host migrates the flat record instead of dropping it
    await store.save_clearance("cf=new", "UA/2", "public.animeout.xyz")
    assert (await store.get_clearance())["cookies"] == "cf=legacy"
    assert (await store.get_clearance("public.animeout.xyz"))["cookies"] == "cf=new"


@pytest.mark.asyncio
async def test_clearing_one_host_leaves_the_other(store):
    await store.save_clearance("cf=a", "UA/1")
    await store.save_clearance("cf=o", "UA/2", "public.animeout.xyz")
    await store.clear_clearance("public.animeout.xyz")
    assert await store.get_clearance("public.animeout.xyz") is None
    assert (await store.get_clearance())["cookies"] == "cf=a"


# ---------------------------------------------------------------------------
# The solver: solve, re-probe, degrade
# ---------------------------------------------------------------------------


class _FakeSolver(AnimeOutSolver):
    """Records solves instead of opening a window."""

    def __init__(self, store=None, probe_ok=True):
        super().__init__(store=store)
        self.solves = 0
        self.probe_ok = probe_ok
        self.probes = 0


@pytest.mark.asyncio
async def test_no_clearance_and_no_store_solves_once(monkeypatch):
    solver = _FakeSolver()
    calls = {"n": 0}

    async def _fake_solve(self):
        calls["n"] += 1
        self._clearance = {"cookies": "cf=x", "user_agent": "UA"}
        return self._clearance

    monkeypatch.setattr(AnimeOutSolver, "solve", _fake_solve)
    first = await solver.clearance()
    assert first == {"cookies": "cf=x", "user_agent": "UA"}
    # a second ask uses the in-memory copy — no second solve
    assert (await solver.clearance()) == first
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_a_persisted_clearance_is_reprobed_not_reused_blindly(monkeypatch, store):
    """A stale cookie must not be replayed: the probe decides, exactly as
    DDoSSolver's does."""
    solver = _FakeSolver(store=store)

    async def _fake_probe(self, clearance):
        self.probes += 1
        return False  # expired

    async def _fake_solve(self):
        self.solves += 1
        return {"cookies": "cf=fresh", "user_agent": "UA"}

    monkeypatch.setattr(AnimeOutSolver, "_probe", _fake_probe)
    monkeypatch.setattr(AnimeOutSolver, "solve", _fake_solve)
    await store.save_clearance("cf=stale", "UA/old", "public.animeout.xyz")
    cleared = await solver.clearance()
    assert cleared["cookies"] == "cf=fresh"  # re-solved, not replayed
    assert solver.probes == 1
    assert solver.solves == 1


@pytest.mark.asyncio
async def test_a_valid_persisted_clearance_skips_the_window(monkeypatch, store):
    solver = _FakeSolver(store=store)
    monkeypatch.setattr(AnimeOutSolver, "_probe", lambda self, c: _yes())
    monkeypatch.setattr(AnimeOutSolver, "solve", _boom)

    await store.save_clearance("cf=good", "UA/good", "public.animeout.xyz")
    cleared = await solver.clearance()
    assert cleared["cookies"] == "cf=good"


async def _yes():
    return True


async def _boom(self):
    raise AssertionError("must not solve when the persisted clearance is good")


@pytest.mark.asyncio
async def test_no_page_means_no_clearance_not_a_crash(monkeypatch):
    """Desktop with no page (and no persisted cookie): quiet None."""
    solver = _FakeSolver()
    monkeypatch.setattr("state.app_state.state", type("S", (), {"page": None})())
    assert await solver.solve() is None


def test_file_headers_carry_the_clearance_when_present():
    solver = AnimeOutSolver()
    empty = solver.file_headers(None)
    assert empty == {"Referer": "https://ddl.animeout.com/"}
    headers = solver.file_headers({"cookies": "cf=abc", "user_agent": "UA/1"})
    assert headers["Cookie"] == "cf=abc"
    assert headers["User-Agent"] == "UA/1"
    assert headers["Referer"] == "https://ddl.animeout.com/"
    # Custom public.php page referer from the download chain
    custom = solver.file_headers(
        {"cookies": "cf=abc"}, referer="https://ddl.animeout.com/public.php?url=foo"
    )
    assert custom["Referer"] == "https://ddl.animeout.com/public.php?url=foo"


def test_has_clearance_follows_the_in_memory_copy():
    solver = AnimeOutSolver()
    assert solver.has_clearance is False
    solver._clearance = {"cookies": "cf=x"}
    assert solver.has_clearance is True


# ---------------------------------------------------------------------------
# The provider's side: the clearance rides the Source headers, and the
# absence of one is a no-stream rather than a hammered request
# ---------------------------------------------------------------------------


class _FakeProviderSolver:
    def __init__(self, clearance):
        self._clearance = clearance

    async def clearance(self):
        return self._clearance

    def file_headers(self, clearance, referer=None):
        from services.animeout_solver import AnimeOutSolver

        return AnimeOutSolver().file_headers(clearance, referer=referer)


@pytest.mark.asyncio
async def test_sources_carry_the_clearance_headers_once_solved():
    from services.providers.animeout import AnimeOutProvider

    clearance = {"cookies": "cf=ok; __cf_bm=1", "user_agent": "UA/1"}
    provider = AnimeOutProvider(
        solver=_FakeProviderSolver(clearance),
        client=None,
    )
    # Skip the live chain: the resolve is covered elsewhere; what matters
    # here is that the wall is no longer a hard stop.
    import services.providers.animeout as ao

    async def _fake_resolve(url, client=None, clearance=None):
        return "https://public.animeout.xyz/series/Show - 04 1080pp [AB][1080pp][SubsProvide][x265][Bot].mkv"

    original = ao._resolve_direct_url
    ao._resolve_direct_url = _fake_resolve
    try:
        sources = await provider.sources(
            "animeout:99",
            "http://nimbus/x - 04 1080pp [AB][1080pp][SubsProvide][x265][Bot].mkv",
        )
    finally:
        ao._resolve_direct_url = original

    assert len(sources) == 1
    assert sources[0].resolution == 1080
    # the clearance rides the source, so the download can use it
    assert sources[0].headers["Cookie"] == "cf=ok; __cf_bm=1"
    assert sources[0].headers["User-Agent"] == "UA/1"
    assert sources[0].headers["Referer"] == "https://ddl.animeout.com/"


@pytest.mark.asyncio
async def test_sources_without_a_clearance_report_no_stream(monkeypatch):
    """No clearance and a solver present: no stream, no raise, and NOT a
    request to the walled host."""
    from services.providers.animeout import AnimeOutProvider

    provider = AnimeOutProvider(solver=_FakeProviderSolver(None), client=None)
    import services.providers.animeout as ao

    calls = {"resolve": 0}

    async def _counting_resolve(url, client=None, clearance=None):
        calls["resolve"] += 1
        return "https://public.animeout.xyz/x.mkv"

    monkeypatch.setattr(ao, "_resolve_direct_url", _counting_resolve)
    sources = await provider.sources("animeout:99", "http://nimbus/x.mkv")
    assert sources == []
    assert calls["resolve"] == 0  # never touched the chain, let alone the wall
