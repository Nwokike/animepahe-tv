"""Discover — the filtered catalog, generated from the SERVING provider's
own vocabulary.

Nothing about genres, categories, types or sorts is hardcoded here: the
provider returns its filter spec at runtime (the site's own lists), this
screen renders it. A provider whose source has no browse surface reports
an empty spec and the screen says so — it never invents filters.
"""

import flet as ft

from components.banner_ad import build_banner_ad
from components.offline_state import empty_or_offline
from components.pagination import pager as ft_pager
from components.result_card import result_card as _result_card
from hooks.use_grid_mode import grid_sources, use_grid_mode
from state.app_state import AppStateCtx
from state.controller_ctx import ControllerMethodsCtx


def _filter_choices(spec: dict, selected, on_pick) -> ft.Control:
    """One filter group as chips. Radio semantics per key: picking a value
    replaces the previous one, and an empty value clears it."""
    key = spec["key"]
    options = spec.get("options") or []
    if spec.get("kind") == "number":
        field = ft.TextField(
            value=str(selected or ""),
            hint_text=spec.get("label", ""),
            width=120,
            height=40,
            text_size=12,
            keyboard_type=ft.KeyboardType.NUMBER,
            on_submit=lambda e, k=key: on_pick(k, (e.control.value or "").strip()),
            on_blur=lambda e, k=key: on_pick(k, (e.control.value or "").strip()),
        )
        return ft.Row([ft.Text(spec.get("label", ""), size=12), field], spacing=8)
    chips = [
        ft.Container(
            content=ft.Text(label, size=12, weight=ft.FontWeight.W_500),
            padding=ft.Padding.symmetric(horizontal=12, vertical=6),
            border_radius=16,
            ink=True,
            bgcolor=ft.Colors.with_opacity(0.18, ft.Colors.PRIMARY)
            if selected == value
            else ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
            on_click=lambda e, k=key, v=value: on_pick(k, v),
        )
        for value, label in ((o["value"], o.get("label", o["value"])) for o in options)
    ]
    return ft.Column(
        [
            ft.Text(spec.get("label", ""), size=12, weight=ft.FontWeight.W_700),
            ft.Row(chips, spacing=6, wrap=True),
        ],
        spacing=4,
        tight=True,
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
        lambda: (
            controller.load_discover_filters() if not state.discover_filters else None
        ),
        [],
    )

    header = ft.Row(
        [
            ft.Text("Discover", size=22, weight=ft.FontWeight.W_700),
            ft.Container(expand=True),
            ft.Text(
                f"via {state.discover_source.capitalize()}"
                if state.discover_source
                else "",
                size=12,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
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

    filters = state.discover_filters or []
    if not filters:
        return ft.Column(
            [
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
                ),
            ],
            spacing=0,
        )

    chips = ft.Column(
        [
            _filter_choices(
                spec, (state.discover_selections or {}).get(spec["key"]), _pick
            )
            for spec in filters
        ],
        spacing=10,
        tight=True,
    )

    results = state.discover_results or []
    grid = ft.ResponsiveRow(
        controls=[
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
        ],
        spacing=16,
        run_spacing=16,
    )

    body: list[ft.Control] = [
        header,
        ft.Container(height=12),
        chips,
        ft.Container(height=12),
    ]
    if results:
        body.append(grid)
        body.append(build_banner_ad(None, inline=True))
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
            )
        )
    return ft.Container(
        content=ft.Column(body, spacing=0, expand=True, scroll=ft.ScrollMode.AUTO),
        padding=ft.Padding.only(left=24, right=24, bottom=16),
        expand=True,
    )
