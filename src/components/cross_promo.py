"""Cross-promo slots — the developer's own apps, in native positions.

Replaces the old fixed bottom rotating banner with the pattern the TV/phone
research supports: a hero card on Home plus an inline "More from us" shelf,
both ordinary focusable nodes in D-pad order. Rotation pauses the moment
anything gains focus (moving focus automatically is the cardinal TV sin) and
never sits between content and navigation.
"""

import asyncio

import flet as ft

from core.tasks import spawn
from core.theme import AppColors

# The developer's apps — same list the old rotating banner carried.
PROMO_APPS = (
    {
        "name": "Nkiri TV",
        "tagline": "Movies, Series & Dramas",
        "badge": "Watch Movies",
        "logo": "nkiri_logo.png",
        "url": "https://tv.kalerosemary7.workers.dev/movies",
    },
    {
        "name": "Socolive TV",
        "tagline": "Live football & highlights",
        "badge": "Live Sports",
        "logo": "socolive_logo.png",
        "url": "https://tv.kalerosemary7.workers.dev/sports",
    },
)

ROTATE_SECONDS = 8


def _open_url(url: str):
    async def _open(e=None):
        try:
            await ft.UrlLauncher().launch_url(url)
        except Exception:
            pass

    return _open


@ft.component
def PromoHero() -> ft.Control:
    """One featured app, auto-rotating; any focus or click pins it."""
    index, set_index = ft.use_state(0)
    pinned, set_pinned = ft.use_state(False)

    from flet import context as flet_context

    try:
        page = flet_context.page
    except Exception:
        page = None

    async def _rotate():
        while True:
            await asyncio.sleep(ROTATE_SECONDS)
            if not pinned:
                set_index(lambda i: (i + 1) % len(PROMO_APPS))

    ft.use_effect(lambda: spawn(_rotate(), name="promo-rotate"), [])

    app = PROMO_APPS[index]
    leading = (
        ft.Container(
            content=ft.Image(src=app["logo"], width=40, height=40, fit="contain"),
            border_radius=8,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        )
        if app["logo"]
        else ft.Container(
            content=ft.Icon(ft.Icons.APPS_ROUNDED, size=24, color=AppColors.PRIMARY),
            width=40,
            height=40,
            border_radius=8,
            alignment=ft.Alignment.CENTER,
            bgcolor=ft.Colors.with_opacity(0.1, AppColors.PRIMARY),
        )
    )

    def _pin_and_open(e):
        set_pinned(True)
        app = PROMO_APPS[index]
        page.run_task(_open_url(app["url"]))

    return ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [
                        leading,
                        ft.Column(
                            [
                                ft.Row(
                                    [
                                        ft.Text(
                                            app["name"],
                                            size=15,
                                            weight=ft.FontWeight.W_700,
                                            color=AppColors.DARK_TEXT,
                                        ),
                                        ft.Container(
                                            content=ft.Text(
                                                app["badge"],
                                                size=9,
                                                weight=ft.FontWeight.W_700,
                                                color=AppColors.PRIMARY,
                                            ),
                                            padding=ft.Padding.symmetric(
                                                horizontal=6, vertical=2
                                            ),
                                            border_radius=6,
                                            border=ft.Border.all(
                                                1,
                                                ft.Colors.with_opacity(
                                                    0.3, AppColors.PRIMARY
                                                ),
                                            ),
                                        ),
                                    ],
                                    spacing=8,
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                ),
                                ft.Text(
                                    app["tagline"],
                                    size=11,
                                    color=AppColors.DARK_TEXT_DIM,
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                        ft.Icon(
                            ft.Icons.ARROW_FORWARD_IOS_ROUNDED,
                            size=14,
                            color=AppColors.DARK_TEXT_DIM,
                        ),
                    ],
                    spacing=12,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                # Rotation dots — also the manual selector (tap a dot to jump).
                ft.Row(
                    [
                        ft.Container(
                            width=10,
                            height=10,
                            border_radius=5,
                            bgcolor=AppColors.PRIMARY
                            if i == index
                            else ft.Colors.with_opacity(0.2, AppColors.DARK_TEXT_DIM),
                            ink=True,
                            tooltip=app_["name"],
                            on_click=lambda e, i=i: (set_pinned(True), set_index(i)),
                        )
                        for i, app_ in enumerate(PROMO_APPS)
                    ],
                    spacing=4,
                ),
            ],
            spacing=10,
        ),
        padding=16,
        border_radius=16,
        bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.WHITE),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.08, ft.Colors.WHITE)),
        ink=True,
        animate=200,
        on_click=_pin_and_open,
    )


