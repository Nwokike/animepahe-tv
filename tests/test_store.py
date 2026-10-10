"""Tests for the durable store: history, continue watching, atomic writes."""

import asyncio
import itertools
import json
import os
import shutil
import tempfile

import pytest

_TMP = tempfile.mkdtemp(prefix="animepahe-store-test-")
os.environ["FLET_APP_STORAGE_DATA"] = _TMP

from services.store import (  # noqa: E402
    CONTINUE_WATCHING_LIMIT,
    SEARCH_HISTORY_LIMIT,
    JsonStore,
)

_seq = itertools.count()


@pytest.fixture
def store():
    return JsonStore(filename=f"test-{next(_seq)}.json")


@pytest.mark.asyncio
async def test_search_history_dedup_and_cap(store):
    for q in [f"q{i}" for i in range(SEARCH_HISTORY_LIMIT + 5)]:
        await store.add_search(q)
    history = await store.get_search_history()
    assert len(history) == SEARCH_HISTORY_LIMIT
    assert history[0] == f"q{SEARCH_HISTORY_LIMIT + 4}"  # newest first
    assert "q0" not in history  # oldest evicted

    # Re-searching an existing query moves it to the front, no duplicate.
    await store.add_search("q10")
    history = await store.get_search_history()
    assert history.count("q10") == 1
    assert history[0] == "q10"

    await store.clear_search_history()
    assert await store.get_search_history() == []


@pytest.mark.asyncio
async def test_empty_and_whitespace_queries_ignored(store):
    await store.add_search("")
    await store.add_search("   ")
    assert await store.get_search_history() == []


@pytest.mark.asyncio
async def test_record_watch_upsert_newest_first(store):
    await store.record_watch(
        {"anime_session": "aaa", "title": "Frieren", "episode_num": 3}
    )
    await store.record_watch(
        {"anime_session": "bbb", "title": "Solo Leveling", "episode_num": 5}
    )
    entries = await store.get_continue_watching()
    assert list(entries) == ["bbb", "aaa"]  # newest first

    # Upserting the same anime keeps one row and refreshes its timestamp.
    await store.record_watch(
        {"anime_session": "aaa", "title": "Frieren", "episode_num": 4}
    )
    entries = await store.get_continue_watching()
    assert len(entries) == 2
    assert list(entries)[0] == "aaa"
    assert entries["aaa"]["episode_num"] == 4

    await store.remove_watch("aaa")
    entries = await store.get_continue_watching()
    assert list(entries) == ["bbb"]


@pytest.mark.asyncio
async def test_continue_watching_capped(store):
    for i in range(CONTINUE_WATCHING_LIMIT + 5):
        await store.record_watch(
            {"anime_session": f"s{i}", "title": f"Anime {i}", "timestamp": i}
        )
    entries = await store.get_continue_watching()
    assert len(entries) == CONTINUE_WATCHING_LIMIT
    # The five oldest (s0..s4) were evicted.
    assert "s0" not in entries
    assert f"s{CONTINUE_WATCHING_LIMIT + 4}" in entries


@pytest.mark.asyncio
async def test_records_survive_reload(store):
    """A fresh store instance over the same file reads what was written."""
    await store.add_search("frieren")
    await store.record_watch({"anime_session": "aaa", "title": "Frieren"})
    reloaded = JsonStore(filename=os.path.basename(store.path))
    assert await reloaded.get_search_history() == ["frieren"]
    assert list(await reloaded.get_continue_watching()) == ["aaa"]


@pytest.mark.asyncio
async def test_records_survive_reload_isolated():
    """Same as above but with an explicit filename (no fixture reuse)."""
    path = os.path.join(_TMP, "animepahe", "reload-check.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        os.unlink(path)
    store = JsonStore(filename="reload-check.json")
    await store.add_search("frieren")
    await store.record_watch({"anime_session": "aaa", "title": "Frieren"})
    reloaded = JsonStore(filename="reload-check.json")
    assert await reloaded.get_search_history() == ["frieren"]
    assert list(await reloaded.get_continue_watching()) == ["aaa"]


@pytest.mark.asyncio
async def test_corrupt_file_recovers_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path))
    (tmp_path / "animepahe").mkdir()
    (tmp_path / "animepahe" / "corrupt.json").write_text("{not json")
    store = JsonStore(filename="corrupt.json")
    assert await store.get_search_history() == []
    # And the next write repairs the file.
    await store.add_search("hello")
    with open(store.path, encoding="utf-8") as f:
        assert json.load(f)["search_history"] == ["hello"]


def teardown_module():
    shutil.rmtree(_TMP, ignore_errors=True)


@pytest.mark.asyncio
async def test_position_resume_rules(store):
    await store.save_position("ep1", 120.0, 1440.0)
    entry = await store.get_position("ep1")
    assert entry == {"position": 120.0, "duration": 1440.0}

    # Under the minimum: not resumable.
    await store.save_position("ep2", 1.5, 1440.0)
    assert await store.get_position("ep2") is None

    # Watched to (nearly) the end: the row is dropped, not just skipped.
    await store.save_position("ep3", 1439.0, 1440.0)
    assert await store.get_position("ep3") is None
    positions = await store.section("positions", {})
    assert "ep3" not in positions

    # Unknown episode: None.
    assert await store.get_position("nope") is None


@pytest.mark.asyncio
async def test_clearance_round_trip(store):
    assert await store.get_clearance() is None
    await store.save_clearance("cf_clearance=abc; __cf_bm=xyz", "UA/1.0")
    entry = await store.get_clearance()
    assert entry["cookies"] == "cf_clearance=abc; __cf_bm=xyz"
    assert entry["user_agent"] == "UA/1.0"
    # Survives a reload (fresh instance, same file) — the boot fix.
    reloaded = JsonStore(filename=os.path.basename(store.path))
    assert (await reloaded.get_clearance())["cookies"] == "cf_clearance=abc; __cf_bm=xyz"
    await store.clear_clearance()
    assert await store.get_clearance() is None


@pytest.mark.asyncio
async def test_clearance_empty_cookies_ignored(store):
    await store.save_clearance("", "UA/1.0")
    assert await store.get_clearance() is None
