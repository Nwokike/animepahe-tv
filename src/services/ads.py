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

import flet as ft

try:
    import flet_yandex_ads as fya

    _HAS_ADS = True
except ImportError:
    fya = None
    _HAS_ADS = False

logger = logging.getLogger(__name__)

AD_INTERSTITIAL_UNIT_ID = "demo-interstitial-yandex"
AD_APP_OPEN_UNIT_ID = "demo-appopenad-yandex"


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
        user_consent=True,
        logging=True,
        on_initialized=on_initialized,
        on_init_failed=on_init_failed,
    )


async def show_interstitial(page) -> None:
    """One-shot interstitial between episodes."""
    if not is_ads_supported(page):
        return
    ad = None
    try:
        ad = fya.InterstitialAd(unit_id=AD_INTERSTITIAL_UNIT_ID)
        page.services.append(ad)
        await asyncio.wait_for(ad.show(), timeout=20.0)
        # show() returns as the ad OPENS; destroy() before the dismissal
        # races the visible ad (the study's §7.2). Wait for the actual
        # dismissal, then tear down.
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
        ad = fya.AppOpenAd(unit_id=AD_APP_OPEN_UNIT_ID)
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
