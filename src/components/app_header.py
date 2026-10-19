"""app_header — the ONE header every screen shares (Sherlock's pattern).

Left: an optional round back button (sub-screens), the app icon, and the
source pill — "<Backend> TV ▾", the content-source switcher — with the
screen's own name as a quiet subtitle beneath it.

Right: the version/update pill, the screen's own extra actions, then the
theme cycle. The whole right group rides a ``Row(scroll=AUTO)``: the
house rule (Sherlock) is **scroll, never clip** — on a phone the actions
pan instead of shoving the title off the edge, so the whole bar scrolls
sideways when a screen adds many actions. The backend badge (the second
source readout) rides the same row on WIDE screens only: on a narrow
phone it is dropped because the title pill already opens the identical
picker and the row needs the room (owner, 2026-10-19).

Every screen renders it, so switching backends (and theme) never depends on
being on Home or finding Settings — the owner's reuse pattern from Sherlock
and CollabShell. Sub-screens (an anime's episodes) pass ``on_back``: the
back control lives INSIDE this header, never as a second bar stacked above
it (the owner's report, 2026-10-16 — a separate AppBar put "back · Anime"
ahead of the header).

**Every control here is a Button-family control, never a Container.** That
is not a style preference: against the installed flet 1.0.4, the controls
that expose ``on_focus``/``on_blur`` are 28 classes — the Button family,
TextField, Switch, Checkbox, Radio, Slider, Dropdown — and ``ft.Container``
is NOT among them. A Container has no focus state, so on a TV remote it
can never be highlighted, let alone activated. The house apps (Sherlock's
version chip, KTV's header actions) are Containers; they are phone-first,
and this app is not.
"""

import flet as ft

from core.constants import APP_NAME, APP_VERSION
from core.theme import AppColors, next_theme_mode
from core.tokens import BREAKPOINT_TABLET

__all__ = ["app_header", "backend_title", "theme_icon_for"]

THEME_ICONS = {
    ft.ThemeMode.DARK: ft.Icons.DARK_MODE_ROUNDED,
    ft.ThemeMode.LIGHT: ft.Icons.LIGHT_MODE_ROUNDED,
    ft.ThemeMode.SYSTEM: ft.Icons.SETTINGS_SYSTEM_DAYDREAM_ROUNDED,
}


def _focus_sides(default: ft.BorderSide | None = None) -> dict:
    """The border map every header control wears: nothing at rest, a
    PRIMARY ring when the remote is on it. The house focus cue
    (``components/focus_styles.card_button_style``'s side map) — without
    it a D-pad user cannot see which control the focus is on."""
    return {
        ft.ControlState.FOCUSED: ft.BorderSide(2.5, AppColors.PRIMARY),
        ft.ControlState.HOVERED: ft.BorderSide(2.0, ft.Colors.with_opacity(0.6, AppColors.PRIMARY)),
        ft.ControlState.PRESSED: ft.BorderSide(2.5, AppColors.PRIMARY),
        ft.ControlState.DEFAULT: default or ft.BorderSide(0, ft.Colors.TRANSPARENT),
    }


def _chip_style(
    *,
    radius: int = 10,
    bgcolor=None,
    color=None,
    padding: ft.PaddingValue | None = None,
    default_border: ft.BorderSide | None = None,
) -> ft.ButtonStyle:
    """The house chip look (Sherlock's version chip / DDGS's version chip):
    a soft tinted plate with a rounded radius — on a Button-family control
    so it can take D-pad focus, with a PRIMARY ring when focused."""
    return ft.ButtonStyle(
        bgcolor=bgcolor or ft.Colors.TRANSPARENT,
        color=color or ft.Colors.ON_SURFACE,
        padding=padding or ft.Padding.symmetric(horizontal=10, vertical=4),
        shape=ft.RoundedRectangleBorder(radius=radius),
        side=_focus_sides(default_border),
        overlay_color={
            ft.ControlState.FOCUSED: ft.Colors.with_opacity(0.12, AppColors.PRIMARY),
            ft.ControlState.HOVERED: ft.Colors.with_opacity(0.06, AppColors.PRIMARY),
            ft.ControlState.PRESSED: ft.Colors.with_opacity(0.12, AppColors.PRIMARY),
            ft.ControlState.DEFAULT: ft.Colors.TRANSPARENT,
        },
        elevation=0,
    )



def backend_title(state) -> str:
    """`<Backend> TV` — "Anikato TV", "Animepahe TV" — the active source's
    own name for the header. The brand name only stands in before anything
    is resolved (the splash covers that moment)."""
    name = (getattr(state, "current_source_name", "") or "").strip()
    return f"{name.capitalize()} TV" if name else APP_NAME


