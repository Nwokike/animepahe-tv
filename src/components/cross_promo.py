"""Cross-promo slots — the developer's own apps, in native positions.

Replaces the old fixed bottom rotating banner with the pattern the TV/phone
research supports: a hero card on Home plus an inline "More from us" shelf,
both ordinary focusable nodes in D-pad order. Rotation pauses the moment
anything gains focus (moving focus automatically is the cardinal TV sin) and
never sits between content and navigation.

The hero carries the original 1.0.9's three slides — the two apps plus a
support slide. The hero itself is a flat ``FilledButton`` (a Container card
can't receive D-pad focus in flet 1.0.4) with the shared card focus styling.
"""

import asyncio

import flet as ft

from components.focus_styles import (
    attach_focus_zoom,
    card_button_style,
    card_focus_scale,
)
from core.shared_services import get_shared_services
from core.tasks import spawn
from core.theme import AppColors

# The developer's apps — same list the old rotating banner carried — plus
# the support slide the 1.0.9 build had as its third hero item.
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
    {
        "name": "Contact Support & Send Feedback",
        "tagline": "Suggest features, report bugs, or request content",
        "badge": "Contact Support",
        "logo": None,
        "url": None,  # -> the support dialog, not a browser launch
    },
)

ROTATE_SECONDS = 8


async def _open_url(page, url: str):
    await get_shared_services(page).launch_url(url)


@ft.component
def PromoHero() -> ft.Control:
    """One featured app, auto-rotating; any focus or click pins it."""
    index, setindex = ft.use_state(0)
    pinned, set_pinned = ft.use_state(False)

    from flet import context as flet_context

    try:
        page = flet_context.page
    except Exception:
        page = None

    # A stable slot for the rotation task, so the effect's cleanup can
    # cancel exactly the task it started.
    task_ref = ft.use_ref()

    async def _rotate():
        while True:
            await asyncio.sleep(ROTATE_SECONDS)
            # pinned is read through the closure — the effect re-arms on
            # the [pinned] dep change, so it never serves a stale
            # first-render False.
            if not pinned:
                setindex(lambda i: (i + 1) % len(PROMO_APPS))

    def _start_rotation():
        task_ref.current = spawn(_rotate(), name="promo-rotate")

    def _cancel_rotation():
        task = task_ref.current
        if task is not None:
            task.cancel()
            task_ref.current = None

    # The effect re-arms when pinned flips, and the cleanup CANCELS the
    # rotation task: the old fire-and-forget version rotated forever
    # after Home unmounted (a leak, and setindex on a dead component).
    ft.use_effect(_start_rotation, [pinned], cleanup=_cancel_rotation)

    app = PROMO_APPS[index]
    leading = (
        ft.Container(
            content=ft.Image(src=app["logo"], width=40, height=40, fit="contain"),
            border_radius=8,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        )
        if app["logo"]
        else ft.Container(
            content=ft.Icon(
                ft.Icons.MARK_CHAT_UNREAD_ROUNDED,
                size=24,
                color=AppColors.PRIMARY,
            ),
            width=40,
            height=40,
            border_radius=8,
            alignment=ft.Alignment.CENTER,
            bgcolor=ft.Colors.with_opacity(0.1, AppColors.PRIMARY),
        )
    )

    def _pin_and_open(e):
        set_pinned(True)
        # page can be None outside a live context (the guard above) —
        # the old code ran page.run_task unconditionally.
        if page is None:
            return
        if app["url"]:
            page.run_task(_open_url, page, app["url"])
        else:
            from components.support_dialog import show_support_dialog

            show_support_dialog(page)

    def _pin_and_jump(i):
        set_pinned(True)
        setindex(i)

    body = ft.Column(
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
                                        color=ft.Colors.ON_SURFACE,
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
                                color=ft.Colors.ON_SURFACE_VARIANT,
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
                        color=ft.Colors.ON_SURFACE_VARIANT,
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
                        else ft.Colors.with_opacity(0.2, ft.Colors.ON_SURFACE_VARIANT),
                        ink=True,
                        tooltip=app_["name"],
                        on_click=lambda e, i=i: _pin_and_jump(i),
                    )
                    for i, app_ in enumerate(PROMO_APPS)
                ],
                spacing=4,
            ),
        ],
        spacing=10,
    )
    # A focusable button, not a Container: the D-pad has to be able to
    # reach the hero at all. Same shared styling as the content cards.
    # on_focus pins the rotation (the module's core promise — "rotation
    # pauses the moment anything gains focus") and chains safely with the
    # zoom handler.
    return attach_focus_zoom(
        ft.FilledButton(
            content=body,
            style=card_button_style(padding=16, radius=16, overlay_alpha=0.18),
            animate_scale=card_focus_scale(1.02),
            on_click=_pin_and_open,
            on_focus=lambda e: set_pinned(True),
        )
    )
