"""Yandex ad service wiring: SDK init + interstitial/rewarded/app-open.

Banners live in `components/banner_ad.py` (the canonical builder). This
module owns the SDK service and the fullscreen formats.

- Interstitial: between every episode (one-shot per instance — a fresh
  InterstitialAd per episode, like the official flet-ads example).
- Rewarded: "watch for early access" — unlock the episode past the free
  line for 24h, recorded in the durable store.
- App-open: cold start, after the SDK initializes.
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
AD_REWARDED_UNIT_ID = "demo-rewarded-yandex"
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
    try:
        ad = fya.InterstitialAd(unit_id=AD_INTERSTITIAL_UNIT_ID)
        page.services.append(ad)
        await asyncio.wait_for(ad.show(), timeout=20.0)
        await ad.destroy()
        if ad in page.services:
            page.services.remove(ad)
    except Exception as ex:
        logger.warning("interstitial failed: %s", ex)


async def show_app_open(page) -> None:
    """Cold-start app open ad (the 'comeback' format)."""
    if not is_ads_supported(page):
        return
    try:
        ad = fya.AppOpenAd(unit_id=AD_APP_OPEN_UNIT_ID)
        page.services.append(ad)
        await asyncio.wait_for(ad.show(), timeout=20.0)
        await ad.destroy()
        if ad in page.services:
            page.services.remove(ad)
    except Exception as ex:
        logger.warning("app-open failed: %s", ex)


def build_rewarded_ad(page, episode_key: str, store, on_granted=None):
    """Rewarded ad that unlocks early access for one episode.

    Returns the control so the caller can keep a reference; the reward
    handler grants early access and invokes `on_granted`.
    """
    if not is_ads_supported(page):
        return None

    def _on_reward(e):
        logger.info("reward granted for %s", episode_key)
        from core.tasks import spawn

        async def _grant():
            await store.grant_early_access(episode_key)
            if on_granted:
                on_granted()

        spawn(_grant(), name="grant-early-access")

    ad = fya.RewardedAd(
        unit_id=AD_REWARDED_UNIT_ID,
        on_reward=_on_reward,
        on_load=lambda e: None,
        on_load_failed=lambda e: logger.warning("rewarded load failed"),
    )
    page.services.append(ad)
    return ad