def theme_icon_for(page, state=None) -> ft.IconData:
    """The icon names the mode the tap LANDS ON (the cycle's next mode).

    The mode comes from ``state.theme_mode`` — the observable field the
    header cycle and the Settings picker both drive — so the icon lands
    via a re-render, never by mutating the control (frozen subtrees raise
    "Frozen controls cannot be updated."). The page is only a fallback
    before the observable has anything."""
    mode = getattr(state, "theme_mode", None) if state is not None else None
    if mode is None:
        mode = getattr(page, "theme_mode", ft.ThemeMode.SYSTEM) if page else ft.ThemeMode.SYSTEM
    return THEME_ICONS.get(next_theme_mode(mode), ft.Icons.DARK_MODE_ROUNDED)


def _cycle_theme(page, controller, state=None) -> ft.IconData:
    """DARK -> LIGHT -> SYSTEM -> DARK, persisted. Returns the icon that
    now names the mode the NEXT tap lands on. The mode lands on the page
    AND on ``state.theme_mode`` (observable), which is what re-renders the
    header's icon through the normal component path."""
    if state is None:
        return ft.Icons.DARK_MODE_ROUNDED
    current = getattr(state, "theme_mode", None)
    if current is None:
        current = getattr(page, "theme_mode", ft.ThemeMode.SYSTEM) if page else ft.ThemeMode.SYSTEM
    nxt = next_theme_mode(current)
    if page is not None:
        page.theme_mode = nxt
    state.theme_mode = nxt
    app_controller = getattr(controller, "_app_controller", None)
    if app_controller is not None:
        from core.tasks import spawn

        spawn(app_controller.save_theme_mode(nxt), name="save-theme")
    return THEME_ICONS.get(next_theme_mode(nxt), ft.Icons.DARK_MODE_ROUNDED)


def _version_pill(state, page) -> ft.Control:
    """Quiet "vX.Y.Z" normally; morphs into the update pill when the boot
    check found a newer build. BOTH states are tappable and open the
    update dialog — up-to-date opens the bundled changelog. The house
    pattern (KTV/Sherlock/DDGS): the version is always a live chip, and
    the changelog is one tap away on a phone.

    A ``TextButton`` wearing the house chip style, not a Container: the
    chip must be reachable by D-pad (installed flet 1.0.4 gives a
    Container no focus state at all)."""
    from components.update_dialog import show_update_dialog

    update_data = state.update_data if state.update_available else None
    if update_data:
        return ft.TextButton(
            content=ft.Row(
                [
                    ft.Text(
                        "Update Available!",
                        size=11,
                        weight=ft.FontWeight.BOLD,
                        color=AppColors.PRIMARY,
                        no_wrap=True,
                    ),
                    ft.Container(width=6, height=6, border_radius=3, bgcolor=AppColors.PRIMARY),
                ],
                spacing=4,
                alignment=ft.MainAxisAlignment.CENTER,
                tight=True,
            ),
            style=_chip_style(
                radius=10,
                bgcolor=ft.Colors.with_opacity(0.15, AppColors.PRIMARY),
                color=AppColors.PRIMARY,
                padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                default_border=ft.BorderSide(1.5, AppColors.PRIMARY),
            ),
            tooltip="A new version is available — tap to view",
            on_click=lambda e: show_update_dialog(page, update_data) if page else None,
        )
    return ft.TextButton(
        content=ft.Text(
            f"v{APP_VERSION}",
            size=11,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.ON_SURFACE_VARIANT,
            no_wrap=True,
        ),
        style=_chip_style(
            radius=10,
            bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE_VARIANT),
            color=ft.Colors.ON_SURFACE_VARIANT,
            padding=ft.Padding.symmetric(horizontal=10, vertical=4),
        ),
        tooltip="What's New — version and changelog",
        on_click=lambda e: show_update_dialog(page, None) if page else None,
    )


