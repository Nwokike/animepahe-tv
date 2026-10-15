"""M2/M4-contract hardening regressions.

The M2 correctness round and the in-flight M4 edits were validated by the
existing suite only; these tests pin each RISKY change individually so a
later refactor cannot silently undo one:

- core/state: every mutable collection is per-instance AND observable
  (in-place mutation notifies), no duplicate player_error annotation
- store: get_follows returns a copy (callers only read), corrupt non-dict
  rows cannot crash record_watch/add_follow, the file on disk is fsync'd
  valid JSON
- notify: the fullscreen toast dispatches even when the page path fails;
  unregister(handler) is staleness-guarded
- shared_services: haptics/share mount lazily exactly once
- cache: an expired get() persists the eviction (survives a reload)
- hls_proxy: the master cache key includes headers
- downloads: _calculate_dir_size sums files, tolerates a missing dir
- ads: demo-id seam defaults, runtime consent setters land in the
  service kwargs, interstitial interval guard skips a second show
- banner_ad: seam id + inline max_height + observability handlers
- home_screen: the Continue Watching shelf filters malformed rows
"""

import asyncio
import json
import os
import sys
import tempfile
from typing import ClassVar

_TMP = tempfile.mkdtemp(prefix="animepahe-m2-test-")
os.environ["FLET_APP_STORAGE_DATA"] = _TMP
os.environ.setdefault("FLET_APP_STORAGE_CACHE", _TMP)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import flet as ft


class _MobilePage:
    """A fake page whose platform reports Android (ads-supported) and
    whose services list is per-instance."""

    platform = ft.PagePlatform.ANDROID

    def __init__(self):
        self.services = []


def _walk(control):
    yield control
    for child in getattr(control, "controls", None) or []:
        yield from _walk(child)
    content = getattr(control, "content", None)
    if content is not None and not isinstance(content, (list, str)):
        yield from _walk(content)


# ---------------------------------------------------------------------------
# core/state — observable, per-instance collections
# ---------------------------------------------------------------------------


def test_every_mutable_collection_is_observable_after_init():
    """The bug class: class-level defaults shared across instances and
    never wrapped by Observable.__setattr__ (in-place mutation silent)."""
    from flet.components.observable import ObservableDict, ObservableList

    from core.state import AppState

    state = AppState()
    for name in (
        "search_results",
        "latest_releases",
        "episodes",
        "search_history",
        "source_test_results",
        "schedule_tabs",
        "schedule_entries",
        "discover_filters",
        "discover_results",
    ):
        assert isinstance(getattr(state, name), ObservableList), name
    for name in (
        "continue_watching",
        "discover_selections",
        "downloads",
        "follows",
    ):
        assert isinstance(getattr(state, name), ObservableDict), name


def test_in_place_mutation_notifies_subscribers():
    from core.state import AppState

    state = AppState()
    fired = []
    # Observable listeners live in a WeakSet: the callback MUST be kept
    # referenced or a notification would never fire.
    listener = lambda *a, **k: fired.append(True)
    state.subscribe(listener)
    state.latest_releases.append(object())  # in-place, no reassignment
    assert fired, "an in-place append must notify observers"


def test_mutable_collections_are_per_instance():
    from core.state import AppState

    a, b = AppState(), AppState()
    a.latest_releases.append("x")
    assert b.latest_releases == []
    assert a.starting_downloads is not b.starting_downloads


def test_player_error_annotation_is_declared_once():
    """A duplicate annotation collapses into one dataclass field — count
    the SOURCE lines, not the fields."""
    path = os.path.join(
        os.path.dirname(__file__), "..", "src", "core", "state.py"
    )
    with open(path, encoding="utf-8") as f:
        source = f.read()
    assert source.count("player_error:") == 1
    from core.state import AppState

    assert AppState.player_error is None


# ---------------------------------------------------------------------------
# store
# ---------------------------------------------------------------------------


def _fresh_store():
    import itertools

    from services.store import JsonStore

    if not hasattr(_fresh_store, "_seq"):
        _fresh_store._seq = itertools.count()
    os.environ["FLET_APP_STORAGE_DATA"] = _TMP  # other test modules overwrite it
    return JsonStore(filename=f"m2-{next(_fresh_store._seq)}.json")


def test_get_follows_returns_a_copy():
    """The lock-holding accessor must not hand out the live dict — a
    caller mutating it in place would bypass put_section."""
    store = _fresh_store()

    async def scenario():
        await store.add_follow({"anime_session": "s1", "title": "A"})
        view = await store.get_follows()
        view["s2"] = {"anime_session": "s2"}
        view.pop("s1", None)
        again = await store.get_follows()
        assert "s1" in again and "s2" not in again

    asyncio.run(scenario())


def test_record_watch_survives_a_corrupt_row():
    """A non-dict row in the section (old shape / hand-edit) crashed the
    timestamp sort with AttributeError."""
    store = _fresh_store()

    async def scenario():
        await store.put_section("continue_watching", {"bad": "string-row"})
        await store.record_watch({"anime_session": "s1", "title": "A"})
        entries = await store.get_continue_watching()
        assert "s1" in entries

    asyncio.run(scenario())


def test_add_follow_eviction_survives_a_corrupt_row():
    store = _fresh_store()
    store.FOLLOWS_LIMIT = 2

    async def scenario():
        await store.put_section("follows", {"bad": "string-row"})
        await store.add_follow({"anime_session": "a"})
        await store.add_follow({"anime_session": "b"})
        await store.add_follow({"anime_session": "c"})
        follows = await store.get_follows()
        assert "c" in follows  # newest kept, eviction ran without crashing

    asyncio.run(scenario())


def test_store_file_is_valid_json_after_a_write():
    """Exercises the fsync'd atomic path end to end."""
    store = _fresh_store()

    async def scenario():
        await store.put_section("probe", {"x": 1})

    asyncio.run(scenario())
    with open(store.path, encoding="utf-8") as f:
        assert json.load(f)["probe"] == {"x": 1}


# ---------------------------------------------------------------------------
# notify
# ---------------------------------------------------------------------------


def test_toast_dispatches_even_when_the_page_path_fails():
    """The fullscreen toast used to ride AFTER show_dialog: a page-path
    failure swallowed the only visible feedback in native fullscreen."""
    from core import notify

    class _BrokenPage:
        def show_dialog(self, dlg):
            raise RuntimeError("no page session")

    seen = []
    notify.register_fullscreen_toast(lambda msg: seen.append(msg))
    try:
        notify.show_snack(_BrokenPage(), "playback failed")  # must not raise
    finally:
        notify.unregister_fullscreen_toast()
    assert seen == ["playback failed"]


def test_unregister_is_staleness_guarded():
    from core import notify

    def old(msg):
        pass

    def new(msg):
        pass

    notify.register_fullscreen_toast(old)
    notify.register_fullscreen_toast(new)
    # A stale unmount (the OLD handler) must not clear the NEW one.
    notify.unregister_fullscreen_toast(old)
    assert notify._toast is new
    notify.unregister_fullscreen_toast()
    assert notify._toast is None


# ---------------------------------------------------------------------------
# shared_services — lazy haptics/share
# ---------------------------------------------------------------------------


class _ServicePage:
    def __init__(self):
        self.services: list = []


def test_haptics_and_share_mount_lazily_once():
    from core.shared_services import get_shared_services

    page = _ServicePage()
    services = get_shared_services(page)
    assert len(page.services) == 2  # launcher + clipboard only
    h1 = services.haptics
    s1 = services.share
    assert len(page.services) == 4
    assert services.haptics is h1  # second access reuses
    assert services.share is s1
    assert len(page.services) == 4  # and does not re-append


# ---------------------------------------------------------------------------
# cache
# ---------------------------------------------------------------------------


def test_expired_get_persists_the_eviction():
    import time

    from services.cache import Cache

    cache = Cache(filename="m2-cache.json")

    async def scenario():
        await cache.set("k", "v", ttl=3600)
        # Force-expire by rewriting the entry through the internals.
        async with cache._lock:
            await cache._ensure_loaded()
            cache._data["k"]["expires"] = int(time.time()) - 1
            cache._dirty = True
            await cache._flush()
        assert await cache.get("k") is None

    asyncio.run(scenario())
    # A fresh instance reading the same file must not see the entry.
    fresh = Cache(filename="m2-cache.json")

    async def check():
        assert await fresh.get("k") is None

    asyncio.run(check())


# ---------------------------------------------------------------------------
# hls_proxy — cache key includes headers
# ---------------------------------------------------------------------------


def test_master_cache_key_distinguishes_headers():
    from services.hls_proxy import HLSProxy

    class _Resp:
        status_code = 200
        headers: ClassVar[dict] = {"Content-Type": "application/vnd.apple.mpegurl"}
        text = "#EXTM3U\n"

    class _Client:
        def __init__(self):
            self.calls = 0

        async def get(self, url, headers=None, **kwargs):
            self.calls += 1
            return _Resp()

    async def scenario():
        proxy = HLSProxy()
        proxy._http_client = _Client()
        await proxy.fetch_master("https://x/m.m3u8", headers={"Referer": "a"})
        await proxy.fetch_master("https://x/m.m3u8", headers={"Referer": "a"})
        assert proxy._http_client.calls == 1  # cached
        await proxy.fetch_master("https://x/m.m3u8", headers={"Referer": "b"})
        assert proxy._http_client.calls == 2  # different headers, new fetch

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# downloads — dir size helper
# ---------------------------------------------------------------------------


