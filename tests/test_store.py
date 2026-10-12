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
    assert history[0]["title"] == f"q{SEARCH_HISTORY_LIMIT + 4}"  # newest first
    assert "q0" not in [r["title"] for r in history]  # oldest evicted

    # Re-searching an existing query moves it to the front, no duplicate.
    await store.add_search("q10")
    history = await store.get_search_history()
    assert [r["title"] for r in history].count("q10") == 1
    assert history[0]["title"] == "q10"

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
    assert [r["title"] for r in await reloaded.get_search_history()] == ["frieren"]
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
    assert [r["title"] for r in await reloaded.get_search_history()] == ["frieren"]
    assert list(await reloaded.get_continue_watching()) == ["aaa"]


@pytest.mark.asyncio
async def test_search_selection_records_the_opened_anime(store):
    """Recents remember what was OPENED (title + session), not what was
    typed — re-opening a result is then one tap."""
    await store.add_search("black clover")
    await store.add_search_selection("Black Clover", "sess-a")
    await store.add_search_selection("Black Clover Season 1", "sess-b")
    history = await store.get_search_history()
    # the typed query stays, below what was actually opened
    assert [r["title"] for r in history] == [
        "Black Clover Season 1",
        "Black Clover",
        "black clover",
    ]
    assert history[0]["session"] == "sess-b"
    # re-opening the same session moves it to the front, no duplicate
    await store.add_search_selection("Black Clover", "sess-a")
    assert [r["title"] for r in await store.get_search_history()] == [
        "Black Clover",
        "Black Clover Season 1",
        "black clover",
    ]


@pytest.mark.asyncio
async def test_legacy_string_history_migrates(store):
    """Rows written before the {title, session} shape still read."""
    import json

    with open(store.path, "w", encoding="utf-8") as fh:
        json.dump({"search_history": ["frieren", "naruto"]}, fh)
    store._data = {}
    store._loaded = False
    history = await store.get_search_history()
    assert [r["title"] for r in history] == ["frieren", "naruto"]
    assert all(r["session"] == "" for r in history)


@pytest.mark.asyncio
async def test_remove_search_drops_one_row(store):
    await store.add_search_selection("A", "s1")
    await store.add_search_selection("B", "s2")
    await store.remove_search("A", "s1")
    assert [r["title"] for r in await store.get_search_history()] == ["B"]


@pytest.mark.asyncio
async def test_follows_round_trip_and_cap(store):
    for i in range(230):
        await store.add_follow({"anime_session": f"s{i}", "title": f"T{i}"})
    favorites = await store.get_follows()
    assert len(favorites) == 200
    assert "s229" in favorites  # newest kept
    assert "s0" not in favorites  # oldest pruned
    assert await store.is_following("s229") is True
    assert (
        await store.toggle_follow({"anime_session": "s229", "title": "T"}) is False
    )
    assert await store.is_following("s229") is False


@pytest.mark.asyncio
async def test_follows_never_store_base64_posters(store):
    await store.add_follow(
        {"anime_session": "s1", "title": "T", "poster": "data:image/webp;base64,AAAA"}
    )
    row = (await store.get_follows())["s1"]
    assert row["poster"] == ""


@pytest.mark.asyncio
async def test_legacy_favorites_section_migrates_to_follows(store):
    """A 1.0.4 file carries a `favorites` section and no `follows`: the
    upgrade path must rename it on read, persist that, and never raise.
    The branch once called a helper that does not exist, so every user
    arriving with a 1.0.4 library crashed here."""
    import json

    legacy = {"s1": {"title": "Naruto", "poster": "http://p/1.jpg"}}
    with open(store.path, "w", encoding="utf-8") as f:
        json.dump({"favorites": legacy}, f)

    assert await store.get_follows() == legacy

    on_disk = json.load(open(store.path, encoding="utf-8"))
    assert on_disk["follows"] == legacy
    assert "favorites" not in on_disk  # the old name is retired, not kept

    # A second instance reads the migrated section without migrating again.
    reloaded = JsonStore(filename=os.path.basename(store.path))
    assert await reloaded.get_follows() == legacy


@pytest.mark.asyncio
async def test_external_player_round_trip(store):
    assert await store.get_external_player() is False
    await store.save_external_player(True)
    assert await store.get_external_player() is True


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
        rows = json.load(f)["search_history"]
    assert [r["title"] for r in rows] == ["hello"]


def teardown_module():
    shutil.rmtree(_TMP, ignore_errors=True)


@pytest.mark.asyncio
async def test_position_resume_rules(store):
    await store.save_position("ep1", 120.0, 1440.0)
    entry = await store.get_position("ep1")
    # the row travels whole — the rate and any later field ride with it
    assert entry["position"] == 120.0 and entry["duration"] == 1440.0
    assert entry["timestamp"] > 0

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


def test_early_access_round_trip(tmp_path, monkeypatch):

    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path))
    from services.store import JsonStore

    (tmp_path / "animepahe").mkdir(parents=True, exist_ok=True)

    async def _run():
        store = JsonStore(filename="ea-test.json")
        assert await store.is_early_access("ep1") is False
        await store.grant_early_access("ep1")
        assert await store.is_early_access("ep1") is True
        # Survives a reload (fresh instance, same file).
        reloaded = JsonStore(filename="ea-test.json")
        assert await reloaded.is_early_access("ep1") is True

    asyncio.run(_run())


def test_early_access_expiry(tmp_path, monkeypatch):

    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path))
    from services.store import JsonStore

    (tmp_path / "animepahe").mkdir(parents=True, exist_ok=True)

    async def _run():
        store = JsonStore(filename="ea-expiry.json")
        await store.put_section(
            "early_access", {"ep1": 1.0}
        )  # epoch 1 — long expired
        assert await store.is_early_access("ep1") is False

    asyncio.run(_run())
