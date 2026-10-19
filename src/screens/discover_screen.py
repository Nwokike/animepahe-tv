"""Discover — the filtered catalog, generated from the SERVING provider's
own vocabulary.

Nothing about genres, categories, types or sorts is hardcoded here: the
provider returns its filter spec at runtime (the site's own lists), this
screen renders it. A provider whose source has no browse surface reports
an empty spec and the screen says so — it never invents filters.

Layout (owner's order, 2026-10-16): the filters are DROPDOWNS in a
compact row — a wall of chips read as noise — an ad slot sits under the
filter row, the grid is Discover-sized, and an ad break lands before the
pager. The "via <source>" line is gone: the header already names the
source, twice.
"""

import flet as ft

from components.ad_breaks import grid_with_ads
from components.banner_ad import build_banner_ad
from components.offline_state import empty_or_offline
from components.pagination import pager as ft_pager
from components.result_card import result_card as _result_card
from hooks.use_grid_mode import grid_sources, use_grid_mode
from state.app_state import AppStateCtx
from state.controller_ctx import ControllerMethodsCtx


def _filter_dropdown(spec: dict, selected, on_pick) -> ft.Control:
    """One filter group as a Dropdown — the owner's order: genre, type,
    status, season and sort collapse into compact pickers instead of a
    wall of chips. Radio semantics per key: picking a value replaces the
    previous one; "All" (an empty value) clears it."""
    key = spec["key"]
    label = spec.get("label", key)
    options = spec.get("options") or []
    if spec.get("kind") == "number":
        field = ft.TextField(
            value=str(selected or ""),
            hint_text=label,
            width=110,
            height=44,
            text_size=12,
            keyboard_type=ft.KeyboardType.NUMBER,
            on_submit=lambda e, k=key: on_pick(k, (e.control.value or "").strip()),
            on_blur=lambda e, k=key: on_pick(k, (e.control.value or "").strip()),
        )
        return field
    items = [ft.DropdownOption(key="", text="All")]
    items += [
        ft.DropdownOption(key=str(o["value"]), text=str(o.get("label", o["value"])))
        for o in options
    ]
    return ft.Dropdown(
        label=label,
        value="" if selected in (None, "") else str(selected),
        options=items,
        width=170,
        text_size=12,
        label_style=ft.TextStyle(size=11),
        dense=True,
        on_select=lambda e, k=key: on_pick(k, e.control.value or ""),
    )


@ft.component
def DiscoverScreen() -> ft.Control:
    state = ft.use_context(AppStateCtx)
    controller = ft.use_context(ControllerMethodsCtx)
    _ = state.discover_version

    # The detected grid shape for this screen (its own backend's own art).
    discover_sources = grid_sources(state.discover_results or [], lambda a: a.poster)
    grid_mode = use_grid_mode("discover", discover_sources, state.discover_source, state)

    def _pick(key: str, value):
        selections = dict(state.discover_selections or {})
        if value == "" or selections.get(key) == value:
            selections.pop(key, None)  # a second tap clears the chip
        else:
            selections[key] = value
        controller.load_discover(selections, 1)

    ft.use_effect(
        lambda: controller.load_discover_filters() if not state.discover_filters else None,
        [],
    )

    header = ft.Row(
        [
            ft.Text("Discover", size=22, weight=ft.FontWeight.W_700),
            ft.Container(expand=True),
            # No "via <source>" here — the shared header names the active
            # source twice already (the title pill and the badge). An owner
            # called it out (2026-10-16).
            ft.IconButton(
                icon=ft.Icons.SEARCH_ROUNDED,
                tooltip="Search",
                on_click=lambda e: controller.open_search(),
            ),
            ft.TextButton(
                content="Reset",
                on_click=lambda e: controller.load_discover({}, 1),
            ),
        ],
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    from flet import context as flet_context

    try:
        page = flet_context.page
    except Exception:
        page = None

    from components.app_header import app_header

    filters = state.discover_filters or []
    if not filters:
        return ft.Container(
            content=ft.Column(
                [
                    app_header(state, page, controller, subtitle="Discover"),
                    header,
                    ft.Container(height=24),
                    empty_or_offline(
                        state,
                        icon=ft.Icons.EXPLORE_OFF_ROUNDED,
                        title="This source offers no discovery",
                        message="The chosen source exposes no filtered browse. "
                        "Pick another source (Settings → Content source) or "
                        "just search — nothing else is consulted on its behalf.",
                        on_retry=lambda e: controller.load_discover_filters(),
                        on_downloads=lambda e: controller.open_downloads(),
                    ),
                ],
                spacing=0,
                expand=True,
                scroll=ft.ScrollMode.AUTO,
            ),
            padding=ft.Padding.only(left=24, right=24, bottom=16),
            expand=True,
        )

    # Dropdowns, not a chip wall (owner's order) — wrapped naturally
    # without expand=True spacers (Expanded inside a wrap=True Row throws
    # Flutter's "WrapParentData is not a subtype of FlexParentData" error).
    filter_row = ft.Row(
        [
            _filter_dropdown(spec, (state.discover_selections or {}).get(spec["key"]), _pick)
            for spec in filters
        ],
        spacing=8,
        wrap=True,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    results = state.discover_results or []
    cards = [
        ft.Container(
            content=_result_card(
                anime,
                controller.open_anime,
                col=None,
                mode=grid_mode,
                provider=state.discover_source or state.current_source_name,
            ),
            col={"xs": 6, "sm": 4, "md": 3, "lg": 2, "xl": 2},
        )
        for anime in results
    ]

    body: list[ft.Control] = [
        # The shared header: the source pill/badge are on EVERY screen, so
        # swapping a walled backend never depends on being on Home.
        app_header(state, page, controller, subtitle="Discover"),
        header,
        ft.Container(height=10),
        filter_row,
        # An ad under the filter row, before the results (KTV's search
        # screen slot: under the header, above the grid).
        build_banner_ad(page, inline=True),
    ]
    if results:
        # Every 12 cards, a break; then one more before the pager (KTV's
        # grid-then-banner-then-pager shape).
        body.extend(grid_with_ads(cards, page, spacing=16, run_spacing=16))
        body.append(
            ft_pager(
                page=state.discover_page,
                has_more=state.discover_has_more,
                on_prev=lambda e: controller.load_discover(
                    dict(state.discover_selections or {}), state.discover_page - 1
                ),
                on_next=lambda e: controller.load_discover(
                    dict(state.discover_selections or {}), state.discover_page + 1
                ),
                is_loading=False,
            )
        )
    else:
        body.append(
            empty_or_offline(
                state,
                icon=ft.Icons.SEARCH_OFF_ROUNDED,
                title="Nothing matched",
                message="Loosen a filter and try again.",
                on_retry=lambda e: controller.load_discover(
                    state.discover_selections, state.discover_page
                ),
                on_downloads=lambda e: controller.open_downloads(),
            )
        )
    return ft.Container(
        content=ft.Column(body, spacing=0, expand=True, scroll=ft.ScrollMode.AUTO),
        padding=ft.Padding.only(left=24, right=24, bottom=16),
        expand=True,
    )
