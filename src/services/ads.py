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

# Configurable seam for Yandex ad unit IDs. Default to official test IDs
# ("demo-*-yandex") so development and testing works out of the box;
# production IDs (R-M-XXXXXX-Y) can be supplied via environment variables or
# swapped directly here when ready for store submission.
AD_UNITS = {
    "banner": os.getenv("YANDEX_BANNER_UNIT_ID", "demo-banner-yandex"),
    "interstitial": os.getenv("YANDEX_INTERSTITIAL_UNIT_ID", "demo-interstitial-yandex"),
    "rewarded": os.getenv("YANDEX_REWARDED_UNIT_ID", "demo-rewarded-yandex"),
    "app_open": os.getenv("YANDEX_APP_OPEN_UNIT_ID", "demo-appopenad-yandex"),
}

AD_INTERSTITIAL_UNIT_ID = AD_UNITS["interstitial"]
AD_APP_OPEN_UNIT_ID = AD_UNITS["app_open"]

# Minimum interval between interstitials (Sherlock house pattern)
INTERSTITIAL_MIN_INTERVAL_SEC = 30.0
_last_interstitial_time = 0.0

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


async def show_interstitial(page) -> None:
    """One-shot interstitial between episodes, rate-limited by interval guard."""
    if not is_ads_supported(page):
        return

    global _last_interstitial_time
    now = time.monotonic()
    if now - _last_interstitial_time < INTERSTITIAL_MIN_INTERVAL_SEC:
        logger.debug(
            "Interstitial skipped (interval guard: %.1fs < %.1fs)",
            now - _last_interstitial_time,
            INTERSTITIAL_MIN_INTERVAL_SEC,
        )
        return

    ad = None
    try:
        ad = fya.InterstitialAd(
            unit_id=AD_INTERSTITIAL_UNIT_ID,
            on_impression=lambda e: logger.debug("Interstitial impression: %s", getattr(e, "impression_data", "")),
        )
        page.services.append(ad)
        await asyncio.wait_for(ad.show(), timeout=20.0)
        _last_interstitial_time = time.monotonic()
        # show() returns as the ad OPENS; wait for actual dismissal
        await asyncio.wait_for(ad.wait_for_dismiss(), timeout=120.0)
    except Exception as ex:
        logger.warning("interstitial failed: %s", ex)
    finally:
        if ad is not None:
            try:
                await ad.destroy()
            except Exception:
                pass
            if ad in page.services:
                page.services.remove(ad)


async def show_app_open(page) -> None:
    """Cold-start app open ad (the 'comeback' format)."""
    if not is_ads_supported(page):
        return
    ad = None
    try:
        ad = fya.AppOpenAd(
            unit_id=AD_APP_OPEN_UNIT_ID,
            on_impression=lambda e: logger.debug("AppOpen impression: %s", getattr(e, "impression_data", "")),
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
                pass
            if ad in page.services:
                page.services.remove(ad)
