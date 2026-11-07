"""AppShell — adaptive navigation + content (house pattern, Sherlock/KTV).

Navigation follows Material 3 window classes:
- <600dp (phone portrait): bottom NavigationBar
- 600-839dp: compact left NavigationRail
- >=840dp and every Android TV: left NavigationRail (TV forces the rail
  regardless of measured width — no TV app puts primary nav at the bottom)

Cross-promo lives in native slots (hero card + "More from us" shelf), never
between content and navigation — an ad sandwiched against nav is the pattern
both AdMob policy and TV focus design call out as wrong.
"""

import logging

import flet as ft

logger = logging.getLogger(__name__)
from flet import context as flet_context

from components.guarded_controls import (
    GuardedOutlinedButton,
    GuardedTextButton,
)
from core.tasks import spawn
from core.theme import AppColors
from screens.anime_detail_screen import AnimeDetailScreen
from screens.discover_screen import DiscoverScreen
from screens.downloads_screen import DownloadsScreen
from screens.home_screen import HomeScreen
from screens.search_screen import SearchScreen
from screens.settings_screen import SettingsScreen
from state.app_state import AppStateCtx
from state.controller_ctx import ControllerMethodsCtx

_TABS = ("Home", "Discover", "Downloads", "Settings")
_TAB_ICONS = (
    ft.Icons.HOME_ROUNDED,
    ft.Icons.EXPLORE_ROUNDED,
    ft.Icons.DOWNLOAD_ROUNDED,
    ft.Icons.SETTINGS_ROUNDED,
)

# Material 3 window size class boundary (dp): below it, bottom bar.
_RAIL_MIN_WIDTH = 600


def _flat_row_style() -> ft.ButtonStyle:
    """The option rows' style: a FLAT row, not a filled button.

    A bare ft.Button wears Flutter's M3 ElevatedButton defaults — a
    surfaceContainerLow fill, PRIMARY rose text, an elevation-1 shadow
    and a 20-radius rounded rect — so a stack of them reads as chunky
    grey pills. The house's option list (KTV's quality/audio rows) is
    flat text on the dialog surface. This is that: no fill, no shadow,
    the surface colour, and the house's focus cue.
    """
    return ft.ButtonStyle(
        bgcolor=ft.Colors.TRANSPARENT,
        color=ft.Colors.ON_SURFACE,
        elevation=0,
        padding=ft.Padding.symmetric(horizontal=4, vertical=10),
        shape=ft.RoundedRectangleBorder(radius=8),
        side={
            ft.ControlState.FOCUSED: ft.BorderSide(2.5, AppColors.PRIMARY),
            ft.ControlState.DEFAULT: ft.BorderSide(0, ft.Colors.TRANSPARENT),
        },
        overlay_color={
            ft.ControlState.FOCUSED: ft.Colors.with_opacity(0.08, AppColors.PRIMARY),
            ft.ControlState.HOVERED: ft.Colors.with_opacity(0.04, AppColors.PRIMARY),
            ft.ControlState.DEFAULT: ft.Colors.TRANSPARENT,
        },
    )


def _is_tv(page) -> bool:
    if page is None:
        return False
    platform = getattr(page, "platform", None)
    return platform is not None and platform == ft.PagePlatform.ANDROID_TV


def _use_rail(page) -> bool:
    if _is_tv(page):
        return True
    width = getattr(page, "width", None) or 0
    return width >= _RAIL_MIN_WIDTH


def _startup_splash(state) -> ft.Control:
    """The startup gate: brand mark, spinner, and the stage line
    ("Finding a source…", "Loading releases…"). CollabShell's shape —
    a full-screen column on the app background."""
    return ft.Container(
        content=ft.Column(
            [
                ft.Image(src="icon.png", width=140, height=140, fit=ft.BoxFit.CONTAIN),
                ft.Container(height=24),
                ft.ProgressRing(width=40, height=40, stroke_width=3, color=ft.Colors.PRIMARY),
                ft.Container(height=10),
                ft.Text(
                    state.startup_stage or "",
                    size=12,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=0,
        ),
        alignment=ft.Alignment.CENTER,
        expand=True,
    )


@ft.component
def AppShell() -> ft.Control:
    controller = ft.use_context(ControllerMethodsCtx)
    state = ft.use_context(AppStateCtx)
    active_tab, set_active_tab = ft.use_state("Home")
    active_view, set_active_view = ft.use_state("tabs")  # tabs | anime | player
    _ = state.episodes_version
    _ = state.player_open
    _ = state.startup_ready  # the splash gate re-renders when it flips
    _ = state.startup_stage

    from flet import context as flet_context

    try:
        page = flet_context.page
    except Exception:
        page = None

    def _open_anime(session: str):
        # Full-screen branch (Sherlock's results-view pattern): nav bar
        # hides, an AppBar with a back button appears.
        set_active_view("anime")
        # load_anime resolves the header (poster/title/metadata) before
        # the episodes load, so cold-opened details don't sit on "Loading...".
        controller.load_anime(session)

    # The controller drives navigation by mutating these closures in place
    # (identity must survive — see controller_ctx.py).
    controller.go_home = lambda: set_active_tab("Home")

    def _open_search():
        # The Discover tab hosts both surfaces; the Home header's search
        # action opens the search one.
        set_active_tab("Discover")
        state.discover_showing_search = True

    controller.open_search = _open_search
    controller.open_discover = lambda: setattr(state, "discover_showing_search", False)
    controller.open_downloads = lambda: set_active_tab("Downloads")
    controller.open_settings = lambda: set_active_tab("Settings")
    controller.open_anime = _open_anime
    controller.back = lambda: set_active_view("tabs")
    controller.close_player = lambda: set_active_view("anime")
    controller.play_adjacent = lambda delta: _play_adjacent(delta)
    controller.choose_quality = lambda idx: _choose_quality(idx)

    def _play_adjacent(delta):
        from core.tasks import spawn

        spawn(controller._app_controller.play_adjacent(delta), name="play-adjacent")

    def _choose_quality(index):
        from core.tasks import spawn

        spawn(controller._app_controller.choose_quality(index), name="choose-quality")

    def _on_tab(name: str):
        # Picking a tab is itself a navigation act: without leaving the
        # detail/player view the body would stay on it (active_view gates
        # the body BEFORE active_tab, so a Downloads tap on an anime page
        # did nothing — owner's report: "only this app dead-ends").
        set_active_tab(name)
        set_active_view("tabs")

    # Dialog portal (Sherlock pattern): one dialog whose identity survives
    # re-renders; screens open sheets through the controller instead of
    # calling page.show_dialog ad hoc. THREE owners share it — the play
    # quality dialog, the download quality dialog, and an imperative
    # sheet (the search-confirm) — so the portal tracks WHO owns it.
    # Clearing on a flag alone is wrong: it would dismiss whichever
    # dialog happened to be open as soon as another flag flipped.
    active_dialog, set_active_dialog = ft.use_state(None)
    portal_owner, set_portal_owner = ft.use_state(None)
    sheet, set_sheet = ft.use_state(None)
    # The quality dialog also rebuilds when its resolving flag flips, so the
    # spinner/disabled state lands without remounting the whole shell.
    dialog_resolving, set_dialog_resolving = ft.use_state(False)
    # The quality dialog's rows can change UNDERNEATH an open dialog: the
    # "More qualities" button earns the kwik clearance and the MP4 rows
    # join the list. The portal watches this version to repaint in place.
    dialog_quality_version, set_dialog_quality_version = ft.use_state(0)
    if state.quality_dialog_open:
        if (
            portal_owner != "quality"
            or dialog_resolving != state.quality_resolving
            or dialog_quality_version != state.quality_version
        ):
            set_portal_owner("quality")
            set_dialog_resolving(state.quality_resolving)
            set_dialog_quality_version(state.quality_version)
            set_active_dialog(_build_quality_dialog(state, controller))
    elif state.download_choice_open:
        if portal_owner != "download":
            set_portal_owner("download")
            set_active_dialog(_build_download_quality_dialog(state, controller))
    elif state.backend_picker_open:
        if portal_owner != "backend":
            set_portal_owner("backend")
            set_active_dialog(_build_backend_picker(state, controller))
    elif sheet is not None:
        if portal_owner != "sheet" or active_dialog is not sheet:
            set_portal_owner("sheet")
            set_active_dialog(sheet)
    else:
        if portal_owner is not None or active_dialog is not None:
            set_portal_owner(None)
            set_active_dialog(None)
            set_dialog_resolving(False)
    try:
        ft.use_dialog(active_dialog)

    except RuntimeError:
        logger.debug("suppressed")

    def _close_dialog():
        """Close whichever dialog is open.

        The flag-driven dialogs (play quality, download quality) are owned
        by the controller's state, so clearing the imperative sheet alone
        leaves their flags set — the elif chain above then rebuilds the
        same dialog on the next render, and neither Cancel nor global Back
        would ever dismiss it."""
        set_sheet(None)
        if state.quality_dialog_open or state.pending_playback is not None:
            state.quality_dialog_open = False
            state.quality_choices = None
            state.pending_playback = None
            state.episodes_version += 1
        if state.download_choice_open or state.pending_download is not None:
            state.download_choice_open = False
            state.download_choices = None
            state.pending_download = None
        if state.backend_picker_open:
            state.backend_picker_open = False

    controller.open_sheet = lambda d: set_sheet(d)
    controller.close_dialog = _close_dialog

    # Publish what global Back should do (the controller's FocusManager
    # reads this on every keypress; the closures above are the actions).
    if controller._app_controller is not None:
        controller._app_controller.ui_state = {
            "dialog_open": active_dialog is not None,
            "view": active_view,
            "player_open": state.player_open,
        }

    # The player mounts imperatively into page.overlay rather than being
    # rendered here: controls built inside a @ft.component render are frozen
    # after mount, and the player rewrites itself constantly (overlay
    # visibility, retry buttons, playback rate, quality swap). KTV mounts
    # its player in a ft.View for the same reason; page.views is gone in
    # flet 1.0.4, so page.overlay is the equivalent top-level slot.
    _use_player_view(state, controller)

    # Stream resolution takes seconds — the overlay is how the tap is
    # acknowledged (KTV's rule: anything slower than a beat gets a spinner).
    _ = state.busy_version
    _use_resolve_overlay(state, controller)

    # Startup gate (CollabShell's pattern): the shell shows the splash
    # until the backend is resolved and the first home fetch has been
    # attempted — so the first thing anyone sees is never a half-loaded
    # app or a CF challenge window. Past all hooks, so hook order stays
    # unconditional while the splash is up.
    if not state.startup_ready:
        return _startup_splash(state)

    if active_view == "anime":
        body = AnimeDetailScreen()
        # The detail screen renders the SHARED header itself, with the
        # back button inside it (the owner's order: the header is always
        # the topmost element — a separate AppBar above it put
        # "back · Anime" ahead of the header, 2026-10-16).
        chrome = None
        # The nav bar STAYS on the detail view: hiding it stranded the
        # owner (tabs unreachable from an anime page — his report,
        # 2026-10-16). Back in the header remains for returning to the tab.
        show_nav = True
    else:
        if active_tab == "Home":
            body = HomeScreen()
        elif active_tab == "Discover":
            # One tab, two surfaces: the filtered catalog and search.
            body = SearchScreen() if state.discover_showing_search else DiscoverScreen()
        elif active_tab == "Downloads":
            body = DownloadsScreen()
        else:
            body = SettingsScreen()
        chrome = None
        show_nav = True

    rail_destinations = [
        ft.NavigationRailDestination(icon=icon, label=label)
        for icon, label in zip(_TAB_ICONS, _TABS, strict=True)
    ]  # The bar takes NavigationBarDestination objects — feeding it rail
    # destinations serializes the wrong wire type and the bottom bar
    # renders empty on phones.
    bar_destinations = [
        ft.NavigationBarDestination(icon=icon, label=label)
        for icon, label in zip(_TAB_ICONS, _TABS, strict=True)
    ]
    selected = _TABS.index(active_tab)

    # SafeArea wraps the WHOLE shell (house standard: KTV app_shell.py:238,
    # Sherlock:1220, DDGS:185) — without it the top row runs under the
    # status bar and the nav bar under the gesture pill (the owner's
    # "you are dragging space with my notifications", 2026-10-16).
    if _use_rail(page):
        rail_or_bar = ft.NavigationRail(
            destinations=rail_destinations,
            selected_index=selected,
            on_change=lambda e: _on_tab(_TABS[e.control.selected_index]),
            min_width=72,
            bgcolor=ft.Colors.SURFACE,
            use_indicator=True,
            indicator_color=ft.Colors.with_opacity(0.15, AppColors.PRIMARY),
        )
        content = ft.Column(
            [
                chrome if chrome is not None else ft.Container(width=0, height=0),
                ft.Container(content=body, expand=True),
            ],
            spacing=0,
            expand=True,
        )
        if show_nav:
            return ft.SafeArea(
                content=ft.Row(
                    [rail_or_bar, ft.VerticalDivider(width=1), content],
                    spacing=0,
                    expand=True,
                ),
                expand=True,
            )
        return ft.SafeArea(
            content=ft.Column([content], spacing=0, expand=True),
            expand=True,
        )

    return ft.SafeArea(
        content=ft.Column(
            [
                ft.Container(content=body, expand=True),
                ft.NavigationBar(
                    destinations=bar_destinations,
                    selected_index=selected,
                    on_change=lambda e: _on_tab(_TABS[e.control.selected_index]),
                ),
            ],
            spacing=0,
            expand=True,
        ),
        expand=True,
    )


# The live player (so Back can run its awaited position save) and the key
# currently mounted — without the first, a remote Back discards the resume
# position. The player itself lives in a /play VIEW on the views stack (KTV
# exact): that is what makes the Android system back reach Python
# (on_view_pop) instead of exiting the app. No SafeArea on the player mount
# — the view carries padding=0, exactly like KTV's ft.View.
_active_player = None
_active_key = None


def _play_adjacent(delta: int, controller) -> None:
    """Next/previous episode from inside the player (module level so the
    overlay mount can reach it)."""
    from core.tasks import spawn

    app_controller = getattr(controller, "_app_controller", None)
    if app_controller is not None:
        spawn(app_controller.play_adjacent(delta), name="play-adjacent")


def _in_overlay(page, node) -> bool:
    """Identity membership — controls are dataclasses, so ``in`` compares by
    value and would match a structurally-equal node."""
    return node is not None and any(node is m for m in page.overlay)


_resolve_mount = None
_resolve_stage_shown = None


def _use_resolve_overlay(state, controller) -> None:
    """Mount the "Resolving stream…" stage into page.overlay.

    Imperative (same reasoning as the player): it must be replaceable when
    the stage text changes without re-rendering the whole shell, and it has
    to sit above the detail screen the tap came from.
    """
    global _resolve_mount, _resolve_stage_shown

    try:
        page = flet_context.page
    except Exception:
        page = None
    if page is None:
        return

    stage = state.resolve_stage if state.is_resolving else None
    if stage is None:
        if _resolve_mount is not None and _in_overlay(page, _resolve_mount):
            page.overlay.remove(_resolve_mount)
            page.update()
        _resolve_mount = None
        _resolve_stage_shown = None
        return

    if stage == _resolve_stage_shown and _in_overlay(page, _resolve_mount):
        return  # already showing this stage

    if _resolve_mount is not None and _in_overlay(page, _resolve_mount):
        page.overlay.remove(_resolve_mount)

    _resolve_mount = ft.Container(
        expand=True,
        bgcolor=ft.Colors.with_opacity(0.7, ft.Colors.BLACK),
        alignment=ft.Alignment.CENTER,
        content=ft.Column(
            [
                ft.ProgressRing(color=AppColors.PRIMARY, stroke_width=4),
                ft.Container(height=16),
                ft.Text(
                    stage,
                    size=15,
                    weight=ft.FontWeight.W_600,
                    color=ft.Colors.WHITE,
                ),
                ft.Container(height=8),
                GuardedTextButton(
                    content="Cancel",
                    on_click=lambda e: controller.cancel_resolve(),
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            tight=True,
        ),
    )
    _resolve_stage_shown = stage
    page.overlay.append(_resolve_mount)
    page.update()


def _pop_play_view(page) -> bool:
    """Pop the /play view if it is the top one. Returns True when popped."""
    try:
        if page.views and getattr(page.views[-1], "route", "") == "/play":
            page.views.pop()
            page.update()
            return True
    except Exception:
        logger.debug("suppressed")
    return False


def _release_player_page_state(page) -> None:
    """The player is gone: the screen may sleep again (unless downloads run)
    and the window-level key stream must stop feeding it."""
    ctrl = getattr(page, "_app_controller", None)
    if ctrl is not None and hasattr(ctrl, "update_wakelock"):
        spawn(ctrl.update_wakelock(), name="wakelock-off")
    fm = getattr(ctrl, "focus_manager", None)
    if fm is not None:
        fm.set_key_consumer(None)


def _close_already_saved(player) -> bool:
    """Single close-guard predicate for every back path (KTV): a close is
    done when the player is closing AND its position is saved."""
    return bool(
        getattr(player, "_is_closing", False)
        and getattr(player, "_position_saved", False)
    )


def _begin_player_close(player) -> None:
    """Run the awaited close-save once, no matter how many paths ask (KTV's
    _begin_player_close): the player's Go Back, the FocusScope, the Android
    system back (view_pop) and the shell all funnel here."""
    if getattr(player, "_is_closing", False):
        logger.info("close-path: close already in flight, skipping duplicate")
        return
    logger.info("close-path: scheduling close-save")
    player._is_closing = True
    page = None
    try:
        page = flet_context.page
    except Exception:
        page = None
    if page is None:
        return
    page.run_task(_close_player_with_save, player)


def _close_player():
    """The player's on_close target — funnels into _begin_player_close."""
    player = _active_player
    if player is None:
        try:
            page = flet_context.page
            if page is not None:
                _pop_play_view(page)
        except Exception:
            logger.debug("suppressed")
        return
    _begin_player_close(player)


async def _close_player_with_save(player):
    """Persist position (awaited), then stop playback and pop the view
    (KTV's _close_player_with_save)."""
    global _active_player
    try:
        await player.save_position_now()
    except Exception:
        logger.debug("close-path: position save failed", exc_info=True)
    # Release native resources while the control tree is still attached.
    try:
        player.teardown()
    except Exception:
        logger.debug("suppressed")

    from state.app_state import state

    page = None
    try:
        page = flet_context.page
    except Exception:
        page = None
    _active_player = None
    state.player_open = False
    state.player_error = None
    state.episodes_version += 1
    if page is not None:
        _pop_play_view(page)
        _release_player_page_state(page)


def _use_player_view(state, controller) -> None:
    """Mount/unmount the player as a /play VIEW on the views stack (KTV
    exact). The view — not an overlay — is what makes the Android system
    back reach Python (on_view_pop) instead of exiting the app. No
    SafeArea on the player mount: the view carries padding=0, exactly like
    KTV's ft.View. The key comparison is what makes retries and episode
    switches remount instead of reusing a stale stage."""
    global _active_player, _active_key

    try:
        page = flet_context.page
    except Exception:
        page = None
    if page is None:
        return

    if not state.player_open:
        if _active_player is not None or _pop_play_view(page):
            _active_player = None
            _active_key = None
            _release_player_page_state(page)
        return

    error = getattr(state, "player_error", None)
    spec = getattr(state, "player_spec", None) or {}
    key = ("error", error) if error else ("play", spec.get("episode_session"), spec.get("resource"))

    top_is_play = bool(page.views) and getattr(page.views[-1], "route", "") == "/play"
    if key == _active_key and top_is_play:
        return  # already showing exactly this stage
    if top_is_play:
        page.views.pop()  # episode switch: replace with a fresh view

    from hooks.use_focus_scope import focus_scope

    if error:
        # Playback couldn't start (e.g. the downloaded file went missing):
        # a black stage view with Retry / Go Back — the same background the
        # player would show, so the transition never flashes the app.
        view = ft.View(
            route="/play",
            controls=[_build_player_error(state, controller, error)],
            padding=0,
        )
        page.views.append(view)
        page.update()
        _active_player = None
        _active_key = key
        return

    from components.player.immersive_player import ImmersivePlayer
    from services.store import get_store

    player = ImmersivePlayer(
        resource=spec.get("resource", ""),
        title=spec.get("title", ""),
        http_headers=spec.get("source_headers"),
        resume_key=spec.get("episode_session"),
        store=get_store(),
        on_close=lambda: _close_player(),
        on_next=lambda: _play_adjacent(1, controller),
        on_previous=lambda: _play_adjacent(-1, controller),
        hls_proxy=getattr(
            getattr(controller, "_app_controller", None), "hls_proxy", None
        ),
        source_url=spec.get("source_url") or "",
        source_referer=spec.get("source_referer"),
        source_headers=spec.get("source_headers"),
        source_proxied=bool(spec.get("proxied", False)),
        subtitles=spec.get("subtitles") or [],
        skip=spec.get("skip") or {},
        variants=spec.get("variants") or [],
        variant_index=spec.get("variant_index"),
    )
    # focus_scope is a plain FUNCTION (KTV's form): the old @ft.component
    # FocusScope rendered a frozen subtree — the exact crash class this
    # imperative mount exists to avoid.
    view = ft.View(
        route="/play",
        controls=[focus_scope(player, lambda: _close_player())],
        padding=0,
    )
    page.views.append(view)
    page.update()
    _active_player, _active_key = player, key
    # The screen must not sleep while the player is open (KTV's wakelock).
    app_controller = getattr(controller, "_app_controller", None)
    if app_controller is not None and hasattr(app_controller, "update_wakelock"):
        spawn(app_controller.update_wakelock(), name="wakelock-on")
    # The window-level key stream is the one that receives ARROW keys
    # (Flutter's focus traversal eats them before any KeyboardListener):
    # register the player's handler there for the life of the view.
    focus_manager = getattr(app_controller, "focus_manager", None)
    if focus_manager is not None and hasattr(player, "handle_key"):
        focus_manager.set_key_consumer(player.handle_key)


def _build_player_error(state, controller, message: str) -> ft.Control:
    """Playback couldn't start: same black stage as the player so the
    transition never flashes the app behind it."""
    session = getattr(state, "current_episode_session", "")

    def _retry():
        state.player_error = None
        state.episodes_version += 1
        spawn(
            controller._app_controller.play_downloaded(session),
            name="retry-downloaded",
        )

    def _back():
        state.player_error = None
        state.player_open = False
        state.episodes_version += 1

    return ft.Container(
        expand=True,
        bgcolor=ft.Colors.BLACK,
        alignment=ft.Alignment.CENTER,
        content=ft.Column(
            [
                ft.Icon(ft.Icons.ERROR_OUTLINE_ROUNDED, size=64, color=AppColors.ERROR),
                ft.Container(height=16),
                ft.Text(
                    "Playback unavailable",
                    size=20,
                    weight=ft.FontWeight.W_700,
                    color=ft.Colors.WHITE,
                ),
                ft.Container(height=8),
                ft.Text(
                    message,
                    size=14,
                    color=ft.Colors.with_opacity(0.7, ft.Colors.WHITE),
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Container(height=24),
                ft.Row(
                    [
                        GuardedOutlinedButton(
                            content="Retry",
                            icon=ft.Icons.REFRESH_ROUNDED,
                            on_click=lambda e: _retry(),
                        ),
                        GuardedOutlinedButton(
                            content="Go Back",
                            icon=ft.Icons.ARROW_BACK_ROUNDED,
                            on_click=lambda e: _back(),
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=12,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
        ),
    )


def _build_download_quality_dialog(state, controller) -> ft.Control:
    """Which rendition to save offline — the same list the play dialog
    shows, because a silent sources[0] downloads whatever the provider
    listed first (a 360p when a 1080p exists). The best is marked in the
    label (" · Best") so every row is the same control and D-pad focus
    stays symmetric (owner, 2026-10-19)."""
    choices = state.download_choices or []
    pending = state.pending_download or {}
    buttons = []
    for i, choice in enumerate(choices):
        is_first = i == 0
        label = choice["label"] if not is_first else f"{choice['label']}  ·  Best"
        buttons.append(
            ft.Button(
                content=label,
                style=_flat_row_style(),
                on_click=lambda e, i=i: controller.choose_download_quality(i),
            )
        )
    label = f"{pending.get('title', '')} — Episode {pending.get('episode_num', '?')}"
    return ft.AlertDialog(
        modal=True,
        title=ft.Text(
            f"Download quality — {label}".strip(" —"),
            weight=ft.FontWeight.W_600,
        ),
        content=ft.Column(
            controls=[
                ft.Text(
                    "Saved in the format the source serves — nothing is converted.",
                    size=12,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                *buttons,
            ],
            tight=True,
            spacing=10,
        ),
        actions=[
            ft.TextButton(
                content="Cancel",
                on_click=lambda e: controller.close_dialog(),
            )
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )


def _build_backend_picker(state, controller) -> ft.Control:
    """Which provider is serving, every provider's live health, and
    one-tap pinning — the header badge's destination. The rows follow the
    FIXED order the app tries at launch (AniKato first); there is no
    "automatic" entry anywhere. The health rows are the router's own
    breaker state, so the picker explains a switch instead of just
    announcing one."""
    from services.providers.base import PROVIDER_ORDER

    # One short line per provider: its rank and its cost. AniKato is the
    # default (multi-language subtitles, strong streaming, no verification);
    # KayoAnime needs no verification and serves direct MKV/MP4 files;
    # AnimePahe is the best all-around streamer but sits behind Cloudflare
    # with English-only subs; AnimeOut shines for downloads, also behind
    # Cloudflare (owner's ranking, 2026-11-03).
    hints = {
        "anikato": "Best overall · multi-language subs · great streaming",
        "kayoanime": "No verification · direct MKV/MP4 downloads",
        "animepahe": "Best streaming & downloads · needs verification · English subs",
        "animeout": "Great for downloads · needs verification",
    }

    health = controller.sources_status() if hasattr(controller, "sources_status") else {}
    listed = {*health, (state.current_source_name or "").strip()} - {""}
    providers = [n for n in PROVIDER_ORDER if n in listed] + [
        n for n in sorted(listed) if n not in PROVIDER_ORDER
    ]
    current = (state.current_source_name or "").strip()

    def _row(name: str) -> ft.Control:
        h = health.get(name) or {}
        rec = str(h.get("state") or "")
        colour = (
            AppColors.ERROR
            if rec == "open"
            else AppColors.WARNING
            if rec == "half_open"
            else AppColors.SUCCESS
        )
        detail = "never probed"
        if h.get("checked_at"):
            latency = h.get("latency_ms")
            detail = f"{latency:.0f}ms" if isinstance(latency, (int, float)) else "—"
            if h.get("last_error"):
                detail += f" · {str(h['last_error'])[:40]}"
        selected = current == name
        label_column = ft.Column(
            [
                ft.Row(
                    [
                        ft.Container(width=8, height=8, border_radius=4, bgcolor=colour),
                        ft.Container(width=8),
                        ft.Text(name.capitalize(), size=13, weight=ft.FontWeight.W_600),
                    ],
                    spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Text(
                    hints.get(name, ""),
                    size=10,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    visible=bool(hints.get(name)),
                ),
            ],
            spacing=2,
            tight=True,
        )
        return ft.Container(
            content=ft.Row(
                [
                    label_column,
                    ft.Container(expand=True),
                    ft.Text(detail, size=11, color=ft.Colors.ON_SURFACE_VARIANT),
                    ft.Text(
                        "serving now" if selected else "tap to pin",
                        size=11,
                        color=ft.Colors.PRIMARY if selected else ft.Colors.ON_SURFACE_VARIANT,
                    ),
                ],
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=10, vertical=10),
            border_radius=8,
            border=ft.Border.all(
                1.5 if selected else 1,
                ft.Colors.PRIMARY
                if selected
                else ft.Colors.with_opacity(0.2, ft.Colors.ON_SURFACE),
            ),
            ink=True,
            on_click=lambda e, n=name: controller.pin_backend(n),
        )

    return ft.AlertDialog(
        modal=True,
        title=ft.Text("Content source", weight=ft.FontWeight.W_700),
        content=ft.Column(
            [
                *[_row(name) for name in providers],
                ft.Text(
                    "Tried in this order at launch (top first). "
                    "What you choose is the app — nothing else is consulted.",
                    size=11,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
            tight=True,
            spacing=8,
        ),
        actions=[ft.TextButton(content="Close", on_click=lambda e: controller.close_dialog())],
        actions_alignment=ft.MainAxisAlignment.END,
    )


def _build_quality_dialog(state, controller) -> ft.Control:
    """The pre-play quality picker: a MODAL BOTTOM SHEET, not a centered
    dialog (owner, 2026-11-07 — the AlertDialog felt heavy; M3 puts option
    lists in a sheet that slides up and is dismissed BY the choice).

    Every site source the scraper found, best first — nothing filtered:
    an anime with 3 qualities in 2 languages shows all of them.

    Rows stay uniform ft.Buttons: in the installed flet 1.1.0.dev4 a
    ListTile has no on_focus/on_blur, so a ListTile row is unreachable by
    a TV remote; Button is focusable and every row is the same control.
    The first (highest) pick carries a small "Best" marker in its label
    instead of being a differently-shaped filled button: a lone filled-red
    row between outlined rows breaks D-pad focus symmetry on a TV remote
    (the owner could feel it moving up and down the list, 2026-10-19).
    The m3u8 variants of whatever is chosen live in the player's settings.

    Minimal by design: drag handle, one caption line, the rows. No tip
    text, no Cancel button — scrim tap / swipe down / remote Back all
    dismiss (on_dismiss clears the state flags so the sheet does not
    resurrect on the next render). Choosing a row clears
    quality_dialog_open first thing (choose_quality), so the sheet slides
    down exactly as the resolve stage / player view takes over.
    """
    choices = state.quality_choices or []
    # A site-source choice re-resolves through kwik (seconds): disable the
    # buttons and show the spinner while it happens.
    resolving = bool(getattr(state, "quality_resolving", False))
    buttons = []
    for i, choice in enumerate(choices):
        is_first = i == 0
        label = choice["label"] if not is_first else f"{choice['label']}  ·  Best"
        buttons.append(
            ft.Button(
                content=label,
                style=_flat_row_style(),
                disabled=resolving,
                on_click=lambda e, i=i: controller.choose_quality(i),
            )
        )

    # "More qualities" — the owner's Cloudflare-free experience (2026-10-23):
    # the usual stream plays with NO verification window; the per-quality
    # MP4s sit behind this one deliberate press, which is the only thing
    # in playback that may ever open Cloudflare. Shown only when the
    # serving provider owns the ability and the MP4 rows are not already
    # in the list.
    pending = state.pending_playback or {}
    more = None
    if pending.get("has_kwik_files") and not any(c.get("kwik") for c in choices):
        more = ft.Button(
            content="More qualities — Cloudflare check",
            style=_flat_row_style(),
            disabled=resolving,
            on_click=lambda e: controller.earn_kwik_qualities(
                pending.get("anime_session", ""),
                pending.get("episode_session", ""),
            ),
        )
    return ft.BottomSheet(
        content=ft.Column(
            controls=[
                ft.Row(
                    [
                        ft.Text(
                            "Quality",
                            size=13,
                            weight=ft.FontWeight.W_600,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            expand=True,
                        ),
                        ft.ProgressRing(
                            width=16,
                            height=16,
                            stroke_width=2,
                            visible=resolving,
                        ),
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Container(height=4),
                *buttons,
                # The deliberate Cloudflare press — the ONLY one playback
                # ever offers (the owner's Cloudflare-free experience).
                *([ft.Divider(height=1), more] if more is not None else []),
            ],
            tight=True,
            spacing=2,
        ),
        show_drag_handle=True,
        draggable=True,
        dismissible=True,
        scrollable=True,
        bgcolor=ft.Colors.SURFACE,
        barrier_color=ft.Colors.with_opacity(0.4, ft.Colors.BLACK),
        # M3: full width on compact screens, capped (and centered) on
        # medium/expanded — a TV gets a centered sheet, not a full-width one.
        size_constraints=ft.BoxConstraints(max_width=520),
        # Snappy in/out so a pick reads as "sheet closes as the player opens".
        animation_style=ft.AnimationStyle(duration=180, reverse_duration=180),
        on_dismiss=lambda e: controller.close_dialog(),
    )