def test_calculate_dir_size():
    from services.downloads import _calculate_dir_size

    assert _calculate_dir_size(os.path.join(_TMP, "nope")) == 0
    target = tempfile.mkdtemp(dir=_TMP)
    with open(os.path.join(target, "a"), "wb") as f:
        f.write(b"x" * 100)
    with open(os.path.join(target, "b"), "wb") as f:
        f.write(b"y" * 50)
    assert _calculate_dir_size(target) == 150


# ---------------------------------------------------------------------------
# ads — seam defaults, consent setters, interval guard
# ---------------------------------------------------------------------------


def test_ad_unit_seam_defaults_to_demo_ids():
    from services import ads

    assert ads.AD_UNITS["banner"] == "demo-banner-yandex"
    assert ads.AD_UNITS["interstitial"] == "demo-interstitial-yandex"
    assert ads.AD_UNITS["rewarded"] == "demo-rewarded-yandex"
    assert ads.AD_UNITS["app_open"] == "demo-appopenad-yandex"
    assert ads.AD_INTERSTITIAL_UNIT_ID == "demo-interstitial-yandex"


def test_consent_setters_land_in_the_service(monkeypatch):
    from services import ads

    captured = {}

    class _FakeFya:
        class YandexAdsService:
            def __init__(self, **kwargs):
                captured.update(kwargs)

    monkeypatch.setattr(ads, "fya", _FakeFya)
    monkeypatch.setattr(ads, "_HAS_ADS", True)

    ads.set_user_consent(False)
    ads.set_location_tracking(True)
    ads.set_age_restricted(False)
    try:
        ads.build_ad_service(_MobilePage())
    finally:
        ads.set_user_consent(True)
        ads.set_location_tracking(False)
    assert captured["user_consent"] is False
    assert captured["location_tracking"] is True
    assert captured["age_restricted"] is False


def test_interstitial_interval_guard(monkeypatch):
    from services import ads

    shown = []

    class _FakeAd:
        def __init__(self, **kwargs):
            shown.append(kwargs.get("unit_id"))

        async def show(self):
            pass

        async def wait_for_dismiss(self):
            pass

        async def destroy(self):
            pass

    class _FakeFya:
        InterstitialAd = _FakeAd

    monkeypatch.setattr(ads, "fya", _FakeFya)
    monkeypatch.setattr(ads, "_HAS_ADS", True)
    monkeypatch.setattr(ads, "_last_interstitial_time", 0.0)

    page = _MobilePage()

    async def scenario():
        await ads.show_interstitial(page)
        assert len(shown) == 1
        # Immediately again: inside the 30s window — skipped.
        await ads.show_interstitial(page)
        assert len(shown) == 1

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# banner_ad — seam id + inline knobs + observability handlers
# ---------------------------------------------------------------------------


def test_banner_uses_the_seam_and_passes_inline_knobs():
    """Pins the in-flight banner change: the unit id comes from
    services.ads's seam, and the inline banner carries max_height plus a
    real on_load_failed/on_click/on_impression."""
    import flet_yandex_ads as fya

    from components import banner_ad
    from services import ads

    control = banner_ad.build_banner_ad(_MobilePage(), inline=True)
    found = [c for c in _walk(control) if isinstance(c, fya.BannerAd)]
    assert len(found) == 1
    ad = found[0]
    assert ad.unit_id == ads.AD_UNITS["banner"]
    assert ad.max_height == banner_ad._INLINE_MAX_HEIGHT
    assert callable(ad.on_load_failed)
    assert callable(ad.on_click)


# ---------------------------------------------------------------------------
# home_screen — continue shelf filters malformed rows
# ---------------------------------------------------------------------------


def test_continue_shelf_filters_malformed_rows():
    from screens.home_screen import _continue_watching_row

    assert _continue_watching_row({}, lambda s: None) is None

    entries = {
        "good": {"anime_session": "s1", "title": "Show", "episode_num": 3},
        "bad-str": "not-a-dict",
        "no-session": {"title": "No session"},
    }
    row = _continue_watching_row(entries, lambda s: None)
    assert row is not None
    buttons = [c for c in _walk(row) if isinstance(c, ft.FilledButton)]
    assert len(buttons) == 1  # only the valid row
