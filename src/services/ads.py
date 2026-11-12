"""Yandex ad service wiring: SDK init + interstitial/rewarded/app-open.

Banners live in `components/banner_ad.py` (the canonical builder). This
module owns the SDK service and the fullscreen formats.

- Interstitial: between every episode (one-shot per instance — a fresh
  InterstitialAd per episode, like the official flet-ads example).
- App-open: cold start, after the SDK initializes.
- The rewarded format is NOT wired: "unlock the episode past the free
  line" needs a gate the app does not have, and inventing a paywall is
  the owner's call, not a code decision. Recorded in docs/roadmap.md.
"""

import asyncio
import logging
import os
import time

import flet as ft

try:
    import flet_yandex_ads as fya

    _HAS_ADS = True
except ImportError:
    fya = None
    _HAS_ADS = False

logger = logging.getLogger(__name__)

# The owner's production Yandex unit IDs (app 20208795, added 2026-10-16):
# one unit per format, exactly as the partner interface lists them.
# Environment variables still override for a local test setup, but the
# shipped default is the real monetization, not a demo id.
AD_UNITS = {
    "banner": os.getenv("YANDEX_BANNER_UNIT_ID", "R-M-20208795-1"),
    "interstitial": os.getenv("YANDEX_INTERSTITIAL_UNIT_ID", "R-M-20208795-3"),
    "rewarded": os.getenv("YANDEX_REWARDED_UNIT_ID", "R-M-20208795-4"),
    "app_open": os.getenv("YANDEX_APP_OPEN_UNIT_ID", "R-M-20208795-5"),
}

AD_INTERSTITIAL_UNIT_ID = AD_UNITS["interstitial"]
AD_APP_OPEN_UNIT_ID = AD_UNITS["app_open"]

# Minimum interval between interstitials (Sherlock house pattern)
INTERSTITIAL_MIN_INTERVAL_SEC = 30.0
_last_interstitial_time = 0.0

# KTV Player's show_interstitial bounds (ad_service.py:289-380): the pre-roll
# may hold playback for at most these windows, and never past the outer
# asyncio.wait_for in start_playback (20 s). Offline, the on-demand ad simply
# never loads inside its window and playback starts — the ad still shows the
# moment it arrives, exactly as KTV Player does.
_PRELOAD_LOAD_WAIT_SEC = 10.0
_PRELOADED_DISMISS_SEC = 30.0
_ON_DEMAND_WAIT_SEC = 10.0

# App-open cadence: cold start via on_initialized, then at most once per
# APP_OPEN_MIN_INTERVAL_SEC on session reconnects (Yandex treats app-open as
# a resume format, but not on every reconnect).
APP_OPEN_MIN_INTERVAL_SEC = 4 * 3600.0
_last_app_open_time = 0.0

# Preloaded interstitial (KTV discipline: preload at startup, re-preload after
# every dismiss, so a show never waits on a cold load). Yandex fullscreen ads
# are one-shot per instance, so the preload holds exactly one ad.
_preloaded_ad = None
_preload_ready: "asyncio.Event | None" = None
_preload_lock = asyncio.Lock()

# Privacy & targeting defaults (settable at runtime before or after init)
_user_consent = True
_location_tracking = False
_age_restricted = False


def set_user_consent(value: bool) -> None:
    global _user_consent
    _user_consent = bool(value)


def set_location_tracking(value: bool) -> None:
    global _location_tracking
    _location_tracking = bool(value)


def set_age_restricted(value: bool) -> None:
    global _age_restricted
    _age_restricted = bool(value)


def is_ads_supported(page) -> bool:
    if not _HAS_ADS or page is None:
        return False
    try:
        return page.platform.is_mobile() or page.platform == ft.PagePlatform.ANDROID_TV
    except Exception:
        return False


def build_ad_service(page, on_initialized=None, on_init_failed=None) -> ft.Control:
    """The SDK service; appended to page.services once at startup."""
    if not is_ads_supported(page):
        return ft.Container(width=0, height=0, visible=False)
    return fya.YandexAdsService(
        user_consent=_user_consent,
        location_tracking=_location_tracking,
        age_restricted=_age_restricted,
        logging=True,
        on_initialized=on_initialized,
        on_init_failed=on_init_failed,
    )


async def preload_interstitial(page) -> None:
    """Preload one interstitial so the next show has no load latency.

    The ad starts loading as soon as it is appended to ``page.services``;
    ``_preload_ready`` is set from its ``on_load``/``on_load_failed`` events.
    """
    global _preloaded_ad, _preload_ready
    if not is_ads_supported(page):
        return
    async with _preload_lock:
        if _preloaded_ad is not None:
            return
        ready = asyncio.Event()
        ad = fya.InterstitialAd(
            unit_id=AD_INTERSTITIAL_UNIT_ID,
            on_load=lambda e: ready.set(),
            on_load_failed=lambda e: ready.set(),  # unblock the waiter either way
        )
        page.services.append(ad)
        _preloaded_ad = ad
        _preload_ready = ready


async def _discard_ad(page, ad) -> None:
    if ad is None:
        return
    try:
        await ad.destroy()
    except Exception:
        logger.debug("suppressed")
    try:
        if ad in page.services:
            page.services.remove(ad)
    except Exception:
        logger.debug("suppressed")