def _backend_badge(state, controller) -> ft.Control:
    """The clickable backend badge: which provider is serving, with a state
    colour from its live health. Tapping opens the picker for one-tap
    switching. There is no "auto" label — the badge shows the provider that
    IS serving (the splash covers the app until one resolves).

    The title pill ("<Backend> TV ▾") opens the SAME picker, so the two
    are redundant on a narrow phone where the action row needs the room
    (owner, 2026-10-19: "should we remove one so that the space will be
    enough for small phones?"). The badge is therefore hidden below the
    tablet breakpoint; wide screens keep both."""
    name = (state.current_source_name or "").strip()
    label = name.capitalize() if name else ""
    colour = AppColors.SUCCESS if name else ft.Colors.ON_SURFACE_VARIANT
    return ft.TextButton(
        content=ft.Row(
            [
                ft.Container(width=8, height=8, border_radius=4, bgcolor=colour),
                ft.Container(width=6),
                ft.Text(label or "…", size=12, weight=ft.FontWeight.W_700, no_wrap=True),
            ],
            spacing=0,
            tight=True,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        style=_chip_style(
            radius=14,
            bgcolor=ft.Colors.with_opacity(0.1, colour),
            color=label or ft.Colors.ON_SURFACE_VARIANT,
            padding=ft.Padding.symmetric(horizontal=10, vertical=6),
            default_border=ft.BorderSide(1, ft.Colors.with_opacity(0.35, colour)),
        ),
        tooltip=f"Served by {label} — tap to switch" if label else "Choosing a source…",
        on_click=lambda e: controller.open_backend_picker(),
    )


def app_header(
    state,
    page,
    controller,
    *,
    subtitle: str = "",
    extra_actions: list[ft.Control] | None = None,
    on_back=None,
) -> ft.Control:
    """The shared header. ``subtitle`` names the screen ("Settings",
    "Downloads"); ``extra_actions`` are the screen's own buttons, rendered
    left of the theme cycle inside the scrolling group. ``on_back`` turns
    the leading round button into a Back control — for screens that were
    pushed (an anime's episodes), never a second bar above the header.

    The header reads ``state.viewport_version``: the badge's visibility
    depends on the window's WIDTH, and without reading the counter the
    header keeps the width of the last render (a rotated phone kept the
    old layout until something else redrew it)."""

    # Re-render when the window changes size (see the docstring).
    _ = state.viewport_version

    def _default_theme(_e=None):
        # The icon must land through a RE-RENDER: the header lives in a
        # frozen `@ft.component` subtree, and mutating `theme_action`
        # here raised "Frozen controls cannot be updated." (owner's run,
        # 2026-10-16 — the 3-way cycle was broken by exactly this line).
        # `state.theme_mode` is observable, so setting it re-renders the
        # screen that called app_header with the new icon.
        _cycle_theme(page, controller, state)

    theme_action = ft.IconButton(
        icon=theme_icon_for(page, state),
        icon_size=20,
        icon_color=ft.Colors.ON_SURFACE,
        style=_chip_style(radius=10, padding=ft.Padding.all(10)),
        tooltip="Switch theme",
        on_click=_default_theme,
    )

    right = ft.Row(
        [
            # Wide screens keep the second source readout; a phone drops
            # it (the title pill opens the same picker). Hidden, not
            # clipped: a zero-size badge instead of a suspended row keeps
            # the layout predictable on both breakpoints.
            _backend_badge(state, controller)
            if (getattr(page, "width", 0) or 0) >= BREAKPOINT_TABLET
            else ft.Container(width=0, height=0),
            _version_pill(state, page),
            *(extra_actions or []),
            theme_action,
        ],
        spacing=4,
        tight=True,
        scroll=ft.ScrollMode.AUTO,  # the house rule: scroll, never clip.
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    # The round back button (sub-screens only): a soft-tinted disc that
    # belongs to the header row — the modern "icon button on the bar",
    # never a separate strip of chrome above it. An IconButton, so the
    # remote can reach it (a Container cannot take D-pad focus).
    leading: list[ft.Control] = []
    if on_back is not None:
        leading.append(
            ft.IconButton(
                icon=ft.Icons.ARROW_BACK_ROUNDED,
                icon_size=18,
                icon_color=ft.Colors.ON_SURFACE,
                style=_chip_style(
                    radius=17,
                    bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE),
                    padding=ft.Padding.all(8),
                ),
                tooltip="Back",
                on_click=lambda e: on_back(),
            )
        )

    left = ft.Row(
        [
            *leading,
            ft.Image(src="icon.png", width=32, height=32, fit="contain"),
            ft.TextButton(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Text(
                                    backend_title(state),
                                    size=18,
                                    weight=ft.FontWeight.W_800,
                                    color=ft.Colors.ON_SURFACE,
                                    no_wrap=True,
                                ),
                                ft.Icon(
                                    ft.Icons.ARROW_DROP_DOWN,
                                    size=20,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                            ],
                            spacing=2,
                            tight=True,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Text(
                            subtitle,
                            size=10,
                            color=ft.Colors.with_opacity(0.55, ft.Colors.ON_SURFACE),
                            visible=bool(subtitle),
                        ),
                    ],
                    spacing=0,
                    tight=True,
                ),
                style=_chip_style(
                    radius=10,
                    padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                ),
                tooltip="Change content source",
                on_click=lambda e: controller.open_backend_picker(),
            ),
        ],
        spacing=10,
        tight=True,
    )

    return ft.Container(
        padding=ft.Padding.only(left=16, right=16, top=12, bottom=8),
        content=ft.Row(
            [left, right],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )
