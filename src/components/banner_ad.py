"""Canonical banner ad builder.

House rule (Sherlock): every screen shows the exact same banner. The glass
container stretches full width; the ad itself stays pinned at its native
320x50 inside it. Never between content and navigation — an ad sandwiched
against nav is the pattern both AdMob's own guidance and TV focus design
call out as wrong.

Collapses to a 0x0 container on desktop/web (and whenever flet-yandex-ads
isn't installed), so shared screens stay safe.
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

    try:
        ad = fya.BannerAd(
            unit_id=AD_BANNER_UNIT_ID,
            size_type=fya.BannerSizeType.INLINE if inline else fya.BannerSizeType.STICKY,
            on_load=lambda e: None,
            on_load_failed=lambda e: None,
            on_click=lambda e: None,
        )
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