async def show_interstitial(page) -> None:
    """One-shot interstitial — KTV Player's exact flow (ad_service.py:289-380),
    never skipped and never allowed to hold playback hostage.

    - Preloaded ad: wait ≤10 s for load → show → wait ≤30 s for dismiss.
    - No preloaded ad (or it failed): the on-demand ad shows ITSELF from
      ``on_load``; this returns when it is dismissed/failed or after 10 s,
      whichever comes first — KTV's own rule: "If it fails or takes too
      long, timeout and let the video play so the user isn't stuck." A slow
      or offline load still shows the ad the moment it arrives, overlaying
      playback exactly as KTV Player does.
    """
    if not is_ads_supported(page):
        return

    global _last_interstitial_time, _preloaded_ad, _preload_ready
    now = time.monotonic()
    if now - _last_interstitial_time < INTERSTITIAL_MIN_INTERVAL_SEC:
        logger.debug(
            "Interstitial deferred (interval guard: %.1fs < %.1fs)",
            now - _last_interstitial_time,
            INTERSTITIAL_MIN_INTERVAL_SEC,
        )
        return

    async with _preload_lock:
        ad, ready = _preloaded_ad, _preload_ready
        _preloaded_ad, _preload_ready = None, None

    # --- preloaded path -------------------------------------------------
    if ad is not None and ready is not None and not ready.is_set():
        logger.info("Waiting for the preloaded interstitial to finish loading...")
        try:
            await asyncio.wait_for(ready.wait(), timeout=_PRELOAD_LOAD_WAIT_SEC)
        except TimeoutError:
            logger.warning(
                "Preloaded ad not ready within %ss — falling back to on-demand",
                _PRELOAD_LOAD_WAIT_SEC,
            )
            await _discard_ad(page, ad)
            ad = None

    if ad is not None:
        try:
            logger.info("Showing the preloaded interstitial ad...")
            await ad.show()
            _last_interstitial_time = time.monotonic()
            try:
                await asyncio.wait_for(
                    ad.wait_for_dismiss(), timeout=_PRELOADED_DISMISS_SEC
                )
            except TimeoutError:
                logger.warning(
                    "Timed out waiting for the preloaded interstitial to close"
                )
            try:
                asyncio.get_running_loop().create_task(preload_interstitial(page))
            except Exception:
                logger.debug("interstitial re-preload skipped")
            return
        except Exception:
            logger.exception("Failed to show the preloaded interstitial ad")
        finally:
            await _discard_ad(page, ad)

    # --- on-demand path (KTV's shape: the ad shows itself from on_load) --
    logger.info("No preloaded ad ready. Loading a fresh ad on-demand...")
    ad_closed = asyncio.Event()

    def _release(e=None):
        ad_closed.set()
        _release_service(page.services, fresh)

    async def _show_when_loaded():
        try:
            await fresh.show()
            _last_interstitial_time = time.monotonic()
            logger.info("On-demand interstitial ad shown.")
        except Exception as ex:
            logger.warning("On-demand ad failed to show: %s", ex)
            _release()

    def _load_failed(e):
        logger.warning("On-demand ad load failed: %s", getattr(e, "data", e))
        _release()

    def _show_failed(e):
        logger.warning("On-demand ad failed to show: %s", getattr(e, "data", e))
        _release()

    def _dismissed(e):
        logger.info("On-demand ad closed by user")
        _release(e)
        try:
            page.run_task(preload_interstitial, page)
        except Exception:
            logger.debug("interstitial re-preload skipped")

    fresh = None
    try:
        fresh = fya.InterstitialAd(
            unit_id=AD_INTERSTITIAL_UNIT_ID,
            on_load=lambda e: page.run_task(_show_when_loaded),
            on_load_failed=_load_failed,
            on_failed_to_show=_show_failed,
            on_dismiss=_dismissed,
            on_impression=lambda e: logger.debug(
                "Interstitial impression: %s", getattr(e, "impression_data", "")
            ),
        )
        page.services.append(fresh)
        # A show was ATTEMPTED: arm the interval guard now, not when the ad
        # eventually appears, so a slow load cannot double-fire.
        _last_interstitial_time = time.monotonic()
        try:
            # The ad loads and shows itself; this only gates playback until
            # it is on screen and closed (or the window passes — KTV's bound).
            await asyncio.wait_for(ad_closed.wait(), timeout=_ON_DEMAND_WAIT_SEC)
        except TimeoutError:
            logger.warning(
                "On-demand interstitial not ready within %ss — letting the "
                "video play; the ad still shows when it loads",
                _ON_DEMAND_WAIT_SEC,
            )
    except Exception:
        logger.exception("Failed to create the on-demand interstitial ad")
        _release()


def _release_service(services, item) -> None:
    """Drop a spent ad service so Flet's service GC can unregister it."""
    if item is None:
        return
    try:
        if item in services:
            services.remove(item)
    except Exception:
        logger.debug("ad service release skipped")


async def show_app_open(page) -> None:
    """App-open ad: cold start via ``on_initialized``, then at most once per
    APP_OPEN_MIN_INTERVAL_SEC on session reconnects."""
    if not is_ads_supported(page):
        return
    global _last_app_open_time
    now = time.monotonic()
    if now - _last_app_open_time < APP_OPEN_MIN_INTERVAL_SEC:
        return
    _last_app_open_time = now
    ad = None
    try:
        ad = fya.AppOpenAd(
            unit_id=AD_APP_OPEN_UNIT_ID,
            on_impression=lambda e: logger.debug(
                "AppOpen impression: %s", getattr(e, "impression_data", "")
            ),
        )
        page.services.append(ad)
        await asyncio.wait_for(ad.show(), timeout=20.0)
        await asyncio.wait_for(ad.wait_for_dismiss(), timeout=120.0)
    except Exception as ex:
        logger.warning("app-open failed: %s", ex)
    finally:
        if ad is not None:
            try:
                await ad.destroy()
            except Exception:
                logger.debug("suppressed")
            if ad in page.services:
                page.services.remove(ad)
