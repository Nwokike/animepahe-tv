"""app_header — the ONE header every screen shares (Sherlock's pattern).

Left: an optional round back button (sub-screens), the app icon, and the
source pill — "<Backend> TV ▾", the content-source switcher — with the
screen's own name as a quiet subtitle beneath it.

Right: the version/update pill, the screen's own extra actions, then the
theme cycle. **The header is ALWAYS one horizontal bar** — it never stacks
into two lines on a narrow screen (the owner, on a version that did:
"you went and made it so that it will fall over"). The house rule
(Sherlock/KTV) is **scroll, never clip**.

HOW the cluster pans took three attempts, and the working mechanism is
Flutter's layout rule, not a scroll MODE: **a scrollable Row nested
directly inside another Row gets an unbounded main axis, lays out at its
full content width, and overflows instead of scrolling.** The header's
cluster was exactly that shape, so no ``ScrollMode`` value ever changed
anything. Discover's filter bar pans perfectly because its scrollable Row
sits inside a BOUNDED box — so below the tablet breakpoint the cluster is
that same shape: ``Container(expand=True)`` takes the width left over from
the title, and the filter bar's scrollable Row lives inside it (owner,
2026-10-20: "learn from the filter part of discover cause it scrolls
horizontally perfectly"). Wide screens keep the house's expanding spacer
and the cluster hugging the right edge — nothing overflows there, so no
viewport is needed.

Two things the owner explicitly rejected in this header, kept out (the
tests below pin both): a stacked layout, and a chevron indicator —
"the arrow is supposed to only show when there is more things to show...
That's why I told you not to do it" (2026-10-23). An overflow-aware
indicator is exactly the complexity the header must not carry; the
filter bar's own scroll affordance is what the owner approved. The gaps
between the icons are gone too (``spacing=0``): the controls' own touch
targets supply the separation.

The backend badge (the second source readout) rides the same row on WIDE
screens only: on a narrow phone it is dropped because the title pill
already opens the identical picker and the row needs the room (owner,
2026-10-19).

Every screen renders it, so switching backends (and theme) never depends on
being on Home or finding Settings — the owner's reuse pattern from Sherlock
and CollabShell. Sub-screens (an anime's episodes) pass ``on_back``: the
back control lives INSIDE this header, never as a second bar stacked above
it (the owner's report, 2026-10-16 — a separate AppBar put "back · Anime"
ahead of the header).

**Every interactive control here is a Button-family control, never a
Container.** That is not a style preference: against the installed flet
1.0.4, the controls that expose ``on_focus``/``on_blur`` are 28 classes —
the Button family, TextField, Switch, Checkbox, Radio, Slider, Dropdown —
and ``ft.Container`` is NOT among them. A Container has no focus state, so
on a TV remote it can never be highlighted, let alone activated. The house
apps (Sherlock's version chip, KTV's header actions) are Containers; they
are phone-first, and this app is not. (The one Container in this file is
the zero-size placeholder that stands in for the backend badge below the
tablet breakpoint — it is a layout spacer, not an interactive control.)
"""

import flet as ft

from components.guarded_controls import GuardedIconButton, GuardedTextButton
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
    default_border: ft.BorderSide | None = None,
) -> ft.ButtonStyle:
    """The house chip look (Sherlock's version chip / DDGS's version chip):
    a soft tinted plate with a rounded radius — on a Button-family control
    so it can take D-pad focus, with a PRIMARY ring when focused.

    """
    return ft.ButtonStyle(
        bgcolor=bgcolor or ft.Colors.TRANSPARENT,
        color=color or ft.Colors.ON_SURFACE,
        shape=ft.RoundedRectangleBorder(radius=radius),
        side=_focus_sides(default_border),
        overlay_color={
            ft.ControlState.FOCUSED: ft.Colors.with_opacity(0.12, AppColors.PRIMARY),
            ft.ControlState.HOVERED: ft.Colors.with_opacity(0.06, AppColors.PRIMARY),
            ft.ControlState.PRESSED: ft.Colors.with_opacity(0.12, AppColors.PRIMARY),
            ft.ControlState.DEFAULT: ft.Colors.TRANSPARENT,
        },
        visual_density=ft.VisualDensity.COMPACT,
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
        # The house names the BUILD on the update chip ("Update: v2.1.0
        # Available!" — Sherlock, DDGS, KTV all do); ours said only
        # "Update Available!", which hid the number the owner wants.
        version = str(update_data.get("version", "") or "").strip()
        title = f"Update: {version} Available!" if version else "Update Available!"
        return GuardedTextButton(
            content=ft.Row(
                [
                    ft.Text(
                        title,
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
                default_border=ft.BorderSide(1.5, AppColors.PRIMARY),
            ),
            tooltip="New update available — tap to view",
            on_click=lambda e: show_update_dialog(page, update_data) if page else None,
        )
    return GuardedTextButton(
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
        ),
        tooltip="What's New — version & changelog",
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
    return GuardedTextButton(
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

    theme_action = GuardedIconButton(
        icon=theme_icon_for(page, state),
        icon_size=20,
        icon_color=ft.Colors.ON_SURFACE,
        style=_chip_style(radius=10),
        tooltip="Switch theme",
        on_click=_default_theme,
    )

    actions: list[ft.Control] = [
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
    ]

    # One horizontal bar at every width. HOW the cluster pans is the part
    # that took three attempts to get right, and the reason is Flutter's
    # own rule, not a scroll MODE: **a scrollable Row nested directly
    # inside another Row gets an unbounded main axis, sizes to its full
    # content width, and overflows instead of scrolling.** That is why
    # every scroll mode looked identical here — while Discover's filter
    # bar, whose scrollable Row sits inside a BOUNDED box, has always
    # panned perfectly (owner, 2026-10-20: "learn from the filter part of
    # discover cause it scrolls horizontally perfectly").
    #
    # So the two regimes differ in the BOX, not the mode:
    # - Narrow: the cluster IS a bounded viewport — `Container(expand=True)`
    #   takes exactly the width left over from the title, and the filter
    #   bar's own shape lives inside it. No arrow: the owner tried the
    #   chevron indicator and rejected it (2026-10-23 — it showed even
    #   when nothing overflowed, and a correct overflow-aware one is the
    #   complexity they refused; "just remove the arrow").
    # - Wide: the house's original shape — an expanding spacer, the
    #   cluster hugging the right edge. Nothing overflows there, so no
    #   viewport is needed.
    #
    # `spacing=0` between the icons is the owner's explicit order (the
    # gaps between the chips read as dead space; the controls' own touch
    # targets supply all the separation a tap needs).
    narrow = (getattr(page, "width", 0) or 0) < BREAKPOINT_TABLET
    if narrow:
        right_cluster = ft.Container(
            expand=True,  # the leftover width after the title IS the viewport
            content=ft.Row(
                actions,
                spacing=0,
                tight=True,
                scroll=ft.ScrollMode.AUTO,  # the filter bar's own mode.
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )
    else:
        right_cluster = ft.Row(
            actions,
            spacing=0,
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
            GuardedIconButton(
                icon=ft.Icons.ARROW_BACK_ROUNDED,
                icon_size=18,
                icon_color=ft.Colors.ON_SURFACE,
                style=_chip_style(
                    radius=17,
                    bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE),
                ),
                tooltip="Back",
                on_click=lambda e: on_back(),
            )
        )

    left = ft.Row(
        [
            *leading,
            ft.Image(src="icon.png", width=32, height=32, fit="contain"),
            GuardedTextButton(
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
                ),
                tooltip="Change content source",
                on_click=lambda e: controller.open_backend_picker(),
            ),
        ],
        spacing=10,
        tight=True,
    )

    # ONE horizontal bar, always, at every width — never a stack, never
    # "falling over".
    # - Wide: the house's mechanism (KTV's header) — an expanding spacer
    #   between the title and the action cluster, so the title keeps its
    #   place and the cluster hugs the right edge.
    # - Narrow: no spacer. The cluster itself takes the leftover width
    #   (it is the scroll viewport — see above), so a spacer would just
    #   compete with it for the same flex space.
    return ft.Container(
        content=ft.Row(
            (
                [left, right_cluster]
                if narrow
                else [
                    left,
                    ft.Container(expand=True),
                    right_cluster,
                ]
            ),
            alignment=ft.MainAxisAlignment.START,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )

