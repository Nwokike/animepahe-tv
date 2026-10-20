"""Discover — the filtered catalog, generated from the SERVING provider's
own vocabulary.

Nothing about genres, categories, types or sorts is hardcoded here: the
provider returns its filter spec at runtime (the site's own lists), this
screen renders it. A provider whose source has no browse surface reports
an empty spec and the screen says so — it never invents filters.

Layout (owner's order): the filters are the HOUSE's outlined pills in
ONE horizontal line that pans sideways when it overflows — KTV Player's
components/filter_bar.py, copied — with the sort as its own control and
an ad slot above the grid. The "via <source>" line is gone: the header
already names the source, twice.
"""

import flet as ft

from components.ad_breaks import grid_with_ads
from components.banner_ad import build_banner_ad
from components.offline_state import empty_or_offline
from components.pagination import pager as ft_pager
from components.result_card import result_card as _result_card
from core.theme import AppColors
from core.tokens import BREAKPOINT_TABLET, FONT_LG, FONT_MD, GRID_COL, ICON_MD, ICON_SM, SPACING_XS
from hooks.use_grid_mode import grid_sources, use_grid_mode
from state.app_state import AppStateCtx
from state.controller_ctx import ControllerMethodsCtx

# Keys whose "no selection" state is meaningless — there is no "sort by
# all", the list always has an active order (the owner, 2026-10-19: "There
# is no such thing as sort all, sort by all"). These groups therefore never
# get the synthetic "All" first option.
_NO_ALL_KEYS = frozenset({"orderby", "sort"})

# The direction control shown beside the sort group: WordPress's `order`
# query parameter, and the up/down arrows every catalog sort carries
# (owner, 2026-10-19: "there is no way to make it up to down and down to
# up... Normally when you see category sort, you see something that points
# up to down and down to up"). Only sources whose spec declares
# "direction" get the control — AniKato's own form has no order
# parameter, so a toggle there would flip an arrow and change nothing.
_ORDER_KEY = "order"


def _multi_valued_keys(filters: list[dict]) -> set[str]:
    """The filter keys that take SEVERAL values, read from the provider's
    own spec ("multi": True) instead of a hardcoded list here.

    The hardcoded list was wrong the moment it was written: it wrapped
    AniKato's genre/status/season in a list the site's form never wanted
    (the request became ``genre[]=['1']`` and the grid came back empty —
    2026-10-19), and it missed WordPress's "type" key. The provider
    declares the shape; the screen renders it."""
    return {str(spec.get("key")) for spec in filters or [] if spec.get("multi")}


def _sort_defaults(filters: list[dict]) -> dict[str, str]:
    """The sort group's own default: the FIRST option the provider listed
    ("Recently updated" for the WordPress sources, "Default" for
    AniKato). The dropdown shows it, so the request must ask for it too —
    a displayed value that is never sent is a lie (the owner's "the
    numbering... does not update", 2026-10-19)."""
    out: dict[str, str] = {}
    for spec in filters or []:
        key = str(spec.get("key") or "")
        if key not in _NO_ALL_KEYS:
            continue
        options = spec.get("options") or []
        if options:
            out[key] = str(options[0]["value"])
    return out


def _effective_selections(selections: dict | None, filters: list[dict]) -> dict:
    """The selections as the SOURCE will receive them: every sort group
    carries its default order even when the user never touched it, so
    what the dropdown shows is what the site is asked for."""
    out = dict(selections or {})
    for key, value in _sort_defaults(filters).items():
        if not out.get(key):
            out[key] = value
    return out


# The filter bar, copied from the house's own: KTV Player's
# components/filter_bar.py ("Country / Category / Custom are
# PopupMenuButton triggers that render as compact outlined pills (icon +
# label + chevron)"). The owner's instruction was to do EXACTLY what their
# own apps do, so the constants, the pill and the trigger below are the
# house's, unchanged.
#
# The house's shape also settles the sort: in the Apple TV / KTV bar the
# SORT is not one of the filters, so here it gets its own row (the
# owner's report, 2026-10-19: "they put the filter and the sort").
_TRIGGER_STYLE = ft.ButtonStyle(
    bgcolor=ft.Colors.TRANSPARENT,
    elevation=0,
    shadow_color=ft.Colors.TRANSPARENT,
    overlay_color=ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
    padding=ft.Padding.all(0),
    shape=ft.RoundedRectangleBorder(radius=8),
)

# Menu dropdown styling — PopupMenuButton uses direct params, not MenuStyle
_MENU_BG = ft.Colors.SURFACE
_MENU_SHADOW = ft.Colors.with_opacity(0.15, ft.Colors.BLACK)
_MENU_ELEVATION = 4
_MENU_PADDING = ft.Padding.symmetric(vertical=4)
_MENU_SHAPE = ft.RoundedRectangleBorder(radius=8)

# The pill's icon per filter group, in the house's idiom (a leading icon
# that names the group).
_PILL_ICON = {
    "genre": ft.Icons.LOCAL_MOVIES_OUTLINED,
    "type": ft.Icons.CATEGORY_OUTLINED,
    "status": ft.Icons.SELL_OUTLINED,
    "season": ft.Icons.CALENDAR_MONTH_OUTLINED,
    "categories": ft.Icons.LOCAL_MOVIES_OUTLINED,
    "orderby": ft.Icons.SORT_ROUNDED,
    "sort": ft.Icons.SORT_ROUNDED,
}


def _selection_label(spec: dict, selected) -> str:
    """The label a pill shows for the value it holds.

    A multi-valued key holds a LIST; a single-valued key holds a string.
    Stringifying the list ("['1']") matches no option, so the pill would
    revert to the group label and never show what was picked."""
    label = spec.get("label", spec["key"])
    options = spec.get("options") or []
    if isinstance(selected, list):
        labels = []
        for value in selected:
            text = next(
                (str(o.get("label", o["value"])) for o in options if str(o["value"]) == str(value)),
                str(value),
            )
            labels.append(text)
        return ", ".join(labels) if labels else label
    current = "" if selected in (None, "") else str(selected)
    return next(
        (str(o.get("label", o["value"])) for o in options if str(o["value"]) == current),
        label,
    )


def _pill(
    label: str,
    icon: str,
    is_selected: bool,
    show_arrow: bool = True,
    compact: bool = True,
    tooltip: str = "",
) -> ft.Control:
    """Compact outlined pill: icon + text + chevron (TV-minimum 48px tall).

    The house's pill, verbatim (KTV components/filter_bar.py)."""
    border_color = (
        AppColors.PRIMARY
        if is_selected
        else ft.Colors.with_opacity(0.3, ft.Colors.OUTLINE_VARIANT)
    )
    bg = (
        ft.Colors.with_opacity(0.08, AppColors.PRIMARY)
        if is_selected
        else ft.Colors.TRANSPARENT
    )
    font_size = FONT_MD if compact else FONT_LG
    icon_size = ICON_SM if compact else ICON_MD
    # Vertical padding keeps the pill at the ~48px touch target: compact
    # text (12px) + 2x8 vertical + border ~= 44-48px on density 1 screens.
    pad = (
        ft.Padding.symmetric(horizontal=8, vertical=8)
        if compact
        else ft.Padding.symmetric(horizontal=12, vertical=10)
    )

    controls: list[ft.Control] = [
        ft.Icon(icon, size=icon_size),
        ft.Text(label, size=font_size, no_wrap=True),
    ]
    if show_arrow:
        controls.append(ft.Icon(ft.Icons.ARROW_DROP_DOWN, size=icon_size))

    return ft.Container(
        content=ft.Row(
            controls=controls,
            spacing=2,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=pad,
        border=ft.Border.all(1, border_color),
        border_radius=8,
        bgcolor=bg,
        tooltip=tooltip or None,
    )


def _menu_button(
    label: str,
    icon: str,
    is_selected: bool,
    items,
    tooltip: str = "",
    compact: bool = True,
) -> ft.Control:
    """The house's trigger: a PopupMenuButton whose content is the pill."""
    return ft.PopupMenuButton(
        content=_pill(label, icon, is_selected, compact=compact, tooltip=tooltip),
        items=items,
        menu_position=ft.PopupMenuPosition.UNDER,
        style=_TRIGGER_STYLE,
        bgcolor=_MENU_BG,
        shadow_color=_MENU_SHADOW,
        elevation=_MENU_ELEVATION,
        menu_padding=_MENU_PADDING,
        shape=_MENU_SHAPE,
    )


def _filter_menu(spec: dict, selected, on_pick) -> list[ft.PopupMenuItem]:
    """The options of one filter, as the house's menu items.

    Radio semantics per key: picking a value replaces the previous one;
    "All" (an empty value) clears it — except for order-only groups
    (Sort), where "All" would be meaningless.
    """
    key = spec["key"]
    options = spec.get("options") or []
    current = "" if selected in (None, "") else str(selected)
    items: list[ft.PopupMenuItem] = []
    if key not in _NO_ALL_KEYS:
        items.append(
            ft.PopupMenuItem(
                content=ft.Text("All", size=FONT_MD),
                checked=not current,
                on_click=lambda e, k=key: on_pick(k, ""),
            )
        )
    for option in options:
        value = str(option["value"])
        items.append(
            ft.PopupMenuItem(
                content=ft.Text(str(option.get("label", value)), size=FONT_MD),
                checked=value == current,
                on_click=lambda e, k=key, v=value: on_pick(k, v),
            )
        )
    return items


@ft.component
def DiscoverScreen() -> ft.Control:
    state = ft.use_context(AppStateCtx)
    controller = ft.use_context(ControllerMethodsCtx)
    _ = state.discover_version

    # The provider's own filter vocabulary — the shape of every key
    # (multi-valued, sortable, its default) is read from THIS, never
    # hardcoded here.
    filters = state.discover_filters or []

    # The detected grid shape for this screen (its own backend's own art).
    discover_sources = grid_sources(state.discover_results or [], lambda a: a.poster)
    grid_mode = use_grid_mode("discover", discover_sources, state.discover_source, state)

    def _pick(key: str, value):
        selections = dict(state.discover_selections or {})
        multi = _multi_valued_keys(filters)
        if value in (None, ""):
            selections.pop(key, None)  # "All" clears the filter
        elif selections.get(key) == value:
            # A second pick of the same value clears the filter — but for
            # a SORT group that would leave the dropdown claiming an order
            # the site is no longer being asked for (the owner's "does
            # not update"). It returns to the group's own default.
            if key in _NO_ALL_KEYS:
                selections[key] = _sort_defaults(filters).get(key, value)
            else:
                selections.pop(key, None)
        else:
            # A multi-valued key travels as a LIST: the provider joins
            # them, and a bare string would be iterated character by
            # character (category 14893 became categories=1,4,8,9,3 —
            # the owner's "DVD 2 but open DVD and there are more").
            selections[key] = [value] if key in multi else value
        controller.load_discover(_effective_selections(selections, filters), 1)

    ft.use_effect(
        lambda: controller.load_discover_filters() if not state.discover_filters else None,
        [],
    )

    header = ft.Row(
        [
            # No big screen title here: every other screen names itself in
            # the shared header's subtitle, and a second "Discover" one
            # screen below read as a stutter.
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
            padding=ft.Padding.only(left=16, right=16, bottom=16),
            expand=True,
        )

    # The FILTERS are a row of house pills; the SORT is its own control on
    # its own row (the owner's report, 2026-10-19: "they put the filter
    # and the sort" — the sort is not one of the filters). The pills are
    # ONE horizontal line that scrolls horizontally, never wrapping.
    #
    # The numeric groups (AniKato's "Min episodes") are NOT rendered:
    # the house's filter bar is a row of value pickers, and the owner's
    # call was to drop the minimum-episode field.
    #
    # KTV's responsive switch: the pills shrink below the tablet
    # breakpoint (FONT_MD/ICON_SM, 8/8 padding) and keep the full size
    # above it. `compact` is a per-render snapshot of the width.
    try:
        _page_width = float(getattr(page, "width", 0) or 0)
    except (TypeError, ValueError):
        _page_width = 0.0
    compact = _page_width <= BREAKPOINT_TABLET
    filter_specs = [spec for spec in filters if spec.get("kind") != "number"]
    sort_specs = [spec for spec in filter_specs if spec.get("key") in _NO_ALL_KEYS]
    value_specs = [spec for spec in filter_specs if spec.get("key") not in _NO_ALL_KEYS]
    filter_controls: list[ft.Control] = []
    for spec in value_specs:
        key = spec["key"]
        selected = (state.discover_selections or {}).get(key)
        shown = _selection_label(spec, selected)
        filter_controls.append(
            _menu_button(
                shown,
                _PILL_ICON.get(key, ft.Icons.FILTER_LIST_OUTLINED),
                bool(selected) and selected != "",
                _filter_menu(spec, selected, _pick),
                tooltip=f"Filter by {spec.get('label', key).lower()}",
                compact=compact,
            )
        )
    # The SORT, on its own row: a house pill that opens the source's own
    # order list, plus the direction arrow where the SOURCE has a
    # direction to toggle (the provider's spec says so, "direction":
    # True). AniKato's own form has no order parameter, so the arrow
    # there flipped and changed nothing (2026-10-19) — no arrow is
    # drawn for it.
    sort_controls: list[ft.Control] = []
    for spec in sort_specs:
        selected = (state.discover_selections or {}).get(spec["key"])
        if not selected:
            options = spec.get("options") or []
            selected = str(options[0]["value"]) if options else None
        shown = _selection_label(spec, selected)
        sort_controls.append(
            _menu_button(
                shown,
                _PILL_ICON.get(spec["key"], ft.Icons.SORT_ROUNDED),
                True,
                _filter_menu(spec, str(selected), _pick),
                tooltip=f"Sort by {spec.get('label', spec['key']).lower()}",
                compact=compact,
            )
        )
    if any(spec.get("direction") for spec in sort_specs):
        order = str((state.discover_selections or {}).get(_ORDER_KEY) or "desc")

        def _toggle_order(e=None):
            selections = dict(state.discover_selections or {})
            current = str(selections.get(_ORDER_KEY) or "desc")
            selections[_ORDER_KEY] = "asc" if current == "desc" else "desc"
            controller.load_discover(_effective_selections(selections, filters), 1)

        sort_controls.append(
            ft.IconButton(
                # The house convention: the icon names the mode the tap
                # LANDS ON, not the one it is leaving. "asc" (oldest
                # first) taps to "desc" (newest first) → down arrow.
                icon=ft.Icons.ARROW_DOWNWARD_ROUNDED
                if order == "asc"
                else ft.Icons.ARROW_UPWARD_ROUNDED,
                icon_size=ICON_SM,
                icon_color=AppColors.PRIMARY,
                # The house pill's own outline (radius 8, the same 1px
                # border, the same 8/8 padding as the filter pills), with
                # the focus ring the house's focus cue uses.
                style=ft.ButtonStyle(
                    bgcolor=ft.Colors.with_opacity(0.08, AppColors.PRIMARY),
                    shape=ft.RoundedRectangleBorder(radius=8),
                    padding=ft.Padding.symmetric(horizontal=8, vertical=8),
                    side={
                        ft.ControlState.FOCUSED: ft.BorderSide(2.5, AppColors.PRIMARY),
                        ft.ControlState.DEFAULT: ft.BorderSide(
                            1, ft.Colors.with_opacity(0.3, ft.Colors.OUTLINE_VARIANT)
                        ),
                    },
                ),
                tooltip="Newest first" if order == "asc" else "Oldest first",
                on_click=_toggle_order,
            )
        )
    # ONE horizontal line of pills, always — the house's bar (KTV's
    # components/filter_bar.py): a Row with no `wrap` (the flet default
    # is False) and `scroll=AUTO`, so the pills pan sideways when they
    # outrun the screen instead of dropping to a second line. The bar owns
    # its own 8/4 padding (KTV's) and the PAGE beneath it owns the vertical
    # scrolling — the bar never scrolls away.
    filter_row = ft.Container(
        content=ft.Row(
            filter_controls,
            spacing=SPACING_XS,
            scroll=ft.ScrollMode.AUTO,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding.symmetric(horizontal=8, vertical=4),
    )
    sort_row = (
        ft.Container(
            content=ft.Row(
                sort_controls,
                spacing=SPACING_XS,
                scroll=ft.ScrollMode.AUTO,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=8, vertical=4),
            alignment=ft.Alignment.CENTER_RIGHT,
        )
        if sort_controls
        else None
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
            col=GRID_COL,
        )
        for anime in results
    ]

    # The shared header: the source pill/badge are on EVERY screen, so
    # swapping a walled backend never depends on being on Home.
    #
    # The filter bar is a FIXED strip: the results region beneath it owns
    # the vertical scrolling (KTV's shape), so the pills never scroll away
    # with the grid. Before this they sat inside the page's scrolling
    # column, which carried them off-screen on the first flick.
    fixed: list[ft.Control] = [
        app_header(state, page, controller, subtitle="Discover"),
        header,
        ft.Container(height=10),
        filter_row,
        # The SORT has its own row — it is not one of the filters.
        *([sort_row] if sort_row is not None else []),
        # An ad under the filter row, before the results (KTV's search
        # screen slot: under the header, above the grid).
        build_banner_ad(page, inline=True),
    ]
    results: list[ft.Control] = []
    if state.discover_results:
        # Every 12 cards, a break; then one more before the pager (KTV's
        # grid-then-banner-then-pager shape).
        results.extend(grid_with_ads(cards, page))
        results.append(
            ft_pager(
                page=state.discover_page,
                has_more=state.discover_has_more,
                on_prev=lambda e: controller.load_discover(
                    _effective_selections(state.discover_selections, filters),
                    state.discover_page - 1,
                ),
                on_next=lambda e: controller.load_discover(
                    _effective_selections(state.discover_selections, filters),
                    state.discover_page + 1,
                ),
                is_loading=False,
            )
        )
    else:
        results.append(
            empty_or_offline(
                state,
                icon=ft.Icons.SEARCH_OFF_ROUNDED,
                title="Nothing matched",
                message="Loosen a filter and try again.",
                on_retry=lambda e: controller.load_discover(
                    _effective_selections(state.discover_selections, filters),
                    state.discover_page,
                ),
                on_downloads=lambda e: controller.open_downloads(),
            )
        )
    return ft.Container(
        content=ft.Column(
            [
                ft.Column(fixed, spacing=0, tight=True),
                # The results region scrolls vertically on its own.
                ft.Column(
                    results,
                    spacing=0,
                    expand=True,
                    scroll=ft.ScrollMode.AUTO,
                ),
            ],
            spacing=0,
            expand=True,
        ),
        padding=ft.Padding.only(left=16, right=16, bottom=16),
        expand=True,
    )
