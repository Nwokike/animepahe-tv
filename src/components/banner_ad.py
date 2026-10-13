"""Canonical banner ad builder.

House rule (Sherlock): every screen shows the exact same banner. The glass
container stretches full width; the ad itself stays pinned at its native
320x50 inside it. Never between content and navigation — an ad sandwiched
against nav is the pattern both AdMob's own guidance and TV focus design
call out as wrong.

Collapses to a 0x0 container on desktop/web (and whenever flet-yandex-ads
isn't installed), so shared screens stay safe.

Reload strategy: a banner that fails to fill leaves a blank slot, so a
failed load rebuilds the banner once after a delay (bounded — a dead ad
unit must not spin forever), and a successful load is left alone. The
rebuild goes through the same builder so the caller needs no logic.
"""

import flet as ft

try:
    import flet_yandex_ads as fya

    _HAS_ADS = True
except ImportError:
    fya = None
    _HAS_ADS = False


# Demo unit — replace per platform in production.
AD_BANNER_UNIT_ID = "demo-banner-yandex"

_STICKY_WIDTH = 320
_STICKY_HEIGHT = 50
# One rebuild attempt, after this delay. Yandex's own guidance is to let
# the next refresh handle it; this is that refresh, once.
_RELOAD_DELAY_SECONDS = 30.0
_MAX_RELOADS = 1


def _is_supported(page) -> bool:
    if page is None or not _HAS_ADS:
        return False
    try:
        return page.platform.is_mobile() or page.platform == ft.PagePlatform.ANDROID_TV
    except Exception:
        return False


def build_banner_ad(page=None, inline: bool = False) -> ft.Control:
    """The house banner. `inline=True` sizes to the feed row instead of 320x50."""
    if page is None:
        try:
            from flet import context

            page = context.page
        except Exception:
            return ft.Container(width=0, height=0)

    if not _is_supported(page):
        return ft.Container(width=0, height=0, visible=False)

    def _ad() -> ft.Control:
        try:
            return fya.BannerAd(
                unit_id=AD_BANNER_UNIT_ID,
                size_type=fya.BannerSizeType.INLINE
                if inline
                else fya.BannerSizeType.STICKY,
                on_load=lambda e: None,
                on_load_failed=lambda e: _reload(),
                on_click=lambda e: None,
            )
        except Exception:
            return ft.Container(width=0, height=0, visible=False)

    state = {"attempts": 0}

    def _reload() -> None:
        """One bounded rebuild after a failed fill: a fresh BannerAd in the
        same slot. Without it a dead unit leaves that row blank for the
        rest of the session; with more attempts it would spin forever."""
        if state["attempts"] >= _MAX_RELOADS:
            return
        state["attempts"] += 1
        from core.tasks import spawn

        async def _later():
            import asyncio

            await asyncio.sleep(_RELOAD_DELAY_SECONDS)
            try:
                ad_box.content = _ad()
                ad_box.update()
            except Exception:
                pass

        spawn(_later(), name="banner-reload")

    try:
        ad = _ad()
    except Exception:
        return ft.Container(width=0, height=0, visible=False)

    ad_box = ft.Container(
        content=ad,
        width=None if inline else _STICKY_WIDTH,
        height=None if inline else _STICKY_HEIGHT,
        alignment=ft.Alignment.CENTER,
    )
    glass = ft.Container(
        content=ft.Column(
            [ad_box],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=4,
            tight=True,
        ),
        expand=True,
        padding=8,
        border_radius=16,
        bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.WHITE),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.08, ft.Colors.WHITE)),
    )
    return ft.Row(controls=[glass], alignment=ft.MainAxisAlignment.CENTER)
